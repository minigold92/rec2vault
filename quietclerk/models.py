"""Download the pinned MLX model set: python -m quietclerk.models prefetch."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from .backends.mlx import MODELS, MODEL_REVISIONS

# Same decimal 2 GB floor as the engine's processing-space contract.
WORKING_BYTES = 2_000_000_000
# Conservative upper bound for the complete pinned set, including small files.
FULL_MODEL_BYTES = 6_000_000_000


def download_sizes():
    """Return missing bytes per immutable snapshot; never mutate the HF cache."""
    from huggingface_hub import HfApi, try_to_load_from_cache

    sizes = {}
    try:
        api = HfApi()
        for repo in MODELS.values():
            revision = MODEL_REVISIONS[repo]
            info = api.model_info(repo, revision=revision, files_metadata=True)
            if not info.siblings:
                raise ValueError('missing file metadata')
            missing = 0
            for file in info.siblings:
                if file.size is None or file.size < 0:
                    raise ValueError('missing file size')
                cached = try_to_load_from_cache(repo, file.rfilename, revision=revision)
                if not isinstance(cached, str) or not Path(cached).is_file() or Path(cached).stat().st_size != file.size:
                    missing += file.size
            sizes[repo] = missing
    except Exception as exc:
        # Metadata failure cannot justify subtracting unverified cached bytes.
        print(f'모델 메타데이터 조회 실패: 전체 크기 {FULL_MODEL_BYTES / 1e9:g} GB로 보수적 점검 / '
              f'Model metadata unavailable: conservatively checking the full {FULL_MODEL_BYTES / 1e9:g} GB: {exc}',
              file=sys.stderr, flush=True)
        return None
    return sizes


def prefetch(*, app_progress=False):
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    from huggingface_hub import snapshot_download
    from huggingface_hub.constants import HF_HUB_CACHE

    sizes = download_sizes()
    missing = FULL_MODEL_BYTES if sizes is None else sum(sizes.values())
    required = missing + WORKING_BYTES
    cache = Path(HF_HUB_CACHE)
    while not cache.exists():
        cache = cache.parent
    free = shutil.disk_usage(cache).free
    if free < required:
        ko = f'모델 설치에 필요 {required / 1e9:.2f} GB, 남은 {free / 1e9:.2f} GB'
        en = f'Model installation requires {required / 1e9:.2f} GB, available {free / 1e9:.2f} GB'
        if app_progress:
            print(json.dumps({'ko': ko, 'en': en, 'error': ko + ' / ' + en}), flush=True)
        raise OSError(ko + ' / ' + en)
    for index, repo in enumerate(MODELS.values(), 1):
        cached = sizes is not None and sizes[repo] == 0
        if app_progress:
            ko = '이미 있음' if cached else '받는 중'
            en = 'already present' if cached else 'downloading'
            print(json.dumps({'ko': f'모델 {index}/{len(MODELS)} {ko}: {repo}',
                              'en': f'Model {index}/{len(MODELS)} {en}: {repo}'}), flush=True)
        else:
            print('already present' if cached else 'fetching', repo, flush=True)
        if not cached:
            snapshot_download(repo, revision=MODEL_REVISIONS[repo])
        if app_progress:
            print(json.dumps({'ko': f'모델 {index}/{len(MODELS)} 완료: {repo}',
                              'en': f'Model {index}/{len(MODELS)} complete: {repo}'}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prefetch',))
    parser.add_argument('--app-progress', action='store_true')
    args = parser.parse_args()
    prefetch(app_progress=args.app_progress)


if __name__ == '__main__':
    main()
