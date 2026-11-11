"""Download the MLX model set: python -m quietclerk.models prefetch."""
import argparse
import json
import os

from .backends.mlx import MODELS


def prefetch(*, app_progress=False):
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    from huggingface_hub import snapshot_download

    for index, repo in enumerate(MODELS.values(), 1):
        if app_progress:
            print(json.dumps({'ko': f'모델 {index}/{len(MODELS)} 받는 중: {repo}',
                              'en': f'Downloading model {index}/{len(MODELS)}: {repo}'}), flush=True)
        else:
            print('fetching', repo, flush=True)
        snapshot_download(repo)
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
