"""Offline hub metadata and cache fakes; never read or write user models."""
import json
import sys
from types import SimpleNamespace

import pytest

from quietclerk import models
from quietclerk.backends.mlx import MODEL_REVISIONS, model_snapshot


@pytest.fixture
def hub(tmp_path, monkeypatch):
    repos = list(models.MODELS.values())
    cached = {}
    downloads = []
    state = SimpleNamespace(free=models.WORKING_BYTES, offline=False, metadata=[])

    def info(repo, *, revision, files_metadata):
        assert revision == MODEL_REVISIONS[repo] and files_metadata
        state.metadata.append(repo)
        if state.offline:
            raise OSError('offline')
        return SimpleNamespace(siblings=[SimpleNamespace(rfilename='weights.bin', size=100),
                                         SimpleNamespace(rfilename='config.json', size=2)])

    def lookup(repo, name, *, revision):
        assert revision == MODEL_REVISIONS[repo]
        return cached.get((repo, name))

    def download(repo, *, revision, **kwargs):
        assert revision == MODEL_REVISIONS[repo]
        downloads.append((repo, kwargs))
        return str(tmp_path / revision)

    def cache(repo, name, size):
        path = tmp_path / f'{repos.index(repo)}-{name}'
        path.write_bytes(b'x' * size)
        cached[repo, name] = str(path)

    for repo in repos:
        cache(repo, 'weights.bin', 100)
        cache(repo, 'config.json', 2)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(
        HfApi=lambda: SimpleNamespace(model_info=info), try_to_load_from_cache=lookup,
        snapshot_download=download))
    monkeypatch.setitem(sys.modules, 'huggingface_hub.constants', SimpleNamespace(HF_HUB_CACHE=str(tmp_path / 'new-cache')))
    monkeypatch.setattr(models.shutil, 'disk_usage', lambda path: SimpleNamespace(free=state.free))
    return SimpleNamespace(repos=repos, cached=cached, downloads=downloads, state=state)


def test_all_cached_needs_only_working_reserve_and_reports_present(hub, capsys):
    assert sum(models.download_sizes().values()) == 0
    models.prefetch(app_progress=True)
    assert hub.downloads == []
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert sum('이미 있음' in event['ko'] and 'already present' in event['en'] for event in events) == 4


def test_partial_cache_counts_only_missing_files_at_pinned_revision(hub):
    del hub.cached[hub.repos[0], 'weights.bin']
    assert sum(models.download_sizes().values()) == 100
    hub.state.free += 100
    models.prefetch()
    assert hub.downloads == [(hub.repos[0], {})]


def test_disk_shortage_stops_before_any_download_with_both_languages(hub, capsys):
    del hub.cached[hub.repos[0], 'weights.bin']
    with pytest.raises(OSError, match=r'필요 2\.00 GB, 남은 2\.00 GB / Model installation requires 2\.00 GB, available 2\.00 GB'):
        models.prefetch(app_progress=True)
    assert hub.downloads == []
    event = json.loads(capsys.readouterr().out)
    assert event['error'] == event['ko'] + ' / ' + event['en']


def test_cached_models_still_need_processing_floor(hub):
    hub.state.free -= 1
    with pytest.raises(OSError, match='Model installation requires'):
        models.prefetch()
    assert hub.downloads == []


def test_metadata_failure_reserves_full_set_and_logs_fallback(hub, capsys):
    hub.state.offline = True
    hub.state.free = models.FULL_MODEL_BYTES + models.WORKING_BYTES - 1
    with pytest.raises(OSError, match='requires 8.00 GB'):
        models.prefetch()
    assert hub.downloads == []
    assert '전체 크기 6 GB' in capsys.readouterr().err
    hub.state.free += 1
    models.prefetch()
    assert len(hub.downloads) == 4


def test_inference_uses_same_pinned_snapshot(hub):
    repo = hub.repos[0]
    _, identity = model_snapshot(repo)
    assert identity == repo + '@' + MODEL_REVISIONS[repo]
    assert hub.downloads == [(repo, {'local_files_only': True})]
