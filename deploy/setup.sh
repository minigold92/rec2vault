#!/bin/sh
# Runs on the Mac that processes recordings (called by deploy/install.sh).
# Installs Python dependencies and models, writes ~/rec/settings.env on first run,
# and (re)loads the launchd agent that runs `python -m rec.tick` every 60 seconds.
set -eu
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
APP=$(cd "$(dirname "$0")/.." && pwd)
ROOT="$HOME/rec"
LABEL=${REC_LABEL:-local.rec.pipeline}

for c in uv ffmpeg; do
  command -v "$c" >/dev/null || { echo "missing: $c (brew install $c)" >&2; exit 1; }
done
[ "$(uname -m)" = arm64 ] || { echo "Apple Silicon (arm64) is required for the MLX models" >&2; exit 1; }
mkdir -p "$ROOT/inbox" "$ROOT/logs"

SETTINGS="$ROOT/settings.env"
if [ ! -f "$SETTINGS" ]; then
  {
    echo "# Read on every run; edit freely. Environment variables with the same name take precedence."
    echo "# Folder for the Markdown notes, ideally inside your Obsidian vault."
    echo "REC_OUTPUT=${REC_OUTPUT:-$ROOT/notes}"
    echo "# Recordings made before this time are skipped (python -m rec.backfill lets chosen ones through)."
    echo "REC_SINCE=${REC_SINCE:-$(date '+%Y-%m-%d %H:%M')}"
  } > "$SETTINGS"
  echo "wrote $SETTINGS"
fi

cd "$APP"
[ -x .venv/bin/python ] || uv venv -q -p 3.12 .venv
uv pip install -q -p .venv/bin/python -r pyproject.toml pytest
.venv/bin/python -m pytest -q tests
.venv/bin/python -m rec.models prefetch

PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s|@LABEL@|$LABEL|g" -e "s|@APP@|$APP|g" -e "s|@ROOT@|$ROOT|g" -e "s|@HOME@|$HOME|g" \
  deploy/launchd.plist.in > "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl print "gui/$(id -u)/$LABEL" | grep -E "state =|last exit" | head -2
echo "installed: inbox $ROOT/inbox, notes $(sed -n 's/^REC_OUTPUT=//p' "$SETTINGS"), logs $ROOT/logs/pipeline.log"
