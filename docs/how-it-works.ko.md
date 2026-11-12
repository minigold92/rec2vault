# QuietClerk는 어떻게 동작하나

가상의 회의 한 건이 폰에서 완성된 노트가 되기까지를 따라갑니다. 단계마다 무엇을 받아 무엇을 내는지, 왜 그렇게
만들었는지를 보여 줍니다. 아래 발췌는 모두 현재 코드가 만든 [`examples/demo-meeting/`](examples/demo-meeting/)의
파일에서 그대로 가져왔습니다.

[English](how-it-works.md)

> **예시에 대해.** 가상의 동네 도서관 앱 「책마루」 개편을 논의하는 2분 37초짜리 3인 회의입니다.
> 대본([`scripts/script.md`](examples/demo-meeting/scripts/script.md))은 이 문서용으로 직접 썼고 macOS `say`
> 목소리(Yuna, Eddy, Shelley)로 합성했습니다. **합성 음성은 사람이 아닙니다.** 여기서 보이는 결과는 각 단계가
> 무엇을 하는지 보여 줄 뿐, 실제 회의에서의 성능이 아닙니다. 실제 녹음 기준 성능은 [benchmark.md](benchmark.md)에
> 있습니다(영문 문서, 한국어 회의 기준). 같은 설명을 영어 회의로 한 [how-it-works.md](how-it-works.md)도 있습니다.

```mermaid
flowchart LR
  A["폰 녹음기<br/>.m4a"] -->|Syncthing| B["inbox/"]
  subgraph MAC["내 Mac: 음성은 여기서만 처리"]
    B --> C["intake<br/>끝났나? 새 파일? 5분~3시간?"]
    C --> D["convert<br/>diarize<br/>detect_language"]
    D --> E["transcribe<br/>second_pass"]
    E --> F["turns"]
  end
  subgraph CLI["텍스트만: 내 LLM CLI (예: Codex)"]
    G["correct<br/>classify<br/>summarize"]
  end
  F --> G --> H["note<br/>Obsidian 보관함"]
```

파이프라인은 Apple M3 Max Mac에서 돌렸고 **157초 분량을 66초에** 처리했습니다(`work/pipeline.log`의 첫 줄 묶음):

```
convert:done:0s diarize:done:2s detect_language:done:4s transcribe:done:9s second_pass:done:6s turns:done:0s correct:done:16s classify:done:13s summarize:done:15s note:done:0s
```

같은 로그의 나머지 두 번은 분류·요약 프롬프트를 고친 뒤의 재실행입니다. 앞 단계는 `reused`(입력과 설정이 같아서 다시 계산하지
않음)로 표시되고 `classify`·`summarize`만 13초씩 다시 돌았으며, 마지막 실행은 LLM 호출 없이 노트만 다시 썼습니다.
참고로 [benchmark.md](benchmark.md#end-to-end-time)에는 Mac mini M4에서 실제 35.4분 녹음이 808초 걸린 기록이 있습니다.
기기도 녹음도 달라서 두 값을 비교할 수는 없습니다.

## 대본에 심어 둔 것

결과는 오디오에 무엇이 들어 있는지 아는 상태에서 채점합니다.

| 심어 둔 것 | 대본 내용 |
|---|---|
| 결정 1개 | 홈 화면 첫 칸을 「내 대출 현황」으로 바꾸고 대출 연장 버튼을 그 안에 넣는다. 푸시 알림과 신규 가입자 온보딩은 이번 범위에서 제외 |
| 할 일 2개 | 오지안: 다음 주 금요일까지 홈 화면 시안 · 문태오: 대출 연장 응답 시간 측정, **기한 미정** |
| 수치 1개 | 앱 문의 중 대출 연장 관련 38% |
| 이름 | 사회자(한다온)가 오지안을 소개하고, 오지안·문태오는 직접 자기소개 |
| 오인식 후보 | 「책마루」, 「에이피아이」, 「피그마」, 「온보딩」, 「푸시 알림」 |

---

## 1. 폰에서 inbox까지

폰 녹음기가 `음성 261110_100000.m4a`(`YYMMDD_HHMMSS`, 녹음 시작 시각)를 저장하면 Syncthing이 Mac의 `inbox/` 폴더로
복사합니다. 파이프라인은 inbox를 **읽기만 합니다.** 파일을 밖으로 복사해 갈 뿐 옮기거나 이름을 바꾸거나 지우지
않습니다.

## 2. Intake: 끝난 파일인가, 새 파일인가, 열어도 안전한가

Mac에서는 백그라운드 서비스(launchd `KeepAlive`, `quietclerk.cli serve`)가 60초마다 inbox를 살펴보고 대기 중인
작업을 한 번에 하나씩 실행합니다. 이 데모는 대신 `python -m quietclerk.tick`을 한 번 돌렸습니다. 파일은 아래 검사를
모두 통과해야 **작업(job)** 이 됩니다.

| 검사 | 이유 | 이 데모 |
|---|---|---|
| 최상위 `.m4a`만. 숨김 파일·`통화*`(통화 녹음)·심볼릭 링크 제외 | 음성 녹음만 처리하고, 링크를 따라 inbox 밖으로 나가지 않음 | 통과 |
| 크기·수정 시각이 60초간 그대로 | Syncthing이 아직 쓰는 중일 수 있음 | 데모는 `stable_sec = 0` |
| `O_NOFOLLOW`로 격리 폴더에 복사, 1 GiB 이하, SHA-256 계산 | 복사 중 바뀐 파일은 무시하고 다시 시도. 해시 하나는 작업 하나(이름이 달라도) | 새 파일 |
| 헤더를 먼저 검사한 뒤 `ffprobe`. AAC 스트림 하나, 5분 ≤ 길이 ≤ 3시간 | 깨진 파일, 호주머니 녹음, 폭주 파일 건너뜀 | 데모는 `min_duration_sec = 60`, 157초 통과 |
| 설치 시각 이후 녹음(또는 `include.txt`에 적은 파일) | 폰에 있던 옛 녹음이 갑자기 처리되지 않게 | 데모는 `since = "2026-01-01 00:00"` |

통과한 파일은 `archive/<job_id>/source.m4a`로 보관됩니다. 작업 id `20261110-100000-8d21adaf`는 녹음 시각과
해시 앞 8자입니다. 정책에 걸린 파일(너무 짧음, 기준 시각 이전)은 `skipped` 작업으로 남아 나중에 처리하도록
올릴 수 있고, 깨졌거나 악의적인 파일은 거부 기록만 남습니다([7절](#7-비정상-입력과-악의-입력)).
단계가 실패하면 최대 3번까지, 시도 횟수 × 5분 간격으로 다시 시도한 뒤 `failed`로 표시합니다.

## 3. 단계별 설명

각 단계는 JSON 파일 하나를 쓰고 입력의 해시와 설정을 함께 기록합니다. 같은 작업을 다시 돌리면 입력과 설정이 같은 단계는
다시 계산하지 않고 **재사용**합니다. 파일은 [`work/`](examples/demo-meeting/work/)에 단계 이름으로 들어 있습니다.
(실제 작업 폴더에서는 `detect_language`, `transcribe`, `second_pass`, `correct`, `classify`, `summarize`가 각각
`language.json`, `asr.json`, `alt.json`, `corrected.json`, `classification.json`, `summary.json`으로 저장됩니다.)

### convert

**입력** `source.m4a` → **출력** `audio.wav`(16 kHz 모노 16비트. 예시 폴더에는 넣지 않음, 157초에 약 5 MB).
`ffmpeg`를 파일 자체만 읽도록 제한해 실행하고, 디코딩한 길이가 probe로 잰 길이와 10% 이내여야 합니다.
아래 모델은 모두 이 형식을 기대합니다.

### diarize: 누가 언제 말했나

**입력** `audio.wav` → **출력** [`diarize.json`](examples/demo-meeting/work/diarize.json)

```json
[{"start": 0.0, "end": 0.85, "speaker": "0"}, {"start": 1.09, "end": 8.52, "speaker": "0"}, {"start": 9.39, "end": 11.67, "speaker": "1"}, {"start": 12.09, "end": 17.29, "speaker": "1"}, …]
```

시간 구간 51개, 라벨은 `"0"`, `"1"`, `"2"`(이름 없음)입니다. NVIDIA Nemotron 3 Diarization(MLX)은 이름도 내용도
모릅니다. 다음 단계가 말소리 구간을 찾는 데 쓰므로 가장 먼저 돕니다.

### detect_language

**입력** `audio.wav`, `diarize.json` → **출력** [`detect_language.json`](examples/demo-meeting/work/detect_language.json)

```json
{"status": "decided", "top": "ko", "shares": {"ko": 1.0}, "windows": [{"start": 1.09, "end": 8.52}, …
```

녹음 전체에 고르게 퍼진 말소리 구간 최대 6곳(각 20초 이하)을 Whisper가 판별해 길이로 가중 투표합니다. 말소리가 15초
이상이고 한 언어가 60% 이상일 때만 `decided`이고, 아니면 노트에 표시가 붙습니다. 결과는 이후 모든 단계(LLM 프롬프트
포함)의 언어를 정합니다. 설정에서 언어를 고정하면 이 단계는 건너뜁니다.

### transcribe: 무슨 말을, 단어별 시각과 함께

**입력** `audio.wav`, `detect_language.json` → **출력** [`transcribe.json`](examples/demo-meeting/work/transcribe.json)(단어 233개)

```json
[{"start": 0.0, "end": 1.12, "text": "안녕하세요"}, {"start": 1.12, "end": 1.44, "text": "동네"}, {"start": 1.44, "end": 2.0, "text": "도서관"}, …]
```

Qwen3-ASR 1.7B(8비트)가 최대 60초 조각으로 받아쓰고, Qwen3-ForcedAligner 0.6B가 단어마다 말한 시각을 찾습니다.
단어 시각이 있어야 다음 단계의 화자 매칭과 노트의 클릭 가능한 근거 링크가 가능합니다. 이 합성 음성에서는 주 받아쓰기가
상당히 틀렸습니다. 예를 들어 `{"start": 59.8696875, "end": 60.2696875, "text": "저도"}, {"start": 60.5896875, "end": 60.9896875, "text": "찾아보"}`
에서 대본의 「좋다고」가 「찾아보」가 됐습니다.

### second_pass: 두 번째 의견

**입력** `audio.wav`, `detect_language.json` → **출력** [`second_pass.json`](examples/demo-meeting/work/second_pass.json)(단어 225개)

```json
[{"start": 0.0, "end": 0.52, "text": "안녕하세요."}, {"start": 0.92, "end": 1.42, "text": "동네"}, {"start": 1.42, "end": 1.96, "text": "도서관"}, …
```

Whisper large-v3 turbo가 같은 오디오를 독립적으로 받아씁니다. **이 결과는 대화록이 되지 않습니다.** 교정 단계에 힌트로만
넘어갑니다. 인식기 두 개는 같은 곳에서 틀리지 않는 경우가 많기 때문입니다. 책마루는 Qwen이 맞혔고 Whisper는
`{"start": 1.96, "end": 2.6, "text": "랩책마루"}`로 틀렸습니다. 반대로 위의 「찾아보」 구간은 Whisper가
`저도 좋다고 생각합니다. 다만 연장 버튼을 눌렀을 때 API 응답이 누르면 사용자가 여러 번 누를 수 있어요.`
로 훨씬 가깝게 들었습니다. 한쪽이 틀린 곳을 다른 쪽이 메우는 것이 이 단계의 목적입니다.

### turns: 단어와 목소리 합치기

**입력** `transcribe.json`, `diarize.json` → **출력** [`turns.json`](examples/demo-meeting/work/turns.json)

```json
{"start": 0.0, "end": 8.48, "speaker": "S1", "text": "안녕하세요 동네 도서관 앱 책마루 개편 회의를 시작하겠습니다 오늘은 디자인을 맡고 계신 오지안 님이 함께 해주셨습니다"}
{"start": 9.36, "end": 22.16, "speaker": "S2", "text": "안녕하세요 오지안입니다 오늘은 홈 화면을 어떻게 바꿀지 먼저 말씀드리려고 합니다 안녕하세요 소보르 맡고 있는 문체오입니다"}
```

모델 없이 코드만 씁니다(`quietclerk/transcript.py`). 단어마다 겹치는 시간이 가장 긴 화자를 붙이고, 같은 화자의
단어는 1.5초 이상 쉬지 않는 한 한 **발언(turn)** 으로 묶으며, 라벨은 처음 나온 순서대로 `S1`, `S2`, …가 됩니다.
이후 모든 단계와 노트의 `t1`, `t2`, …가 이 발언입니다.

**여기가 이 단계의 실패 지점입니다.** 대본 20줄이 발언 16개가 됐고, 두 사람이 한 화자로 합쳐졌습니다. 위의 `S2` 발언은
오지안(대본 2번)과 문태오(3번 「안녕하세요, 서버를 맡고 있는 문태오입니다」)의 자기소개를 한 발언으로 담고 있습니다.
화자 분리가 문태오의 목소리를 오지안의 라벨에 붙였기 때문입니다.

발언 텍스트를 대본과 줄 단위로 맞춰 보면(문자 단위가 아니라 사람이 읽고 비교) 화자는 이렇게 나왔습니다.
`S1`=한다온, `S2`=오지안, `S3`=문태오입니다.

| 결과 | 대본 줄 | 설명 |
|---|---|---|
| 맞음 14줄 | 1·2·4·5·6·7·9·11·12·13·14·16·17·18번 | |
| 경계가 밀림 3줄 | 8번, 10번, 20번 | 8번 첫 단어 「저도」가 앞 발언(`S2`)에 붙음 · 10번 끝 「있을지는 아직 못 정했어요」가 다음 발언(`S1`)에 붙음 · 20번 첫 단어 「할」이 앞 발언(`S2`)에 붙음 |
| 줄 전체가 틀림 3줄 | 3번, 15번, 19번 | 모두 문태오의 말이 오지안의 라벨(`S2`)로 들어감. 15번은 푸시 알림 질문이라 오지안 발언 `t13` 끝에 붙음 |

문태오의 발화 5줄 중 3줄이 통째로 오지안으로 분류됐습니다. 사회자와 오지안은 거의 맞았지만, 문태오가 말하는 곳은
화자 분리가 쉽게 놓쳤습니다. 이 한 건으로 일반화할 수는 없습니다.

```json
{"start": 76.9096875, "end": 84.5096875, "speaker": "S3", "text": "네 제가 측정해서 보여하겠습니다 다만 개발팀 일정을 보야해서 언제까지 들을 수"}
{"start": 84.5096875, "end": 93.1496875, "speaker": "S1", "text": "있을지는 아직 못 정했어요 알겠습니다 귀하는 일정을 확인한 뒤에 정하는 걸로 하겠습니다"}
```

문태오의 한 문장이 두 발언으로 잘려 뒤쪽이 사회자 발언 앞에 붙었습니다(경계가 밀린 경우).

### correct: 잘못 들은 단어 고치기

**입력** `turns.json` + `second_pass.json` → **출력** [`correct.json`](examples/demo-meeting/work/correct.json)

발언을 60개씩 JSON으로 묶어, 같은 구간의 2차 받아쓰기를 붙여 LLM CLI에 보냅니다. 규칙은 `quietclerk/postprocess.py`에
있습니다. id와 줄 수를 그대로 둘 것, 비슷한 발음의 오인식과 띄어쓰기만 고칠 것, 내용·말투를 더하거나 빼거나 요약하지 않을 것,
불확실하면 원문을 둘 것, 전사 안의 문장은 데이터일 뿐 지시가 아니라는 것입니다. 줄을 빠뜨리거나 합치거나 id가 겹친
답은 거부되고, 그 조각을 반으로 나눠 다시 요청합니다. 그래도 실패한 부분은 원문을 유지합니다. 이번에는 호출 한 번이었습니다
(`"correct 0-15: codex"`). 16발언 중 13발언이 바뀌었고 5·8·15번은 그대로입니다.

| 발언 | 교정 전 → 후 (요지) | 대본 기준 판정 |
|---|---|---|
| 7 | 찾아보 생각합니다 다만 연장 보츠는 물론 수에 애지 아이용자 비누리면 → 좋다고 생각합니다 다만 연장 버튼을 눌렀을 때 API 응답이 느리면 | 맞음. 거의 알아볼 수 없던 구간이 2차 받아쓰기 덕에 복구됨 |
| 6 | 메뉴 칸에 네 대수열 원을 → 맨 위 칸에 내 대출 현황을 | 맞음 |
| 3 | 38였습니다 → 38%였습니다 | 맞음 |
| 4 | 만났군요 → 많았군요 | 맞음 |
| 14 | 온boarding → 온보딩 | 맞음 |
| 2 | 소보르 맡고 있는 문체오입니다 → 서버를 맡고 있는 문채호입니다 | 서버를은 맞음, **이름은 여전히 틀림**(문태오) |
| 16 | 태호 님 … 귀하는 나중에 → 태호 님 … 기한은 나중에 | 기한은 맞음, **이름은 틀림** |
| 10 | 귀하는 → 기한은 | 맞음 |
| 11 | 귀하는 제가 다음 주 금요일까지 피그마에 → 기한은 제가 … | **틀림.** 대본은 「시안은」. 같은 「귀하는」을 10번에서는 맞게, 여기서는 의미가 바뀌게 고침 |

표에 없는 1번(「함께 해주셨습니다」→「함께해 주셨습니다」), 9번, 12번, 13번도 바뀌었습니다. 9·12·13번은 대본과 맞게
고쳤고, 1번은 띄어쓰기만 바뀌었습니다.

대본 677자(공백·문장부호 제외, 「38퍼센트」=「38%」, 「에이피아이」=「API」로 맞춤)와 편집 거리로 비교하면 주 받아쓰기는
**63자 틀림(9.3%)**, 2차 받아쓰기는 17자(2.5%), **교정 후는 7자(1.0%)** 입니다. 남은 7자는 문태오→문채호(2자),
시안은→기한은(2자), 「넣어 볼게요」→「넣을게요」(2자, 뜻 유지), 태오→태호(1자)입니다. 교정은 LLM이 문맥으로 추측하는
것이라 말이 안 되는 곳은 잘 고치지만, 틀린 단어를 자신 있게 써 넣기도 합니다. 이름이 가장 어렵습니다.

### classify: 유형, 제목, 화자

**입력** `correct.json` + 원본 파일 이름 + 보관함에 이미 있는 프로젝트 이름 → **출력**
[`classify.json`](examples/demo-meeting/work/classify.json)

```json
"title": "책마루 홈 화면 개편과 대출 연장 기능 논의",
"type": "meeting",
"type_confidence": "high",
"type_basis_id": "t1",
"division": "work",
"project": null,
"project_suggest": "책마루 앱 개편",
"role": "홈 화면 디자인 제안 및 시안 작성, 서버 담당자 자기소개도 혼재",
"name": "오지안",
"name_id": "t2",
"split_suspect": true
```

LLM의 답을 믿지 않고 코드가 검증합니다. `type`은 정해진 목록에서만, 이름은 `name_id`가 실제 줄을 가리킬 때만, 프로젝트는
보관함 노트에 이미 있을 때만 인정하고(아니면 `project_suggest`), 제목은 8~50자여야 하며 화자 라벨이 발언과 일치해야
합니다. `split_suspect`는 모델이 하는 「한 라벨에 두 사람이 섞인 것 같다」는 표시입니다.

이번에 모델은 `S2`의 역할에 「서버 담당자 자기소개도 혼재」라고 적어 합쳐진 것을 스스로 알아챘습니다. `S2`는 실제로 합쳐진
라벨이므로 맞는 표시입니다. 같은 응답에서 `S1`도 `split_suspect: true`이고 `S3`는 `false`입니다. `S1`에는 문태오의 말
조각이 실제로 섞여 있으니 부분적으로 맞고, `S3`는 거의 문태오뿐이라 맞습니다. 이름은 `S2`의 「오지안」만 채워졌습니다(실제로
`S2`가 오지안이라 맞음). 문채호·태호가 누구인지는 모델이 `S3`에 붙이지 않았고, 이는 틀린 이름을 확정하는 것보다 낫습니다.

### summarize: 근거 줄이 붙은 요약

**입력** `correct.json`, `classify.json` → **출력** [`summarize.json`](examples/demo-meeting/work/summarize.json)

```markdown
## 결정 사항
- 홈 화면 첫 칸에 내 대출 현황을 표시하고 대출 연장 버튼을 넣는다. [t14, t15]
- 푸시 알림은 이번 개편에서 제외하고, 신규 가입자 온보딩 화면은 다음 개편으로 미룬다. [t14]

## 할 일
- [ ] 홈 화면 시안을 피그마에 올리고, 큰 글자 버전과 현재 글자 크기 버전을 포함한다. (오지안 / 다음 주 금요일) [t11, t13, t16]
- [ ] 대출 연장 API 응답 시간을 측정해 공유한다. (S3, 실명 확인 필요 / 개발팀 일정 확인 후 결정) [t8, t9, t10, t16]
```

섹션 구성은 회의 유형에 따라 다릅니다(`meeting`은 핵심 요약·안건별 논의·결정 사항·할 일·미해결·확인 필요). 프롬프트가 항목마다
`[t11]` 같은 근거 줄을 요구하고, 근거가 하나도 없는 요약은 거부합니다. 합의된 것만 결정으로, 맡거나 맡기는 말이 나온 것만
할 일로 씁니다.

### note: Markdown 파일 쓰기

**입력** `summarize.json`과 앞 단계 출력 → **출력** 보관함의 노트
`notes/2026-11-10_1000_책마루_홈_화면_개편과_대출_연장_기능_논의.md`
([예전 파일명으로 저장된 데모 사본](examples/demo-meeting/notes/2026-11-10_책마루_홈_화면_개편과_대출_연장_기능_논의_1000.md))와
[`work/note.json`](examples/demo-meeting/work/note.json)(경로·검토 사유). 이 단계는 캐시하지 않습니다. 보관함에 이미
있는 내용과 병합해야 하기 때문입니다. [5절](#5-노트)을 보세요.

## 4. 대본 대비 결과

| 심어 둔 것 | 결과 |
|---|---|
| 결정 | ✅ `## 결정 사항`에 홈 화면 첫 칸 변경과 푸시 알림·온보딩 제외가 적힘 |
| 할 일: 오지안 | ✅ `(오지안 / 다음 주 금요일)`. 「다음 주 금요일」은 날짜(11-20)로 바뀌지 않고 말 그대로 남음 |
| 할 일: 문태오, 기한 미정 | ✅ `(S3, 실명 확인 필요 / 개발팀 일정 확인 후 결정)`. 기한을 지어내지 않았고 `## 미해결`에도 올라감. **담당이 이름이 아니라 `S3`** |
| 수치 38% | ✅ 핵심 요약에 있음 |
| 이름 | ⚠️ 오지안은 맞음. **문태오는 「문채호」(자기소개)와 「태호」(마지막 호명)로 적혔고** 어느 쪽도 바로잡지 못함 |
| 고유명사·영어 용어 | ✅ 책마루·API·피그마·온보딩·푸시 알림 모두 최종 텍스트에서 맞음 |
| 화자 구분 | ❌ 위 표처럼 문태오 5줄 중 3줄이 오지안 라벨. 파이프라인은 이를 `## 확인 필요`에 스스로 적었음(아래) |
| 단어 | 「시안은」→「기한은」(11번 발언) 틀림. 노트의 할 일 문장 자체는 영향 없음 |

노트의 `## 확인 필요` 콜아웃은 실제 문제와 겹칩니다. 세 항목 모두 `t2`, `t9`~`t10`, `t16`을 가리킵니다.

```markdown
> [!warning] 확인 필요
> - S2 발언에 오지안과 서버 담당자 문채호의 자기소개가 함께 있어 화자 구분이 필요하다. [[#^t2|00:09]]
```

반대로 파이프라인이 **알아채지 못한** 것도 있습니다. 15번 줄(푸시 알림 질문)과 19번 줄(「알겠습니다」)이 오지안으로 들어간 것,
「저도」가 앞 발언에 붙은 것은 표시가 없습니다. 이 구간은 요약의 어느 항목에도 영향을 주지 않았지만, 대화록에서 누가 말했는지는
틀려 있습니다.

---

## 5. 노트

`render.py`와 `notes/`가 노트를 만들고 **원자적으로**(임시 파일, fsync, 저널, 이름 바꾸기) 씁니다. 속성 발췌입니다
([전체 노트](examples/demo-meeting/notes/2026-11-10_책마루_홈_화면_개편과_대출_연장_기능_논의_1000.md)).

```yaml
qc_schema: 2
title: 책마루 홈 화면 개편과 대출 연장 기능 논의
date: '2026-11-10'
started_at: '2026-11-10T10:00:00'
duration_min: 2.6
language: ko
type: meeting
status: draft
needs_review: true
review_reasons:
- summary_review
source_file: 음성 261110_100000.m4a
source_sha256: 8d21adaf901dbea43f82e42fa26c54ea8ccebcc835297379d9c8ab117585fa2d
job_id: 20261110-100000-8d21adaf
pipeline_llm:
- codex
external_text_to:
- codex
```

본문입니다(제목줄은 평범한 Markdown이고 숨은 주석 표식은 없습니다).

```markdown
## 할 일
- [ ] 홈 화면 시안을 피그마에 올리고, 큰 글자 버전과 현재 글자 크기 버전을 포함한다. (오지안 / 다음 주 금요일) [[#^t11|01:33]] [[#^t13|01:45]] [[#^t16|02:22]] ^task-1

## 회의 내용

> [!info] 개요
> 회의 · 2.6 분

| 화자 | 역할 | 이름 |
|---|---|---|
| S2 | 홈 화면 디자인 제안 및 시안 작성, 서버 담당자 자기소개도 혼재 | 오지안 [[#^t2\|00:09]] |

> [!summary] 핵심 요약
…
## 전체 대화록

**[00:09] S2**: 안녕하세요 오지안입니다 오늘은 홈 화면을 어떻게 바꿀지 먼저 말씀드리려고 합니다 안녕하세요 서버를 맡고 있는 문채호입니다 ^t2

## 메모
```

- **근거는 링크입니다.** `[t11]`이 `[[#^t11|01:33]]`이 되고 각 대화록 줄은 `^t11` 블록 id로 끝나므로 시각을 누르면
  그 줄로 갑니다. 가리키는 줄이 없는 근거는 `[?t999]`로 표시되고 검토 사유에 추가됩니다. 근거는 어디를 볼지를 알려 줄 뿐,
  그 문장이 맞다는 증명은 아닙니다.
- **할 일**은 자체 블록 id(`^task-1`)가 붙은 Markdown 체크박스입니다.
- **`needs_review: true`** 와 사유 `summary_review`는 요약에 `확인 필요` 절이 있어서입니다. 그 밖의 사유는 유형·언어가
  불확실한 경우, 교정 조각 실패, 없는 줄을 가리키는 근거입니다.
- **출처 기록**: 모델과 리비전(`pipeline_asr`), LLM CLI(`pipeline_llm`), 텍스트를 받은 곳(`external_text_to`), 원본 파일명과
  SHA-256이 들어가므로 노트에서 언제나 녹음을 찾아갈 수 있습니다.
- 이름은 녹음 날짜·시각이 앞서는 `YYYY-MM-DD_HHMM_제목.md`, 메모는
  `YYYY-MM-DD_HHMM_메모_제목.md`입니다. 내보내기도 같은 줄기를 씁니다. 다음 게시(완료한 작업의 이어 하기 포함) 때
  그 작업의 녹음 날짜·분과 일치하는 옛 엔진 이름만 제목 부분을 그대로 옮깁니다. 직접 정한 이름·대상 충돌은 보존합니다.
  기존 게시 저널로 중단된 prepared 이동은 원이름으로 되돌리고 renamed 이동은 새 이름으로 완료합니다.
  데일리 노트를 켰다면 링크의 옛 stem만 바꾸고 별칭·다른 줄은 바이트 그대로 둡니다.
- `notes/회의록-v2.base`는 최근/검토 대기 보기 모두 녹음 시각을
  `date(started_at).format("YYYY-MM-DD HH:mm")`으로 분까지 표시하고 `started_at` 내림차순으로 정렬합니다
  ([Bases 함수](https://help.obsidian.md/bases/functions)). 파일이 없으면 만들고, 기존 파일은 알려진 옛 엔진 템플릿과
  바이트 또는 엄격한 YAML 파싱 값이 같을 때만 갱신합니다. Obsidian이 들여쓰기·따옴표만 바꾼 경우도 갱신하지만
  뷰 추가 등 내용을 고쳤거나 파싱할 수 없는 파일은 건드리지 않습니다.

### 노트를 다시 만들어도 내 것으로 남는 것

같은 녹음을 다시 처리하면(LLM을 바꿨거나 요약을 새로 만들었을 때) 파일 이름을 바꿨더라도 `job_id`와 해시로 노트를 찾아 그 자리에서
갱신합니다.

- **엔진이 소유하는 구간은 하나**입니다. `## 회의 내용`부터 그 뒤 첫 `## 메모` 앞까지입니다. 할 일 목록에서 고친 내용, 그 구간
  밖에 적은 글, `## 메모`는 바이트 단위로 그대로 보존됩니다.
- **속성**: `project`, `attendees`, `status`는 처음부터 내 것입니다. 그 밖의 속성(예: `title`)을 고치면 엔진이 마지막으로 쓴
  값과 달라진 순간부터 내 것이 되어 다시는 덮어쓰지 않습니다.
- 새 요약이 제안하는 할 일 중 내 목록에 없는 것은 내 목록을 몰래 바꾸는 대신 엔진 구간 안의 「새로 제안된 할 일」에
  나옵니다. 이미 있는 할 일을 인용만 바뀌었다고 다시 제안하지는 않습니다.
- 모델이 쓴 글로는 경계를 위조할 수 없습니다. 모델이 쓴 `## 메모` 같은 제목은 한 단계 낮춰지고, 모델 글 안의 HTML·링크·
  이미지·블록 id는 무력화됩니다.
- 경계 제목이 없거나 둘이거나, YAML이 깨졌거나, 쓰는 순간 해시가 달라졌으면 **쓰지 않습니다.** 작업은 충돌로 보고하고
  내 파일은 그대로 남습니다.

이 데모 노트는 실제로 이 경로를 거쳤습니다. 분류·요약 프롬프트를 고친 뒤 같은 작업을 다시 돌려(`work/pipeline.log`의
두 번째 실행) 노트를 갱신했고, 노트를 보관함에서 지우고 저장된 결과로 다시 게시하기도 했습니다(세 번째 실행, LLM 호출 없음).

## 6. 밖으로 나가는 것

| 데이터 | 가는 곳 |
|---|---|
| **음성** | 폰 → 내 Mac(Syncthing). AI 서비스로는 보내지 않음 |
| 모든 발언의 텍스트(`correct`, `classify`, `summarize` 단계) | 설정한 LLM CLI(여기서는 `codex`, 즉 OpenAI) |
| 원본 파일 이름, 보관함에 이미 있는 프로젝트 이름 목록(`classify` 단계만) | 같은 CLI |
| 모델 가중치 | 설치할 때 한 번 내려받고, 실행 중에는 로컬 Hugging Face 캐시에서만 읽음 |
| 업데이트 확인(`updates.check`, 기본 켬) | 하루 한 번 설치 체크아웃에서 `git fetch`로 GitHub에 새 커밋만 물어봄. 회의 데이터·설정·회의록은 보내지 않음 |

제한하는 방법입니다.

- **제공자별·항목별 동의.** 이 데모의 `settings.toml`에는
  `"providers.consent" = {codex = ["transcript", "source_name", "project_list"]}`가 있습니다. 어떤 항목에 동의하지
  않은 제공자는 그 호출에 쓰이지 않고, 쓸 수 있는 제공자가 없으면 작업은 몰래 보내지 않고 대기(`blocked`)합니다.
- **`providers.local_only = true`** 이면 로컬 엔드포인트(`127.0.0.1`의 Ollama)만 허용하고, 외부이거나 알 수 없는 곳은 거부합니다.
- **도구 끔.** Codex는 읽기 전용 샌드박스에서 셸·웹 검색·플러그인을 끈 채 빈 임시 폴더에서 실행하고, Claude는 도구 없이 실행합니다.
  CLI가 도구 호출을 보고하면 대체 제공자 없이 그 단계를 중단합니다.
- **노트에 기록**: `external_text_to: [codex]`가 텍스트를 받은 모든 제공자(실패한 시도 포함)를 적습니다.

## 7. 비정상 입력과 악의 입력

신뢰할 수 없는 입력은 세 곳입니다. 오디오 파일, LLM이 읽는 대화록, 디스크의 노트 파일입니다. 코드가 하는 일과 그것을 확인하는
테스트(`tests/`, 모두 **생성한** 오디오와 파일을 쓰며 실제 녹음은 쓰지 않음)입니다.

| 입력 | 처리 | 테스트 |
|---|---|---|
| 평범한 `.m4a` | 처리 | `test_intake.py::test_in03_duration_boundary`(299초는 건너뜀, 300초는 대기열) |
| 아직 쓰는 중 / 커지는 중 | 대기. 커지면 60초 안정 시간이 다시 시작 | `test_in09_stability_restarts_after_growth` |
| 0바이트 파일 | 대기(한 시간 뒤 `empty_file` 표시). 나중에 커지면 수락 | `test_in08_zero_byte_waits_and_late_growth_is_accepted` |
| 같은 음성 재수신, 또는 내가 지운 음성 | 다시 처리 안 함(`duplicate`, `deleted_by_user`) | `test_in16_duplicate_and_tombstone` |
| 이름은 같고 내용이 다름 | 새 작업 | `test_in17_same_name_different_contents_creates_new_job` |
| 너무 짧음 / 기준 시각 이전 | `skipped` 작업, 나중에 올릴 수 있으며 올릴 때 원본을 다시 검증 | `test_in05_promote_revalidates_original` |
| 3시간 초과, 1 GiB 초과 | 거부. 너무 큰 파일은 읽지도 해시하지도 probe하지도 않음 | `test_in14_invalid_probe_lengths`, `test_in13_sparse_oversized_file_never_hashed_or_probed` |
| 잘린 파일, `.m4a`로 위장한 비-MP4, AAC가 아닌 코덱 | 거부(`decode`, `format`, `codec`), 작업 없음 | `test_in10_…`, `test_in11_disguised_format_and_unsupported_codec` |
| 다른 곳을 가리키는 컨테이너(HLS 재생목록, ffconcat 목록, `http`·`file`·`urn` 데이터 참조가 든 MP4) | **디먹서가 실행되기 전에** `format`으로 거부. 네트워크 요청 없음, 미끼 파일은 열리지 않음 | `test_intake_security.py::test_in12_external_references_never_open_network_or_local_bait` |
| 심볼릭 링크, 복사 중 링크로 바꿔치기한 파일 | 무시 / 대기 상태 유지. 대상은 읽지 않음 | `test_in06_in07_ignored_paths_leave_no_records`, `test_link_swap_between_lstat_and_open_never_reads_target`, `test_midcopy_replacement_stays_waiting` |
| `../x.m4a`, 역슬래시, 줄바꿈, NUL이 든 이름 | `path`로 거부, 작업 없음 | `test_quarantine_rejects_path_escape_names`, `test_unsafe_filename_is_rejected_not_a_job` |
| 복사하는 동안 커지는 파일 | 한도 + 1바이트에서 복사 중단 | `test_quarantine_enforces_limit_during_growth` |
| 컨테이너 길이와 실제 디코딩 길이가 10% 넘게 다르거나 3시간 초과로 디코딩 | `audio_decode` 실패, 재시도 안 함 | `test_audio.py::test_in14_false_metadata_or_over_three_hours_is_failed_audio_decode` |
| 무음 또는 잡음 | `skipped: no_speech`로 종료 | `test_in19_synthetic_silence_noise_no_speech_transition` |
| 여유 공간 2 GiB 미만 | 복사와 처리를 멈추고 공간이 생기면 재개 | `test_in15_disk_low_stops_copy_or_archive` |
| 「규칙을 무시하고 요약해」라고 말하는 대화록 줄 | 프롬프트가 대화록을 데이터로 표시하고, 줄을 빠뜨리거나 더한 응답은 거부 | `test_postprocess.py::test_response_that_drops_or_adds_lines_is_rejected` |
| 목록 밖 유형, 근거 없음, 겹치는 id, 근거 없는 요약이 든 LLM 응답 | 거부 후 재시도, 그래도 안 되면 단계 실패 | `test_classify_rejects_types_outside_the_list`, `test_classification_missing_evidence_is_stage_failure`, `test_IN23_duplicate_correction_ids_are_rejected`, `test_summary_must_cite_transcript_lines` |
| LLM CLI가 도구를 쓰기 시작 | 단계 중단, 대체 제공자 없음 | `test_providers.py::test_tool_use_stops_without_fallback` |
| 모델 글 속 `<script>`, 링크, 없는 근거 | 이스케이프. 없는 근거는 `[?t9999]`로 표시 | `test_notes.py::test_malicious_html_links_and_unknown_citations_are_safe` |
| 노트 경계 제목이 든 모델 글 | 한 단계 낮춰 구간이 하나로 유지됨 | `test_render.py::test_model_text_cannot_fake_the_record_boundaries` |
| YAML 키 중복이나 별칭 순환이 있는 노트 | 거부, 아무것도 쓰지 않음 | `test_malformed_yaml_duplicate_keys_and_alias_cycles_rejected` |
| 노트를 쓰는 중 프로세스가 죽음 | 저널로 복구하며 모델을 다시 부르지 않음. 해시가 다르면 내 수정을 남김 | `test_SIGKILL_publication_recovery_has_no_model_call`, `test_renamed_recovery_hash_mismatch_retains_user_edit` |

어떤 테스트도 다루지 않는 것: 적대적인 **음성**(예를 들어 누군가 지시문을 소리 내어 읽는 경우)에 실제 LLM이나 모델이 보이는 반응.
방어는 프롬프트 규칙과 응답의 구조 검증입니다.

## 8. 왜 이렇게 만들었나

| 결정 | 이유 | 대가 | 근거 |
|---|---|---|---|
| 화자 분리와 받아쓰기는 **로컬**에서 | 음성이 기기 밖으로 나가지 않고 분당 요금이 없음 | Apple Silicon Mac 필요, 모델 가중치 약 5 GB | 최대 메모리 5.1 GB, 한 시간 분량 약 7분([benchmark](benchmark.md#full-recordings)) |
| Qwen3-ASR + aligner를 대화록으로 | 로컬 후보 중 가장 안정적이고 실제 한국어 회의 4건에서 오디오를 건너뛴 적이 없으며 단어 시각을 줌 | Whisper보다 느림 | [benchmark](benchmark.md#full-recordings) |
| Whisper turbo는 **힌트로만** | 가장 빠르지만 네 녹음 모두 꼴찌이고 텍스트의 6~9%를 빠뜨림 | 오디오를 한 번 더 처리 | [benchmark](benchmark.md#full-recordings) |
| LLM 교정은 텍스트만, 2차 받아쓰기를 붙여서 | 문맥만 준 교정은 CLOVA 대비 문자 오류율을 1~2포인트, 2차 인식기까지 주면 약 1포인트 더 낮춤 | 텍스트가 기기 밖으로 나감. 맞는 단어를 바꾸기도 함 | [benchmark](benchmark.md#correction-with-a-subscription-cli-two-5-minute-clips)(5분 구간 2개) |
| 발언 60개씩 호출, 나쁜 응답이면 반으로 쪼개 재시도 | 긴 입력은 줄이 합쳐져 돌아오는 일이 있고, 나쁜 조각은 그 조각의 교정만 잃음 | 호출이 늘어남 | `quietclerk/postprocess.py`, 테스트 `test_large_chunk_that_keeps_failing_is_retried_in_halves` |
| 화자는 `S1`, `S2`…로 두고 이름에는 들은 곳 링크를 붙임 | 화자 분리가 사람을 합치거나 쪼갤 수 있고 이름은 추측 | 이름은 직접 고침 | 위 3절의 turns·4절 |
| 단계마다 JSON 하나, 입력 해시와 설정으로 캐시 | 중간에 죽어도 실패한 단계부터 재개하고, 요약 프롬프트만 바꾸면 앞 단계를 재사용 | 디스크 공간 | `work/pipeline.log`의 `reused` 표시 |
| API 키 대신 구독 CLI | 이미 내는 요금제를 씀 | CLI의 지원 버전에 의존(Codex 0.163~0.167만 검증됨, 그 밖은 허용하지 않으면 거부) | `quietclerk/providers/cli.py` |

어디에서도 측정하지 않은 것: 영어 정확도, 요약 품질, 다른 Mac에서의 속도, 사람이 만든 정답 대비 절대 정확도.

## 9. 무엇을 어떻게 확인했나

| 수준 | 내용 |
|---|---|
| **합성 입력으로 실행** | 이 파일(과 영어 파일) 하나로 파이프라인을 끝까지 돌림. 문서의 시간과 출력은 그 실행 결과 |
| **알려진 대본과 비교** | 심어 둔 결정·할 일·수치·이름, 화자 배정, 글자 차이: 4절과 3절 |
| **실제 녹음으로 확인** | 이 문서에서는 하지 않음. [benchmark.md](benchmark.md): 실제 한국어 회의 4건(18~56분, git에서 제외된 `samples/`에 로컬 보관, 비공개)과 35분 녹음 종단 실행 1회 |
| **비정상·악의 입력** | 7절의 단위 테스트. 생성한 파일만 사용했고 실제로 깨진 녹음은 쓰지 않음 |
