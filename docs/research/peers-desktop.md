# 데스크톱 회의 앱에서 QuietClerk로 가져올 점 (조사 확인일 2026-11-10)

대상: Zackriya-Solutions/meetily, fastrepl/anarlog(구 Hyprnote), RecapAI/Recap, OpenWhispr/openwhispr, sjoon21/Tractus, jmmi/meeting-moa, teconomix/local-transcriber, mameli/Takku, Baladhurgesh/minutes. 참고로 Granola·Otter·Fireflies가 호평받는 기능 중 위 오픈소스가 따라 한 것.
기준: `local://quietclerk-features.md`(2026-11-10)의 현재 기능. 이미 있는 것은 뺐고, QuietClerk(이하 QC) 쪽이 더 나은 것은 6절에 따로 적었다.

## 0. 가져올 가치가 큰 것 상위 10개

크기: S = 한 모듈·테스트 포함 1일 안팎, M = 며칠(화면·테스트 포함), L = 1주 이상 또는 새 모델·서비스 추가. **크기는 내 판단이며 측정값이 아니다.**
원칙 = (가) 음성은 Mac 밖으로 안 나감 (나) 회의 텍스트는 동의한 엔진에만 (다) 갤럭시 기본 녹음 앱 그대로.

| 순위 | 항목 | 출처 프로젝트 | 크기 | 원칙 충돌 | 상세 |
|---|---|---|---|---|---|
| 1 | 받아쓰기 안전망: 반복 루프·무음 환각 문구·토큰 상한 | local-transcriber, Tractus, Takku (OpenWhispr 이슈가 문제 확인) | S~M | 없음 | 3-1 |
| 2 | 사용자 단어장(핫워드 주입 + 변형어 치환 + 고친 낱말을 단어장으로) | Tractus, Takku, local-transcriber | M | 없음(단어장도 엔진으로 가면 "보낸 데이터"에 표시) | 3-2 |
| 3 | 요약 템플릿 사용자 정의(구성만 사용자, 근거·안전 규칙은 고정) | Tractus, Takku, meetily (anarlog) | M | 없음 | 3-3 |
| 4 | 할 일 담당·기한·숫자를 근거 줄에서 결정적으로 대조 + `담당 미정` 표시 | Tractus (OpenWhispr 같은 규칙) | S~M | 없음 | 3-4 |
| 5 | 노트 렌더 방어 추가: Dataview 블록·인라인 쿼리, 열린 코드 펜스 | Takku | S | 없음 | 3-5 |
| 6 | 가상 화자(맞장구 조각 클러스터) 정리 | OpenWhispr, meeting-moa | S | 없음 | 3-6 |
| 7 | 회의록 검색: SQLite FTS5 음절 bigram + 웹 검색창 + CLI | Tractus (Takku·anarlog CLI) | M | 없음(로컬 색인) | 3-7 |
| 8 | 캘린더 일정 연결(녹음 시각 ↔ 일정, 사용자가 확정) → 제목·참석자 | Tractus, Takku, local-transcriber, OpenWhispr(사후 연결) | M | 조건부(나): 참석자·제목이 엔진으로 가면 동의 범위에 포함 | 3-8 |
| 9 | 회의 질문(인용 검증·`근거 없음`) + 읽기 전용 MCP | Tractus, Takku, anarlog | L | 조건부(나): MCP를 읽는 에이전트는 QC 통제 밖 | 3-9 |
| 10 | 회의 간 목소리 등록(이름 제안, 미확정 표시, 동의·삭제) | Tractus, local-transcriber, Takku (meetily 이슈가 수요 확인) | L | 조건부: 음성 임베딩은 생체정보. 로컬 저장이면 (가) 유지 | 3-10 |

바로 다음 후보(11~): 내보내기 srt/vtt/csv/docx(3-11), 한국어 숫자 표기 바꾸기(3-12), 카톡용 짧은 요약 복사(3-13), 화자 표 보강(발화 비율·이름 지정 화면)(3-14), 열린 할 일 모음·주간 리캡(3-15), 재생 배속·무음 건너뛰기·단어 단위 재생(3-16), 진단 묶음(3-17), Homebrew 설치(3-18), 문서·릴리스 관행(3-19), 이름 자리표시자 치환(3-20), 긴 회의 구간 요약(3-21), 훅·자동화(3-22).

**검증 수준(이 문서 전체):** 저장소 clone(depth 1) 후 README·문서·소스 열람 + `gh api`로 스타·이슈 조회 + Granola/Otter/Fireflies 공개 도움말 열람. **코드 실행·설치·실제 녹음 입력으로 확인한 것은 없다.** QC 저장소는 파일을 읽어 현재 동작을 확인했고(경로 표기), 실행하지 않았다. `samples/`의 m4a·txt는 파일 목록만 봤고 이 조사에 쓰지 않았다. 타 프로젝트의 수치(CER, 재현율, EER 등)는 전부 **그 프로젝트의 자체 측정**이며 독립 검증이 아니다.

---

## 1. 근거 표기와 조사 대상

### 1-1. 근거 URL 만드는 법
`https://github.com/<저장소>/blob/<커밋>/<경로>#L<줄>`. 아래 약칭의 커밋은 2026-11-10에 clone한 HEAD다. 본문의 `TR:경로#L줄`은 이 규칙으로 URL이 된다. 이슈는 `https://github.com/<저장소>/issues/<번호>`.

| 약칭 | 저장소 | 커밋(HEAD) |
|---|---|---|
| TR | sjoon21/Tractus | 19d872f93320a498ec970d0628abb18ec23278c0 |
| TK | mameli/Takku | 29e14cbb2a6a8bd1cd2f645b840f4a847c0fb55d |
| LT | teconomix/local-transcriber | 6253a87052be687638a2494ecc2b02af48e70e6f |
| OW | OpenWhispr/openwhispr | 36ca8a0769d414d6647013728c9c1df2abd56231 |
| MM | jmmi/meeting-moa | c900feca66c7579e4854b4599ae3d57ddcf65688 |
| ML | Zackriya-Solutions/meetily | 07c4dfd45361bb6776916a0d46f493dda447f471 |
| AN | fastrepl/anarlog | 0a97fcd408aa62230484787e462be4b56bd4f1ee |
| RC | RecapAI/Recap | 6d3ccf5967bb7857632aad624467a97afe461792 |
| BM | Baladhurgesh/minutes | 00a81943a68a3073380db5cf61ad4424f04b3580 |
| QC | 이 저장소(rec) | 로컬 파일, 경로만 표기 |

### 1-2. 프로젝트 현황 (스타·열린 이슈는 2026-11-10 `gh api repos/<r>`)

| 프로젝트 | ★ | 열린 이슈 | 라이선스 | 마지막 커밋 | 가져올 것 |
|---|---|---|---|---|---|
| meetily | 32,578 | 399 | MIT(+유료 PRO) | 2026-11-02 | 수요 근거(이슈)가 가장 풍부. 코드는 템플릿 JSON 형식·요약 분할 정도 |
| OpenWhispr | 11,154 | 478 | MIT | 2026-11-09 | 팬텀 화자 정리, 사후 캘린더 연결, 회의 버그 수정 이력 |
| anarlog | 9,843 | 33(`gh api`의 open_issues_count. 저장소 설정상 이슈 기능이 꺼져 있어 PR이 섞였을 수 있음) | MIT(+`enterprise/` 상용, 제외) | 2026-11-05 | 가져오기 결과 4분류, 쓰기는 '제안'만 하는 MCP, 오디오 보관 기간 |
| Recap | 719 | 8 | MIT | 2026-02-07 | 거의 없음(README가 "POC, 프로덕션 사용 비권장" 명시) |
| Tractus | 5 | 1 | Apache-2.0 | 2026-11-10 | **가장 많음**: 한국어 Qwen3-ASR 안전장치·검색·질문·ITN·템플릿·목소리·내보내기 |
| Takku | 6 | 0 | MIT | 2026-11-06 | 템플릿·단어장 형식, 읽기 전용 MCP, 렌더 방어, 진단 묶음, 설치 |
| local-transcriber | 11 | 0 | MIT | 2026-11-02 | 환각·루프 필터, 화자 신뢰도 표기, 이름 치환, 진단 묶음 |
| meeting-moa | 0 | 0 | MIT | 2026-10-04 | 구독 CLI 약관 문서, VALIDATION.md 관행, 긴 회의 분할 |
| minutes (Baladhurgesh) | 2 | 0 | MIT | 2026-09-26 | 거의 없음(모델 프로필 JSON, 합성 샘플 회의 스크립트) |

라이선스: 코드를 그대로 옮길 때는 MIT(TK·LT·OW·MM·ML·AN·RC·BM)는 저작권·허가 문구 유지, Apache-2.0(TR)은 NOTICE·변경 표시가 필요하다. 이 문서는 **설계·규칙을 가져오는 것을 기본**으로 하고 코드 이식은 구현 시 라이선스 확인을 전제로 한다. anarlog `enterprise/`는 상용이라 제외했다.

**사용자 호응 근거의 한계:** Tractus(★5)·meeting-moa(★0)·Takku(★6)·local-transcriber(★11)·minutes(★2)는 사용자 반응 자료가 사실상 없다. 이들 항목의 가치 판단은 "코드·문서의 구체성과 측정 여부"에 의존한다. anarlog는 이슈가 비활성이라 반응을 **확인 못 함**. 이슈 반응은 meetily·OpenWhispr만 수치로 남겼다.

---

## 2. 읽는 법

각 항목은 (무엇·어떻게) / 근거 / 호응 / QC 이식 형태와 크기 / 원칙 충돌 / 비정상·악의 입력 검증 순서. `[추정 E#]`·`[E#]`은 11절의 열린 항목 번호. **호응 줄이 없는 항목의 호응 근거는 10절 표를 보고, 거기에도 없으면 "확인 못 함"이다**(해당 프로젝트에 이슈 반응 자료가 없음).

---

## 3. 항목 상세

### 3-1. 받아쓰기 안전망: 반복 루프·무음 환각 문구·토큰 상한 (분야: 받아쓰기 품질)

**QC 현재(코드 확인):** `quietclerk/backends/mlx.py`의 `transcribe`는 60초 청크마다 `asr.generate(chunk, language=…, chunk_duration=60.0, max_tokens=200000)`을 부르고, `validate_output`(`quietclerk/backends/__init__.py#L40-L75`)은 시각 순서·유한성만 검사한다. 텍스트 반복·환각 검사는 없다(`loop`·`repeat`·`환각` grep 결과 없음). 2차 패스 `mlx_whisper.transcribe(…, condition_on_previous_text=False)`도 후처리가 없다.

**타 프로젝트가 하는 것**
- **토큰 상한 + 루프 재시도 (Tractus).** 청크 길이로 상한을 둔다: `ceil(초×16)+32`(`TR:src/tractus/asr.py#L26-L27`, `#L86-L87`). 4글자 이상 문자열이 연속 3회 이상이면 루프로 본다(`#L32`, `#L90-L97`). 루프가 나면 언어 자동 감지로 한 번 더, 그래도 루프면 반복을 한 번만 남긴다(`#L181-L199`). 짧은 한국어 맞장구("네", "음")를 중국어·일본어로 감지해 한자로 받아 적는 사례를 실제 노트에서 관찰했다고 적었다(`#L40`).
- **무음 환각 문구 제거 + 제거 내역 보존 (local-transcriber).** Whisper가 무음에 "Vielen Dank." 등을 지어내는 문제(한 녹음에서 12회). 문구 = 3초 이상 쉼 없이 이어진 단어, 6단어·8초 이하일 때 아래 중 하나면 제거: (a) 평균 발화 음량의 10% 미만이면서 인식된 발화 구간에서 0.3초 이상 밖 (b) 같은 문구가 3번 연속 (c) 알려진 상투 문구이면서 (a)의 둘 중 하나 (d) 길이 무관, 발화 구간 밖이면서 Whisper 평균 단어 확률 0.2 미만. 24개 녹음에서 51단어가 제거됐고 모두 지어낸 것이었다고 코드 주석이 적는다(`LT:transcriber/pipeline.py#L456-L523`). 같은 1~4단어 열이 10번 이상 연속이면 1번만 남김(57개 전사로 확인, `#L525-`). 결과에 `dropped`(시각·텍스트·이유 코드)를 남겨 "조용히 사라지지 않게" 한다(`#L703-L705`, `#L727`).
- **상투 문구 목록 (Takku).** 독일어·프랑스어·스페인어·이탈리아어·영어의 Whisper 상투 문구를 짧은 소리 위에 있을 때만 삭제(`TK:CHANGELOG.md#L60`).
- **핫워드 목록 받아쓰기 방지 (Tractus).** 청크가 1.0초 미만이면 핫워드를 넣지 않고(`#L35`, QwenLM/Qwen3-ASR 이슈 #186 인용), 서로 다른 핫워드 3개 이상이 출력 글자의 80% 이상을 덮으면 목록을 받아 적은 것으로 보고 그 청크만 핫워드 없이 다시 돌린다(`#L100-L107`). 3-2와 함께 도입할 때 필요하다.
- **디지털 무음 감지 (Takku, 녹음 중 트랙 기준).** 버퍼 피크가 -80 dBFS 아래면 무음으로 보고 2분 지속 시 경고(`TK:docs/SPEC.md#L247-L254`). QC는 파일 입력이라 "파일 전체/구간 피크로 무음 판정" 형태로 바꿔야 한다 [추정 E3].

**호응:** OpenWhispr 이슈 #462 "Whisper hallucinations ("Thank you for watching!") during silence"(열림, 👍2, 댓글 14). 같은 문제를 local-transcriber·Takku가 각자 고쳤다는 점이 반복 확인이다. 한국어 환각 문구 사례는 이들 프로젝트에서 **확인 못 함**(영어·독일어·이탈리아어 등).

**QC 이식 형태**
1. `mlx.py`: 청크 길이 기반 `max_tokens` + 루프 감지·재시도·반복 축약, 재시도 사실을 단계 로그에 기록. S.
2. 새 후처리 `drop_hallucinations(words, audio)`를 2차 패스 뒤에 두고 `dropped` 목록을 단계 캐시와 "처리 데이터" 패널에 남김. 입력으로 오디오 음량과 단어 확률이 필요한데 `mlx_whisper` 단어에 확률 필드가 있는지는 **확인 못 함** [추정 E3]. M.
3. 5분 미만 건너뛰기와 같은 층에서 "전 구간 무음" 판정 → 건너뜀 사유 `silent`. S.

**원칙 충돌:** 없음(전부 로컬).

**비정상·악의 입력 검증:** (a) 10분짜리 전부 0인 WAV (b) -60 dBFS 백색 잡음 (c) 합성한 한 단어 200회 반복 (d) "네/응"만 있는 5분 (e) 상투 문구가 **실제 발화 구간 안에** 있는 파일에서 지워지지 않는지(오삭제 회귀) (f) 핫워드 5,000개·줄바꿈 포함 시 에코 판정 오작동.

---

### 3-2. 사용자 단어장 (분야: 받아쓰기 품질)

**QC 현재:** 단어장 UI·핫워드 없음(features 문서가 알려진 부재로 적음). `mlx.py`의 Qwen 호출에 `hotwords` 인자 없음.

**타 프로젝트가 하는 것**
- **Tractus:** `glossary.md`를 Qwen3-ASR `hotwords`로 넣어 용어 재현율을 72%→84%로 올렸다고 적는다(`TR:docs/models.md#L50`, 자체 측정). 상한 50개(앞이 우선; 100개를 넘기면 크게 나빠진다는 논문 인용, `asr.py#L36`), 최근 추가한 것부터 사용. 노트 제목·메모의 낱말(조사 제거, 흔한 말 제외, 최대 20개)을 그 노트 변환에만 덧붙임(`asr.py#L110-L131`). 사전 화면: 한 개씩 Enter, 쉼표·줄바꿈 목록 일괄 붙여넣기, 삭제 후 `실행 취소`(`TR:docs/en/usage.md#L33`). 대화 수정에서 고친 낱말을 "자주 쓰는 단어에 추가?"로 제안(`#L32`).
- **Takku:** `~/.takku/vocabulary.md` 한 줄 한 항목 `- Kubernetes = cubernetes, kubernetis | 데이터 변환 도구`. 변형어는 대화록 생성 때 **단어 단위로 결정적 치환**하고, 용어·변형어 앞 3개·설명은 요약 프롬프트에 준다(`TK:README.md#L145-L155`). 엔진 편향·별도 LLM 교정 패스를 **일부러 쓰지 않은 이유**가 ADR에 있다: 대화록 전체를 LLM에 한 번 더 보내야 하고, 모델이 말한 내용을 바꿀 수 있으며, 7일 뒤 오디오가 사라진다(`TK:docs/adr/0005-vocabulary-without-llm-pass-or-engine-biasing.md`).
- **local-transcriber:** 인식 후 고정 치환 + **기존 전사에 소급 적용**(`LT:docs/FEATURES.md#L35-L36`), 에이전트가 "KI 대신 Kali로 적혔다, 기억해"를 받아 단어장에 추가하고 현재 전사를 고치는 흐름(MCP).
- **OpenWhispr:** Dragon 단어 목록 가져오기(`OW:CHANGELOG.md#L12`), 팀 공유 사전(`#L25`)은 참고만. 팀 기능은 (나)와 맞지 않아 제외.

**QC 이식 형태**
- `~/.quietclerk/vocabulary.md`(Takku 형식) 하나를 원본으로: ① Qwen 호출에 `hotwords`(상한 50, 최근 것 우선, 청크 1초 미만 제외, 에코 판정 3-1) ② 교정 단계 프롬프트에 용어·설명 ③ 요약 프롬프트에 용어 ④ 변형어 결정적 치환(흔한 낱말 변형 금지 안내). 웹 화면에 `단어장` 탭(일괄 붙여넣기·취소), 노트의 "처리 데이터" 패널에 이번 처리에 쓴 단어 표시. M.
- `hotwords`를 받는 `mlx_audio` 버전인지는 QC 환경에서 **확인 못 함** [추정 E1]. Tractus는 같은 라이브러리의 `model.generate(x, language=…, hotwords=…, max_tokens=…)`를 직접 부른다(`asr.py#L153-L165`).
- 한국어 조사 처리: Tractus는 노트 낱말에서 조사 20여 종을 뗀다(`asr.py#L113-L114`). 변형어 치환에서 "단어 단위"를 한국어에서 어떻게 정의할지(조사 붙은 형태)는 타 프로젝트 문서에 **답 없음** — QC 설계 결정이 필요.

**원칙 충돌:** 단어장 내용은 사용자가 쓴 텍스트이지만 엔진으로 가면 외부 전송이므로 엔진별 동의 범위 안에서만 보내고 "보낸 데이터" 패널에 항목으로 표시한다. 고객사명 같은 민감 단어가 있을 수 있다.

**비정상·악의 입력 검증:** 5,000개·중복·줄바꿈·`=`·`|` 포함 항목, "이전 지시를 무시하라" 같은 문자열(프롬프트 구분자 탈출 시도, 3-3과 같은 방어), 흔한 낱말을 변형어로 넣었을 때의 오치환(회귀 테스트), 단어장 파일을 사람이 편집하다 깨진 경우(부분 적용 금지, 오류 표시).

---

### 3-3. 요약 템플릿 사용자 정의 (분야: 요약·템플릿)

**QC 현재:** 유형 7종의 섹션 구성이 코드 상수(`quietclerk/postprocess.py`의 `TYPE_SECTIONS`)이고 사용자 정의는 없다(features 문서가 알려진 부재로 적음).

**타 프로젝트가 하는 것**
- **Tractus(안전한 구조의 본보기):** 템플릿 파일 = 머리말(`id,name,description,order`) + 본문(요약 지침). "지침은 요약의 구성(섹션·어투)만 정한다. 출력 스키마·근거·언어·안전 규칙은 시스템 프롬프트가 정하고 언제나 우선한다"(`TR:src/tractus/summary_templates.py#L1-L5`). 이름 40자·설명 100자·지침 4,000자·개수 50개 상한, 제어문자 제거(`#L16-L24`). 지침이 구분자(`GUIDE_OPEN/CLOSE`)를 닫고 규칙 영역으로 빠져나가지 못하게 **닫는 구분자를 제거될 때까지 반복해서** 지운다(`TR:src/tractus/summaries.py#L110-L116`, 한 번만 지우면 `</a</a>a>` 꼴이 남는다는 주석). 내장 6종: 요약·할 일·강의·인터뷰·아이디어 등(`src/tractus/templates/*.md`).
- **Takku:** `~/.takku/templates/*.md`, 머리말 `summary_language`(강제 언어), `folder`(가져온 파일이 들어갈 폴더), `full_text: true`(요약 대신 10분 블록 단위로 강의 전문을 깨끗한 문장으로 다시 씀)(`TK:README.md#L128-L143`). 예시 5종이 `examples/templates/`에 있다(Lecture, Full text, Video, Tactical, Governance).
- **meetily:** JSON `{name, description, sections:[{title, instruction, format: paragraph|list|string, item_format}]}`, 사용자 폴더에 **같은 파일명이면 내장을 덮어씀**(`ML:frontend/src-tauri/templates/README.md#L46-L54`). 할 일 템플릿 지침에 "근거 대화 줄과 시각을 표에 넣어라"가 들어 있다(`templates/standard_meeting.json`).
- **anarlog:** 템플릿 선택기 + `Auto` 형식 편집. "템플릿을 바꿔도 기존 요약을 자동으로 다시 쓰지 않음, 다시 생성해야 반영"(`AN:docs/customize-summaries.mdx`). 노트·대화록·참석자는 편집으로 못 빼게 항상 따로 보냄.

**호응(meetily):** 이슈 #243 "Make summary templates configurable"(열림, 👍11, 댓글 7). 요약 출력 언어 설정 #233(닫힘, 👍16, 댓글 12)·#413(닫힘, 👍7)도 템플릿 영역의 요구(QC는 `notes.output_language` 설정이 이미 있어 후자는 해결됨, `quietclerk/config.py#L28`).

**QC 이식 형태:** `~/.quietclerk/templates/<유형>.md`(머리말 `name`, `type`(7종 중 하나에 연결), 본문 = 섹션 구성·어투만). `COMMON_SUMMARY_RULES`의 인용 `[tN]`·`## 핵심 요약`·`## 확인 필요`·할 일 형식은 그대로 우선. 검증 `validate`(제목·인용 1개 이상)는 유지. 노트 보기에서 "이 템플릿으로 다시 요약"(요약만 다시). 이름·길이·개수 상한과 구분자 방어는 Tractus 값을 참고. `full_text` 같은 전문 모드는 11~ 후보(강의 유형 정리). M.

**원칙 충돌:** 없음. 템플릿 본문은 사용자가 쓴 것이고 요약 엔진에만 간다.

**비정상·악의 입력 검증:** 본문에 `인용을 쓰지 마`·`확인 필요 섹션 삭제`(규칙 무력화 시도) → 규칙 우선 확인, 구분자 중첩 탈출, 제어문자·4,000자 초과·51번째 템플릿, 파일명에 `../`, 머리말 없는 파일, 유형 연결 누락(기본 템플릿으로 폴백하고 사유 표시).

---

### 3-4. 할 일 담당·기한·숫자의 결정적 대조 (분야: 요약·템플릿)

**QC 현재(코드 확인):** 요약 규칙은 "할 일은 `- [ ] 작업 (담당 / 기한)`"을 요구하지만(`quietclerk/postprocess.py`의 `COMMON_SUMMARY_RULES`), 요약 `validate`는 `## 핵심 요약` 제목과 인용 1개 이상만 검사한다. 존재하지 않는 인용 id는 렌더가 `[?t99]`로 표시하고 `unknown_citation` 사유를 남긴다(`quietclerk/render.py#L106-L118`) — **이 부분은 이미 있다.** 담당·기한·숫자를 근거 줄과 비교하는 코드는 없다(`unverified`·`숫자` grep 결과 없음).

**타 프로젝트가 하는 것 (Tractus, 코드):** 요약 뒤에 코드가 결정적으로 다시 검사하고 AI에 재요청하지 않는다.
- 담당: 근거 줄(또는 말한 사람의 확정 이름)에 전체 이름이 있거나 "지훈님"으로 불렸고 전체 이름이 대화 어디에 있을 때만 유지(`TR:src/tractus/minutes.py#L154-L164`).
- 기한: 근거 문장에 그 표현이 **그대로** 있을 때만(`#L179-L182`, `다음 주 수요일까지`⊃`다음 주 수요일`).
- 팀: 말한 사람의 확정 이름에 팀이 있거나 근거 문장에서 "저희 플랫폼팀"처럼 자기 팀으로 말했을 때(`#L167-L176`).
- 숫자: 문장 속 숫자 중 근거에 없는 것만 `숫자 확인` 표시, 지우지는 않음. 근거의 한자어 수는 ITN으로 숫자로 읽어 비교(`#L185-L190`).
- 담당·기한이 없는 할 일은 `담당 미정`·`기한 미정`을 눈에 띄게(`TR:docs/design/meeting-minutes.md` 사용자 경험 6항, 근거로 블로그 한 건 인용).
- OpenWhispr도 같은 규칙으로 바꿨다: 할 일을 `- [ ] Action — Owner`로 쓰되 "담당·기한은 대화록이나 메모에 있을 때만"(`OW:CHANGELOG.md#L111`, 1.10.4, 2026-10-21).

**QC 이식 형태:** 요약 후처리 `verify_tasks`: 각 `- [ ]` 줄의 괄호 `(담당 / 기한)`를 같은 줄이 인용한 대화 줄(+화자 이름)에서 찾고, 없으면 `담당 미정`·`기한 미정`으로 치환, 숫자는 `⚠ 숫자 확인` 표시. 하나라도 걸리면 노트 `needs_review` 사유에 `unverified_task_fields` 추가. 요약만 다시 돌릴 때 결과가 일관되도록 결정적 코드로만. S~M.
주의: 한국어 숫자 표기(삼십만/30만) 불일치로 오경고가 난다. Tractus는 ITN(3-12)을 먼저 둬서 해결했고, 못 해결한 경우는 "지우지 않고 표시만"으로 설계했다. QC도 표시만.

**원칙 충돌:** 없음.

**비정상·악의 입력 검증:** 동명이인 2인, 호칭만 있는 담당("부장님"), 담당 칸에 `[[링크]]`·줄바꿈·HTML, 존재하지 않는 인용 id, 한자어 수 vs 아라비아 수, 기한에 상대 표현만("그때까지").

---

### 3-5. 노트 렌더 방어 추가: Dataview·열린 코드 펜스 (분야: 프라이버시·보안)

**QC 현재(코드 확인):** 전사·화자명은 `safe_text`(HTML 이스케이프, `[ ] ` * _ ! ^ |` 이스케이프), 요약은 `safe_summary`(HTML 이스케이프, `[텍스트](url)`·이미지 제거, `[[`·`]]` 이스케이프, 참조 링크 정의 삭제)로 막는다(`quietclerk/render.py#L91-L103`). **백틱·코드 펜스는 요약에서 손대지 않는다.** `tests/`에 `fence`·`dataview` 키워드가 없다(grep). 이전에 Takku가 막은 위험 중 이미지·HTML·링크는 QC가 이미 막고 있어 **여기에는 해당 없음**.

**Takku가 하는 것:** 대화에서 나온 텍스트는 신뢰하지 않으므로 알려지지 않은 것을 찾지 않고 무력화한다: 마크다운 이미지→링크, HTML 태그→텍스트(속성 없는 몇 개 제외), **Dataview 블록**(인용·목록 마커·펜스 길이 뒤의 `dataview`/`dataviewjs`)→`text` 블록, **인라인 Dataview**(`` `= ``, `` `$= ``)→공백 삽입(`TK:TakkuCore/Sources/TakkuCore/MeetingNote.swift#L340-L360`). 응답에 열린 코드 블록이나 CR이 있어 **관리 영역 밖(아래 대화록·사용자 영역)을 삼키는 문제**를 막기 위해 CommonMark 규칙(같은 문자·같은 길이 이상의 닫는 펜스)으로 펜스 상태를 추적하고 끝에서 닫는다(`MeetingNote.swift#L362-`의 `Fences`, `TK:CHANGELOG.md#L9-L10`, 1.19.2 2026-11-06). 테스트 입력 예시는 `TakkuCoreTests/MeetingNoteTests.swift#L573-L590`.

**QC 이식 형태:** `safe_summary`에 ① 펜스 시작이 `dataview`·`dataviewjs`(+`tasks`, `button` 등 쿼리 플러그인 블록)면 `text`로 ② `` `= `` · `` `$= `` 뒤 공백 삽입 ③ 요약 끝에서 열린 펜스를 닫기. 요약 블록이 끝난 뒤 사용자 영역·전체 대화록이 이어지므로 ③이 핵심. S.
실제 Obsidian에서 Dataview JS가 실행되는지는 **직접 확인 못 함** — 방어가 싸므로 확인 없이 적용하고 격리 vault에서 테스트 노트 1건으로 닫는다 [E6].

**원칙 충돌:** 없음.

**비정상·악의 입력 검증:** ` ```dataviewjs `, `~~~dataview`, 인용·목록 안의 펜스, 닫히지 않는 ` ```` `, `\r` 포함 화자 이름, 요약 본문에 `%%` 주석 마커·`^t3` 블록 ID 위조, 매우 긴 한 줄.

---

### 3-6. 가상 화자 정리 (분야: 화자)

**QC 현재(코드 확인):** `quietclerk/transcript.py`의 `assign_speakers`는 단어마다 겹침이 가장 큰 화자, 겹침 없으면 가장 가까운 구간의 화자를 준다(`#L4-L17`). 소수 조각 클러스터를 정리하는 단계는 없다. 대신 분류 단계의 `split_suspect`(한 라벨에 두 사람이 섞임)가 LLM 판단으로 있다. Nemotron 3는 최대 8명(TR ARCHITECTURE D3, `TR:ARCHITECTURE.md#L130`).

**OpenWhispr(실제 버그 이력):** 짧은 맞장구·말 시작 조각이 별도 화자가 된다. 73분 음성 메모에서 46명(`OW:src/helpers/diarizationPolicy.js#L5-L9`), 20분 2인 통화에서 팬텀 4개가 발화의 8%(`#L21-L26`). 규칙: ① 총 발화 1초 미만 클러스터 제거(`#L19`) ② **발화 점유 10% 미만이면서 평균 세그먼트 3초 미만이면 팬텀**, 상위 2개 클러스터는 보호(`#L28-L33`) ③ 한 화자가 93% 이상이고 나머지 평균이 2.2초 미만이면 클러스터링이 두 사람을 합친 "붕괴"로 보고 라벨을 쓰지 않음(`#L35-L45`) ④ 임계값을 길이에 따라 0.55→0.7로 올림(15~60분 선형, `#L10-L18`). **알려진 비용을 코드 주석이 직접 적는다:** 실제 세 번째 참석자가 10% 미만·평균 3초 미만이면 같이 삭제됨(`#L28-L30`). 변경 이력: `OW:CHANGELOG.md#L230`(1.10.3, 2026-10-12).
**meeting-moa:** 목소리 중심 유사도 0.7 이상 병합 후 `max(10초, 발화 1%)` 미만 화자를 가장 가까운 화자로 재배정(`MM:worker/engine.py#L114-L148`).

**QC 이식 형태:** `prune_speakers(diar)`를 `turns()` 앞에 두고 위 ①② 규칙 적용(③은 선택). **삭제가 아니라 재배정**: QC는 단어를 버릴 수 없으므로 팬텀 구간을 시간상 가장 가까운 유지 화자로 보낸다(Nemotron은 임베딩을 안 줘 시간 근접이 유일한 기준 [추정 E2]). 임계값은 설정값으로 두고 처리 로그에 "N명→M명" 기록. S.

**원칙 충돌:** 없음.

**비정상·악의 입력 검증:** 2인+맞장구 조각, 한 사람 독백(93% 규칙 오발동), **실제 소수 세 번째 발언자 보호**(회귀 — 10% 미만 3초 미만이 지워지는 알려진 비용을 QC 4개 샘플로 측정), 9명 이상, 화자 1명뿐인 입력.

---

### 3-7. 회의록 검색 (분야: 검색·질문)

**QC 현재:** 검색 없음(features 문서). Obsidian 자체 검색은 있다.

**Tractus(설계·측정 공개):** SQLite FTS5 + 한국어 **음절 bigram** 토크나이저 + 조사 뗀 완화 질의 + sqlite-vec + 가중 RRF(`TR:src/tractus/index.py#L1-L8`, `#L51-L106`). 청크 300~500자(`#L34`). 인덱스는 transcript 파일에서 언제나 재생성 가능한 **캐시**, 바뀐 노트만 증분 색인(`#L1-L6`). **측정(hit@1, 가상 30질의 / AI Hub 실제 ASR 139질의):** RRF 동일가중 0.97/0.50, **키워드만 0.90/0.85**, 키워드 우선+벡터 가중 0.3 → 0.97/0.80(`#L35-L38`, 자체 측정). 즉 **실제 ASR 질의에서는 키워드만이 가장 높았다.** 벡터는 자연어 질의용 보조다. 임베딩은 로컬 Qwen3-Embedding-0.6B(`TR:ARCHITECTURE.md#L133`).
사용자 화면: 단어 일치와 `비슷한 의미` 결과를 함께, 스마트 검색 모델이 없으면 단어만(`TR:docs/en/usage.md#L56-L57`).
**Takku CLI:** `takku search release regression`(모든 단어 포함, 일치한 줄 표시, 대소문자·악센트 무시), `takku list --from … --query mario`, `--json`(MCP와 같은 필드)(`TK:README.md#L215-L220`). **anarlog:** `list_meetings`에 제목/ID 부분 문자열·폴더·반복 시리즈 필터와 페이지(`AN:docs/reference/mcp.mdx#L10-L46`). 참고로 Granola API 검색도 키워드·참석자·폴더·기간 필터(https://docs.granola.ai/introduction.md).

**QC 이식 형태:** 상태 SQLite에 FTS5 테이블(노트 id·줄 id·시각·화자·텍스트) + 노트 sha 기반 증분 동기화 → 웹 화면 검색창(결과 클릭 시 해당 시각 재생) + `quietclerk search --json`. 벡터는 후순위(자체 측정이 키워드 우세). "처리 데이터 삭제"가 색인 행도 지우도록 연결. M.

**원칙 충돌:** 없음(로컬).

**비정상·악의 입력 검증:** FTS 구문 주입(`"`, `*`, `NEAR(`, `OR`, 괄호 불일치), 조사 붙은 질의, 10만 줄 규모, 삭제된 노트의 잔재, 이모지·제어문자.

---

### 3-8. 캘린더 일정 연결 (분야: 입력·동기화)

**QC 현재:** 캘린더 없음(features 문서 알려진 부재).

**타 프로젝트가 하는 것**
- **Tractus:** macOS EventKit(Swift `tractus-rec calendar next|range|list`), Google·Exchange도 macOS 캘린더에 있으면 읽힘(OAuth 없음). 이메일은 내보내지 않고 이름만, 제목 200자 절단, 종일·취소·거절 일정 제외, 권한 없으면 빈 목록(오류 아님)(`TR:docs/design/calendar.md#L1-L30`). 참석자 이름은 그 녹음의 ASR 힌트(단어장에는 저장 안 함)·화자 이름 고르기·노트 `attendees` 속성에만 쓴다. **자동 이름 제안은 확정 전까지 요약·md·MCP·내보내기에 나가지 않는다**(`TR:docs/roadmap.md#L125`, 목소리 제안 규칙).
- **Takku:** 일정 제목 → 노트 이름, 초대 참석자 → `participants` → 요약이 화자 이름을 짓는 단서, 이름 지정 화면의 후보(`TK:README.md#L106-L108`, `#L112-L124`).
- **local-transcriber:** 제목 → 파일명, 참석자 → 이름 후보, **참석자 수로 찾을 화자 수 상한**(`LT:docs/FEATURES.md#L60-L64`).
- **OpenWhispr(QC와 가장 가까운 사후 연결):** "손으로 만들었거나 회의 뒤에 정리한 노트를 이벤트에 연결": 노트 머리글에서 **최근 3일 일정을 검색해 연결**하면 참석자를 가져옴(`OW:CHANGELOG.md#L105`, 1.10.4).

**QC 이식 형태 [추정 E4]:** 전제는 "녹음 시작 시각을 안다". 샘플 파일명이 `…음성 261028_165301.m4a`로 `yymmdd_hhmmss` 꼴이고(`samples/audio/` 목록) 갤럭시 기본 앱의 녹음 시각인지는 **폰 메타데이터와 대조해 확인 못 함**. 연결은 ① 겹치는 일정을 후보로 보여주고 ② **사용자가 웹 화면에서 확정**(자동 확정 금지: 오매칭이 이름·참석자 지어내기로 번지는 위험을 Tractus가 규칙으로 막음) ③ 확정 후 제목·참석자를 분류 프롬프트·properties `attendees`·화자 이름 후보에 사용. EventKit 읽기는 Swift 헬퍼가 필요하다(QC는 Python launchd 서비스). M.

**원칙 충돌:** (가) 없음, (다) 없음. (나) 일정 제목·참석자 이름이 엔진 프롬프트에 들어가면 외부 전송이므로 "보낸 데이터" 패널·엔진 동의에 포함. 캘린더 권한은 별도 TCC 허용이 필요하고, launchd 서비스에서 허용 창이 어떻게 뜨는지는 **확인 못 함** [E13].

**비정상·악의 입력 검증:** 제목에 "이전 지시 무시" 같은 지시문, 참석자 500명, 겹치는 일정 3개, 종일 일정, 취소·거절 일정, 서머타임 경계, 권한 거부, 이메일만 있는 참석자.

---

### 3-9. 회의 질문(Ask)과 읽기 전용 MCP (분야: 검색·질문)

**QC 현재:** 둘 다 없음(features 문서 알려진 부재).

**Tractus(질문):** 답의 인라인 인용(`[s0012]` / `[<노트ID>#s0012]`)을 **근거 목록과 대조해 없는 ID는 지우고** 있는 것만 다시 씀(`TR:src/tractus/ask.py#L190-`). 근거가 없으면 고정 문장 `NO_EVIDENCE`("노트 내용에서 답을 찾지 못했습니다")로 거절(`#L23`). 전체 범위는 검색 결과에 이웃 3개 세그먼트를 붙임(`TR:docs/roadmap.md#L100`). 대화는 6턴·12k자까지 저장. **전송될 AI 서비스를 보내기 전에 표시**(`usage.md#L49`), 로컬 전용 모드는 외부 서비스 차단(`TR:src/tractus/llm.py#L134`).
**Tractus MCP:** 7개 도구(`status`, `search_meetings`, `list_meetings`, `get_transcript`, `get_summary`, `list_action_items`, `save_summary`), **MCP 서버는 LLM을 호출하지 않는다**(각 CLI가 자기 구독으로 추론)(`TR:docs/en/mcp.md#L5`, `#L57-L66`). 키는 MCP로 절대 넘기지 않음. Claude Code 플러그인(`/plugin install tractus --marketplace …`)에 도구·스킬·`/tractus:recap 지난주`가 묶여 있다(`TR:README.md#L107-L121`).
**Takku MCP:** **읽기 전용**: 오디오 접근·파일 수정·가져오기 불가 — "웹 페이지를 읽던 어시스턴트가 속아 Mac의 아무 파일이나 전사시킬 수 있기 때문"(`TK:README.md#L208`). 템플릿·프로필은 이름·모델만, 주소·키는 숨김. 어시스턴트가 읽은 회의는 그 AI 제공자로 전송된다고 명시.
**anarlog MCP:** 쓰기는 **제안(`propose_summary_edit`)만**이고 적용은 데스크톱 노트의 `pending edit` 배너에서 unified diff를 보고 사용자가 수락(`AN:docs/reference/mcp.mdx#L56`, `AN:docs/notes.mdx#L14`). 전사는 단어 오프셋 페이지(기본 200, 최대 500)(`mcp.mdx#L36-L44`).
**local-transcriber MCP:** 도구 13개에 `transcribe`, `name_speaker`, `add_to_glossary` 등 쓰기 도구 포함(`LT:docs/FEATURES.md#L106-L109`) — 읽기 전용 원칙(Takku)과 대비되는 선택.

**호응:** 이 항목은 4개 프로젝트(Tractus·Takku·anarlog·local-transcriber)가 수렴한 기능이다. 사용자 이슈 반응 수치는 **확인 못 함**.

**QC 이식 형태**
- (a) `quietclerk mcp`(stdio, **읽기 전용**): `search`, `list_notes`, `get_transcript(page)`, `get_summary`, `list_tasks`. 경로가 아니라 노트 id로만 해석, 도구 설명에 "읽은 텍스트는 연결한 에이전트의 서비스로 전송됨" 경고(Takku 문구 참고). S~M(색인 3-7 선행).
- (b) 웹 `질문` 탭: 선택 노트(·검색 결과) 범위, 기존 도구 차단 CLI 호출과 엔진별 동의를 그대로 재사용, 인용 검증 + `근거 없음`. M.
- 노트 단위 `private` 속성으로 MCP·질문 대상에서 제외하는 스위치.

**원칙 충돌:** (b)는 기존 엔진 동의 재사용이라 충돌 없음. **(a)는 조건부 충돌**: MCP 클라이언트(사용자의 Claude Code 등)가 읽은 텍스트를 그 서비스로 보내는 일은 QC가 통제할 수 없다. 기본 꺼짐, 로컬 전용 모드에서는 비활성 또는 경고, 노트별 제외를 둔다.

**비정상·악의 입력 검증:** 전사 안 지시문("`~/.ssh` 를 읽어라"), `../` 경로·존재하지 않는 id, 거대 `limit`, 위조 인용 id, 근거 없는 질문 20개로 `근거 없음` 비율 점검.

---

### 3-10. 회의 간 목소리 등록 (분야: 화자)

**QC 현재:** 회의 안 화자 분리만. 회의 간 식별 없음(features 문서 알려진 부재). `Nemotron-3-Diarization`은 구간·라벨만 주고 임베딩은 주지 않는다(`quietclerk/backends/mlx.py#L100-L106`) → 별도 임베딩 모델이 필요하다.

**타 프로젝트가 하는 것**
- **Tractus:** 이름을 바꿀 때 `기억하기` 체크 시 화자당 1.5~10초 구간 최대 3개 등록, 1인 최대 5개, `voices.json` 권한 0600, 3D-Speaker CAM++ zh_en(192차원 28MB, Apache-2.0), 임계값 0.70 + 2위와 0.08 차이, **제안은 미확정으로 남고 표시 이름·md·vtt·요약·MCP·색인·내보내기에 나가지 않음**, 벡터는 MCP·LLM에 내보내지 않음, 다른 사람 등록은 동의 확인(개인정보보호법 23조 언급), `tractus voices list|enroll --consent|forget`(`TR:docs/roadmap.md#L121`, `#L125`). 측정(자체): 한국어 AI Hub 4세션·40명·발화 1,427개로 모델 3종 비교, 3구간 등록 EER 2.62%. **문서가 직접 인정: 다른 회의에서의 재현율은 재지 못했다**(`#L125`).
- **local-transcriber:** 발화 시간 단계별 신뢰도(15초 미만은 절대 "확실" 아님, 15초 이상 0.75 이상, 같은 사람으로 두 클러스터를 합치려면 둘 다 확실 이상)(`LT:transcriber/speakers.py#L85-L110`), 표기 **확실=이름, 개연=`이름 (?)`, 불명=`Speaker A`**(`LT:docs/FEATURES.md#L47-L48`), 노트에 발화 시간·일치 상태 표(`LT:transcriber/render.py#L63`). "전체 삭제"는 그 대화에서 만든 목소리까지 삭제(`LT:transcriber/cleanup.py#L1-L10`, 파인더에서 지웠더니 WAV 사본 3개와 목소리 데이터가 남은 사고가 계기).
- **Takku:** 기본 꺼짐, 동의 안내, 설정에서 개별 삭제(`TK:README.md#L126`). **OpenWhispr:** ONNX 목소리 지문(Intel Mac은 ONNX Runtime 지원 중단으로 불가, README 각주).

**호응(meetily):** 이슈 #226 "Identify the speaker in the transcriptions"(열림, 👍15), #230 "Speaker Diarization / Identification"(열림, 👍7, 댓글 18). meetily는 README에서 화자 식별을 PRO(유료)로 둔다(`ML:README.md` PRO 안내 문단).

**QC 이식 형태:** 새 임베딩 모델 추가(L) + `~/.quietclerk/voices.json`(0600) + 웹 화자 표의 `이 목소리 기억`(동의 체크) + 매칭 임계·시간별 신뢰 단계(LT) + 제안은 노트에 `이름 (?)`, 확정 전에는 요약·properties·내보내기에 이름으로 쓰지 않음(TR) + `forget` 명령과 "처리 데이터 삭제"가 목소리까지 지우는 선택지. L.

**원칙 충돌:** (가) 유지 — 임베딩은 로컬에만. 단 **생체정보**라 동의·삭제·권한 0600을 문서(SECURITY·데이터 정책)에 넣어야 한다. 확정 이름이 요약에서 엔진으로 가는 것은 기존 동의 범위.

**비정상·악의 입력 검증:** 한 사람이 두 클러스터로 갈린 경우, 비슷한 목소리 2인 오인식(회귀), 15초 미만 발화, 동의 체크 없는 등록 시도, `voices.json` 권한 변경 감지, 삭제 후 잔재, 단일 마이크 대면 회의(QC 입력의 기본 조건)에서의 EER은 **타 프로젝트 자료로 알 수 없음**.

---

### 3-11. 내보내기: srt·vtt·txt·csv·docx·백업 (분야: 노트·Obsidian)

**QC 현재:** Obsidian Markdown과 Bases 파일 위주(features 문서). 내보내기는 알려진 부재.
**타 프로젝트:** Tractus: txt·md·srt·vtt·csv·docx·전체 백업(zip: 오디오+전사+요약+메모)·PDF(인쇄)(`TR:docs/en/usage.md#L60`). CSV는 **`utf-8-sig`(BOM) 인코딩으로 한국어 Excel이 바로 열게** 함(`TR:src/tractus/export.py#L87`), DOCX는 `w:eastAsia` 글꼴에 `Apple SD Gothic Neo`를 지정해 Word·Pages에서 한글이 대체 글꼴로 깨지지 않게 함(`#L28`). 수정·화자 이름이 반영된다. anarlog: PDF·텍스트·Markdown·Org, 포함할 부분(메모·요약·전사) 선택(`AN:docs/notes.mdx` Export 절). local-transcriber: srt·json·txt/md.
**QC 이식 형태:** QC는 단어 시각이 있어 srt/vtt는 쉽다(S). txt·csv(BOM)·zip 백업 S, docx M. 노트 보기의 `내보내기` 메뉴. **원칙 충돌:** 없음(사용자가 파일로 저장).
**검증:** 줄바꿈·쉼표·따옴표 든 발언의 CSV 인용, 큐 길이 0, 화자 이름에 제어문자, 한글 파일명.

### 3-12. 한국어 숫자 표기 바꾸기(ITN) (분야: 받아쓰기 품질)
**Tractus:** 규칙 기반 한 파일(`TR:src/tractus/itn.py`), 새 의존성 없음. 단위(원·명·개월·년·분·프로·퍼센트·조…) 앞의 한자어 수만, 단위 뒤에는 조사나 문장 끝, **고유어 수("두 번")·`이` 한 글자는 바꾸지 않음, 만·억·조는 말로 남김**("35만 원")(`TR:docs/design/korean-itn.md#L16-L29`). 이유: Qwen3-ASR이 숫자 셋 중 둘을 한글로 적음(한글 407, 숫자 195)(`#L12`). 측정(자체): AI Hub 4세션 2,527발화 CER 9.48→9.14, 바뀐 121발화 중 113 나아지고 7 나빠짐, 세션 단위 9.49→9.33. 잘못 바꾼 사례 `공조→0조`·`구조→9조`는 규칙으로 막음(`#L30-L41`).
**QC:** 같은 모델(Qwen3-ASR 1.7B)을 쓰지만 교정(LLM)·Whisper 2차를 거치므로 효과가 같은지는 **확인 못 함** [추정 E5]. 3-4의 숫자 대조를 정확하게 하는 전제 부품. M. 원칙 충돌 없음. 검증: "오세요/사위/일시" 오변환, `공조` 회귀, 소수·시각·전화번호(안 바꾸는 것) 불변.

### 3-13. 카톡용 짧은 요약 복사
**Tractus:** 같은 데이터를 코어가 두 가지로 그린다(AI 호출 없음): `복사`(위키용 전체 Markdown), `짧게 복사`(결정 / 할 일 / 아직 안 정한 것 3블록, 근거 시각 없음)(`TR:src/tractus/minutes.py#L326`, `TR:docs/design/meeting-minutes.md` 사용자 경험 7항). 담당·기한 미정 줄이 그대로 나가 틀린 부분을 바로 알리게 하는 문구("짧게 정리했습니다. 틀린 부분은 알려 주세요.")도 있다.
**QC:** 노트 보기에 `메신저용 복사` 버튼. 요약 섹션과 `^task` 줄에서 렌더만 한다. S. 충돌 없음. 검증: 근거 링크·블록 ID가 복사본에 안 남는지.

### 3-14. 화자 표 보강: 발화 비율·이름 지정 화면
**근거:** local-transcriber 노트의 화자 표 `Speaker | Speaking time | Match`(`LT:transcriber/render.py#L63`). Takku `Name speakers…`: ▶로 그 화자의 목소리 샘플 재생(다시 누르면 다른 샘플) + 대화 인용 + 캘린더 참석자 후보, `Save and Regenerate`(`TK:README.md#L112-L124`); frontmatter `speakers: - Speaker 1 = Mario Rossi`로도 매핑해 요약 다시 생성. Tractus: 화자 막대에서 이름 더블클릭 변경, 다른 화자로 드래그해 `화자 병합`(`TR:docs/en/usage.md#L31`). anarlog: `Apply to all`로 같은 화자 전부 갱신(`AN:docs/notes.mdx#L23`). OpenWhispr: "This is me"(내 목소리 한 번에 지정), 대면 노트에서 화자가 모델에 내 이름으로 전달되던 버그 수정(`OW:CHANGELOG.md` 1.10.4 Notes).
**QC:** 웹 화자 표에 발화 비율(턴 길이 합) 열 + `이름 지정/병합` + 샘플 재생(이미 구간 재생 있음). QC에 **화자 이름 편집 경로가 이미 있는지는 확인 못 함**(`quietclerk/server/__init__.py`는 화자 표 출력만 확인, features 문서에도 없음) [E7]. 지정 후 `요약만 다시`로 반영. S~M. 충돌 없음. 검증: 이름에 제어문자·`[[ ]]`·200자 초과, 두 화자를 같은 이름으로.

### 3-15. 열린 할 일 모음 · 주간 리캡
**Otter:** 모든 대화에서 내게 배정된 할 일을 모은 Action Items 탭, 체크하면 Completed로 이동, `View in transcript`로 근거 위치 이동(https://help.otter.ai/hc/en-us/articles/25983095114519-Action-Items-Overview). **Tractus:** MCP `list_action_items`, `/tractus:recap 지난주`(결정·할 일·미결 리캡)(`TR:README.md#L121`).
**QC:** 노트에 `^task-N` 체크박스와 Bases 보기 파일이 이미 있으므로 "열린 할 일 전부" 보기는 Bases/Tasks 쿼리 파일 추가만으로 가능할 수 있다. Bases 필터로 체크박스 줄을 모을 수 있는지는 **확인 못 함** [E10]. S. 주간 리캡은 엔진 호출이라 동의 범위 안에서 M(3-9 이후). 충돌: 리캡은 (나) 엔진 동의 재사용.

### 3-16. 재생 배속·무음 건너뛰기·단어 단위 재생
**Tractus 계획·구현:** 배속 0.8~2배(`preservesPitch` 유지), ←/→ ±5초, Shift ±10초, 속도 기억(`TR:docs/roadmap.md#L85`); **무음 건너뛰기**: 세그먼트 간격 1.0초 초과 시 `next.start-0.2`로 이동, 화자 필터와 조합해 "이 화자만 듣기"(`#L86`); 단어 강조는 CSS Custom Highlight API로 단어 span 없이 그리고 단어 클릭 시 그 단어부터 재생(`#L99`, 실제 회의 295개 세그먼트 중 294개 사용). `R`=직전 문장 다시, 음성 강조 필터(Web Audio highpass 100Hz+3kHz +4dB)(`#L101`).
**QC:** 재생과 근거 클릭 재생은 이미 있다. 배속·건너뛰기·단어 강조 지원 여부는 **확인 못 함**(features 문서에 없음) [E7]. QC는 ForcedAligner 단어 시각이 있어 단어 단위 재생을 만들 재료가 이미 있다. 각 S~M. 충돌 없음. 검증: 단어 시각 불변식 위반 데이터(Tractus는 정렬 실패 시 `words`를 null로 두고 세그먼트 단위로 폴백, `#L98`), WKWebView/Safari 호환.

### 3-17. 진단 묶음 (분야: 설치·업데이트·운영)
**Takku:** `Report a problem…` = 버전·Mac 모델·사용 모델·최근 3일 로그를 담은 진단 파일을 만들고 Finder에서 보여주며 **미리 채운 GitHub 이슈를 연다. 자동 업로드 없음**(`TK:README.md#L104`). 이후 로그에서 오류 문장 인용 제거, 주소·경로 가림(`TK:CHANGELOG.md#L14`). **local-transcriber:** ZIP 14일 보관, 파일명·일정 제목·이름·이메일을 자리표시자로 치환(끌 수 있음), 녹음·전사·목소리 DB·용어집은 미포함, 이메일은 사용자가 직접 보냄(`LT:docs/PRIVACY.md` Problem reports 절).
**QC:** `quietclerk diag` + 홈 화면 버튼: 버전·모델 revision·최근 작업 로그·설정(경로·제목 마스킹). 노트 제목(회의 내용이 담길 수 있음)을 반드시 가림. S~M. 충돌 없음(자동 전송 안 함). 검증: 로그에 녹음 파일명·제목·경로가 남지 않는지.

### 3-18. Homebrew 설치
**Takku:** `brew install --cask mameli/takku/takku`, 앱 자체 업데이트와 `brew upgrade` 경로 모두 안내, `brew uninstall --cask --zap`은 설정·녹음·모델까지 삭제하되 **노트 폴더는 건드리지 않음**(`TK:README.md#L35-L44`). **local-transcriber:** `curl … | bash` 설치기 + `brew install --cask teconomix/tap/local-transcriber`(`LT:README.md` 상단). **OpenWhispr:** 이슈 #707 "Add Homebrew Formula"(닫힘, 👍8), #681 "Package with homebrew"(닫힘, 👍6). **meetily:** 설치 사고 사례 #251 "Brew Cask Installation Fails with 404 Error Due to Incorrect Asset Filename"(열림, 👍5), #148 "brew install meetily-backend fails with a SHA-256 mismatch"(닫힘).
**QC:** 현재 `git clone + deploy/install.sh` + 자체 `update`(롤백). Homebrew 공식 배포가 launchd 상주·모델 다운로드·롤백과 어떻게 겹치는지는 **설계 확인 못 함** [E11]. 위 사고 사례(자산 이름·체크섬 불일치)는 릴리스 자동 검증 항목으로 쓸 만하다. M. 충돌 없음. 검증: 제거 시 노트·받는 폴더(Syncthing)를 건드리지 않는지.

### 3-19. 문서·릴리스 관행
- **Takku `CHANGELOG.md`의 `Before you update`:** 사용자 행동이 필요한 변경을 버전 맨 위에 별도 문단으로(`TK:CHANGELOG.md#L7-L18`). QC 루트에는 CHANGELOG가 없다(루트 파일: CONTRIBUTING·LICENSE·README·SECURITY…). S.
- **meeting-moa `VALIDATION.md`:** 날짜·환경(M4 Pro, macOS 26.5.2, Codex 0.156.1)과 **확인한 것/못 한 것**을 분리("실제 마이크 녹음은 하지 않음", "합성 음성이며 실제 회의 정확도는 측정하지 않음"), 확인 중 발견한 버그(0초 길이 단어 누락)와 수정까지 기록(`MM:VALIDATION.md#L1-L30`). 이번 조사 규칙(검증 수준 구분)과 같은 형식.
- **Tractus README의 "데이터 → 어디로 가나" 표:** 오디오·목소리 프로필은 Mac 안, 요약·질문은 필요한 텍스트만 고른 AI 서비스로(`TR:README.md#L123-L131`). 로드맵에 **"사람만 할 수 있는 확인"**과 "알려진 한계"를 항목으로 둠(`TR:docs/roadmap.md#L40-L50`, `#L153`).
- **meeting-moa `docs/AI-PROVIDERS.md`:** 구독 CLI 호출 방식·약관 요지·확인일을 표로(`MM:docs/AI-PROVIDERS.md`). Takku는 `Claude Code at your own risk`(`TK:README.md#L62`), Tractus는 같은 약관을 보고 **구독 CLI를 공급자로 쓰지 않기로** 했다(`TR:ARCHITECTURE.md#L138-L146`, 2026-10-02: Claude Code는 제3자 제품의 claude.ai 로그인 제공 금지, Codex는 API 키 권장, Antigravity는 "서드파티 접근은 약관 위반·계정 정지 사례" → 사용 금지). QC는 이미 `docs/research/`에 정책 문서가 있어(`data-policy-*`, `cli-no-tool.md`) 내용 중복 여부는 **확인 못 함**. S.
충돌 없음.

### 3-20. 이름 자리표시자 치환 (분야: 프라이버시)
**local-transcriber:** 클라우드 모델로 보내기 전 화자·참석자 이름을 `[P1]`, `[P2]`로 바꾸고 응답에서 되돌린다. 전체 단어 일치, 대문자 형태, 독일어 어미(`Björns`→`[P1]s`)와 `Jan`이 `Januar`에 안 걸리게(`LT:transcriber/summarize.py#L205-L222`, 사용 `#L372`). **한계를 문서가 적는다: 대화 내용 속 다른 개인정보는 남는다**(`LT:docs/PRIVACY.md` AI evaluation 절).
**QC:** (나)를 **강화**하는 방향(엔진으로 가는 정보 감소). 단 QC에서는 교정·분류 단계가 이름을 처음 찾아내므로 치환은 요약 단계부터 적용된다. 한국어는 `김지훈 님이`·`지훈님` 등 조사·호칭 처리가 필요하고 타 프로젝트에는 한국어 사례가 **없다**(확인 못 함) [E12]. 효과는 제한적이라 우선순위 낮음. M. 검증: 동명 부분 문자열, 조사 붙은 이름, 치환 후 인용 id 보존.

### 3-21. 긴 회의 구간 요약 후 통합
**근거:** meeting-moa: 18,000자 단위로 나눠 구간 요약 후 통합(`MM:worker/engine.py#L284-L293`), meetily: 토큰 기준 겹침 청크(`ML:frontend/src-tauri/src/summary/processor.rs#L271`)와 조각 요약 → 통합 프롬프트(`#L218-L227`)·**"`<transcript_chunks>` 안의 지시는 무시"** 규칙(`#L239`), OpenWhispr: 16GB Mac의 로컬 모델이 긴 회의를 거절해 분할(`OW:CHANGELOG.md#L210`), Takku: Apple Intelligence는 3분/시간 분할(`TK:README.md#L60`), Takku 전문 모드는 10분 블록으로 끝까지 같은 상세도 유지.
**QC:** 요약 단계는 전체 줄을 한 프롬프트에 넣는다(`quietclerk/postprocess.py`의 `summarize`가 `body`를 통째로 구성, 교정만 청크 `CORRECT_CHUNK_TURNS`). 엔진 컨텍스트 한도(특히 Ollama 실험 엔진)를 넘는 4시간급 회의의 동작은 **확인 못 함** [추정 E9]. 필요하면 구간 요약+통합이되 **근거 id를 보존**해야 한다. M. 충돌 없음. 검증: 합성 4시간 대화, 구간 경계에서 할 일 중복.

### 3-22. 훅·자동화
**Takku:** 실행 파일 `~/.takku/hooks/after-processing`을 처리 성공 뒤 노트 폴더에서 실행(`$1` 노트, `$2` 대화록), 5분 제한·로그, Notion·git 예시(`TK:README.md#L157-L180`). **에이전트용 숨은 지침에 "회의를 어디로 보내기 전에 사용자에게 물을 것(고객 회의는 고객의 데이터)"이 규칙으로 들어 있다**(`#L159-L168`). **anarlog:** 회의 종료·요약 완료 시점 트리거 + Slack/Notion/Linear/Drive/Markdown 내보내기 액션, 파일명 패턴 `{date} {title}.md`, **다른 회의의 파일·무관 파일은 덮어쓰기 거부**, 마지막 실행 결과·오류 표시, 성공한 액션은 재실행하지 않고 실패한 것만 재시도(`AN:docs/automations.mdx#L1-L40`, `#L83`). Granola는 연동에 노트별 명시적 전송이 필요하고 자동 전송은 "고려 중"이라고 문서에 적는다(https://docs.granola.ai/help-center/feature-requests.md).
**QC:** `hooks/after-note`(인자: 노트 경로), 기본 꺼짐, 작업 로그에 결과, 훅이 외부로 보내는 것은 사용자 책임임을 설정 화면에 경고. QC에는 이미 properties `외부 전송 대상`이 있어 훅 사용 시 여기에 기록하면 맞는다. M. **원칙 충돌 조건부:** 훅 코드는 사용자 소유라 "동의한 엔진" 개념이 직접 적용되지 않는다 — 훅이 켜져 있다는 사실과 목적지를 홈 화면에 표시. 검증: 훅 실패·무한 루프(시간 제한), 노트 제목에 쉘 메타문자(인자 전달 시 인용), 환경변수로 API 키 새는지.

---

## 4. 프로젝트별 평가

| 프로젝트 | 한 줄 평가 | 가져올 것(위 항목) |
|---|---|---|
| Tractus | QC와 가장 가깝다(Apple Silicon MLX, Qwen3-ASR, Nemotron, Obsidian 보내기, 근거 링크). 설계 문서·측정·한계 기록이 상세하다. 구독 CLI는 약관상 공급자로 안 쓴다 | 3-1,2,3,4,7,9,10,11,12,13,15,16 |
| Takku | 템플릿·단어장 파일 형식이 단정하고, 보안(렌더 방어·읽기 전용 MCP) 결정이 문서화돼 있다. 구독 CLI 5종을 도구 없이 호출하는 방식이 QC와 같은 철학 | 3-2,3,5,9,14,17,18,19,22 |
| local-transcriber | 환각·루프 필터와 화자 신뢰도 표기가 실측 근거와 함께 코드에 있다 | 3-1,10,14,17,20 |
| OpenWhispr | 대규모 사용에서 나온 회의 버그 수정 이력이 쓸모 있다(팬텀 화자, 에코, 재개 세션). 제품은 받아쓰기 중심이라 회의 기능은 일부 | 3-4,6,8,21 |
| meetily | 이슈 수요 근거가 가장 풍부(👍 기준). 코드는 템플릿 JSON·요약 분할 정도. 화자 식별은 유료 | 3-3(수요),10(수요),18(사고 사례),21 |
| anarlog | 문서가 매우 구체적(가져오기 결과 4분류, 제안 후 승인하는 편집, 자동화 재시도). 클라우드 동기화·공유·웹 검색 채팅은 원칙상 제외 | 3-9,22, 6절 참고 |
| meeting-moa | 기능은 적고 **문서 관행(VALIDATION·AI-PROVIDERS·PRIVACY)이 좋다**. 구독 CLI 호출 보호 장치는 QC가 더 엄격(6절) | 3-19,21 |
| Recap | README가 "broken in its current state", "incomplete, 프로덕션 사용 비권장"이라고 적고(`RC:README.md#L40`, `#L45`, `#L75`), 마지막 커밋이 2026-02-07이다. 이슈 #12 "Retry Summarization triggers an entirely new transcription"은 단계 캐시 없이 재시도하면 생기는 문제의 예이며 QC는 단계 캐시가 이미 있다. **가져올 것 없음** | — |
| minutes (Baladhurgesh) | README에 전사·화자·0.6B 요약 파이프라인이 있으나 한국어 ASR이 없다(Parakeet v3). 모델 프로필 JSON(`BM:README.md#L81-`), 합성 샘플 회의 생성 스크립트(`#L128`, `#L136`), `127.0.0.1` + 실행마다 토큰 서버(`#L69`, QC는 이미 일회 토큰). **가져올 것 거의 없음** | 3-19(샘플 스크립트) |

---

## 5. Granola·Otter·Fireflies가 호평받는 기능 중 오픈소스가 따라 한 것 (참고만)

공개 도움말 열람. 호평의 근거(리뷰·점유율)는 **확인 못 함**: 이 표는 "그 회사가 문서로 내세우는 기능"과 "대상 오픈소스가 따라 한 근거"만 적는다.

| 상용 기능(출처) | 오픈소스가 따라 한 곳(근거) | QC 관련 |
|---|---|---|
| Granola 개선 노트: 내가 쓴 메모가 AI 정리를 이끈다(https://docs.granola.ai/help-center/taking-notes/ai-enhanced-notes.md) | Tractus "Granola가 시장에서 검증한 경험"이라고 설계 문서가 명시(`TR:docs/design/enhanced-notes.md#L13`), Takku `Personal notes` + 요약이 읽음(`TK:README.md#L20`, `#L88`), anarlog `Memos / Summary / Transcript` 3뷰(`AN:docs/notes.mdx#L6-L10`) | QC 입력은 폰 녹음이라 녹음 중 메모가 없다. 사후 Obsidian 메모를 재요약 입력으로 쓰는지는 **확인 못 함** [E7]. S~M |
| Granola 템플릿(기본 `auto`만 지정 가능, 기본 템플릿 설정은 요청 사항) (https://docs.granola.ai/help-center/feature-requests.md) | Tractus·Takku·meetily·anarlog 모두 사용자 템플릿 | 3-3 |
| Granola Recipes: 저장 프롬프트, 단일 회의/여러 회의 범위 구분(https://docs.granola.ai/help-center/getting-more-from-your-notes/recipes.md) | OpenWhispr "템플릿 + 노트 액션(프롬프트를 노트에 실행)"과 스킬 라이브러리(`OW:CHANGELOG.md#L202`), Tractus `직접 프롬프트로 요약` → `내 유형`으로 저장(`usage.md#L43`) | 3-3과 통합. "여러 회의에 실행"은 3-9 이후 |
| Granola 회의 전 브리프(밤새 준비) | Takku `meeting-prep` 스킬(`TK:README.md#L206`), anarlog `docs/recipes/meeting-prep.mdx` | QC는 캘린더·검색 이후에나 의미. 후순위 |
| Granola 후속 이메일 | local-transcriber 템플릿에 `follow-up email`(`LT:docs/FEATURES.md#L92`), anarlog 채팅 예시(`AN:docs/chat.mdx`) | QC: 템플릿 유형 하나로 가능(3-3) |
| Granola 용어 사용자화(Customizing transcription) | Tractus·Takku·local-transcriber·OpenWhispr·anarlog 사전 | 3-2 |
| Granola 화자 태그(회의 앱의 표시 이름) | 해당 없음(앱 연동). 대신 캘린더 참석자 이름 후보(Takku·local-transcriber·Tractus) | 3-8, 3-14 |
| Granola API·MCP·웹훅(키워드·참석자·폴더 필터 검색) | Tractus·Takku·anarlog·local-transcriber MCP, anarlog 웹훅(`AN:docs/reference/webhooks.mdx`) | 3-9, 3-22 |
| Granola 대화록 자동 삭제 정책 | Takku 오디오 기본 7일(`TK:README.md#L262`), anarlog 보관 선택 `Don't save`~`Forever`(`AN:docs/data-and-privacy.mdx#L46-L55`), local-transcriber 30일 옵션(`LT:docs/FEATURES.md#L33-L34`) | QC는 이미 `retention.wav_days: 7`(`quietclerk/config.py#L33`), 원본 m4a 보관 정책은 **확인 못 함** |
| Granola 한계: 전사 편집 불가, 오디오·영상 보관 계획 없음(feature-requests) | Tractus가 줄 편집·오디오 재생(`TR:docs/roadmap.md#L87`, `TR:docs/en/usage.md#L32`), anarlog가 전사 편집·오디오 보관 기간 선택(`AN:docs/notes.mdx#L18-L25`, `AN:docs/data-and-privacy.mdx#L46-L55`)으로 차별화 | QC는 오디오 재생이 있다 |
| Otter Action Items 전체 탭(여러 회의, 체크 시 완료, 근거 위치 이동) | Tractus `list_action_items`(MCP) 정도. 화면 수준으로 따라 한 곳은 **확인 못 함** | 3-15 |
| Fireflies Smart Search: 질문·과업·날짜·수치 필터, 화자 발화 비율·WPM, 90초 이상 독백, Topic Tracker 키워드 집계(https://guide.fireflies.ai/articles/2608597716-understand-fireflies-analytics-and-conversation-intelligence) | local-transcriber가 화자별 발화 시간 표만(`LT:transcriber/render.py#L63`). anarlog `Insights`는 요일·대화 수 같은 **활동량** 통계(`AN:docs/notes.mdx#L50-L54`)로 발화 분석이 아님. 나머지는 따라 한 곳 **확인 못 함** | 발화 비율만 3-14. 코칭·감정 분석은 개인 회의록 도구 범위 밖으로 판단(내 판단) |

---

## 6. QC가 이미 같거나 더 나은 것 (가져올 필요 없음, 근거 포함)

| 영역 | 타 프로젝트 | QC (코드·문서 근거) |
|---|---|---|
| 구독 CLI 호출 격리 | meeting-moa: Codex는 API 환경변수 제거+`login status`가 ChatGPT인지 확인, Claude는 환경 그대로(`MM:worker/engine.py#L203-L257`). Takku ADR 0017: 도구·설정·세션 없음, API 키 환경변수 제거(`TK:docs/adr/0017-agent-clis-run-with-nothing-of-the-users-setup.md`) | QC는 환경변수를 `PATH HOME USER TMPDIR CODEX_HOME`만 **허용 목록**으로 넘김(`quietclerk/providers/cli.py#L15-L17`), 엔진별 `verified/unverified` 도구 차단 상태와 명시 허용(`quietclerk/providers/__init__.py#L115`, `#L188-L229`). 같은 철학이고 허용 목록 방식이 더 엄격. 참고: Takku는 CLI가 스스로 업데이트되므로 **릴리스 전마다 실제 실행으로 플래그를 다시 검증**(`docs/TESTING.md`)한다 — QC의 `verified` 상태 재검증 절차가 문서화돼 있는지는 **확인 못 함** |
| 모델 재현성 | Minutes 프로필 JSON(자유 교체), Tractus 모델 선택 UI | QC는 HF 스냅숏을 **40자리 커밋으로 고정하고 실행 설정과 불일치하면 거부**(`quietclerk/backends/mlx.py#L24-L38`, `#L86-L93`) |
| 요약 근거 | Tractus 세그먼트 ID 검증·재요청, meeting-moa `[00:08]`, meetily 표에 시각 | QC는 문장마다 `[[#^t12|01:23]]` **Obsidian 블록 링크**로 노트 안에서 바로 이동하고, 존재하지 않는 인용은 `[?t99]`+`unknown_citation` 사유로 노출(`quietclerk/render.py#L106-L118`) |
| 렌더 방어 | Takku 이미지·HTML·링크 방어 | QC `safe_text`/`safe_summary`가 이미지·링크·`[[ ]]`·HTML·참조 정의를 이미 막음(`render.py#L91-L103`). 남은 틈은 3-5 |
| 단계 캐시·재개 | Recap 이슈 #12(재요약이 재전사를 유발) | QC는 단계별 캐시·재개·재시도(features 문서) |
| 중복·안정화 | local-transcriber(이름 바꾼 파일을 내용으로 인식), Takku(0Hz 헤더 파일이 앱을 멈춘 사고, `TK:CHANGELOG.md#L11`) | QC: SHA-256 중복, 디코딩·크기 검사, 격리 복사(features 문서) |
| 로컬 웹 화면 인증 | minutes `127.0.0.1` + 실행마다 토큰(`BM:README.md#L69`) | QC: 127.0.0.1 + 일회 토큰(features 문서) |
| 사용자 영역 보존 | Takku `%% takku:start/end %%` 밖은 건드리지 않음 | QC: 재요약해도 메모·제목·할 일 체크 보존(features 문서) |

---

## 7. 가져오지 않을 것 (또는 지금은 안 함)

| 항목 | 출처 | 이유 |
|---|---|---|
| 실시간 전사·미리보기 | Tractus `live.py`, meetily, OpenWhispr | QC 입력은 사후 파일. 참고: Tractus 측정에서 1.7B 표준 엔진은 실시간에 쓸 수 없다고 판정(확정 지연 p95 1.59~1.95초, 목표 1.0초)(`TR:docs/roadmap.md#L138-L151`) |
| 화상회의 봇·클라우드 공유 링크 | Tractus가 스스로 "하지 않는 것"으로 둠(`#L159-L160`) | (가)(나) 충돌 |
| 계정·팀 공간·클라우드 동기화·공유 | OpenWhispr, anarlog CloudSync | (나) 회의 텍스트를 외부 서버에 보관. anarlog는 종단간 암호화라고 적지만 서버 보관 자체가 QC 원칙과 다름 |
| 웹 검색이 섞인 채팅 | anarlog `Chat can also search the public web… the search query leaves your device`(`AN:docs/chat.mdx`) | (나) |
| 사용 통계·세션 리플레이 | anarlog(PostHog, 끄는 설정) | 기본값이 켜짐인지는 **확인 못 함**. QC는 계측을 두지 않는 편이 원칙과 맞음 |
| 스크린샷 삽입·핫키 표식 | Takku | 폰 녹음 입력이라 해당 없음 |
| 받아쓰기 핫키·메뉴 막대 앱 | OpenWhispr, local-transcriber, Tractus | 제품 범위 밖 |
| Windows·Linux | meetily #32 "Linux support"(열림, 👍31로 해당 저장소 최다), OpenWhispr | QC는 MLX·Apple Silicon 전제. 요청이 많다는 사실만 기록 |
| Vault로 오디오 복사 | Tractus `Send to Obsidian` 오디오 포함 옵션(기본 꺼짐, `TR:docs/design/obsidian-export.md` 결정 3), | Obsidian Sync·iCloud가 vault를 동기화하면 음성이 Mac 밖으로 나간다 → (가) 충돌. 한다면 기본 꺼짐+경고 |
| 한국어 파인튜닝 ASR 추가 | Tractus 0.5.2~0.5.3(TeamUNIVA 8bit 변환본 4.7GB→2.5GB, 약 30% 빠름, `roadmap.md#L36-L37`) | 정확도 근거를 이 조사에서 **확인 못 함**. 후속 조사 후보 |

---

## 8. 입력 유형별 처리 방침 (이 조사가 더하는 것)

기존 처리는 features 문서와 코드 확인 범위. "제안"은 위 항목 도입 시의 방침이다.

| 입력 | QC 현재 | 제안 |
|---|---|---|
| 정상 m4a(5분 이상) | 처리 | — |
| Syncthing 전송 중·중복·5분 미만·디코딩 불가·크기 초과 | 안정화 대기·SHA-256·건너뜀·격리(features) | 변경 없음 |
| 전 구간 무음·거의 무음 | **확인 못 함**(처리 방침 문서 없음) | ASR 전 판정 → `silent`로 건너뜀 + 노트·작업 화면에 사유 (3-1) |
| 소음·배경음악만, 긴 침묵 | 환각 가능(코드상 검사 없음) | 환각·루프 필터 + `dropped` 기록 (3-1) |
| 맞장구가 많은 대면 회의 | 가상 화자 가능(코드상 정리 없음) | 팬텀 화자 재배정 (3-6) |
| 한 사람 독백·화자 9명 이상 | Nemotron 8명 한계 | 변경 없음, 3-6의 오발동 회귀 테스트 |
| 대화 내용에 지시문·마크다운·HTML·Dataview | 프롬프트가 "데이터로 취급", 렌더가 이스케이프 | 3-5의 펜스·Dataview 방어 |
| 단어장·템플릿·일정 제목(새 입력) | 해당 기능 없음 | 3-2·3-3·3-8의 각 악의 입력 테스트 |
| 매우 긴 회의(수 시간) | **확인 못 함** | 3-21 |

## 9. 비정상·악의 입력 테스트 모음 (구현 시 공통 체크)

| 범주 | 케이스 | 해당 항목 |
|---|---|---|
| 무음·환각·루프 | 전부 0 WAV, -60 dBFS 잡음, 한 단어 200회, 맞장구만, 실제 상투 문구가 발화 안에 | 3-1 |
| 프롬프트 탈출 | 단어장·템플릿·일정 제목·화자 이름에 구분자·지시문, 구분자 중첩 | 3-2, 3-3, 3-8 |
| 마크다운·Dataview | 펜스 길이·`~~~`·인용 안 펜스·인라인 `` `= ``, `\r` 이름, `%%`, `^t` 위조 | 3-5 |
| 화자 | 2인+맞장구, 독백, 실제 소수 3번째 발언자, 9명 이상 | 3-6 |
| 검색·MCP | FTS 구문, `../`, 존재 않는 id, 큰 limit, 삭제 후 잔재 | 3-7, 3-9 |
| 목소리 | 동의 없는 등록, 임계값 경계, 같은 목소리 두 클러스터, 15초 미만, 권한 | 3-10 |
| 파일·내보내기 | 한글 파일명, CSV 인용, 큐 길이 0 | 3-11 |

---

## 10. 사용자 호응 근거 요약

| 항목 | 근거 | 수준 |
|---|---|---|
| 템플릿 설정 | meetily #243 (👍11, 열림), #233 (👍16), #413 (👍7) | 이슈 반응(수치) |
| 화자 식별 | meetily #226 (👍15, 열림), #230 (👍7, 댓글 18) | 이슈 반응(수치) |
| Homebrew | OpenWhispr #707 (👍8), #681 (👍6) | 이슈 반응(수치) |
| 환각 문구 | OpenWhispr #462 (👍2, 댓글 14, 열림) | 이슈 반응(수치) |
| 사후 처리 요청 | OpenWhispr #1914 "record meeting audio and transcribe after the call ends"(👍2, 열림), meetily #238 "Offline/already recorded meetings processing"(👍9, 닫힘) — QC의 사후 처리 방향과 일치 | 이슈 반응(수치) |
| 나머지(Tractus·Takku·local-transcriber·meeting-moa·minutes·anarlog) | 사용자 이슈 반응 **확인 못 함** | 문서·코드 구체성만 |

---

## 11. 열린 항목([추정]·확인 못 함) — 담당·확인 시각

담당·시각은 **제안**이며 Main이 확정한다. 제안 담당은 영역 기준(받아쓰기=PeersTranscribe, 파이프라인=PeersPipeline, 화면=UpdateUI, 백엔드=UpdateBackend). 확인 시각 기준은 KST.

| ID | 내용 | 확인 방법 | 제안 담당 | 제안 확인 시각 |
|---|---|---|---|---|
| E1 | QC 환경의 `mlx_audio` Qwen3-ASR `generate`가 `hotwords`를 받는가(Tractus는 같은 라이브러리에 전달) | 설치된 버전에서 시그니처 확인 + `samples/audio` 1건으로 용어 재현율 전/후 | PeersTranscribe | 2026-11-11 18:00 |
| E2 | 팬텀 화자 규칙(10%·3초)이 Nemotron 출력에서 유효한가, 실제 3번째 발언자 오삭제율 | `samples/audio` 4건의 화자 분포 측정 | PeersTranscribe | 2026-11-11 18:00 |
| E3 | 한국어 2차 패스(Whisper)에서 환각이 나는가, 단어 확률·음량 입력을 쓸 수 있는가(`mlx_whisper` 단어 필드) | 무음 합성 파일 + 샘플 4건 + 단어 필드 출력 확인 | PeersTranscribe | 2026-11-11 18:00 |
| E4 | 파일명 `yymmdd_hhmmss`가 녹음 시작 시각인가(캘린더 연결 전제) | 폰 원본 파일 메타데이터와 대조 | PeersPipeline | 구현 착수 전 |
| E5 | ITN이 QC 파이프라인(교정·2차 패스 거침)에서도 개선되는가 | QC 산출물에 규칙 적용해 한글 수사 비율·오변환 측정 | PeersTranscribe | 구현 착수 전 |
| E6 | 요약 경유 Dataview 실행 가능성 | 격리 vault에서 테스트 노트 1건 — 3-5 구현 테스트로 닫음 | PeersPipeline | 3-5 구현 PR 전 |
| E7 | QC 현재 동작 확인 못 함: 화자 이름 편집, 대화록 줄 수정 보존, 재생 배속, 재요약 시 사용자 메모 반영 | QC 웹 화면·코드 확인 | UpdateUI / UpdateBackend | 2026-11-11 12:00 |
| E8 | 사용자 호응: anarlog(이슈 비활성)·소형 프로젝트 반응 | **닫음: "확인 못 함"으로 확정**(추가 조사 안 함) | — | 닫힘 |
| E9 | 4시간급 긴 회의의 요약 단계 동작(컨텍스트 한도) | 합성 장시간 대화로 한 번 실행 | PeersPipeline | 구현 착수 전 |
| E10 | Obsidian Bases로 `^task` 체크박스를 모아 "열린 할 일" 보기를 만들 수 있는가 | 격리 vault에 테스트 노트 3건과 Bases 파일로 확인 | UpdateBackend | 2026-11-12 18:00 |
| E11 | Homebrew 배포가 launchd 상주·모델 다운로드·`update` 롤백과 충돌하지 않는 구조 | 설계 메모 1장(포뮬러가 서비스를 직접 등록하는지, 업데이트 경로 이중화) | UpdateBackend | 구현 착수 전 |
| E12 | 이름 자리표시자 치환의 한국어 조사·호칭 처리 | 한국어 문장 20개로 치환·복원 왕복 테스트 | PeersPipeline | 구현 착수 전 |
| E13 | launchd 상주 서비스(또는 Swift 헬퍼)가 캘린더(TCC) 권한을 받는 방식 | 헬퍼를 앱 번들 없이 실행했을 때 권한 요청이 뜨는지 실제 Mac에서 확인 | UpdateBackend | 3-8 착수 전 |
| E14 | QC 문서 쪽 확인 3건: ① `docs/research/`의 약관·정책 문서와 3-19 제안의 중복 ② 구독 CLI `verified` 상태 재검증 절차 문서 유무(6절) ③ 원본 m4a 보관 정책(5절) | 해당 문서·코드 열람 | Main | 2026-11-11 12:00 |

---

## 12. 조사 한계

- 코드 실행 없음. 타 프로젝트 동작은 코드·문서 열람 기준이며 실제로 그렇게 동작하는지는 실행하지 않았다.
- 타 프로젝트 수치(CER, 재현율, EER, hit@1)는 전부 자체 측정이다. 특히 Tractus의 목소리·검색·ITN 수치는 AI Hub 데이터 기반이며 갤럭시 단일 마이크 대면 녹음에서의 값은 알 수 없다.
- meetily·OpenWhispr의 호응은 GitHub 👍 수로만 봤다. anarlog는 이슈 비활성으로 확인 못 함.
- Granola·Otter·Fireflies는 각사 공개 도움말만 봤고 호평(리뷰·점유율)은 조사하지 않았다.
- `local://quietclerk-features.md`와 QC 저장소(2026-11-10)를 현재 상태로 가정했다. 그 사이 변경은 반영하지 않았다.
