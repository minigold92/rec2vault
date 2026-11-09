#!/bin/sh
# Install or update the pipeline.
#   On this Mac:                 deploy/install.sh
#   On another Mac over SSH:     HOST=my-mac-mini deploy/install.sh
# First install only (stored in ~/rec/settings.env on the target):
#   REC_OUTPUT="<folder inside your Obsidian vault>"  REC_SINCE="YYYY-MM-DD HH:MM"
set -eu
SRC=$(cd "$(dirname "$0")/.." && pwd)
copy() {
  rsync -a --delete --exclude .git --exclude .venv --exclude samples --exclude .pytest_cache \
    --exclude __pycache__ "$SRC/" "$1"
}
if [ -z "${HOST:-}" ]; then
  mkdir -p "$HOME/rec/app"
  [ "$SRC" = "$HOME/rec/app" ] || copy "$HOME/rec/app/"
  exec sh "$HOME/rec/app/deploy/setup.sh"
fi
ssh "$HOST" 'mkdir -p ~/rec/app'
copy "$HOST:rec/app/"
ssh "$HOST" "REC_OUTPUT='${REC_OUTPUT:-}' REC_SINCE='${REC_SINCE:-}' REC_LABEL='${REC_LABEL:-}' sh rec/app/deploy/setup.sh"
