"""One pipeline pass: scan the inbox, then process queued jobs one at a time.

Run by launchd every 60 s (`python -m rec.tick`). A file lock keeps passes from overlapping, so a
long job simply makes later passes exit immediately. Each stage writes its output under
WORK/<job_id>/ and is skipped when that output exists, so retries resume where they stopped.
"""
import fcntl
import json
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import config, db, intake, postprocess, render, syncthing
from .transcript import turns as build_turns

log = logging.getLogger("rec")


def ops(*args) -> None:
    exe = shutil.which("ops") or str(Path.home() / ".local/bin/ops")
    if Path(exe).exists():
        subprocess.run([exe, *args, "--dir", str(config.OPS_DIR)], capture_output=True, timeout=30)


class Heartbeat:
    """Emit an ops heartbeat every 60 s while a long stage runs."""

    def __init__(self):
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            ops("heartbeat", "--source", "rec-pipeline")
            self._stop.wait(60)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()


def run_model(stage: str, wav: Path, out: Path) -> None:
    if out.exists():
        return
    r = subprocess.run([sys.executable, "-m", "rec.models", stage, str(wav), str(out)],
                       capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent))
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"{stage} failed: {r.stderr[-800:]}")


def load(path: Path):
    return json.loads(path.read_text())


def save(path: Path, data) -> None:
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.rename(path)


def process(con, job) -> None:
    jid = job["job_id"]
    work = config.WORK / jid
    work.mkdir(parents=True, exist_ok=True)
    recorded = datetime.strptime(jid[:15], "%Y%m%d-%H%M%S")
    timer = {"name": None, "t": time.time()}

    def stage(s):
        """Mark the job's current stage and log how long the previous one took (for finding slow stages)."""
        now = time.time()
        if timer["name"]:
            log.info("stage %s %s %.0fs", jid, timer["name"], now - timer["t"])
        timer.update(name=s, t=now)
        db.update(con, jid, status="running", stage=s)

    wav = work / "audio.wav"
    if not wav.exists():
        stage("convert")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", job["archive_path"], "-ac", "1", "-ar", "16000",
                        str(wav.with_suffix(".part.wav"))], check=True)
        wav.with_suffix(".part.wav").rename(wav)
    for name in ("diarize", "asr", "alt"):
        stage(name)
        run_model(name, wav, work / f"{name}.json")

    turns_path = work / "turns.json"
    if not turns_path.exists():
        save(turns_path, build_turns(load(work / "asr.json"), load(work / "diarize.json")))
    turns = load(turns_path)

    corrected_path = work / "corrected.json"
    if not corrected_path.exists():
        stage("correct")
        texts, notes = postprocess.correct(turns, load(work / "alt.json"))
        save(corrected_path, {"texts": texts, "notes": notes})
    corrected = load(corrected_path)

    meta_path = work / "meta.json"
    meta, meta_error = None, None
    if meta_path.exists():
        meta = load(meta_path)
    else:
        stage("classify")
        try:
            meta, engine = postprocess.classify(turns, corrected["texts"], job["source_name"],
                                                render.known_projects(config.OUTPUT))
            save(meta_path, meta)  # cached: the title (and so the file name) is decided once
            corrected["notes"].append(f"classify: {engine}")
        except Exception as e:  # noqa: BLE001 — recorded and retried; the note is still published
            meta_error = str(e)

    summary_path = work / "summary.md"
    summary, summary_error = None, None
    if summary_path.exists():
        summary = summary_path.read_text()
    elif meta is not None:
        stage("summarize")
        try:
            summary, engine = postprocess.summarize(turns, corrected["texts"], meta)
            summary_path.write_text(summary)
            corrected["notes"].append(f"summary: {engine}")
        except Exception as e:  # noqa: BLE001 — recorded and retried; transcript is still published
            summary_error = str(e)
    save(corrected_path, corrected)  # keep classify/summary engine notes for later re-renders

    stage("render")
    engines = {"transcribe": [m.split("/")[-1] for m in (config.ASR_MODEL, config.DIAR_MODEL, config.ALT_ASR_MODEL)],
               "postprocess": ", ".join(sorted({m.group(1) for n in corrected["notes"]
                                                if (m := re.search(r": (codex|agy)$", n))}))}
    existing, current_format = render.find_existing(config.OUTPUT, jid)
    target = existing if (existing and current_format) else \
        config.OUTPUT / render.note_name(recorded, (meta or {}).get("title"), (meta or {}).get("type") or "녹음")
    render.write_atomic(target, render.render(job, recorded, turns, corrected["texts"], meta, summary,
                                              corrected["notes"], engines, datetime.now()))
    if existing and existing != target:
        existing.unlink()  # note from the earlier naming scheme, replaced by the titled one
    render.ensure_base(config.OUTPUT)
    syncthing.rescan(config.OUTPUT)
    save(Path(job["archive_path"]).parent / "result.json", {
        "job_id": jid, "sha256": job["sha256"], "source_name": job["source_name"],
        "duration_sec": job["duration_sec"], "models": engines, "meta": meta,
        "segments": [{**t, "id": render.line_id(i), "text_raw": t["text"], "text": x}
                     for i, (t, x) in enumerate(zip(turns, corrected["texts"]))],
        "summary": summary, "notes": corrected["notes"],
    })
    warnings = [n for n in corrected["notes"] if "failed" in n]
    if meta_error or summary_error:
        raise RuntimeError(f"classify: {meta_error}" if meta_error else f"summary: {summary_error}")
    db.update(con, jid, status="done", stage=None, error=None, output_path=str(target),
              warnings="\n".join(warnings) or None)


def main() -> int:
    config.ROOT.mkdir(parents=True, exist_ok=True)
    (config.ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(filename=config.ROOT / "logs" / "pipeline.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    lock = open(config.LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    con = db.connect(config.STATE_DB)
    # The lock guarantees no other pass is running, so a 'running' job was interrupted (crash, reboot).
    con.execute("UPDATE jobs SET status='failed_retryable', attempts=attempts+1, error='interrupted' WHERE status='running'")
    con.commit()
    ops("heartbeat", "--source", "rec-pipeline")
    for jid in intake.scan(con):
        job = con.execute("SELECT * FROM jobs WHERE job_id=?", (jid,)).fetchone()
        log.info("discovered %s %s status=%s reason=%s", jid, job["source_name"], job["status"], job["error"])
        ops("emit", "job_discovered", "--source", "rec-pipeline", "--message", f"{job['source_name']} {job['status']}")
    while (job := db.next_job(con, time.time(), config.MAX_ATTEMPTS, config.RETRY_BACKOFF_SEC)) is not None:
        jid = job["job_id"]
        log.info("start %s attempt=%d", jid, job["attempts"] + 1)
        started = time.time()
        try:
            with Heartbeat():
                process(con, job)
            log.info("done %s in %.0fs", jid, time.time() - started)
            ops("emit", "job_done", "--source", "rec-pipeline", "--message", job["source_name"])
            ops("metric", "job_minutes", f"{(time.time() - started) / 60:.1f}", "--unit", "분", "--source", "rec-pipeline")
        except Exception as e:  # noqa: BLE001 — every failure is recorded on the job and retried
            attempts = job["attempts"] + 1
            status = "failed_final" if attempts >= config.MAX_ATTEMPTS else "failed_retryable"
            db.update(con, jid, status=status, attempts=attempts, error=str(e)[-2000:])
            log.exception("fail %s (%s)", jid, status)
            ops("emit", "job_failed", "--kind", "error", "--source", "rec-pipeline", "--message", f"{job['source_name']}: {str(e)[:200]}")
    c = db.counts(con)
    ops("metric", "queue", str(c.get("queued", 0) + c.get("failed_retryable", 0)), "--unit", "건", "--source", "rec-pipeline")
    ops("metric", "failed_final", str(c.get("failed_final", 0)), "--unit", "건", "--source", "rec-pipeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
