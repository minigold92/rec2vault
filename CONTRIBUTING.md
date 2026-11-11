# Contributing

Thanks for looking. QuietClerk is a small project run by one person, so short, focused changes are
the easiest to review.

## Before you start

- **Bugs:** open an issue with the bug template. Include `deploy/setup.sh doctor` output and the
  relevant lines of `~/QuietClerk/logs/pipeline.log`. Remove names and meeting text first.
- **Features:** open an issue to discuss first, especially for changes to what is sent to engines,
  how odd input is handled, or which parts of a note belong to you. The current rules are in
  [How it works](docs/how-it-works.md) sections 6-8.
- **Never attach real meeting audio, transcripts or notes** to issues or pull requests. Use the
  fictional demos in [docs/examples](docs/examples) or make your own with
  `scripts/make_audio.py` in either demo folder.

## Layout

| Path | What it does |
|---|---|
| `app/` | Tauri v2 Mac menu bar shell (Rust + one static fallback page; no JS framework or bundler) |
| `quietclerk/serve.py`, `executor.py`, `store.py` | The service: scheduler, one-job-at-a-time executor, SQLite state |
| `quietclerk/intake.py`, `quarantine.py`, `probe.py` | Inbox checks: stability, size, duration, decoding, deduplication |
| `quietclerk/stages/` | Pipeline stages (audio, local models, text, note) |
| `quietclerk/backends/mlx.py`, `worker.py` | MLX models, run in a separate worker process |
| `quietclerk/providers/` | Codex / Claude / Ollama / omp text engines and what they may receive |
| `quietclerk/postprocess.py`, `render.py`, `notes/` | Prompts, Markdown rendering, note publishing and user-edit preservation |
| `quietclerk/server/` | Local web screens and JSON API (loopback only) |
| `quietclerk/install.py`, `deploy/` | launchd install, update and v1 upgrade with rollback |
| `docs/how-it-works.md` | Walkthrough of every stage with real outputs |

## Tests

```sh
uv run --python 3.12 --no-project --with pytest --with pyyaml --with starlette --with uvicorn \
  --with jinja2 --with httpx --with jsonschema --with numpy python -m pytest -q tests
```

The suite runs on Linux CI without MLX: models and text engines are faked, audio is synthesized
with ffmpeg. A change in behaviour should come with a test that fails without it. Tests must not
touch your real `~/QuietClerk`, `~/Library/LaunchAgents` or launchctl.

### Mac app (Apple Silicon, macOS 14+)

Install Rust stable (including `aarch64-apple-darwin`), Xcode Command Line Tools and Node/npm.
The app contract is [docs/contracts-app.md](docs/contracts-app.md). From the repository root:

```sh
cd app
npm ci
cargo test --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings
npm run tauri -- dev
# Local ad-hoc app + DMG build; no updater private key required:
npm run tauri -- build --target aarch64-apple-darwin --bundles app,dmg \
  --config '{"bundle":{"createUpdaterArtifacts":false}}'
```

The app and DMG are under `app/src-tauri/target/aarch64-apple-darwin/release/bundle/`.
Rust unit tests use temporary bootstrap files and never touch the real engine data.
The normal shell reads the existing engine's private bootstrap file; it does not implicitly install or start it.
The S1 library exposes explicit service functions that call the Python installer (`contracts-app.md` §6).
The opt-in `scripts/probe_login_service.py` exercises real launchd and cleans its temporary app/service;
it refuses an existing local engine and is never part of pytest. Build its Rust entrypoint with
`cargo build --manifest-path app/src-tauri/Cargo.toml --release --target aarch64-apple-darwin --example login_service_probe`.
The colored app icon comes from `quietclerk/server/static/seogi.svg` (`tauri icon … --fit contain`);
`app/src-tauri/icons/tray.svg` is its monochrome outline, rendered with `tauri icon … --png 44`.
For release builds only, CI uses the two updater signing secrets and creates signed update artifacts.
Keep Cargo, npm, Tauri and CHANGELOG versions aligned before pushing a `v*` tag.

To exercise the real models on an Apple Silicon Mac, process a demo recording into a throwaway root:

```sh
mkdir -p /tmp/qc-try/inbox && cp "docs/examples/demo-meeting-en/Recording 261112_140000.m4a" /tmp/qc-try/inbox/
cp docs/examples/demo-meeting-en/settings.toml /tmp/qc-try/
QC_ROOT=/tmp/qc-try QC_SETTINGS=/tmp/qc-try/settings.toml \
  uv run --python 3.12 --no-project --with pyyaml --with "mlx-audio==0.6.4" --with "mlx-whisper==0.4.3" \
  --with soundfile --with numpy --with soynlp python -m quietclerk.tick
```

## Pull requests

- One topic per pull request; describe what changed for the user and how you checked it.
- Prompt changes bump the matching `*_PROMPT_VERSION` in `quietclerk/postprocess.py` so cached
  results are not reused.
- Keep user-facing text in both languages (`L('한국어', 'English')` in the screens, `ko`/`en`
  prompts).
- By contributing you agree that your contribution is licensed under the MIT license.
