#!/bin/sh
# Install from this durable checkout, or upgrade a root in place:
#   deploy/install.sh install
#   deploy/install.sh upgrade --root "$HOME/rec"
# Remote deployment must first place a checkout on the target; never rsync
# --delete over a live application's source or guess an operational SSH host.
set -eu
APP=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -n "${HOST:-}" ]; then
  echo 'Run deploy/install.sh in a durable checkout on the target Mac; automatic remote replacement is disabled.' >&2
  exit 1
fi
exec sh "$APP/deploy/setup.sh" "$@"
