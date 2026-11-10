---
qc_schema: 2
title: Arbor Bikes App First-Screen Review
aliases:
- Arbor Bikes App First-Screen Review
- Recording 261112_140000
date: '2026-11-12'
started_at: '2026-11-12T14:00:00'
duration_min: 1.5
language: en
language_detected: en
type: meeting
division: work
topics:
- Moving ride passes to the first screen
- Displaying the active pass with a renew button
- Support tickets about buying and renewing ride passes
- Measuring unlock API latency
- Mockups due next Thursday
project:
- unassigned
project_suggest: Arbor Bikes app
attendees: []
speakers:
- 'S1: Meeting facilitator'
- 'S2: Priya · Design representative'
- 'S3: Leo · Backend representative'
speaker_count: 3
status: draft
needs_review: true
review_reasons:
- summary_review
source_file: Recording 261112_140000.m4a
source_sha256: 66bb249562015d787ecfd2858a310836ca180fff9edcab2b00dbd1c13094582d
job_id: 20261112-140000-66bb2495
pipeline_asr:
- mlx-community/Qwen3-ASR-1.7B-8bit@a8379a2e2f9e313c9292cdf1af4055ab56d50d55
- mlx-community/Qwen3-ForcedAligner-0.6B-8bit@0e1a68e91d815300c7c9754b2a7639378b23db15
- mlx-community/whisper-large-v3-turbo@a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb
pipeline_llm:
- codex
external_text_to:
- codex
processed_at: '2026-11-10T11:20:34'
tags:
- meeting-notes
---
## Tasks
- [ ] Measure unlock API latency and share the results (Leo / deadline to be set after checking the sprint). [[#^t10|00:53]] [[#^t11|01:02]] ^task-1
- [ ] Prepare mockups (Priya / next Thursday). [[#^t12|01:06]] ^task-2

## Meeting record

> [!info] Overview
> Meeting · 1.5 min

| Speaker | Role | Name |
|---|---|---|
| S1 | Meeting facilitator |  |
| S2 | Design representative | Priya [[#^t2\|00:07]] |
| S3 | Backend representative | Leo [[#^t3\|00:11]] |

> [!summary] Key summary
>
> - Buying or renewing ride passes accounted for 41% of support tickets last quarter; the pass button is currently two menu levels deep. [[#^t4|00:15]] [[#^t5|00:24]]
> - Ride passes will move to the first screen, and the referral program will stay out of this release. [[#^t13|01:09]] [[#^t14|01:17]] [[#^t15|01:18]]
> - Leo will measure and share unlock API latency; Priya will prepare mockups by next Thursday. [[#^t10|00:53]] [[#^t12|01:06]]
> - Whether to retain the old map view for older phones remains open for discussion next week. [[#^t15|01:18]] [[#^t16|01:24]]

## Agenda

- Review the Arbor Bikes app’s new first screen and whether ride passes should move there. [[#^t1|00:00]] [[#^t2|00:07]] [[#^t6|00:30]]

## Decisions

- Move ride passes to the first screen. [[#^t13|01:09]] [[#^t14|01:17]] [[#^t15|01:18]]
- Exclude the referral program from this release. [[#^t13|01:09]] [[#^t14|01:17]] [[#^t15|01:18]]

## Open issues

- Whether to keep the old map view for older phones; revisit next week. [[#^t15|01:18]] [[#^t16|01:24]]

> [!warning] Review needed
>
> - Leo reported current median bike-unlocking time as 2.3 seconds and said users tap twice when it is slow; proper measurement is pending. [[#^t8|00:39]] [[#^t9|00:49]] [[#^t10|00:53]]

## Full transcript

> AI transcript draft. Speaker labels are not real names.

**[00:00] S1**: Hi everyone Let's start the Arbor Bikes app review Priya from Design is joining us today ^t1

**[00:07] S2**: Hi I'm Priya I'd like to walk through the new first screen ^t2

**[00:11] S3**: Hi Leo here I look after the backend ^t3

**[00:15] S1**: Some background first Over the last quarter forty-one percent of support tickets were about buying or renewing ride passes ^t4

**[00:24] S2**: That matches what we see in testing The pass button is hidden two levels deep in the menu ^t5

**[00:30] S1**: So the question is whether ride passes should move to the first screen ^t6

**[00:34] S2**: I'd say yes Show the active pass at the top with a renew button right there ^t7

**[00:39] S3**: I agree One concern though Unlocking a bike currently takes two point three seconds Seconds at the median and people tap twice when it's slow ^t8

**[00:49] S1**: Can you measure that properly before we commit to a design ^t9

**[00:53] S3**: Sure I'll measure the unlock API latency and share it I can't promise a date yet I need to check the sprint first ^t10

**[01:02] S1**: Fine we'll set the deadline once you've checked ^t11

**[01:06] S2**: I'll have the mockups ready by next Thursday ^t12

**[01:09] S1**: Great So we agree Passes move to the first screen and the referral program stays out of this release ^t13

**[01:17] S3**: Agreed ^t14

**[01:18] S2**: Agreed One thing we haven't settled is whether to keep the old map view for older phones ^t15

**[01:24] S1**: Let's leave that open and revisit it next week Thanks everyone ^t16

## Notes
