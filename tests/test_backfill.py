"""§5.3: exact Syncthing selection, including Unicode and glob metacharacters.

Pattern syntax reference: https://docs.syncthing.net/users/ignoring.html
No Syncthing installation, API key, pairing or phone is used in these tests.
"""
import unicodedata

import pytest

from quietclerk import backfill, config, syncthing


def test_backfill_in18_normalizes_and_deduplicates_names(tmp_path, monkeypatch):
    settings = config.load(environ={'QC_ROOT': str(tmp_path)})
    include = settings.root / 'include.txt'
    nfc = '음성 261106_142617.m4a'
    nfd = unicodedata.normalize('NFD', nfc)
    include.write_text(nfd + '\n', encoding='utf-8')
    calls = []
    monkeypatch.setattr(syncthing, 'unignore', lambda inbox, names: calls.append((inbox, names)) or [])
    assert backfill.request([nfc, nfd], settings=settings) == []
    assert backfill.included(include) == {nfc}
    assert calls == [(tmp_path / 'inbox', [nfc])]
    assert len(include.read_text(encoding='utf-8').splitlines()) == 1


@pytest.mark.parametrize('name', ['../escape.m4a', '/absolute.m4a', 'sub/a.m4a', '..\\a.m4a',
                                 'bad\nname.m4a', 'bad\0.m4a', '.hidden.m4a', '통화 홍길동.m4a', 'a.mp3'])
def test_backfill_rejects_bad_names_before_any_io(tmp_path, monkeypatch, name):
    settings = config.load(environ={'QC_ROOT': str(tmp_path)})
    monkeypatch.setattr(syncthing, 'unignore', lambda *_: pytest.fail('invalid name reached Syncthing'))
    with pytest.raises(ValueError):
        backfill.request([name], settings=settings)
    assert not (settings.root / 'include.txt').exists()


@pytest.mark.parametrize('relative', ['', 'inbox'])
@pytest.mark.parametrize('escape', ['\\', '|'])
def test_unignore_exact_escaped_nfc_nfd_patterns_only(tmp_path, monkeypatch, relative, escape):
    name = '음성 [a]*?{b,c}.m4a'
    literal = '/'.join(filter(None, [relative, name]))
    quoted = syncthing.escape_pattern(literal, escape)
    selected = '/' + unicodedata.normalize('NFD', quoted)
    generic = '*.m4a'
    unrelated = '/different.m4a'
    current = ['#escape=' + escape, selected, generic, unrelated, literal]
    calls = []
    monkeypatch.setattr(syncthing, 'folder_for', lambda _: ('folder-id', relative))
    def api(method, endpoint, params, body=None):
        calls.append((method, endpoint, params, body))
        return {'ignore': current} if method == 'GET' else None
    monkeypatch.setattr(syncthing, '_api', api)
    assert syncthing.unignore(tmp_path, [name]) == [selected]
    assert calls[1] == ('POST', 'db/ignores', {'folder': 'folder-id'},
                        {'ignore': ['#escape=' + escape, generic, unrelated, literal]})
    assert calls[2] == ('POST', 'db/scan', {'folder': 'folder-id'}, None)


def test_unignore_already_syncing_does_not_write_patterns(tmp_path, monkeypatch):
    monkeypatch.setattr(syncthing, 'folder_for', lambda _: ('folder-id', ''))
    calls = []
    def api(method, *args):
        calls.append(method)
        return {'ignore': ['*.tmp']}
    monkeypatch.setattr(syncthing, '_api', api)
    assert syncthing.unignore(tmp_path, ['음성.m4a']) == []
    assert calls == ['GET']
