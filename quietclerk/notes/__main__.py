"""python -m quietclerk.notes migrate --preview | --apply --consent."""
import argparse
import json

from .. import config, store
from . import NoteConflict
from .migration import migrate


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    migration = sub.add_parser('migrate')
    mode = migration.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preview', action='store_true')
    mode.add_argument('--apply', action='store_true')
    migration.add_argument('--consent', action='store_true', help='explicitly consent to backing up and converting vault notes')
    args = parser.parse_args(argv)
    if args.apply and not args.consent:
        parser.error('--apply requires --consent')
    settings = config.load()
    con = store.connect(settings.root / 'state.sqlite3')
    try:
        result = migrate(con, settings.root, settings.get('output'), apply=args.apply, consent=args.consent)
    except NoteConflict as exc:
        parser.exit(2, f'migration not applied: {exc}\n')
    finally:
        con.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
