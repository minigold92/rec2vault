"""Paths and limits.

Each REC_* value comes from the environment first, then from the settings file
(`~/rec/settings.env`, KEY=VALUE lines, written by deploy/setup.sh), then from the default below.
"""
import os
from datetime import datetime
from pathlib import Path

HOME = Path.home()
SETTINGS = Path(os.environ.get("REC_SETTINGS", str(HOME / "rec" / "settings.env"))).expanduser()


def _load_settings(path: Path) -> dict:
    out = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                out[key.strip()] = value.strip().strip('"')
    return out


_settings = _load_settings(SETTINGS)


def _get(key: str, default=None):
    return os.environ.get(key) or _settings.get(key) or default


def _path(key: str, default: Path) -> Path:
    return Path(_get(key, str(default))).expanduser()


ROOT = _path("REC_ROOT", HOME / "rec")
INBOX = _path("REC_INBOX", ROOT / "inbox")          # Syncthing receive-only folder
ARCHIVE = _path("REC_ARCHIVE", ROOT / "archive")    # original copies + unified JSON
WORK = _path("REC_WORK", ROOT / "work")             # per-job intermediate files
STATE_DB = _path("REC_DB", ROOT / "state.sqlite3")
LOCK = _path("REC_LOCK", ROOT / "tick.lock")
OUTPUT = _path("REC_OUTPUT", ROOT / "notes")        # point this at a folder inside your Obsidian vault
OPS_DIR = _path("REC_OPS_DIR", ROOT)

MIN_DURATION_SEC = float(_get("REC_MIN_DURATION_SEC", 300))
MAX_DURATION_SEC = 3 * 3600
MAX_BYTES = 1 << 30
STABLE_SEC = float(_get("REC_STABLE_SEC", 60))
# Recordings made before this local time are never processed (only new recordings).
SINCE = datetime.strptime(_get("REC_SINCE"), "%Y-%m-%d %H:%M") if _get("REC_SINCE") else None
# Older recordings the user chose to process anyway, one file name per line (python -m rec.backfill).
INCLUDE = _path("REC_INCLUDE", ROOT / "include.txt")
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SEC = 300

ASR_MODEL = "mlx-community/Qwen3-ASR-1.7B-8bit"
ALIGNER_MODEL = "mlx-community/Qwen3-ForcedAligner-0.6B-8bit"
DIAR_MODEL = "mlx-community/Nemotron-3-Diarization"
ALT_ASR_MODEL = "mlx-community/whisper-large-v3-turbo"
ASR_CHUNK_SEC = 60.0

CODEX_EFFORT = _get("REC_CODEX_EFFORT", "low")
AGY_MODEL = _get("REC_AGY_MODEL", "gemini-4-argon-medium")
LLM_TIMEOUT_SEC = 900
CORRECT_CHUNK_TURNS = 60
