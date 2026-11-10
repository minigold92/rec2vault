# demo-meeting-en: one fictional meeting run through the real pipeline

> The audio is **synthetic speech** (macOS `say`), not people. What follows shows what each stage produces and where
> it goes wrong; it says nothing about accuracy on real meetings. One clip, one run. The walkthrough that quotes
> these files is [`docs/how-it-works.md`](../../how-it-works.md).

## What is where

| Path | What | Stage that wrote it |
|---|---|---|
| `scripts/script.md` | The script: 16 lines, 3 speakers, the answer key | written by hand |
| `scripts/make_audio.py` | Script → speech with `say` voices, joined with 0.7 s gaps, AAC | written by hand |
| `Recording 261112_140000.m4a` | The input: AAC 48 kHz mono, 90.0 s | `say` + ffmpeg |
| `settings.toml` | The only settings the run changed | written by hand |
| `work/diarize.json` | Who spoke when (22 ranges, labels 0–2) | `diarize` |
| `work/detect_language.json` | Language vote (`en`, decided) | `detect_language` |
| `work/transcribe.json` | 224 words with times (Qwen3-ASR + aligner) | `transcribe` |
| `work/second_pass.json` | 225 words with times (Whisper large-v3 turbo) | `second_pass` |
| `work/turns.json` | 16 speaker turns | `turns` |
| `work/correct.json` | Corrected text of each turn | `correct` (Codex CLI) |
| `work/classify.json` | Title, type, topics, speakers | `classify` (Codex CLI) |
| `work/summarize.json` | Summary Markdown with `[t4]` citations | `summarize` (Codex CLI) |
| `work/note.json` | Where the note was written, review reasons | `note` |
| `work/pipeline.log` | The log lines of the run (stage times) | executor |
| `notes/2026-11-12_…_1400.md` | The finished Obsidian note | `note` |
| `notes/회의록-v2.base` | The Obsidian Bases view the engine writes next to notes | `note` |

Left out: `audio.wav` (16 kHz conversion, 2.9 MB), the `*.meta.json` files that record input hashes and parameters,
`run-settings.json` and `state.sqlite3`. On disk the stage files are named `language.json`, `asr.json`, `alt.json`,
`corrected.json`, `classification.json`, `summary.json`; here they carry the stage name. Absolute paths inside
`note.json` and `pipeline.log` were replaced by `<root>`. Nothing else was edited.

## How it was run

One `python -m quietclerk.tick` pass, in an empty scratch root, with the m4a placed in its `inbox/`. `settings.toml`
lowers the cutoffs for a short demo (`min_duration_sec = 60`, `stable_sec = 0`, `since = "2026-01-01 00:00"`), sets
the language and selects the Codex CLI with fast mode and consent for `transcript`, `source_name` and `project_list`.
Run on an Apple M3 Max Mac. The whole job took 45 s for 90 s of audio:
`convert 0 s · diarize 2 s · detect_language 3 s · transcribe 5 s · second_pass 4 s · turns 0 s · correct 11 s · classify 11 s · summarize 10 s · note 0 s`.
The warning `no Syncthing folder contains <root>/notes` is expected: the scratch folder is not a Syncthing folder, so
the post-write rescan is skipped. The LLM calls were one each for `correct`, `classify` and `summarize`.

## Script versus result

Answer key: `scripts/script.md`. Everything below was checked by reading the files, except the word-difference count,
which is a script (`difflib` on lower-cased words, with `forty-one` = `41 percent`, `2.3` = `two point three`,
`mock-ups` = `mockups`, `programme` = `program` folded together).

**Speakers (right).** The 16 script lines became 16 turns; each turn has the speaker of its line (S1 = Marcus the
chair, S2 = Priya, S3 = Leo). Diarization found 3 speakers. The model named Priya (from line 2) and Leo (from line 3)
and left the chair unnamed, which matches the script (nobody says his name). `split_suspect` is `false` for all three.

**Planted items.**

| Planted | Result |
|---|---|
| Decision: passes move to the first screen, referral programme out | caught, as two bullets under `## Decisions` |
| Task: Priya, mock-ups by next Thursday | caught: `Prepare mockups (Priya / next Thursday)`; the date is left as "next Thursday" |
| Task: Leo, measure unlock API latency, no deadline | caught: `deadline to be set after checking the sprint`, nothing invented |
| 41% of tickets | caught, in the key summary |
| 2.3 s median unlock time | caught, but only inside a `Review needed` item ("proper measurement is pending"); absent from the key summary |
| Open issue: old map view | caught under `## Open issues` |

**Wrong or lost.**

- **Brand name.** The script says *Harbor Bikes*. Both recognizers heard `Arbor`: `transcribe.json` has `ArborBikes`,
  `second_pass.json` has `Arbor`. The correction stage joined it to `Arbor Bikes` and the error carries into the
  title (`Arbor Bikes App First-Screen Review`), the topics, the agenda and the note's file name. Nothing in the
  pipeline can catch it because both inputs agree.
- **`Seconds` doubled.** Turn 8 reads `two point three seconds Seconds at the median`; the extra word survived the
  correction. The note's own summary says "2.3 seconds" correctly.
- **Second pass.** Whisper wrote `look off to the back end` for "look after the backend" (script line 3) and `the renew button`
  for "a renew button"; the primary transcript got both right.
- **Correction changed 2 of 16 turns:** `ArborBikes` → `Arbor Bikes` and `fortyone` → `forty-one`. No word was wrongly changed.
- Word difference against the 225-word script: `transcribe` 2 (Harbor→Arbor, extra Seconds), `correct` 2 (same),
  `second_pass` 4 (those plus `after`→`off to`, `a`→`the`).
- Not converted: "next Thursday" is not turned into a date.

## Verification level

- **Ran on synthetic input:** yes, the full pipeline once, no errors, no retries.
- **Compared with known text:** yes, against the script as above.
- **Checked on real recordings:** no. This folder is synthetic speech in a single voice per speaker. Real recordings
  are covered by [`docs/benchmark.md`](../../benchmark.md) (four Korean meetings; English not measured).
- **Not checked:** other synthetic voices, repeated runs of the same clip, English on real speech.
