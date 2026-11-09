"""Calls to the local Syncthing REST API.

- rescan: ask Syncthing to pick up a just-written vault note promptly. The macOS file watcher sometimes
  misses files created by background processes. Best effort: failures are logged, never raised.
- unignore: drop exact-name patterns from a folder's ignore list so chosen older recordings sync.
"""
import json
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG = Path.home() / "Library/Application Support/Syncthing/config.xml"
log = logging.getLogger("rec")


def _api(method: str, endpoint: str, params: dict, body=None):
    xml = CONFIG.read_text()
    key = re.search(r"<apikey>([^<]+)</apikey>", xml).group(1)
    addr = re.search(r"<gui[^>]*>.*?<address>([^<]+)</address>", xml, re.S).group(1)
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(f"http://{addr}/rest/{endpoint}?{urllib.parse.urlencode(params)}", data=data,
                                 method=method, headers={"X-API-Key": key, "Content-Type": "application/json"})
    raw = urllib.request.urlopen(req, timeout=10).read()
    return json.loads(raw) if raw.strip() else None


def folder_for(path: Path):
    """(folder id, path relative to the folder root) of the Syncthing folder containing path, or None."""
    path = path.resolve()
    for fid, fpath in re.findall(r'<folder id="([^"]+)"[^>]*path="([^"]+)"', CONFIG.read_text()):
        root = Path(fpath.replace("~", str(Path.home()), 1)).resolve()
        if root == path:
            return fid, ""
        if root in path.parents:
            return fid, str(path.relative_to(root))
    return None


def rescan(path: Path) -> None:
    try:
        found = folder_for(path)
        if not found:
            log.warning("no Syncthing folder contains %s", path)
            return
        _api("POST", "db/scan", {"folder": found[0], "sub": found[1]})
    except Exception as e:  # noqa: BLE001 — sync is a convenience, the note is already written
        log.warning("syncthing rescan failed for %s: %s", path, e)


def unignore(folder_dir: Path, names: list[str]) -> list[str]:
    """Remove '/<name>' or '<name>' patterns for these names. Returns the patterns removed."""
    found = folder_for(folder_dir)
    if not found:
        raise RuntimeError(f"no Syncthing folder at {folder_dir}")
    fid = found[0]
    current = _api("GET", "db/ignores", {"folder": fid}).get("ignore") or []
    wanted = {n for name in names for n in (name, "/" + name)}
    keep = [p for p in current if p not in wanted]
    removed = [p for p in current if p in wanted]
    if removed:
        _api("POST", "db/ignores", {"folder": fid}, {"ignore": keep})
        _api("POST", "db/scan", {"folder": fid})
    return removed
