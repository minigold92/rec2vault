# How QuietClerk works

This page follows **one fictional meeting** from the phone to the finished note. For every stage it shows what
goes in, what comes out, and why it is built that way. Every excerpt is copied from files in
[`examples/demo-meeting-en/`](examples/demo-meeting-en/), produced by the current code.

[한국어](how-it-works.ko.md)

> **About the example.** A 90-second, three-person product meeting about a made-up bike-share app
> ("Harbor Bikes" in the script). The script ([`scripts/script.md`](examples/demo-meeting-en/scripts/script.md))
> was written for this page and voiced with macOS `say` (voices Reed, Daniel, Tara). **Synthetic voices are
> not people**: what you see here shows what each stage does, not how well it works on real meetings. Accuracy on
> real recordings is in [benchmark.md](benchmark.md), and only for Korean.
> The same walkthrough with a Korean meeting, including a speaker-separation failure, is in
> [how-it-works.ko.md](how-it-works.ko.md).

```mermaid
flowchart LR
  A["Phone recorder<br/>.m4a"] -->|Syncthing| B["inbox/"]
  subgraph MAC["Your Mac: the audio stays here"]
    B --> C["intake<br/>stable? new? 5 min to 3 h?"]
    C --> D["convert<br/>diarize<br/>detect_language"]
    D --> E["transcribe<br/>second_pass"]
    E --> F["turns"]
  end
  subgraph CLI["Text only: your LLM CLI (e.g. Codex)"]
    G["correct<br/>classify<br/>summarize"]
  end
  F --> G --> H["note<br/>Obsidian vault"]
```

The pipeline ran on an Apple M3 Max Mac and took **45 s for 90 s of audio** (`work/pipeline.log`):

```
convert:done:0s diarize:done:2s detect_language:done:3s transcribe:done:5s second_pass:done:4s turns:done:0s correct:done:11s classify:done:11s summarize:done:10s note:done:0s
```

For scale, [benchmark.md](benchmark.md#end-to-end-time) has a real 35.4-minute recording on a Mac mini M4 taking
808 s. The two machines and recordings are not comparable.

## What the script plants

The pipeline is judged against things we know are in the audio:

| Planted | In the script |
|---|---|
| 1 decision | Ride passes move to the first screen; the referral programme is out of this release |
| 2 action items | Priya: mock-ups by next Thursday · Leo: measure the unlock API latency, **no deadline yet** |
| 2 figures | 41% of support tickets; 2.3 s median unlock time |
| 1 open issue | Keep the old map view for older phones? |
| Names | Priya and Leo introduce themselves; the chair (Marcus in the script) is never named |
| Easy to mishear | The app name, "API", "mock-ups", "referral programme" |

---

## 1. Phone to inbox

The phone's recorder app saves `Recording 261112_140000.m4a` (`YYMMDD_HHMMSS`, the start time). Syncthing copies
it into the Mac's `inbox/` folder. The pipeline **only reads the inbox**: it copies a file out and never moves,
renames or deletes anything there.

## 2. Intake: is this file finished, new, and safe to open?

On your Mac a background service (launchd `KeepAlive`, `quietclerk.cli serve`) scans the inbox every 60 s and runs
queued jobs one at a time; this demo used a single pass of `python -m quietclerk.tick` instead. A file must pass
every check before it becomes a **job**:

| Check | Why | In this demo |
|---|---|---|
| Only top-level `.m4a`; not hidden, not `통화*` (call recordings), not a symlink | Only voice recordings; never follow a link out of the inbox | passed |
| Size and modification time unchanged for 60 s | Syncthing may still be writing | demo set `stable_sec = 0` |
| Copied to a private quarantine folder with `O_NOFOLLOW`, ≤ 1 GiB, hashed (SHA-256) | A file that changes mid-copy is ignored and retried; one hash = one job, even under another name | new |
| `ffprobe` after a header scan; one AAC stream; 5 min ≤ length ≤ 3 h | Skip broken, pocket-length and runaway files | demo set `min_duration_sec = 60`; 90 s passes |
| Recorded after the install time (or listed in `include.txt`) | Old phone recordings are not processed by surprise | demo set `since = "2026-01-01 00:00"` |

A pass is copied to `archive/<job_id>/source.m4a`. The job id is `20261112-140000-66bb2495`: recording time plus
the first 8 characters of the hash. A policy failure (too short, before the cutoff) is kept as a `skipped` job
that you can promote later; a hostile or broken file is only logged as rejected (see [section 7](#7-odd-and-hostile-input)).
A failed stage is retried up to 3 times, 5 minutes × attempt number apart, then marked `failed`.

## 3. The ten stages

Each stage writes one JSON file and records the hash of its inputs and its parameters. Run it again and a stage
whose inputs and parameters did not change is **reused** instead of recomputed. Files below are in
[`work/`](examples/demo-meeting-en/work/), named after the stage. (On disk, `detect_language`, `transcribe`,
`second_pass`, `correct`, `classify` and `summarize` are stored as `language.json`, `asr.json`, `alt.json`,
`corrected.json`, `classification.json` and `summary.json`.)

### convert

**In** `source.m4a` → **Out** `audio.wav`, 16 kHz mono 16-bit (not kept in the examples; ~2.9 MB for 90 s).
`ffmpeg` with a restricted protocol list reads only the file itself, and the decoded length must match the probed
length within 10%. Every model below expects this format.

### diarize: who spoke when

**In** `audio.wav` → **Out** [`diarize.json`](examples/demo-meeting-en/work/diarize.json)

```json
[{"start": 0.0, "end": 3.48, "speaker": "0"}, {"start": 3.8000000000000003, "end": 6.1000000000000005, "speaker": "0"}, {"start": 7.15, "end": 10.67, "speaker": "1"}, {"start": 11.34, "end": 14.49, "speaker": "2"}, …]
```

22 time ranges, labels `"0"`, `"1"`, `"2"` (anonymous). The model, NVIDIA Nemotron 3 Diarization (MLX), knows
neither names nor words. It runs first because the next stage uses it to find speech.

### detect_language

**In** `audio.wav`, `diarize.json` → **Out** [`detect_language.json`](examples/demo-meeting-en/work/detect_language.json)

```json
{"status": "decided", "top": "en", "shares": {"en": 1.0}, "windows": [{"start": 7.15, "end": 10.67}, …
```

Takes up to six windows (≤ 20 s each) of diarized speech spread across the recording and lets Whisper vote on
each one, weighted by length. It is `decided` only with at least 15 s of speech and a 60% share; otherwise the
note is flagged. The result picks the language for every later stage, including the LLM prompts. A fixed language
in settings skips this stage.

### transcribe: what was said, with word times

**In** `audio.wav`, `detect_language.json` → **Out** [`transcribe.json`](examples/demo-meeting-en/work/transcribe.json)
(224 words)

```json
[{"start": 0.0, "end": 0.24, "text": "Hi"}, {"start": 0.24, "end": 0.96, "text": "everyone"}, {"start": 1.12, "end": 1.36, "text": "Let's"}, …, {"start": 1.92, "end": 2.72, "text": "ArborBikes"}, …]
```

Qwen3-ASR 1.7B (8-bit) transcribes in chunks of at most 60 s; Qwen3-ForcedAligner 0.6B then finds when each word
was spoken. Output has no punctuation. Word times are what make the next stage and the clickable citations in
the note possible. Note `ArborBikes`: the script says *Harbor Bikes*.

### second_pass: a second opinion

**In** `audio.wav`, `detect_language.json` → **Out** [`second_pass.json`](examples/demo-meeting-en/work/second_pass.json)
(225 words)

```json
[{"start": 0.0, "end": 0.24, "text": "Hi"}, {"start": 0.24, "end": 0.7, "text": "everyone,"}, {"start": 1.14, "end": 1.42, "text": "let's"}, …
```

Whisper large-v3 turbo transcribes the same audio independently. It is **never used as the transcript**; it is
only given to the correction stage as a hint, because two recognizers rarely make the same mistake. Here they did
make the same one: Whisper also heard `Arbor` (`{"start": 1.9, "end": 2.3, "text": "Arbor"}`) and it also
misheard "look after the backend" as `{"start": 13.34, "end": 13.6, "text": "off"}`.

### turns: words plus voices

**In** `transcribe.json`, `diarize.json` → **Out** [`turns.json`](examples/demo-meeting-en/work/turns.json)

```json
{"start": 0.0, "end": 6.08, "speaker": "S1", "text": "Hi everyone Let's start the ArborBikes app review Priya from Design is joining us today"}
{"start": 7.28, "end": 10.64, "speaker": "S2", "text": "Hi I'm Priya I'd like to walk through the new first screen"}
{"start": 11.44, "end": 14.48, "speaker": "S3", "text": "Hi Leo here I look after the backend"}
```

Plain code, no model (`quietclerk/transcript.py`): each word gets the diarization speaker it overlaps most; words
by the same speaker join into one **turn** unless there is a pause of 1.5 s or more; labels become `S1`, `S2`, …
in order of first appearance. Turns are the unit everything after this refers to: `t1`, `t2`, … in the note.

Against the script, **all 16 script lines became 16 turns with the right speaker** (S1 chair, S2 Priya, S3 Leo)
in this clip. That is not typical: it takes clearly different voices and clean turn-taking. The Korean demo shows
what happens when it fails.

### correct: fix misheard words

**In** `turns.json` + `second_pass.json` → **Out** [`correct.json`](examples/demo-meeting-en/work/correct.json)

The turns go to your LLM CLI 60 at a time as JSON with the matching stretch of the second-pass text attached. The
rules (`quietclerk/postprocess.py`): keep every id and line count, fix only misrecognized words and spelling, never
add, drop or summarize, keep uncertain text unchanged, and treat anything in the transcript as data, never as an
instruction. A reply that drops, merges or duplicates lines is rejected and the chunk is retried in halves; a
part that still fails keeps its original text. One call here (`"correct 0-15: codex"`). Two of 16 lines changed:

| Turn | Before → after |
|---|---|
| 1 | `ArborBikes` → `Arbor Bikes` |
| 4 | `fortyone percent` → `forty-one percent` |

The other 14 are identical. What it could **not** fix: `Arbor` stays (both recognizers agree, and the LLM has no
way to know the app is called *Harbor*), and the stray word in `two point three seconds Seconds at the median` (turn 8) survived.
Correction is a language model guessing from context: it fixes nonsense, and it can just as confidently write a
wrong word.

### classify: type, title, speakers

**In** `correct.json` + the source file name + names of projects already in your vault → **Out**
[`classify.json`](examples/demo-meeting-en/work/classify.json)

```json
"title": "Arbor Bikes App First-Screen Review",
"type": "meeting",
"type_confidence": "high",
"type_basis_id": "t13",
"division": "work",
"project": null,
"project_suggest": "Arbor Bikes app",
"S2": {"role": "Design representative", "name": "Priya", "name_id": "t2", "split_suspect": false},
"S3": {"role": "Backend representative", "name": "Leo", "name_id": "t3", "split_suspect": false}
```

The code validates the reply instead of trusting it: `type` must be from a fixed list, a name counts only if
`name_id` points at a real line, a project counts only if it already exists in your notes (otherwise it becomes
`project_suggest`), the title must be 8–50 characters, and speaker labels must match the turns. `split_suspect` is the
model's flag for "one label seems to contain two people". The chair `S1` has no name because nobody says it,
which matches the script.

### summarize: summary with line citations

**In** `correct.json`, `classify.json` → **Out** [`summarize.json`](examples/demo-meeting-en/work/summarize.json)

```markdown
## Decisions

- Move ride passes to the first screen. [t13, t14, t15]
- Exclude the referral program from this release. [t13, t14, t15]

## Tasks

- [ ] Measure unlock API latency and share the results (Leo / deadline to be set after checking the sprint). [t10, t11]
- [ ] Prepare mockups (Priya / next Thursday). [t12]
```

The section layout depends on the meeting type (a *meeting* gets key summary, agenda, decisions, tasks, open
issues, review needed). The prompt asks for a `[t12]` citation on every item, and a summary with no citation at
all is rejected. Only agreed outcomes count as decisions and only assigned or volunteered work as tasks.

### note: write the Markdown file

**In** `summarize.json` and the other stage outputs → **Out** a note in your vault,
`notes/2026-11-12_1400_Arbor_Bikes_App_First-Screen_Review.md`
([demo snapshot, saved under the former filename](examples/demo-meeting-en/notes/2026-11-12_Arbor_Bikes_App_First-Screen_Review_1400.md)),
plus [`work/note.json`](examples/demo-meeting-en/work/note.json) (path and review reasons). This stage is never
cached: it merges into whatever is already in the vault. See [section 5](#5-the-note).

## 4. Against the script

Planted items, checked by reading the output:

| Planted | Result |
|---|---|
| Decision | ✅ Two lines in `## Decisions`: passes to first screen; referral programme out |
| Task: Priya | ✅ `Prepare mockups (Priya / next Thursday)`, with owner by name. "Next Thursday" stays a phrase; it is not converted to 2026-11-19 |
| Task: Leo, no deadline | ✅ `deadline to be set after checking the sprint`: the missing date was kept, not invented |
| 41% | ✅ in the key summary |
| 2.3 s | ⚠️ Present only as an item under `Review needed` ("proper measurement is pending"); not in the key summary |
| Open issue | ✅ `## Open issues`: old map view |
| Speakers | ✅ 16/16 lines on the right speaker; Priya and Leo named from their introductions; chair unnamed |
| App name | ❌ **`Arbor Bikes` everywhere, including the title and the note's file name.** Script says *Harbor* |
| Wording | One extra word `Seconds` remains in turn 8 |

Counting words after folding spelling variants (`forty-one` = `41 percent`, `mock-ups` = `mockups`, …),
the 225-word script differs from the transcript by 2 words (*Harbor* → *Arbor*, the extra *Seconds*) before and
after correction, and from the second pass by 4. A single clip, one speaker voice each, synthetic: do not read
these as an error rate.

---

## 5. The note

`render.py` and `notes/` assemble the note and write it **atomically** (temp file, fsync, journal, rename).
Excerpt of the properties ([full note](examples/demo-meeting-en/notes/2026-11-12_Arbor_Bikes_App_First-Screen_Review_1400.md)):

```yaml
qc_schema: 2
title: Arbor Bikes App First-Screen Review
date: '2026-11-12'
started_at: '2026-11-12T14:00:00'
duration_min: 1.5
language: en
type: meeting
status: draft
needs_review: true
review_reasons:
- summary_review
source_file: Recording 261112_140000.m4a
source_sha256: 66bb249562015d787ecfd2858a310836ca180fff9edcab2b00dbd1c13094582d
job_id: 20261112-140000-66bb2495
pipeline_llm:
- codex
external_text_to:
- codex
```

The body (the headings are plain Markdown; there are no hidden comment markers):

```markdown
## Tasks
- [ ] Measure unlock API latency and share the results (Leo / deadline to be set after checking the sprint). [[#^t10|00:53]] [[#^t11|01:02]] ^task-1
- [ ] Prepare mockups (Priya / next Thursday). [[#^t12|01:06]] ^task-2

## Meeting record

> [!info] Overview
> Meeting · 1.5 min

| Speaker | Role | Name |
|---|---|---|
| S2 | Design representative | Priya [[#^t2\|00:07]] |

> [!summary] Key summary
…
## Full transcript

**[00:07] S2**: Hi I'm Priya I'd like to walk through the new first screen ^t2

## Notes
```

- **Citations are links.** `[t10]` became `[[#^t10|00:53]]` and each transcript line ends with the block id `^t10`,
  so clicking a time jumps to the line. A citation that points at no line is shown as `[?t999]` and adds a review
  reason. A citation proves where to look, not that the sentence is right.
- **Tasks** are Markdown checkboxes with their own block ids (`^task-1`).
- **`needs_review: true`** with the reason `summary_review` because the summary has a *Review needed* section. Other
  reasons: uncertain type or language, a failed correction chunk, an unknown citation.
- **Provenance**: models and revisions (`pipeline_asr`), the LLM CLI (`pipeline_llm`), and who received text
  (`external_text_to`), plus the original file name and SHA-256, so a note can always be traced to its recording.
- Filenames use recording date and time first: `YYYY-MM-DD_HHMM_title.md`; memos use
  `YYYY-MM-DD_HHMM_메모_title.md`. Exports use the same stem. On the next publication (including
  Resume for a completed job), only old engine filenames matching that job's recording date/time move
  to the new format, retaining the existing slug. Custom names and occupied destinations are preserved.
  The existing publication journal rolls prepared moves back and completes renamed moves after a crash.
  Enabled daily-note links keep their alias and other bytes, changing only the old note stem.
- `notes/회의록-v2.base` is an Obsidian Bases view. Both recent and review-waiting views show
  `date(started_at).format("YYYY-MM-DD HH:mm")` as recording time and sort by `started_at` descending
  ([Bases functions](https://help.obsidian.md/bases/functions)). Missing views are created; known old
  templates are upgraded only when bytes or strictly parsed YAML values match. YAML formatting-only
  changes from Obsidian are accepted; added views or other content edits are left alone.

### What stays yours when the note is regenerated

If the same recording is processed again (you changed the LLM, or asked for a fresh summary), the note is found by
`job_id` + hash even if you renamed the file, and updated in place:

- **The engine owns exactly one stretch**: from `## Meeting record` to the next `## Notes`. Everything else,
  including your edits to the task list, text you add anywhere outside that stretch, and the `## Notes` section,
  is preserved byte for byte.
- **Properties**: `project`, `attendees` and `status` are yours from the start. Any other property you edit
  (say `title`) becomes yours the moment it differs from what the engine last wrote, and is never overwritten afterwards.
- Tasks the new summary proposes that you do not already have appear under *Newly proposed tasks* inside the
  engine stretch instead of silently changing your list.
- Text produced by a model cannot fake the boundaries: a model-written `## Notes` heading is demoted, and
  HTML, links, images and block ids in model text are neutralized.
- A note with a missing or duplicated boundary heading, malformed YAML, or a changed hash at write time is **not
  written**; the job reports a conflict and your file stays as it was.

## 6. What leaves your Mac

| Data | Where it goes |
|---|---|
| **Audio** | Phone → your Mac through Syncthing. Never sent to an AI service |
| Transcript text of every turn (stages `correct`, `classify`, `summarize`) | The LLM CLI you configured (here `codex`, i.e. OpenAI) |
| Source file name and the list of project names already in your vault (stage `classify` only) | The same CLI |
| Model weights | Downloaded once at install; at run time loaded from the local Hugging Face cache only |
| Update check (`updates.check`, default on) | Once a day `git fetch` in the install checkout asks GitHub for new commits; no meeting data, settings or notes |

How it is limited:

- **Per-provider consent per field.** `settings.toml` of this demo has
  `"providers.consent" = {codex = ["transcript", "source_name", "project_list"]}`. A provider without consent for
  a field is not used for that call; with no eligible provider the job waits (`blocked`), it does not fall back
  to sending anyway.
- **`providers.local_only = true`** allows only local endpoints (Ollama on `127.0.0.1`); an external or unknown one
  is refused.
- **Tools off.** Codex runs with a read-only sandbox, shell, web search and plugins disabled, in an empty temp
  directory; Claude with no tools. If the CLI reports a tool call, the stage aborts without fallback.
- **The note says so**: `external_text_to: [codex]` lists every provider that received text, including failed
  attempts.

## 7. Odd and hostile input

Input is untrusted at three places: the audio file, the transcript the LLM reads, and the note files on disk. What
the code does, and the test that checks it (`tests/`, all with **generated** audio and files, no real recordings):

| Input | What happens | Test |
|---|---|---|
| Ordinary `.m4a` | Processed | `test_intake.py::test_in03_duration_boundary` (299 s skipped, 300 s queued) |
| Still being written / growing | Waits; the 60 s stability timer restarts on growth | `test_in09_stability_restarts_after_growth` |
| 0-byte file | Waits (flagged `empty_file` after an hour); accepted if it later grows | `test_in08_zero_byte_waits_and_late_growth_is_accepted` |
| Same audio again, or one you deleted | Not processed twice (`duplicate`, `deleted_by_user`) | `test_in16_duplicate_and_tombstone` |
| Same name, different audio | New job | `test_in17_same_name_different_contents_creates_new_job` |
| Too short / before the cutoff | `skipped` job, can be promoted later; the original is re-validated first | `test_in05_promote_revalidates_original` |
| Longer than 3 h; larger than 1 GiB | Rejected; an oversized file is never read, hashed or probed | `test_in14_invalid_probe_lengths`, `test_in13_sparse_oversized_file_never_hashed_or_probed` |
| Truncated, non-MP4 bytes named `.m4a`, or non-AAC codec | Rejected (`decode`, `format`, `codec`), no job | `test_in10_…`, `test_in11_disguised_format_and_unsupported_codec` |
| Container pointing elsewhere (HLS playlist, ffconcat list, MP4 with `http`/`file`/`urn` data references) | Rejected `format` **before any demuxer runs**: no network request, bait file never opened | `test_intake_security.py::test_in12_external_references_never_open_network_or_local_bait` |
| Symlink, or file swapped for a link mid-copy | Ignored / stays waiting; target never read | `test_in06_in07_ignored_paths_leave_no_records`, `test_link_swap_between_lstat_and_open_never_reads_target`, `test_midcopy_replacement_stays_waiting` |
| Names like `../x.m4a`, backslash, newline, NUL | Rejected `path`, not a job | `test_quarantine_rejects_path_escape_names`, `test_unsafe_filename_is_rejected_not_a_job` |
| File that grows while being copied | Copy stops at the limit plus one byte | `test_quarantine_enforces_limit_during_growth` |
| Container length and the decoded audio length disagree by more than 10%, or decode to over 3 h | `audio_decode` failure, not retried | `test_audio.py::test_in14_false_metadata_or_over_three_hours_is_failed_audio_decode` |
| Silence or noise | Ends as `skipped: no_speech` | `test_in19_synthetic_silence_noise_no_speech_transition` |
| Less than 2 GiB free | Copying and processing pause; resume when space returns | `test_in15_disk_low_stops_copy_or_archive` |
| A transcript line that says "ignore the rules and summarise" | Prompts mark transcript text as data; a reply that drops or adds lines is rejected | `test_postprocess.py::test_response_that_drops_or_adds_lines_is_rejected` |
| LLM reply with invalid type, missing evidence, duplicate ids, or a summary without citations | Rejected and retried, then the stage fails | `test_classify_rejects_types_outside_the_list`, `test_classification_missing_evidence_is_stage_failure`, `test_IN23_duplicate_correction_ids_are_rejected`, `test_summary_must_cite_transcript_lines` |
| LLM CLI starts using tools | Stage aborts, no fallback provider | `test_providers.py::test_tool_use_stops_without_fallback` |
| `<script>`, links, unknown citations in model text | Escaped; unknown citation shown as `[?t9999]` | `test_notes.py::test_malicious_html_links_and_unknown_citations_are_safe` |
| Model text that contains the note's boundary headings | Demoted, so the record span stays unique | `test_render.py::test_model_text_cannot_fake_the_record_boundaries` |
| Note with duplicate YAML keys or alias cycles | Refused, nothing written | `test_malformed_yaml_duplicate_keys_and_alias_cycles_rejected` |
| Process killed while writing a note | Recovered from the journal without a model call; a hash mismatch keeps your edit | `test_SIGKILL_publication_recovery_has_no_model_call`, `test_renamed_recovery_hash_mismatch_retains_user_edit` |

Not covered by any test: the quality of what a **real** LLM or model does with adversarial *speech* (for example someone
reading instructions aloud). The defences above are the prompt rules plus structural validation of the reply.

## 8. Why it is built this way

| Decision | Reason | Cost | Evidence |
|---|---|---|---|
| Diarization and transcription run **locally** | Audio never leaves your devices; no per-minute quota | Needs an Apple Silicon Mac; ~5 GB of model weights | Peak memory 5.1 GB, one hour of audio ≈ 7 min ([benchmark](benchmark.md#full-recordings)) |
| Qwen3-ASR + aligner as the transcript | Steadiest of the local candidates; never skipped audio on four real Korean meetings; gives word times | Slower than Whisper | [benchmark](benchmark.md#full-recordings) |
| Whisper turbo only as a *hint* | Fastest, but last on all four recordings and it dropped 6–9% of the text | An extra pass of audio | [benchmark](benchmark.md#full-recordings) |
| LLM correction on text only, with the second transcript attached | A context-only correction improved character error against CLOVA by 1–2 points; the second recognizer about 1 more | Text leaves the machine; it can also change a correct word | [benchmark](benchmark.md#correction-with-a-subscription-cli-two-5-minute-clips) (Korean, two 5-minute clips) |
| Turns of 60 per call, split in halves on a bad reply | Long inputs sometimes come back with merged lines; a bad chunk only costs its own correction | More calls | `quietclerk/postprocess.py`; test `test_large_chunk_that_keeps_failing_is_retried_in_halves` |
| Speakers stay `S1`, `S2`… and names carry a link to where they were heard | Diarization can merge or split people; a name is a guess | You rename by hand | [Korean walkthrough](how-it-works.ko.md), where speakers do get merged |
| One JSON file per stage, keyed by input hash and parameters | A crash resumes at the failed stage; changing only the summary prompt reuses everything before it | Disk space | `quietclerk/executor.py`; `reused` in the stage log of a re-run |
| Subscription CLI instead of an API key | Uses a plan you already pay for | Depends on the CLI's supported versions (Codex 0.163–0.167 are the verified ones; others are refused unless you allow them) | `quietclerk/providers/cli.py` |

Not measured anywhere: English accuracy, summary quality, speed on other Macs, absolute accuracy against a human
transcript.

## 9. What was verified, and how

| Level | What |
|---|---|
| **Ran on synthetic input** | The full pipeline on this clip (and on the Korean clip) end to end, once each; timings and outputs on this page are from that run |
| **Compared with a known script** | Planted decision, tasks, figures, names, speaker assignment, word differences: section 4 |
| **Checked on real recordings** | Not by this page. [benchmark.md](benchmark.md): four real Korean meetings (18–56 min, kept locally in the git-ignored `samples/`, not published) and one 35-minute end-to-end run |
| **Hostile and malformed input** | Unit tests in section 7 with generated files. Not tested with real-world corrupt recordings |
