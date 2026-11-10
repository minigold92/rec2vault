"""Download the MLX model set: python -m quietclerk.models prefetch."""
import argparse
import os

from .backends.mlx import MODELS


def prefetch():
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    from huggingface_hub import snapshot_download

    for repo in MODELS.values():
        print('fetching', repo, flush=True)
        snapshot_download(repo)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prefetch',))
    parser.parse_args()
    prefetch()


if __name__ == '__main__':
    main()
