# Benchmark: local Korean transcription and diarization on a Mac mini M4

Measured 2026-11-09 on a Mac mini M4 (16 GB), mlx 0.32.4, mlx-audio 0.6.4, mlx-whisper 0.4.3.
Inputs are four real Korean work meetings recorded on a Galaxy S25 Ultra with the built-in recorder
(18, 29, 42 and 56 minutes, 3–7 speakers). The recordings themselves are not published.

## How accuracy was judged

There is no human-made ground truth. Each recording was also transcribed by two commercial services,
**Samsung Voice Recorder (Transcript Assist)** and **CLOVA Note**, and every candidate was compared
with both. The two services already disagree on 16–21 of every 100 characters, so a local candidate
whose distance to them is in the same range is treated as "commercial-grade". This shows relative
quality, not absolute accuracy.

- **CER**: character error rate after keeping only Hangul, Latin letters and digits (spacing and
  punctuation ignored). Lower is better.
- **Speaker agreement**: share of 0.1 s frames where reference and candidate both have a speaker and
  the speakers match under the best one-to-one label mapping.
- **RTF**: processing time ÷ audio length, models already downloaded. Lower is faster.
- **Chars**: characters produced relative to CLOVA Note; values well below 100% mean skipped audio.

## Full recordings

| Recording | Candidate | CER vs Samsung | CER vs CLOVA | Speaker agreement | Speakers | Chars | RTF | Peak memory |
|---|---|---|---|---|---|---|---|---|
| A · 18 min | Samsung ↔ CLOVA | 0.163 | — | 0.917 | 3 | — | — | — |
| | **Qwen3-ASR 1.7B + aligner + Nemotron 3** | 0.183 | 0.169 | 0.939 | 3 | 99% | 0.122 | 4.5 GB |
| | MOSS-Transcribe-Diarize 0.9B, one pass | 0.176 | 0.151 | 0.946 | 3 | 98% | 0.263 | 2.9 GB |
| | Whisper large-v3 turbo + Nemotron 3 | 0.224 | 0.196 | 0.944 | 3 | 93% | 0.082 | 2.2 GB |
| B · 29 min | Samsung ↔ CLOVA | 0.165 | — | 0.861 | 3 | — | — | — |
| | **Qwen3-ASR 1.7B + aligner + Nemotron 3** | 0.176 | 0.153 | 0.905 | 3 | 100% | 0.114 | 4.7 GB |
| | MOSS, one pass | 0.172 | 0.152 | 0.930 | 3 | 100% | 0.360 | 3.5 GB |
| | MOSS, 10-minute chunks | 0.250 | 0.239 | 0.933 | 3 | 90% | 0.213 | 2.4 GB |
| | Whisper large-v3 turbo + Nemotron 3 | 0.210 | 0.174 | 0.913 | 3 | 94% | 0.081 | 2.3 GB |
| C · 42 min | Samsung ↔ CLOVA | 0.211 | — | 0.838 | 4 vs 7 | — | — | — |
| | **Qwen3-ASR 1.7B + aligner + Nemotron 3** | 0.224 | 0.184 | 0.780 | 7 | 99% | 0.119 | 4.9 GB |
| | MOSS, 10-minute chunks | 0.219 | 0.183 | 0.788 | 7 | 96% | 0.167 | 2.4 GB |
| | Whisper large-v3 turbo + Nemotron 3 | 0.276 | 0.224 | 0.782 | 7 | 91% | 0.086 | 2.5 GB |
| D · 56 min | Samsung ↔ CLOVA | 0.175 | — | 0.900 | 4 vs 5 | — | — | — |
| | **Qwen3-ASR 1.7B + aligner + Nemotron 3** | 0.187 | 0.174 | 0.938 | 4 | 98% | 0.111 | 5.1 GB |
| | MOSS, 10-minute chunks | 0.195 | 0.177 | 0.939 | 5 | 97% | 0.148 | 2.5 GB |
| | Whisper large-v3 turbo + Nemotron 3 | 0.257 | 0.227 | 0.947 | 4 | 91% | 0.084 | 2.6 GB |

Findings:
- **Qwen3-ASR + ForcedAligner + Nemotron 3** is the steadiest: on all four recordings its distance to
  the services is close to the services' distance to each other, and it never skips audio. One hour
  of audio takes about 7 minutes; peak memory is 5.1 GB. This is the pipeline's primary transcriber.
- MOSS-Transcribe-Diarize is the most accurate on short recordings in one pass but slows down with
  length (RTF 0.36 at 29 minutes), and chunking it skipped up to 10% of the audio.
- Whisper large-v3 turbo is the fastest but last on all four recordings and drops 6–9% of the text.
  The pipeline uses it only as a second hypothesis for correction.
- Nemotron 3 diarization costs about 15 seconds per hour of audio and 0.5–0.9 GB.
- Meetings with many speakers are hard for everyone: on C every candidate's speaker agreement drops
  to ~0.78, and the two services disagree on the speaker count (4 vs 7).

## Correction with a subscription CLI (two 5-minute clips)

The local transcript is sent as speaker turns with the instruction to fix only misheard words and
spacing, keep lines, speakers and times, and add or remove nothing. "+ X" means the transcript of a
second recognizer was included as a hint.

| Correction | Clip 1: CER vs Samsung / CLOVA | Clip 2: CER vs Samsung / CLOVA |
|---|---|---|
| None (Qwen3-ASR) | 0.161 / 0.155 | 0.208 / 0.178 |
| Codex | 0.167 / 0.141 | 0.207 / 0.166 |
| Gemini 3.8 Flash | 0.162 / 0.140 | 0.206 / 0.164 |
| Gemini 4 Argon | 0.164 / 0.142 | 0.203 / 0.161 |
| Codex + MOSS | 0.160 / 0.135 | 0.200 / 0.159 |
| Gemini 4 Argon + MOSS | 0.156 / 0.120 | 0.197 / 0.152 |
| Gemini 4 Argon + Whisper turbo | 0.157 / 0.133 | 0.193 / 0.152 |
| Reference: Samsung ↔ CLOVA | 0.148 | 0.205 |

Correction never dropped or merged lines. Context-only correction improves CER vs CLOVA by 1–2
points; adding a second recognizer's transcript improves it by another ~1 point, which is why the
pipeline runs Whisper turbo as a second pass. Improvements against the Samsung reference are smaller
(0–1 point), so part of the gain may be convergence toward CLOVA's spelling conventions.

## End-to-end time

A 35.4-minute recording on the Mac mini M4, 2026-11-06, from the job's start to the written note:

| Stage | Time |
|---|---|
| Convert + diarize (Nemotron 3) | 19 s |
| Transcribe (Qwen3-ASR + aligner) | 260 s |
| Second pass (Whisper turbo) | 190 s |
| Correction (Codex, 405 turns in 7 calls) | 283 s |
| Classification + summary (Codex) | 56 s |
| **Total** | **808 s (13.5 min)** |

Not measured: absolute accuracy against a human transcript, summary quality, other Macs.
