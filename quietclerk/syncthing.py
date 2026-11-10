"""Calls to the local Syncthing REST API.

- rescan: ask Syncthing to pick up a just-written vault note promptly. The macOS file watcher sometimes
  misses files created by background processes. Best effort: failures are logged, never raised.
- unignore: drop exact-name patterns from a folder's ignore list so chosen older recordings sync.
"""
import json
import logging
import re
import urllib.parse
import unicodedata
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


def escape_pattern(name: str, escape='\\') -> str:
    """Quote a literal Syncthing glob, not a wildcard selecting other recordings."""
    return ''.join(escape + char if char in '*?[]{},!#()' + escape else char for char in name)


def unignore(folder_dir: Path, names: list[str]) -> list[str]:
    """Remove only exact literal patterns, comparing their NFC/NFD equivalents."""
    found = folder_for(folder_dir)
    if not found:
        raise RuntimeError(f"no Syncthing folder at {folder_dir}")
    fid, relative = found
    current = _api("GET", "db/ignores", {"folder": fid}).get("ignore") or []
    escape = '\\'
    for pattern in current:
        if pattern.startswith('#escape=') and len(pattern) == 9:
            escape = pattern[-1]
            break
    wanted = set()
    for name in names:
        if (not name or '/' in name or '\\' in name or any(ord(c) < 32 for c in name)):
            raise ValueError('expected a single recording name')
        literal = escape_pattern('/'.join(filter(None, (relative, name))), escape)
        wanted.update(unicodedata.normalize('NFC', value) for value in (literal, '/' + literal))
    selected = lambda pattern: unicodedata.normalize('NFC', pattern) in wanted
    keep = [pattern for pattern in current if not selected(pattern)]
    removed = [pattern for pattern in current if selected(pattern)]
    if removed:
        _api("POST", "db/ignores", {"folder": fid}, {"ignore": keep})
        _api("POST", "db/scan", {"folder": fid})
    return removed
