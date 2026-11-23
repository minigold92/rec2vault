"""The settings editor for extra receiving folders and the folder-aware backlog screen (contract 3.3, 9.2).

The real front-end modules run in node against a fake DOM (see test_server_screens.UPDATE_UI_HARNESS); the engine's answers that
matter here (the 400 reasons) are produced by the real settings code, everything else is assumed.
"""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from quietclerk import config
from test_server_screens import SCHEMA, UPDATE_UI_HARNESS, needs_node, run_ui, word_settings

SCENARIOS = Path(__file__).with_name('ui_inbox_scenarios.js')
PRIMARY, OLD, KEPT = '/home/me/rec/inbox', '/home/me/rec/not-shared-yet', '/home/me/rec/inbox-interpreter'


@pytest.fixture(scope='module')
def inbox_harness(tmp_path_factory):
    marker = 'const out = await scenarios[scenario](params);'
    assert UPDATE_UI_HARNESS.count(marker) == 1
    path = tmp_path_factory.mktemp('inbox-ui') / 'harness.mjs'
    path.write_text(UPDATE_UI_HARNESS.replace(marker, SCENARIOS.read_text(encoding='utf-8') + '\n' + marker), encoding='utf-8')
    return path


T = {
    'ko': {'section': '저장과 삭제', 'label': '추가 받는 폴더', 'help': '예: 통역 앱 녹음을 받는 두 번째 Syncthing 폴더 · 최대 8개',
           'apply': '다음 확인부터 적용', 'placeholder': '예: ~/rec/inbox-interpreter', 'empty': '폴더 경로를 적어 주세요.',
           'relative': '/ 또는 ~/로 시작하는 전체 경로를 적어 주세요.', 'dots': '경로에 ‘..’을 쓸 수 없어요.', 'primary': '기본 받는 폴더와 같은 폴더예요.',
           'dup': '이미 있어요.', 'chars': '제어문자나 보이지 않는 글자는 쓸 수 없어요.', 'full': '8개를 모두 채웠어요. 하나를 지우면 더 넣을 수 있어요.',
           'inside': '데이터 폴더 자체나 그 안의 엔진 폴더(archive·work 등), 회의록 폴더 안에는 둘 수 없어요. 다른 폴더를 써 주세요.', 'none': '바꾼 항목이 없어요', 'changes': '바꾼 항목 1개',
           'saved': '저장했어요.', 'not_saved': '저장하지 못했어요.', 'remove': '삭제: {}', 'lock': '환경 변수 QC_EXTRA_INBOXES로 정해져 있어 여기서 바꿀 수 없어요.',
           'primary_name': '기본 받는 폴더', 'selected': '3개 선택'},
    'en': {'section': 'Storage & deletion', 'label': 'Extra inboxes', 'help': 'e.g. a second Syncthing folder for interpreter recordings · up to 8',
           'apply': 'Applies from the next scan', 'placeholder': 'e.g. ~/rec/inbox-interpreter', 'empty': 'Type a folder path first.',
           'relative': 'Write a full path starting with / or ~/.', 'dots': 'A path can\'t contain ‘..’.', 'primary': 'That is the primary inbox itself.',
           'dup': 'Already in the list.', 'chars': 'Control and invisible characters aren\'t allowed.',
           'full': 'The list is full (8). Remove one to add more.',
           'inside': 'It can\'t be the data folder itself, one of its engine folders (archive, work…) or inside the notes folder. Pick another folder.', 'none': 'No changes', 'changes': '1 change',
           'saved': 'Saved.', 'not_saved': 'Not saved.', 'remove': 'Remove: {}', 'lock': 'Set by the environment variable QC_EXTRA_INBOXES, so it can\'t be changed here.',
           'primary_name': 'Primary inbox', 'selected': '3 selected'},
}


def screen_settings(lang, **changes):
    return word_settings(lang, **{'inbox': PRIMARY, 'extra_inboxes': [KEPT, OLD]} | changes)


def identity(*missing):
    return {'engine_version': '1.0', 'installation_method': 'cli', 'last_updated_at': None,
            'sync': {'state': 'connected', 'extra': [{'path': path, 'exists': path not in missing} for path in (KEPT, OLD)]}}


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_extra_inboxes_are_added_refused_removed_and_saved(inbox_harness, lang):
    t = T[lang]
    seen = run_ui(inbox_harness, 'extraInboxes', lang=lang, settings=screen_settings(lang), identity=identity(OLD))
    assert seen['section'] == t['section'] and seen['label'] == t['label'] and seen['tip'] == 'extra_inboxes' and seen['help'] == t['help']
    assert t['apply'] in seen['tags'] and 'extra_inboxes' not in seen['tags'] and seen['placeholder'] == t['placeholder']
    initial = seen['initial']   # the saved list; the folder the engine says is not on this Mac is marked
    assert initial['paths'] == [KEPT, OLD] and initial['marked'] == [OLD] and initial['missingNote'] and initial['count'] == '2 / 8' and initial['bar'] == t['none']
    added = seen['added']   # trimmed, trailing slash dropped; the box is empty and keeps the focus
    assert added['paths'] == [KEPT, OLD, '~/rec/inbox-interpreter']
    assert added['box'] == '' and added['focus'] == 'f-extra' and added['bar'] == t['changes'] and added['said'] == ''
    for name in ('dup', 'relative', 'dots', 'primary', 'empty', 'chars'):   # refused: the list does not change and the box says why
        view = seen[name]
        assert view['paths'] == added['paths'] and view['said'] == t[name] and view['invalid'] == 'true', name
    assert seen['relative']['box'] == 'Recordings/Interpreter' and seen['dots']['box'] == '/a/../b'   # what must be fixed stays in the box
    full = seen['full']
    assert full['count'] == '8 / 8' and full['add']['disabled'] and len(full['paths']) == 8
    assert seen['over']['said'] == t['full'] and len(seen['over']['paths']) == 8
    removed = seen['removed']   # one gone: room again, the focus moves on to the next remove button
    assert len(removed['paths']) == 7 and OLD not in removed['paths'] and not removed['add']['disabled']
    assert removed['focus'] == t['remove'].format(removed['paths'][1])
    saved = seen['saved']
    assert saved['bodies'] == [{'extra_inboxes': removed['paths']}] and saved['saveOff'] and t['saved'] in saved['banner'] and saved['view']['bar'] == t['none']
    refused = seen['refused']   # the engine's own refusal (an engine folder of the data folder) is shown in words with the status; the draft stays
    assert refused['errorLine'].startswith(t['inside']) and '400 extra_inboxes' in refused['errorLine'] and t['not_saved'] in refused['banner']
    assert '/home/me/QuietClerk/work' in refused['paths']
    assert seen['afterRefusal']['errorLine'] is None and '/home/me/QuietClerk/work' not in seen['afterRefusal']['paths']   # editing the list clears the stale line
    assert seen['reverted']['paths'] == saved['view']['paths'] and seen['reverted']['bar'] == t['none'] and seen['reverted']['box'] == ''


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_extra_inboxes_locked_by_the_environment_cannot_be_edited(inbox_harness, lang):
    t = T[lang]
    seen = run_ui(inbox_harness, 'extraInboxes', lang=lang, settings=screen_settings(lang), identity=identity(), locked=['extra_inboxes'])
    assert seen['initial']['inputDisabled'] and seen['initial']['add']['disabled'] and seen['lock'].startswith(t['lock'])


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_the_engines_refusals_are_shown_in_words(inbox_harness, lang, tmp_path):
    t = T[lang]
    primary = tmp_path / 'inbox'
    root = tmp_path / 'root'
    messages = {}
    for name, value in {'relative': ['rel/x'], 'dots': ['/a/../b'], 'full': [f'/m/{i}' for i in range(9)], 'dup': ['/d', '/d/'], 'primary': [str(primary)],
                        'inside': [str(root / 'archive')]}.items():
        path = tmp_path / f'{name}.toml'
        path.write_text('extra_inboxes = ' + json.dumps(value) + '\n')
        with pytest.raises(config.SettingsError) as error:
            config.load(path, environ={'QC_ROOT': str(root), 'QC_INBOX': str(primary)})
        assert error.value.field == 'extra_inboxes'
        messages[name] = error.value.args[0].split(': ', 1)[1]
    seen = run_ui(inbox_harness, 'inboxReasons', lang=lang, messages=messages)
    assert seen == {name: t[name] for name in ('relative', 'dots', 'full', 'dup', 'primary', 'inside')}


BACKLOG = {'items': [{'name': 'same_261105_083634.m4a', 'folder': PRIMARY}, {'name': 'same_261105_083634.m4a', 'folder': KEPT},
                     {'name': '통역_261106_142617.m4a', 'folder': KEPT}],
           'skipped': [], 'inventory': 'partial'}


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_backlog_tells_the_folders_apart_and_requests_each_folder_on_its_own(inbox_harness, lang):
    t = T[lang]
    Draft202012Validator(SCHEMA | {'$ref': '#/$defs/Backlog'}).validate(BACKLOG)
    seen = run_ui(inbox_harness, 'backlogFolders', lang=lang, backlog=BACKLOG, settings=screen_settings(lang))
    assert [(r['name'], r['title']) for r in seen['rows']] == [
        ('same_261105_083634.m4a', PRIMARY), ('same_261105_083634.m4a', KEPT), ('통역_261106_142617.m4a', KEPT)]
    assert t['primary_name'] in seen['rows'][0]['meta'] and 'inbox-interpreter' in seen['rows'][1]['meta'] and 'inbox-interpreter' in seen['rows'][2]['meta']
    assert seen['bar'] == t['selected']
    assert seen['posts'] == [{'names': ['same_261105_083634.m4a', '통역_261106_142617.m4a'], 'folder': KEPT},   # in the order picked
                             {'names': ['same_261105_083634.m4a'], 'folder': PRIMARY}]


@needs_node
def test_backlog_without_extra_folders_shows_no_folder_labels(inbox_harness):
    one = BACKLOG | {'items': [BACKLOG['items'][0]]}
    seen = run_ui(inbox_harness, 'backlogFolders', lang='en', backlog=one, pick=[0], settings=word_settings('en', inbox=PRIMARY))
    assert seen['rows'][0]['title'] is None and 'Primary' not in seen['rows'][0]['meta']
