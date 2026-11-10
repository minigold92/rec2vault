#!/bin/sh
# Run from a durable checkout on the processing Mac. No launchctl calls here:
# install/upgrade/update own the complete transaction, including rollback.
# Examples: deploy/setup.sh install
#           deploy/setup.sh upgrade --root "$HOME/rec" --dry-run
#           deploy/setup.sh update --root "$HOME/QuietClerk"
set -eu
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
APP=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
command -v uv >/dev/null || { echo 'missing: uv (brew install uv)' >&2; exit 1; }
[ "$#" -gt 0 ] || set -- install
# Bootstrap only the stdlib installer; MLX dependencies are installed into a
# fresh, versioned venv by the transaction. Keep dry-run free of data writes.
cd "$APP"
exec uv run --no-project --python 3.12 python -m quietclerk.cli "$@"
