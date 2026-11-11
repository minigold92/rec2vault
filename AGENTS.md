# Notes for coding agents

Layout and the test command are in [CONTRIBUTING.md](CONTRIBUTING.md). This file adds what an agent maintaining
the project needs and cannot infer from the code. Write user-facing replies to the maintainer in Korean.

## Read first

| Document | What it fixes |
|---|---|
| `docs/contracts-v2.md` | Engine contract: stages, states, caching, providers, note ownership, settings. Change it before changing behaviour |
| `docs/product-design-v3.md` | Mac app design, work items (D0, S1-S3, E1-E4, A1-A3, B, P), development and QA process (chapter 10) |
| `docs/contracts-app.md` | App shell ↔ engine boundary: bootstrap security, navigation, identity, updates and version policy |
| `docs/acceptance-v2.md`, `docs/acceptance.md` | What was verified, at which level (real input / assumed / not verified) |
| `docs/how-it-works.md` | Every stage on the fictional demo meeting |

Private material (real recordings, real meeting text, research that quotes it, Mac mini operations) lives in the
private repo at `~/Projects/side/rec`. Some design documents link to files that are only there.

## Rules

- **Nothing real goes into this repo.** No real recordings, transcripts, notes, people, work topics, hostnames or
  home paths. Use the fictional demos in `docs/examples/`. The pre-push hook runs
  `~/Projects/side/rec/scripts/scan_public.sh` (private pattern list) and blocks the push on a hit.
- **Contract first.** A change to stages, stored data, settings keys, API routes or the app <-> engine interface
  updates `docs/contracts-v2.md` (or the app contract) in the same commit.
- **Logic belongs in the engine.** The app shell (Tauri, Rust) only does windows, menu bar, notifications,
  drag and drop, updates and engine install progress; the Swift helper only registers the login item and launches
  the engine. Budgets: Rust 1,500 lines, Swift 300 lines.
- **Both languages.** Screen strings use `L('한국어', 'English')`; prompts and note text have `ko` and `en` paths.
- **A bug fix starts with a test that fails on the old code.** Run the full suite once before committing.
- **Done means executed.** Report each item as real input / assumed (tests, fakes) / not verified.
- **No dev builds during user tests.** A local build has the same bundle identifier, so macOS may open it
  instead of the downloaded app. Before asking the maintainer to test a release, quit it, unregister it
  (`lsregister -u <path>`) and delete `app/src-tauri/target/*/release/bundle`.

## Local release gate

On the maintainer's Mac a local gate (configured outside git) blocks pushes that contain code unless
`docs/contract.md` and `docs/acceptance.md` are filled, the real-path E2E items in `docs/acceptance.md` are
checked, and the test command passes. Real input samples are in `~/Projects/side/rec/samples/`. If the gate's
hooks are reinstalled, check that `.git/hooks/pre-push` still calls `scan_public.sh` first.

## Production (the maintainer's Mac mini)

- The Mac mini runs `local.quietclerk.serve` from a git checkout of this repo and updates through the in-app update
  button after a push. Never copy files to it by hand. Host name and paths are in `docs/operations.md` in the private repo.
- Restart its service only when no job is running.
- It is the first user of every release (QA stage 6 in `docs/product-design-v3.md` 10.3).
