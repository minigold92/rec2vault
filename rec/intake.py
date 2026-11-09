"""Inbox scanning: wait until a synced file is stable, validate it, dedupe by hash, archive, enqueue."""
import hashlib
import json
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import backfill, config, db


def probe_duration(path: Path):
    """Seconds, or None when ffprobe cannot decode the file."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def recorded_at(name: str, mtime: float) -> datetime:
    m = re.search(r"(\d{6})_(\d{6})", name)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%y%m%d%H%M%S")
        except ValueError:
            pass
    return datetime.fromtimestamp(mtime)


def candidates(inbox: Path):
    """Regular .m4a files directly in the inbox. Subfolders, symlinks, temp files and calls are ignored."""
    for p in sorted(inbox.iterdir()) if inbox.is_dir() else []:
        if p.is_symlink() or not p.is_file():
            continue
        if p.suffix.lower() != ".m4a" or p.name.startswith((".", "~")) or p.name.startswith("통화"):
            continue
        yield p


def check(path: Path, duration):
    """Return a skip reason, or None when the file should be processed."""
    if path.stat().st_size > config.MAX_BYTES:
        return "too_big"
    if duration is None:
        return "decode"
    if duration > config.MAX_DURATION_SEC:
        return "too_long"
    if duration < config.MIN_DURATION_SEC:
        return "too_short"
    return None


def scan(con, now: float | None = None) -> list[str]:
    """One pass over the inbox. Returns job ids created in this pass."""
    now = time.time() if now is None else now
    created = []
    for p in candidates(config.INBOX):
        st = p.stat()
        row = db.observe(con, str(p), st.st_size, st.st_mtime, now)
        if row["handled"] or st.st_size == 0:
            continue
        if now - row["last_change"] < config.STABLE_SEC or now - st.st_mtime < config.STABLE_SEC:
            continue
        digest = sha256(p)
        if db.job_by_sha(con, digest):
            db.mark_handled(con, str(p))
            continue
        duration = probe_duration(p)
        when = recorded_at(p.name, st.st_mtime)
        reason = check(p, duration)
        if reason is None and config.SINCE and when < config.SINCE and backfill.nfc(p.name) not in backfill.included():
            reason = "before_cutoff"
        job_id = f"{when:%Y%m%d-%H%M%S}-{digest[:8]}"
        archive = config.ARCHIVE / job_id / f"source{p.suffix.lower()}"
        if reason is None:
            archive.parent.mkdir(parents=True, exist_ok=True)
            tmp = archive.with_suffix(".part")
            shutil.copy2(p, tmp)
            if sha256(tmp) != digest:
                tmp.unlink()
                continue  # file changed under us; next pass re-checks it
            tmp.rename(archive)
        db.add_job(con, job_id, digest, p.name, str(archive), duration,
                   "queued" if reason is None else "skipped", error=reason)
        db.mark_handled(con, str(p))
        created.append(job_id)
    return created
