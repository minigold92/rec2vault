# demo-meeting: 가상 회의 한 건을 실제 파이프라인으로 돌린 기록

> 이 폴더의 음성은 **합성 음성**(macOS `say`)이고 사람이 아닙니다. 각 단계가 무엇을 만들고 어디서 틀리는지 보여 줄 뿐
> 실제 회의 성능을 뜻하지 않습니다. 표본은 한 건이고 실행도 한 건입니다. 이 파일들을 인용해 설명하는 문서는
> [`docs/how-it-works.ko.md`](../../how-it-works.ko.md)입니다.

## 무엇이 어디에 있나

| 경로 | 내용 | 만든 단계 |
|---|---|---|
| `scripts/script.md` | 대본 20줄, 화자 3명. 정답지 | 사람이 작성 |
| `scripts/make_audio.py` | 대본 → `say` 음성 합성, 0.7초 간격으로 결합, AAC 인코딩 | 사람이 작성 |
| `음성 261110_100000.m4a` | 입력. AAC 48 kHz 모노, 157.3초 | `say` + ffmpeg |
| `settings.toml` | 실행에서 바꾼 설정 전부 | 사람이 작성 |
| `work/diarize.json` | 화자 분리: 구간 51개, 라벨 0~2 | `diarize` |
| `work/detect_language.json` | 언어 투표(`ko`, decided) | `detect_language` |
| `work/transcribe.json` | 단어 233개와 시각(Qwen3-ASR + aligner) | `transcribe` |
| `work/second_pass.json` | 단어 225개와 시각(Whisper large-v3 turbo) | `second_pass` |
| `work/turns.json` | 화자 발언 16개 | `turns` |
| `work/correct.json` | 발언별 교정 텍스트 | `correct`(Codex CLI) |
| `work/classify.json` | 제목·유형·주제·화자 | `classify`(Codex CLI) |
| `work/summarize.json` | `[t4]` 근거가 붙은 요약 Markdown | `summarize`(Codex CLI) |
| `work/note.json` | 노트를 쓴 위치, 검토 사유 | `note` |
| `work/pipeline.log` | 세 번의 실행 로그(단계별 시간) | executor |
| `notes/2026-11-10_…_논의_1000.md` | 완성된 Obsidian 노트 | `note` |
| `notes/회의록-v2.base` | 엔진이 노트 옆에 만드는 Obsidian Bases 보기 | `note` |

뺀 것: `audio.wav`(16 kHz 변환본, 5 MB), 입력 해시와 설정을 적은 `*.meta.json`, `run-settings.json`, `state.sqlite3`.
실제 작업 폴더에서는 단계 파일이 `language.json`, `asr.json`, `alt.json`, `corrected.json`, `classification.json`,
`summary.json`이고 여기서는 단계 이름을 붙였습니다. `note.json`과 `pipeline.log` 안의 절대 경로는 `<root>`로
바꿨고 그 밖에는 손대지 않았습니다.

## 어떻게 돌렸나

빈 작업 폴더(root)의 `inbox/`에 m4a를 넣고 `python -m quietclerk.tick`을 돌렸습니다. `settings.toml`은 짧은 데모에 맞게
기준을 낮추고(`min_duration_sec = 60`, `stable_sec = 0`, `since = "2026-01-01 00:00"`), 언어를 정하고, Codex CLI를 빠른
모드로 선택하며 `transcript`·`source_name`·`project_list`에 동의한다는 것만 적습니다. Apple M3 Max Mac에서 돌렸습니다.

`work/pipeline.log`에는 같은 작업의 실행이 세 번 있습니다.

1. **첫 실행**, 157초 분량에 66초: `convert 0초 · diarize 2초 · detect_language 4초 · transcribe 9초 · second_pass 6초 · turns 0초 · correct 16초 · classify 13초 · summarize 15초 · note 0초`.
2. **분류·요약 프롬프트를 고친 뒤 재실행**, 26초: 앞 일곱 단계는 `reused`, `classify` 13초와 `summarize` 13초만 다시 돌았습니다.
   노트는 같은 `job_id`로 찾아 갱신했습니다. 이 재실행 결과(`classify.json`, `summarize.json`)가 폴더에 있습니다.
3. **노트 다시 게시**, 0초: 보관함에서 노트를 지우고 저장된 결과로 다시 썼습니다. LLM 호출은 없습니다.

`no Syncthing folder contains <root>/notes` 경고는 정상입니다. 임시 폴더가 Syncthing 폴더가 아니라 쓰기 뒤 재스캔을 건너뛴 것입니다.
LLM 호출은 `correct` 1회(`correct.json`의 처리 기록 `correct 0-15: codex`), `classify`와 `summarize`는 각 2회(첫 실행과 재실행)입니다.
교정과 받아쓰기는 첫 실행의 것이고 재실행에서 바뀌지 않았습니다.

## 대본 대비 결과

정답지는 `scripts/script.md`입니다. 아래는 파일을 읽고 비교한 것이며, 글자 오류 수만 스크립트로 셌습니다(공백·문장부호를
지우고 「38퍼센트」=「38%」, 「에이피아이」=「API」로 맞춘 677자에 대한 편집 거리).

**받아쓰기 글자 오류**

| 대상 | 틀린 글자 | 비율 |
|---|---|---|
| Qwen3-ASR(`transcribe.json`) | 63 | 9.3% |
| Whisper turbo(`second_pass.json`) | 17 | 2.5% |
| 교정 후(`correct.json`) | 7 | 1.0% |

이 한 건에서는 2차 받아쓰기(Whisper)가 주 받아쓰기보다 정확했습니다. 일반화할 수 없습니다. 교정 후 남은 7자는
문태오→**문채호**(자기소개, 2자), 문태오→**태호**(마지막 호명, 1자), 시안은→**기한은**(11번 발언, 2자), 「넣어 볼게요」→「넣을게요」(말투, 2자)입니다.

**화자 분리 (줄 단위로 읽고 비교)**: `S1`=한다온, `S2`=오지안, `S3`=문태오. 대본 20줄이 발언 16개가 됐습니다.

| 결과 | 대본 줄 |
|---|---|
| 화자가 맞음 | 1, 2, 4, 5, 6, 7, 9, 11, 12, 13, 14, 16, 17, 18번(14줄) |
| 경계가 밀림 | 8번(첫 단어 「저도」가 앞 발언에), 10번(끝 「있을지는 아직 못 정했어요」가 사회자 발언에), 20번(첫 단어 「할」이 앞 발언에) |
| 줄 전체가 오지안으로 | 3번(문태오 자기소개, 오지안 발언 `t2`에 합쳐짐), 15번(푸시 알림 질문, `t13` 끝), 19번(「알겠습니다」, `t15`) |

문태오의 5줄 중 3줄이 통째로 틀렸습니다. 이 결과는 합성 음성에서 실제로 나온 것이고 고치지 않았습니다.

**심어 둔 것**

| 심어 둔 것 | 결과 |
|---|---|
| 결정: 홈 화면 첫 칸을 내 대출 현황으로, 연장 버튼 포함. 푸시 알림·온보딩 제외 | 잡음. `## 결정 사항` 두 항목 |
| 할 일: 오지안, 다음 주 금요일까지 시안 | 잡음. 「다음 주 금요일」은 날짜로 바꾸지 않음 |
| 할 일: 문태오, 응답 시간 측정, 기한 미정 | 잡음. 기한을 지어내지 않았고 `## 미해결`에도 올라감. 단 **담당이 이름이 아니라 `S3, 실명 확인 필요`** |
| 수치 38% | 잡음(핵심 요약) |
| 오지안 소개 | 잡음. `S2`에 이름이 붙음(실제로 `S2`가 오지안) |
| 오인식 후보 | 책마루·API·피그마·온보딩·푸시 알림은 최종 텍스트에서 맞음. 「책마루」는 ASR이 맞혔고 Whisper는 「랩책마루」 |

**틀린 것**

- 문태오의 이름: 「문채호」, 「태호」(위). 노트의 `## 확인 필요`에서 「S3의 실명과 문채호와의 관계는 확인되지 않는다」고 스스로 적었습니다.
- 11번 발언의 「기한은」(대본은 「시안은」). ASR 원문은 「귀하는」, Whisper는 「기한」이었고 교정이 따라갔습니다.
- 화자 합침: 위 표. 노트의 `## 확인 필요`는 `t2`(오지안과 문태오 자기소개가 `S2`에)와 `t9`~`t10`(문태오 문장 끝이 사회자 발언에)을
  짚었지만, 15번·19번 줄이 오지안으로 들어간 것과 8번의 「저도」는 표시하지 못했습니다. `classify`는 `S1`·`S2`에
  `split_suspect: true`를 줬고 `S3`는 `false`입니다.

## 검증 수준

- **합성 입력으로 실행**: 예. 파이프라인 전 단계를 오류 없이 한 번에, 이어서 두 번 재실행.
- **알려진 대본과 비교**: 예. 위 표.
- **실제 녹음으로 확인**: 아니요. 이 폴더는 화자마다 합성 목소리 하나입니다. 실제 녹음은 [`docs/benchmark.md`](../../benchmark.md)(한국어 회의 4건)가 다룹니다.
- **확인하지 않은 것**: 다른 합성 목소리, 같은 파일 반복 실행(재실행은 분류·요약만), 사람 목소리.
