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


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _one_line(value):
    """Keep terminal output inert, including untrusted transcript/filename controls."""
    import unicodedata
    return ''.join(c if not unicodedata.category(c).startswith('C') else ' ' for c in str(value))


def _print_read(args, result):
    if args.command == 'show' and args.md:
        print(result, end='')
    elif getattr(args, 'json', False):
        print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    elif args.command == 'list':
        for item in result['items']:
            print(_one_line(f"{item['date']} | {item['title']} | {item['job_id']} | {item['type'] or '—'} | {item['duration_sec']}s | {item['status']}"))
    elif args.command == 'search':
        for item in result['items']:
            text = ''.join(part['text'] for part in item['snippet'])
            print(_one_line(f"{item['date']} | {item['title']} | {item['job_id']} {item['line_id'] or item['kind']} | {text}"))
        print(f"{result['total']} result(s)")
    elif args.command == 'show':
        print(_one_line(f"{result['title']} | {result['job_id']} | {result['date']}"))
        print(json.dumps(result['properties'], ensure_ascii=False))
        for line in result['summary'].splitlines():
            print(_one_line(line))
        for line in result.get('transcript', []):
            seconds = int(line['start'])
            stamp = f"{seconds // 60:02d}:{seconds % 60:02d}"
            print(_one_line(f"[{line['id']} {stamp}] {line['speaker'] or ''}: {line['text']}"))
    else:
        print(json.dumps(result, ensure_ascii=False))


def main(argv=None):
    parser = Parser(prog='quietclerk')
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--support', type=Path, default=SUPPORT)
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--legacy-label', action='append', default=[])
    sub.add_parser('open')
    login = sub.add_parser('login-service', help='read or change the app-managed login service')
    login.add_argument('action', choices=('status', 'register', 'unregister'))
    sub.add_parser('status')
    search = sub.add_parser('search')
    search.add_argument('query')
    search.add_argument('--limit', type=int, default=20)
    search.add_argument('--offset', type=int, default=0)
    search.add_argument('--json', action='store_true')
    listing = sub.add_parser('list')
    listing.add_argument('--since')
    listing.add_argument('--limit', type=int, default=50)
    listing.add_argument('--json', action='store_true')
    show = sub.add_parser('show')
    show.add_argument('job_id')
    formats = show.add_mutually_exclusive_group()
    formats.add_argument('--json', action='store_true')
    formats.add_argument('--md', action='store_true')
    show.add_argument('--no-transcript', action='store_true')
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
            command.add_argument('--app-install', action='store_true',
                                 help='mark this as an app-managed login service (same Python engine)')
            command.add_argument('--agents', type=Path)
            command.add_argument('--source', type=Path,
                                 help='source checkout or retained QuietClerk wheel (required for wheel installs)')
    args = None
    try:
        args = parser.parse_args(argv)
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
                                  legacy_labels=args.legacy_label, app_install=args.app_install))
            return 0
        if args.command == 'login-service':
            from .install import login_service
            print(json.dumps(login_service(args.action, support=args.support)))
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
            if args.command == 'list':
                params = {'limit': args.limit}
                if args.since is not None:
                    params['since'] = args.since
                endpoint = '/api/meetings?' + urllib.parse.urlencode(params)
            elif args.command == 'show':
                import re
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', args.job_id):
                    raise ValueError('invalid job_id')
                endpoint = '/api/meetings/' + args.job_id + '?' + urllib.parse.urlencode(
                    {'format': 'md' if args.md else 'json', 'transcript': '0' if args.no_transcript else '1'})
            elif args.command == 'search':
                endpoint = '/api/search?' + urllib.parse.urlencode({'q': args.query, 'limit': args.limit, 'offset': args.offset})
            else:
                endpoint = '/api/status'
            with urllib.request.urlopen(urllib.request.Request(base + endpoint, headers=headers), timeout=30) as response:
                result = response.read().decode('utf-8') if args.command == 'show' and args.md else json.load(response)
            _print_read(args, result)
        finally:
            request = urllib.request.Request(base + '/api/logout', data=b'{}',
                headers=headers | {'Origin': base, 'X-CSRF-Token': csrf, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=10):
                pass
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, sqlite3.DatabaseError) as exc:
        if args and args.command in ('install', 'upgrade', 'update', 'doctor', 'login-service'):
            print(f'QuietClerk {args.command} failed: {exc}', file=sys.stderr)
            return 1
        print('QuietClerk is unavailable; check the service and its private bootstrap file.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
