"""QuietClerk service, installation and local-client commands."""
import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
import urllib.parse
import webbrowser
from pathlib import Path

from .bootstrap_file import read_bootstrap
from .install import SUPPORT


def main(argv=None):
    parser = argparse.ArgumentParser(prog='quietclerk')
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--support', type=Path, default=SUPPORT)
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--legacy-label', action='append', default=[])
    sub.add_parser('open')
    sub.add_parser('status')
    search = sub.add_parser('search')
    search.add_argument('query')
    search.add_argument('--limit', type=int, default=20)
    search.add_argument('--offset', type=int, default=0)
    update = sub.add_parser('update')
    update.add_argument('--root', type=Path)
    update.add_argument('--source', type=Path, help='source checkout or retained QuietClerk wheel')
    update.add_argument('--dry-run', action='store_true')
    for name in ('install', 'upgrade', 'doctor'):
        command = sub.add_parser(name)
        command.add_argument('--root', type=Path)
        command.add_argument('--legacy-label', action='append', default=[])
        if name != 'doctor':
            command.add_argument('--dry-run', action='store_true')
            command.add_argument('--agents', type=Path)
            command.add_argument('--source', type=Path,
                                 help='source checkout or retained QuietClerk wheel (required for wheel installs)')
    args = parser.parse_args(argv)
    try:
        if args.command in ('install', 'upgrade', 'update', 'doctor'):
            from . import install
            if args.command == 'doctor':
                print(install.doctor(root=args.root, legacy_labels=args.legacy_label))
            elif args.command == 'update':
                print(install.update(root=args.root, source=args.source, dry_run=args.dry_run,
                                     support=args.support, settings=args.settings))
            else:
                print(install.run(upgrading=args.command == 'upgrade', root=args.root,
                                  dry_run=args.dry_run, agents=args.agents, source=args.source,
                                  support=args.support, settings=args.settings,
                                  legacy_labels=args.legacy_label))
            return 0
        if args.command == 'serve':
            from . import config
            from .serve import main as serve_main
            serve_main(config.load(args.settings), support=args.support,
                       legacy_labels=tuple(dict.fromkeys(['local.rec.pipeline', *args.legacy_label])))
            return 0
        bootstrap = read_bootstrap(args.support)
        base = f"http://127.0.0.1:{bootstrap['port']}"
        if args.command == 'open':
            return 0 if webbrowser.open(base + '/#bootstrap=' + bootstrap['token']) else 1
        # Status is authenticated too. It consumes the file token, not an
        # unauthenticated HTTP issuance endpoint, and logs out after reading.
        payload = json.dumps({'token': bootstrap['token']}).encode()
        request = urllib.request.Request(base + '/api/session', data=payload,
                                         headers={'Content-Type': 'application/json', 'Origin': base})
        with urllib.request.urlopen(request, timeout=10) as response:
            cookie = response.headers['Set-Cookie'].split(';', 1)[0]
            csrf = response.headers['X-CSRF-Token']
        headers = {'Cookie': cookie}
        try:
            endpoint = '/api/search?' + urllib.parse.urlencode({'q': args.query, 'limit': args.limit, 'offset': args.offset}) if args.command == 'search' else '/api/status'
            with urllib.request.urlopen(urllib.request.Request(base + endpoint, headers=headers), timeout=30) as response:
                result = json.load(response)
                if args.command == 'search':
                    for item in result['items']:
                        text = ''.join(part['text'] for part in item['snippet'])
                        print(f"{item['date']} | {item['title']} | {item['job_id']} {item['line_id'] or item['kind']} | {text}")
                    print(f"{result['total']} result(s)")
                else:
                    print(json.dumps(result, ensure_ascii=False))
        finally:
            request = urllib.request.Request(base + '/api/logout', data=b'{}',
                headers=headers | {'Origin': base, 'X-CSRF-Token': csrf, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=10):
                pass
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, sqlite3.DatabaseError) as exc:
        if args.command in ('install', 'upgrade', 'update', 'doctor'):
            print(f'QuietClerk {args.command} failed: {exc}', file=sys.stderr)
            return 1
        print('QuietClerk is unavailable; check the service and its private bootstrap file.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
