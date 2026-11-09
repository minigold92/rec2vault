"""Process chosen recordings made before the REC_SINCE cutoff.

    python -m rec.backfill "음성 261106_142617.m4a" [...]

Adds the names to the include list (so intake does not skip them as before_cutoff) and removes their
patterns from the inbox folder's Syncthing ignore list (so the phone sends them). The next tick then
handles them like any new recording. Calls are never included (intake ignores 통화*).
"""
import sys
import unicodedata

from . import config, syncthing


def nfc(name: str) -> str:
    """macOS stores Korean file names decomposed (NFD); compare in NFC."""
    return unicodedata.normalize("NFC", name)


def included() -> set[str]:
    if not config.INCLUDE.exists():
        return set()
    return {nfc(l.strip()) for l in config.INCLUDE.read_text(encoding="utf-8").splitlines() if l.strip()}


def main(names: list[str]) -> int:
    bad = [n for n in names if "/" in n or not n.lower().endswith(".m4a") or n.startswith("통화")]
    if not names or bad:
        print(f"usage: python -m rec.backfill <recording.m4a>...  (rejected: {bad})", file=sys.stderr)
        return 2
    new = [n for n in names if n not in included()]
    if new:
        config.INCLUDE.parent.mkdir(parents=True, exist_ok=True)
        with config.INCLUDE.open("a", encoding="utf-8") as f:
            f.writelines(n + "\n" for n in new)
    removed = syncthing.unignore(config.INBOX, names)
    print(f"included: {names}\nunignored: {removed or 'none (already syncing or not in the ignore list)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
