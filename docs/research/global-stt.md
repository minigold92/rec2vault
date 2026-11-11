# 글로벌·구독 기반 STT 조사 (한국어 녹음 → 전사 + 화자 분리 + 요약)

- 조사일/확인일: **2026-11-09** (아래 모든 URL은 이 날 직접 열어 확인)
- 표기: **[확인]** = 해당 페이지에서 직접 읽음 / **[추정]** = 페이지에 없고 내가 추론 / **[2차]** = 블로그·서드파티·벤더 자체 발표 / **확인 못 함** = 찾지 못함
- 요구 사항 기준: 한국어, **2명 이상 화자 분리**, 구간·단어 타임스탬프, 요약·할 일 추출, Mac mini에서 자동화
- 2026-11 기준 모델 세대가 바뀌었다는 점이 핵심: OpenAI는 `whisper-1`·`gpt-4o-transcribe`·`gpt-4o-transcribe-diarize`를 **2027-02-26 종료**로 공지했고 새 기본 모델은 `gpt-transcribe`; Google은 전용 STT 모델 `gemini-3.5-transcribe`(2026-08)를 냈다.

---

## 0. 먼저 읽을 핵심 발견

1. **구독(앱)과 API 과금은 별개** (3절 표 참고). Gemini Pro/ChatGPT Plus를 내고 있어도 API 전사는 별도 과금(Google Cloud Billing / OpenAI API 크레딧).
2. **ChatGPT 앱 자동화는 약관 위반 소지가 큼.** OpenAI 이용약관에 "Automatically or programmatically extract data or Output" 금지 조항이 있고, Pro 안내 문서도 "automatically extracting data are prohibited … may restrict access"라고 명시. → ChatGPT 웹/앱을 ego-lite·Aside로 자동 조작하는 경로는 권하지 않는다. 같은 모델은 API로 호출하는 게 맞다.
3. **OpenAI는 새 권장 모델 `gpt-transcribe`에 화자 분리·타임스탬프가 문서화돼 있지 않다.** 화자 분리는 단종 예정 `gpt-4o-transcribe-diarize`뿐. 화자 분리가 필수인 이 프로젝트에선 OpenAI 단독 파이프라인이 장기적으로 불리.
4. **Gemini 3.5 Transcribe**는 한국어(ko-KR)+화자 분리(최대 8명)+단어 타임스탬프를 API로 제공하지만 **화자 분리/타임스탬프를 켜면 요청당 30분 제한**. 긴 녹음은 분할해야 하고, 분할 간 화자 라벨 일관성은 문서에 보장 없음 [추정].
5. **공개 한국어 벤치마크에서 ElevenLabs Scribe v2가 일관되게 상위권** (단, 일부는 이해관계 있는 출처 — 8절). Deepgram Nova-3는 한국어에서 가장 낮게 나옴. AssemblyAI는 한국어 근거가 약함.
6. **한국어 화자 분리(DER) 공개 수치는 어느 상용 서비스에서도 찾지 못함.** 화자 분리 품질은 실측으로만 판단 가능.

---

## 1. Google

### 1-A. Gemini 앱 (구독: 무료 / Google AI Plus / Pro / Ultra)

1. **한국어 STT**: 앱에서 오디오 업로드 후 "전사해 줘" 프롬프트로 가능(공식 기능 문서는 업로드·분석 일반 설명; 한국어 정확도 근거는 확인 못 함). 전용 전사 UI가 아니라 채팅 모델 기반.
2. **화자 분리**: 공식 문서 없음. 프롬프트로 "화자 구분" 요청하는 방식 [2차: findskill.ai·vomo.ai 블로그는 가능하다고 설명]. 최대 화자 수·화자 수 지정: 확인 못 함.
3. **타임스탬프**: 프롬프트 요청으로 텍스트에 포함시키는 방식 [추정]. 구조화 타임스탬프 보장 없음.
4. **요약·할 일**: 가능(채팅 모델의 일반 기능, 프롬프트로 결정 사항·할 일 추출).
5. **입력/길이/크기**: 오디오 **총 길이 무료 10분 / Google AI Pro·Ultra 3시간**, 비영상 파일 **100MB/개**, 한 프롬프트 최대 10파일. Android·웹·데스크톱 동일 수치. Google AI Plus 등급은 문서에 언급 없음(확인 못 함). 컨텍스트 윈도우도 무료 대비 Pro는 1M 토큰.
   - 출처: https://support.google.com/gemini/answer/14903178 (Android: `?co=GENIE.Platform%3DAndroid`)
6. **가격**: 무료 ₩0 / Google AI Plus ₩7,500/월 / **Google AI Pro 한국 월 가격은 가져온 페이지에 금액이 안 나옴(확인 못 함)** / Ultra ₩119,000~/월(AI Pro 대비 5배 한도)·₩300,000/월(20배). 업로드 한도는 "채팅 파일 업로드 롤링 리밋"도 있음.
   - 출처: https://gemini.google/subscriptions/ , https://one.google.com/about/google-ai-plans/?hl=ko
7. **접근/자동화**: 앱 전용(웹 gemini.google.com 포함), **공개 API 없음**(앱과 별개로 Gemini API가 있음 → 1-B). 자동화는 브라우저 자동화(Aside/ego-lite)만 가능. 한 프롬프트 10파일·롤링 리밋·계정 로그인 유지 필요.
8. **내보내기**: 채팅 응답 텍스트 복사. Docs 내보내기 등 구조화 내보내기 이 조사에선 확인 못 함.
9. **데이터 정책**: Keep Activity 켜면 대화가 기본 18개월 보관(조정 가능), 인간 검토를 거친 대화는 계정에서 분리돼 **최대 3년 보관**, 모델 개선 사용. Keep Activity 끔/임시 채팅은 72시간 보관 후 학습에 쓰지 않음.
   - 출처: https://support.google.com/gemini/answer/13594961
10. **약관상 자동화**: Google 이용약관 "Don't abuse our services"에 보호 장치 우회, robots.txt를 어기는 자동 접근, 가짜 계정 등이 금지. **개인 계정을 브라우저로 자동 조작하는 것 자체를 명시적으로 금지하는 문구는 확인 못 함**, 다만 비정상 트래픽 판정으로 인한 계정 제한 리스크는 있다 [추정]. 출처: https://policies.google.com/terms?hl=en
11. **공개 한국어 정확도**: 앱 자체 수치 없음. 같은 계열 모델의 API 벤치는 1-B 참고.

**판단: 실측 비교에 넣을 가치 — 조건부(수동 1~2건만).** 이유: 구독 한도(Pro 3시간)로 "비용 0원 추가"가 되는지 보는 용도로는 의미 있지만, 자동화가 약관 회색지대이고 구조화 출력(화자·타임스탬프)이 불안정해 상시 파이프라인으로는 API(1-B/1-C)가 낫다.

### 1-B. Gemini API — ① `gemini-3.5-transcribe` (전용 STT) ② `gemini-3.8-flash` 등 오디오 이해(LLM)

**① gemini-3.5-transcribe** (2026-08 업데이트)

1. **한국어**: 지원, `ko-KR` (85개+ 언어, 자동 감지·코드 스위칭).
2. **화자 분리**: 지원. `diarization_mode: "speaker"`(verbatim 모드), 라벨 `spk_1`, `spk_2`… **최대 8명, 3명 이상 귀속은 "experimental"**. 화자 수 지정 파라미터는 문서에 없음. 커스텀 어휘(custom_vocabulary)·smart 모드와 **동시 사용 불가**.
3. **타임스탬프**: 단어 단위(`timestamp_granularities: ["word"]`), `start_offset`/`end_offset`. **켜면 정확도가 떨어질 수 있다고 문서가 경고**.
4. **요약·할 일**: 이 모델에는 없음(전사 전용). 같은 API의 다른 모델(②)에 전사 텍스트나 오디오를 넣어 요약해야 함.
5. **입력/길이**: 오디오 **요청당 최대 1시간, 화자 분리 또는 단어 타임스탬프를 켜면 30분**. Batch/Flex/Priority 추론 미지원. 파일은 Files API 업로드(20MB 초과), 인라인은 요청 전체 20MB 이하.
6. **가격**: 입력 $2.00/1M 토큰(= **$0.003/분**, 오디오 25토큰/초 기준) + 출력 $12.00/1M(= $0.002/분) → **합산 약 $0.005/분(≈ $0.30/시간)**(Google 자체 추정치). 무료 티어 있음.
7. **접근**: 공개 API(REST/SDK). 자동화 = API 호출(스크립트 그대로 가능).
8. **출력**: JSON(`output_text` + `word_info` annotations: text, speaker, start_offset, end_offset). SRT/DOCX 내보내기는 없음 → 직접 변환.
9. **데이터 정책**: **무료 티어는 입력·출력이 Google 제품 개선에 사용되고 사람이 검토할 수 있음("민감·개인 정보 넣지 말 것")**. **유료(Cloud Billing 연결) 티어는 학습 미사용**, 오남용 탐지용 로그를 한시적 보관. 즉 개인 대화 녹음이면 **유료 티어로 써야** 한다.
10. **약관 자동화**: API이므로 자동 호출은 정상 경로. Gemini API 추가 약관은 "개발자의 업무/사업 목적용, 소비자용 아님" 문구와 경쟁 모델 개발 금지·역공학 금지가 있음(개인 사이드 프로젝트가 문제되는지는 문구상 확인 못 함).
11. **공개 한국어 정확도**: 이 모델 자체의 한국어 공개 벤치는 **확인 못 함**(출시 2026-08, 아래 koedesk는 07-05 실행이라 미포함). 인접 모델: koedesk FLEURS 한국어 Gemini 3.1 Pro WER 11.46 / CER 5.30, Gemini 3.5 Flash WER 12.48 / CER 5.72 (8절 [2차·이해관계 있음]).

- 출처: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-transcribe (본문은 https://aistudio.google.com/docs/models/gemini-3.5-transcribe), https://ai.google.dev/gemini-api/docs/transcribe , 가격 https://ai.google.dev/gemini-api/docs/pricing , 약관 https://ai.google.dev/gemini-api/terms

**② 오디오 이해(프롬프트로 전사·화자 라벨·요약, 예: `gemini-3.8-flash`)**

1. 한국어 STT: 가능(Gemini 일반 오디오 이해, 공식 한국어 수치 없음).
2. 화자 분리: **프롬프트+JSON 스키마로 받는 방식**(공식 예제: "Identify distinct speakers (Speaker 1, 2), 타임스탬프 MM:SS, 요약을 앞에 붙여라"). 모델이 "추정"하는 라벨이라 정밀 DER 보장 없음. 화자 수 지정은 프롬프트로 지시할 뿐.
3. 타임스탬프: 구간 단위(MM:SS) 프롬프트 요청. 단어 단위 보장 없음.
4. **요약·할 일: 같은 호출에서 가능**(요약 필드·결정 사항·할 일을 스키마로 지정).
5. 입력/길이: **프롬프트당 최대 9.5시간 오디오**, 32토큰/초(1분=1,920토큰), 16kbps로 다운샘플·다채널은 모노로 합침. 인라인 20MB 이하, 초과는 Files API.
6. 가격(gemini-3.8-flash 표준): 입력 $0.75/1M 토큰, 출력(사고 토큰 포함) $3.75/1M — **2026-12-31까지, 2027-01-01부터 입력 $1.50 / 출력 $7.50로 2배**. 표에 오디오 단가가 따로 구분돼 있지 않음(단일 입력가 표기). 입력만 계산하면 1시간 = 115,200토큰 ≈ $0.09(12월까지) [계산]. 출력(전사 텍스트) 토큰이 추가됨.
7. 접근/자동화: 공개 API → API 호출.
8. 출력: 텍스트/JSON(스키마 지정).
9. 데이터 정책: 1-B①과 동일(무료=학습 사용, 유료=미사용).
10. 약관 자동화: 1-B①과 동일.
11. 한국어 정확도: LLM형 전사는 **긴 오디오에서 지시문·영어 설명을 대신 출력하는 실패 사례**가 보고됨(koedesk: Gemini 2.5 Pro 중국어 1건에서 약 4,800자 영어 추론 텍스트 출력) → 환각·누락 검증 필요.
- 출처: https://ai.google.dev/gemini-api/docs/audio (본문 https://aistudio.google.com/docs/audio), https://ai.google.dev/gemini-api/docs/pricing

**판단: 실측 비교에 넣을 가치 — 높음(①②둘 다).** 이유: ①은 한국어+화자 분리+단어 타임스탬프를 $0.30/시간 수준으로 주고, ②는 "전사+화자+요약·할 일"을 한 번에 해결해 파이프라인이 가장 단순. 대신 ①의 30분 제한/화자 일관성, ②의 환각을 실측으로 확인해야 한다.

### 1-C. Google Cloud Speech-to-Text v2 (Chirp 3)

1. **한국어**: Chirp 3 `ko-KR` GA.
2. **화자 분리**: **`ko-KR` 지원**(Chirp 3 화자 분리 언어 목록에 한국어 포함). **BatchRecognize(권장)·Recognize**에서 동작, StreamingRecognize에서는 불가. 일반 STT 문서는 `min_speaker_count`/`max_speaker_count` 지정을 요구하고, Chirp 3 샘플은 빈 `SpeakerDiarizationConfig()`만 사용(최대 화자 수 상한은 확인 못 함). 문서 내 모순: 기능 표는 "Batch에서만", 언어표는 "Batch·Recognize" — 실사용 시 Batch로 시험.
3. **타임스탬프**: 단어 단위 가능(Recognize/Batch, "다소 정확도 저하 예상"), 발화 단위는 Streaming에서만. 같은 문서 안에서 단어 타임스탬프가 "지원 기능"과 "미지원 기능" 표에 모두 언급돼 문구가 모호 → 실측 필요.
4. 요약·할 일: **없음**(순수 STT).
5. **입력/길이**: BatchRecognize 일반적으로 **1시간까지, 단어 타임스탬프 켜면 20분까지**. Chirp 3 리전은 `us`·`eu` 멀티리전(한국 리전 없음 → 오디오가 미국/EU로 감).
6. **가격(v2)**: Standard **$0.016/분**(월 50만분까지, 초 단위 과금), **Dynamic batch $0.003/분**. Chirp 3가 어느 SKU인지 표에 명시 안 됨(chirp 계열은 Standard¹에 포함, Chirp 3는 [추정] 동일). 무료 한도: v1은 월 60분 무료, v2 표에는 무료 행 없음.
7. 접근/자동화: 공개 API(Google Cloud 서비스 계정, GCS 업로드 필요). 자동화 = API.
8. 출력: JSON(단어·speakerLabel). SRT/DOCX 등은 직접 변환.
9. **데이터 정책**: Cloud STT는 **기본적으로 오디오·전사를 로깅하지 않음**. "data logging" 프로그램에 옵트인하면 Google이 개선에 사용하고 대신 할인(v1 문서 기준).
10. 약관 자동화: API라 정상 경로.
11. **한국어 정확도**: koedesk FLEURS 한국어 Chirp 3 WER 11.49 / CER 5.30 (T2) [2차·이해관계 있음]. GigaSpeechBench 한국어 CER 15.96. AeCeCi 회의 1,000클립에서 Google STT v2 `latest_long`(Chirp 3 아님) CER 16.75(교정 13.00) [2차].
- 출처: https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3 , https://cloud.google.com/speech-to-text/pricing , https://docs.cloud.google.com/speech-to-text/docs/multiple-voices , https://docs.cloud.google.com/speech-to-text/docs/data-logging

**판단: 실측 비교에 넣을 가치 — 낮음~중(1~2건 샘플만).** 이유: 한국어 화자 분리가 지원되는 건 확실하지만, 20분 제한(단어 타임스탬프)·GCS·서비스 계정 설정이 필요하고 가격($0.96/시간)이 Gemini 3.5 Transcribe(≈$0.30/시간)보다 높은데 한국어 벤치가 압도적이지 않다. 비교 기준선 "Google 전통 STT" 한 건 정도만.

### 1-D. Google Recorder 앱

- **Pixel 전용**: Play 스토어 페이지는 기기 제한을 명시하지 않지만, Google 도움말이 전부 "Pixel 기기" 문서이며 서드파티 문서가 "Pixel 3 이상·Pixel Tablet에서만 실행"이라 설명 [2차: https://flintvoice.app/blog/google-recorder-android]. 갤럭시 S25에는 해당 없음.
- 참고: 실시간 전사 지원 언어 목록(Pixel 6+)에 한국어 없음, "다시 전사" 언어 목록엔 Korean 있음, AI 요약은 Pixel 8+ 일부 언어(한국어 제외). 출처: https://support.google.com/pixelphone/answer/16267698 , https://play.google.com/store/apps/details?id=com.google.android.apps.recorder

**판단: 실측 비교에 넣을 가치 — 없음(갤럭시 불가).**

---

## 2. OpenAI

### 2-A. ChatGPT 구독 (Go / Plus / Pro / Business…)

1. **한국어 STT**: 오디오 파일 업로드 후 전사 가능. Record 모드는 "영어에서 가장 잘 동작, 다른 언어 정확도는 편차" 라고 OpenAI가 명시. (한국어 수치 확인 못 함)
2. **화자 분리**: Record 모드는 다화자 구분 + "Speaker 1" 등 라벨(이름 변경 가능). 파일 업로드 경로는 **"speaker identification may be unreliable"** 이라고 도움말에 명시. 최대 화자 수·지정 가능 여부: 확인 못 함.
3. 타임스탬프: Record 모드/업로드 모두 구조화 보장 문서 없음(확인 못 함).
4. **요약·할 일**: 가능 (회의록·결정 사항·후속 질문·할 일 메일 초안 등).
5. **입력/길이/크기·플랫폼**: 오디오 업로드는 **유료 구독 한정(무료 불가)**, 형식 WAV·MP3/MPEG·OGG·FLAC·AAC·M4A·오디오 전용 MP4/WebM, **파일 최대 512MB**, 긴 녹음은 "best-effort, 매우 길면 타임아웃". 분 단위 한도 명시 없음. **Record 모드는 macOS 데스크톱 앱 전용**(1세션 최대 4시간, 마이크·시스템 오디오 캡처, **Android 미지원**). Meetings 플러그인도 macOS(Pro·Business, iOS·Android는 "coming soon"). Android 앱에서 오디오 업로드 가능 여부는 문서에 명시 없음. Mac mini에서는 Record로 "라이브 캡처"는 되지만 기존 녹음 파일 일괄 처리용이 아니다.
6. **가격**: Plus $20/월, Pro 100/200/500 = $100/$200/$500/월. Go 가격은 확인 못 함. Pro 요금제 설명에 "월 API 크레딧 포함"이라고 나오나 금액이 비어 있어 확인 못 함(API 크레딧은 별도 API 조직에 귀속).
7. 접근: **앱 전용**(공개 API 아님). 자동화 = 브라우저/앱 조작뿐.
8. 내보내기: Record = canvas/노트로 저장, 변환(이메일·계획 등). SRT/JSON 없음.
9. **데이터 정책**: Record 오디오는 전사 후 삭제, 학습 미사용. **Plus/Pro/Free에서 "Improve the model for everyone"이 켜져 있으면 전사·canvas가 학습에 쓰일 수 있음(옵트아웃 가능)**; Business/Enterprise/Edu는 기본 제외. 삭제 시 30일 내 제거. 업로드 파일은 Library/Space에 별도 보관될 수 있음.
10. **약관 자동화 제한: 있음 — 금지.** "Automatically or programmatically extract data or Output" 금지, Pro 문서는 계정 제한 가능성을 명시. 출처: https://openai.com/policies/row-terms-of-use/ , https://help.openai.com/en/articles/9793128-about-chatgpt-pro-tiers
11. 공개 한국어 정확도: 앱 자체 수치 없음.
- 출처: https://help.openai.com/en/articles/11487532-chatgpt-record , https://help.openai.com/en/articles/8555545-uploading-files-and-audio-to-chatgpt , https://help.openai.com/en/articles/20001546 , https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus-and-pro

**판단: 실측 비교에 넣을 가치 — 제외 권장(수동 1회 샘플만).** 이유: 약관이 자동화를 금지하고, Record는 macOS 라이브 캡처·영어 위주이며, 업로드는 화자 정확도 경고가 있다. 같은 계열 모델의 품질은 API(2-B)로 본다.

### 2-B. OpenAI API — `gpt-transcribe` (권장 최신 파일 전사 모델)

1. **한국어**: 공식 권장 "원어 전사" 모델. 문서의 언어 파라미터는 ISO 639-1 코드를 받음(`ko` 허용). **지원 언어 목록·한국어 명시는 문서에 없음(확인 못 함)**.
2. **화자 분리: 문서화 안 됨.** 응답은 `text` + 감지 언어(`languages`)만. 화자 분리는 단종 예정 `gpt-4o-transcribe-diarize`에 있음(2-C).
3. **타임스탬프: 문서화 안 됨.** `timestamp_granularities`는 `whisper-1`(2027-02-26 종료)에서만 지원한다고 명시. 가이드도 "모델 ID만 바꿔서는 기존 기능이 보존되지 않는다"고 경고.
4. 요약·할 일: 없음(별도 LLM 호출 필요).
5. 입력/길이: **파일 최대 25MB**, 형식 mp3·mp4·mpeg·mpga·m4a·wav·webm(API 레퍼런스는 flac·ogg 추가). 분 단위 길이 한도는 새 문서에서 확인 못 함. 25MB 초과는 압축 또는 분할 권장. [계산] 64kbps 모노 압축이면 약 52분, 32kbps면 약 104분이 25MB. 스트리밍 출력 지원. `prompt`·`keywords`·`languages`로 문맥 힌트.
6. **가격**: **$0.0045/분 ($0.27/시간)**. 실시간용 `gpt-live-transcribe`는 $0.017/분. 무료 한도는 없음(API 크레딧 선결제).
7. 접근/자동화: 공개 API → API 호출. (ChatGPT 구독과 **과금 별개**)
8. 출력: JSON(`text`, `languages`). srt·vtt·verbose_json 등은 구형 모델용.
9. **데이터 정책**: API 데이터는 **기본적으로 학습에 사용되지 않음(2023-03-01 이후)**. `/v1/audio/transcriptions`는 표상 **남용 모니터링 보관 "None"**, 애플리케이션 상태 보관 None, ZDR 적격. 한국 데이터 레지던시(`kr.api.openai.com`)는 저장 지역만 가능, 처리는 지역화 안 됨(승인·MAM/ZDR 필요).
10. 약관 자동화: API는 정상 경로(별도 Business Terms 적용).
11. **공개 한국어 정확도**: `gpt-transcribe` 한국어 수치는 **확인 못 함**(일본어 소규모 비교만 존재 [2차]). 이전 세대 `gpt-4o-transcribe`: koedesk FLEURS 한국어 WER 12.31 / CER 5.41 (T2), 한국어-영어 혼용 HiKE(EACL 2026 Findings)에서 10개 모델 중 최상 MER 21.8 [2차: 컴파일 인용], 반면 GigaSpeechBench 실환경 한국어 CER **41.31로 한국어 값이 있는 14개 중 최하위**(8절) — 혼재.
- 출처: https://developers.openai.com/api/docs/guides/speech-to-text , https://developers.openai.com/api/docs/models/gpt-transcribe , https://developers.openai.com/api/docs/guides/transcription , https://developers.openai.com/api/docs/deprecations , 가격 https://developers.openai.com/api/docs/pricing , 데이터 https://developers.openai.com/api/docs/guides/your-data

### 2-C. OpenAI API — `gpt-4o-transcribe-diarize` (화자 분리, **2027-02-26 종료 예정**)

1. 한국어: 문서 명시 없음(확인 못 함).
2. **화자 분리**: `response_format=diarized_json`으로 `speaker`·`start`·`end`가 붙은 세그먼트. 30초 초과 오디오는 `chunking_strategy: "auto"` 필수. 알려진 화자 이름 매핑용으로 2~10초 참조 클립 **최대 4개**. 최대 화자 수·"화자 수 지정"은 문서에 없음(확인 못 함). `prompt` 미지원. Realtime 세션에서는 미지원.
3. 타임스탬프: 세그먼트 단위(start/end).
4. 요약: 없음.
5. 입력: 25MB, 위와 동일.
6. 가격: **$0.006/분 ($0.36/시간)**.
7~10. API, JSON, API 데이터 정책 동일(2-B).
11. 한국어 화자 분리/DER 공개 수치: 확인 못 함.
- **단종 예정이라는 점이 결정적**: 공지(2026-08-26)에서 대체 모델은 `gpt-live-transcribe` 또는 `gpt-transcribe`인데, 둘 다 화자 분리가 문서화돼 있지 않다 → 2027-02 이후 OpenAI 쪽 화자 분리는 공백이 된다.

**판단(2-B/2-C): 실측 비교에 넣을 가치 — 중간.** 이유: `gpt-transcribe`는 저렴($0.27/시간)한 "텍스트 정확도 기준선"으로 한 번 넣을 가치가 있으나 화자 분리·타임스탬프가 없어 단독으로는 요구 사항을 못 채운다. `gpt-4o-transcribe-diarize`는 지금 시험은 가능하지만 3개월 뒤 종료라 장기 선택지가 아니다.

---

## 3. 구독(앱) vs API 과금 — 분리 정리

| 구분 | 구독(앱) | API | 서로 연동? |
|---|---|---|---|
| OpenAI | ChatGPT Go/Plus($20)/Pro($100·200·500) — 앱·웹 전용, 오디오 업로드 512MB, Record는 macOS | `gpt-transcribe` $0.0045/분 등, API 조직 크레딧 | **별개.** 도움말: "ChatGPT and the API platform have separate billing systems. API credits … are separate from your ChatGPT subscription." 일부 구독에 프로모션 API 크레딧이 붙을 수 있으나 API 조직에 귀속(금액 확인 못 함) — https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform |
| Google | Gemini 앱: Google AI Plus ₩7,500 / Pro / Ultra ₩119,000~ — 업로드 오디오 한도만 상향(10분→3시간) | Gemini API(무료 티어 있음/유료는 Cloud Billing), Cloud STT v2(GCP 결제) | **별개.** Pro 구독 혜택에 "Google Developer Program 월 $10 Google Cloud 크레딧"이 포함된다고 표기돼 있으나 이 크레딧이 Gemini API·STT 비용에 적용되는지는 **확인 못 함** — https://one.google.com/about/google-ai-plans/?hl=ko |
| ElevenLabs | 웹 앱 플랜(ElevenCreative) | ElevenAPI(Scribe v2 $0.22/시간) | 가격 페이지가 별도(`/pricing` vs `/pricing/api`); 크레딧 공유 여부는 확인 못 함 — https://elevenlabs.io/pricing/api |

→ 사용자가 가진 ChatGPT·Gemini 구독으로 **자동화 파이프라인의 API 비용이 줄어들지는 않는다.** 구독을 활용하는 길은 "앱/웹을 사람이 쓰는 것" 뿐인데, ChatGPT는 자동화 금지, Gemini는 회색지대.

---

## 4. ElevenLabs — Scribe v2

1. **한국어**: 지원(`kor`, 90개+ 언어, 자동 감지).
2. **화자 분리**: `diarize=true`, **최대 32명**, `num_speakers`(정수, "최대 화자 수" 힌트 — 정확한 인원 지정이라기보다 상한), `diarization_threshold`(기본 약 0.22), `use_speaker_library`, 콜센터용 `detect_speaker_roles`(+10%). 한국어에서의 DER 공개 수치는 확인 못 함.
3. **타임스탬프**: `word`/`character` 단위 + `audio_event` 태그(웃음·박수 등).
4. 요약·할 일: **전용 요약 없음.** 대신 `transcript_edit`(자연어 지시로 전사 편집, +30% 요금), 엔티티 검출(65종), `no_verbatim`. 요약/할 일은 LLM 별도 호출.
5. **입력/길이/크기**: 파일 업로드 **5GB**, URL 방식 2GB, **길이 최대 10시간**(멀티채널은 1시간·최대 5채널), 오디오·영상 모든 주요 형식. 동기 호출 또는 웹훅 비동기.
6. **가격**: **Scribe v2 $0.22/시간(≈$0.0037/분)**. 부가: 키텀(`keyterms`) +20%, `transcript_edit` +30%, 화자 역할 +10%. 무료 한도는 플랜 종속(웹 UI 무료 4.5시간/월은 [2차: sonetho.com]).
7. 접근/자동화: 공개 API(+웹 UI). 자동화 = API.
8. **내보내기**: `additional_formats` = `docx`, `html`, `pdf`, `srt`, `txt`, `segmented_json` + 기본 JSON(단어·speaker_id·logprob).
9. **데이터 정책**: **기본 보관·서비스 개선에 사용**(이용약관 "Content" 라이선스가 영구·취소 불가 조건 포함). **'Terms and Privacy → Data use' 메뉴에서 학습 사용 옵트아웃 가능**(이전 사용분 제외). **Zero Retention Mode(`enable_logging=false`)는 엔터프라이즈 전용.** 무료 사용자는 비상업 용도만.
10. 약관 자동화: 공식 API가 있어 API 호출이 정상 경로. (웹 UI 자동화는 검토 안 함 — 불필요)
11. **공개 한국어 정확도**(8절): FLEURS 한국어 WER 10.08 / CER 4.93(koedesk 1위 tier, **이해관계 있음**), GigaSpeechBench 한국어 CER 11.81(한국어 값이 있는 14개 중 2위), HF Open ASR 다국어 7개 언어(한국어 미포함) 평균 1위 [2차: 컴파일 인용 — 참고만].
- 출처: https://elevenlabs.io/docs/api-reference/speech-to-text/convert.md , https://elevenlabs.io/docs/overview/capabilities/speech-to-text , https://github.com/elevenlabs/skills/blob/main/speech-to-text/references/transcription-options.md , https://elevenlabs.io/pricing/api , https://elevenlabs.io/terms-of-use , https://elevenlabs.io/docs/eleven-api/resources/zero-retention-mode.md

**판단: 실측 비교에 넣을 가치 — 최우선.** 이유: 한국어 공개 벤치에서 상위, 화자 분리 32명·단어 타임스탬프·10시간/5GB·$0.22/시간으로 요구 사항을 가장 완결되게 만족. 약관상 기본 학습 사용이라 옵트아웃을 먼저 설정해야 한다.

---

## 5. AssemblyAI

1. **한국어**: **`Universal-2`(99개 언어) 한국어 지원**. 최신 `Universal-3.5 Pro`는 18개 언어에 **한국어 미포함**, `Universal-3.6 Pro Preview`(32개 언어)는 한국어 포함(프리뷰라 변경 가능). 기본 `speech_models`는 `["universal-3-5-pro","universal-2"]`라 한국어는 자동으로 Universal-2로 폴백.
2. **화자 분리**: `speaker_labels=true`. 한국어 지원은 **2024-05 공지**로 확인(중국어·힌디어·일본어·한국어·베트남어 추가), 현재 문서의 언어별 지원표는 확인 못 함. 화자 수: `speakers_expected`(정확히), `min/max_speakers_expected`(하드 경계), 기본 상한 2–10분 오디오 10명 / 10분 이상 30명. 화자당 연속 30초 이상 발화 권장.
3. 타임스탬프: 단어 단위(ms), 발화(utterance) 단위.
4. **요약·할 일**: 내장 Summarization/Auto Chapters는 Universal-2 전용 + **deprecated**(U3.5 Pro에서 500 오류 사례 명시) → **LLM Gateway(Claude/GPT/Gemini 등, 토큰 과금)** 로 대체하라고 안내.
5. 입력/길이: 이 조사에서 비동기 최대 파일 크기·길이는 **확인 못 함**(FAQ 페이지 404). 업로드 후 폴링/웹훅.
6. **가격**: Universal-2 **$0.15/시간**(+ 화자 분리 표준 **+$0.02/시간**, "experimental" +$0.065), Universal-3.5 Pro $0.21/시간(한국어 불가), U3.6 Pro Preview 가격 확인 못 함. 신규 $50 무료 크레딧.
7. 접근/자동화: 공개 API. 자동화 = API.
8. 내보내기: JSON, SRT·VTT·TXT(문서 "Transcript export options").
9. **데이터 정책**: 모델 학습에 **일부 파일이 사용될 수 있음(PII 제거 후)**, **옵트아웃·EU 서버·BAA 사용 시 제외**. 비동기 기본: 업로드 오디오 24~48시간 후 삭제 시작, 전사 결과 30일(TTL 최소 1시간 설정 가능).
10. 약관 자동화: 이 조사에서 약관 원문은 읽지 못함(확인 못 함). API는 정상 경로.
11. **공개 한국어 정확도**: AssemblyAI 자체 문서 Universal-2 한국어 FLEURS WER **14.54%**(벤더 발표, 2026-01). AeCeCi 한국어 회의 1,000클립(2026-10-13)에서 AssemblyAI(기본 모델) CER 17.23(교정 13.17)로 CLOVA·Azure·Whisper-1·Google STT보다 **최하위** [2차: 개인 GitHub]. 2026년 모델 세대 비교는 없음.
- 출처: https://www.assemblyai.com/docs/pre-recorded-audio/supported-languages.md , https://www.assemblyai.com/docs/pre-recorded-audio/select-the-speech-model.md , https://www.assemblyai.com/docs/pre-recorded-audio/label-speakers.md , https://www.assemblyai.com/pricing , https://www.assemblyai.com/docs/data-retention-and-model-training.md , https://www.assemblyai.com/docs/pre-recorded-audio/benchmarks.md , https://www.assemblyai.com/blog/assemblyai-newsletter-37

**판단: 실측 비교에 넣을 가치 — 낮음.** 이유: 한국어는 구형 Universal-2에 머물고 한국어 근거가 약하며(자사 14.5% WER, 3자 CER 최하위), 최신 모델은 한국어를 못 하거나 프리뷰다. 시간이 남으면 U3.6 Pro Preview만 1~2건.

---

## 6. Deepgram

1. **한국어**: Nova-3 `ko`/`ko-KR`(monolingual), Nova-2도 지원.
2. **화자 분리**: `diarize_model=latest`(배치는 v2). 문서 헤더에 "All available languages"로 표기돼 한국어도 가능한 것으로 읽히나 한국어 품질 수치는 확인 못 함. 화자 수 지정·최대 화자 수: 문서에 없음(확인 못 함). 응답에 `speaker`·`speaker_confidence`.
3. 타임스탬프: 단어 단위(start/end), `utterances` 옵션.
4. 요약: Audio Intelligence(Summarization·Topic·Sentiment, 토큰 과금 $0.0003/1k 입력, $0.0006/1k 출력). 한국어 지원 여부 확인 못 함.
5. **입력/길이**: 최대 **2GB**, 100+ 형식. **처리 10분 초과(Nova/Base/Enhanced)면 504 타임아웃** → 긴 파일은 분할/비동기 콜백 고려.
6. **가격**: Nova-3 Monolingual 배치 **$0.0043/분($0.258/시간)**, **배치 화자 분리 포함(무료)**, 키텀 +$0.0013/분. 신규 **$200 무료 크레딧**.
7. 접근/자동화: 공개 API.
8. 출력: JSON(+ utterances/paragraphs). SRT 내보내기 문서는 확인 못 함.
9. **데이터 정책**: **Model Improvement Program이 기본 참여(데이터 보관·학습 사용)**, 요청 단위 `mip_opt_out=true`로 옵트아웃하면 처리 후 보관 안 함(메타데이터·사용 로그는 90일).
10. 약관 자동화: 확인 못 함(API 정상 경로).
11. **공개 한국어 정확도**: koedesk FLEURS 한국어 Nova-3 **WER 22.09 / CER 9.27 — 11개 엔진 중 최하위(T6)** [2차·이해관계 있음]. GigaSpeechBench 한국어에는 Nova-3 값이 없음(아랍어 등에만).
- 출처: https://deepgram.com/pricing , https://developers.deepgram.com/docs/models-languages-overview.md , https://developers.deepgram.com/docs/diarization.md , https://developers.deepgram.com/docs/pre-recorded-audio.md , https://developers.deepgram.com/trust-security/your-data.md

**판단: 실측 비교에 넣을 가치 — 낮음.** 이유: 가격·화자 분리 포함 구조는 매력이나 공개 한국어 정확도가 가장 낮고 기본 학습 옵트인이다.

---

## 7. Speechmatics

1. **한국어**: `ko` 지원(Enhanced/Standard 언어 목록). 최신 `Melia 1`(56개 언어, 언어 사전 선택 불필요)·`Enhanced`(언어별 최고 정확도)·`Standard`.
2. **화자 분리**: 배치 `diarization: "speaker"`(음향 매칭, 라벨 `S1`,`S2`…, 식별 불가 `UU`) / `channel`. `speaker_sensitivity`(0~1), `prefer_current_speaker`. **최대 화자 수·화자 수 직접 지정: 문서에 없음**, 한국어 언어별 제한도 명시 안 됨(확인 못 함). 처리시간 +10~50%.
3. 타임스탬프: 단어 단위(start/end_time).
4. 요약: Summaries 애드온 **$0.12/시간**, Chapters $0.40, Topics $0.20, Sentiment $0.12(배치 전용). 한국어 지원 여부 확인 못 함.
5. **입력/길이**: 지원 형식 wav·mp3·aac·ogg·mpeg·amr·m4a·mp4·flac. 요청 본문 파일 **1GB 미만**(초과는 fetch URL). 최대 길이 확인 못 함.
6. **가격**: 배치 Melia 1 **$0.24/시간**, Enhanced **$0.75/시간**, Standard $0.45/시간. 화자 분리 별도 애드온 항목 없음(확인한 애드온 목록 기준). 신규 **$100 무료 크레딧**.
7. 접근/자동화: 공개 API(Batch REST + 웹훅 알림).
8. 출력: JSON(v2), SRT/TXT 변환은 확인 못 함.
9. **데이터 정책**: 배치 **오디오·전사·설정을 7일 저장 후 자동 삭제**(API로 조기 삭제 가능), 실시간은 저장 안 함. **모델 학습 사용 여부는 확인 못 함**.
10. 약관 자동화: 확인 못 함(API 정상 경로).
11. **공개 한국어 정확도**: **찾지 못함**(HF Open ASR 영어 장문에서 Enhanced 5위 등 영어만).
- 출처: https://www.speechmatics.com/pricing.md , https://docs.speechmatics.com/speech-to-text/languages.md , https://docs.speechmatics.com/speech-to-text/batch/batch-diarization.md , https://docs.speechmatics.com/speech-to-text/batch/limits.md , https://docs.speechmatics.com/administration/security-and-compliance.md

**판단: 실측 비교에 넣을 가치 — 낮~중(선택).** 이유: 한국어 근거가 없어 우선순위는 낮지만 $100 무료 크레딧이 있어 1~2건 비용 없이 시험 가능, 7일 자동 삭제는 프라이버시상 장점.

---

## 8. 한국어 공개 벤치마크 모음 (수치는 이 절에서만; 모두 낮을수록 좋음)

> 주의: 출처마다 데이터·정규화·모델 버전이 달라 **서로 합산·단일 순위로 쓰면 안 됨**. DER 등 화자 분리 지표는 한국어 상용 서비스에 대해 공개 수치를 찾지 못함.

**(A) koedesk STT Bench Track A — FLEURS 한국어, 200발화, 2026-07-05 실행** — https://koedesk.app/benchmark
- 이해관계 명시: 벤치 제작·후원사 koedesk가 ElevenLabs Scribe v2를 쓰는 받아쓰기 제품. FLEURS는 학습 데이터 오염 가능성이 있다고 스스로 밝힘. 사전 등록 방법론·원시 응답 공개.

| 엔진 | WER% | CER% | tier |
|---|---:|---:|---|
| ElevenLabs Scribe v2 | 10.08 | 4.93 | T1 |
| Microsoft MAI Transcribe (Azure) | 10.60 | 5.15 | T1 |
| Gemini 3.1 Pro (preview) | 11.46 | 5.30 | T2 |
| Google STT v2 (Chirp 3) | 11.49 | 5.30 | T2 |
| Gemini 2.5 Pro | 11.59 | 5.27 | T2 |
| OpenAI gpt-4o-transcribe | 12.31 | 5.41 | T2 |
| Gemini 3.5 Flash | 12.48 | 5.72 | T2 |
| Gemini 2.5 Flash | 13.07 | 5.82 | T3 |
| OpenAI whisper-1 | 16.92 | 6.62 | T5 |
| Deepgram Nova-3 | 22.09 | 9.27 | T6 |

미포함: `gpt-transcribe`, `gemini-3.5-transcribe`, AssemblyAI, Speechmatics.

**(B) GigaSpeechBench (SpeechColab, 기술보고서 arXiv 2606.28884) — 한국어 실환경 CER%** — https://github.com/SpeechColab/GigaSpeechBench (commit `ca782bf`)
- FunASR-Realtime 9.92, **ElevenLabs Scribe v2 11.81**, Qwen3-ASR-1.7B 12.90, Azure 13.13, **Chirp 3 15.96**, Gemini 3.0 Flash 16.78, Whisper-large-v3 18.53, **GPT-4o-transcribe 41.31**. (AssemblyAI·Deepgram·Speechmatics 한국어 값 없음. `gpt-4o-transcribe`가 비정상적으로 높아 긴/실환경 오디오에서 약점이 있는지 확인 필요 — 원인은 문서에 없음.)

**(C) AeCeCi 한국어 회의 CER — AI Hub KconfSpeech 1,000클립(평균 6.2초), 2026-10-13** — https://github.com/AeCeCi/STT-Meeting-CER-Benchmark [2차: 개인 GitHub, 비동료 검토]
- 원본/교정 CER%: CLOVA 12.11/7.69, Azure 13.79/10.11, OpenAI Whisper(`whisper-1`) 16.32/12.84, Google STT v2(`latest_long`) 16.75/13.00, AssemblyAI(기본 모델) 17.23/13.17.

**(D) 벤더 발표: AssemblyAI Universal-2 한국어 FLEURS WER 14.54%** (2026-01) — https://www.assemblyai.com/docs/pre-recorded-audio/benchmarks.md [벤더 자체]

**(E) HiKE (EACL 2026 Findings, 한국어-영어 혼용)**: GPT-4o-transcribe MER 21.8로 10개 모델 중 최상 [2차: 컴파일 문서 인용 — https://github.com/kyle-playground/asr-evaluation-framework/blob/main/research-korean-asr-rankings.md , 논문 원문은 직접 확인 안 함]

---

## 9. 비교 요약 표

| 후보 | 한국어 | 화자 분리 (한국어/최대/수 지정) | 타임스탬프 | 요약·할 일 | 길이·크기 한도 | 가격 | 접근·자동화 | 학습 사용/보관 | 자동화 약관 | 실측 가치 |
|---|---|---|---|---|---|---|---|---|---|---|
| **ElevenLabs Scribe v2** | ○ 상위 벤치 | ○ / 32 / 상한 힌트(`num_speakers`) | 단어·문자 | ✕(편집 지시 +30%) | 10h / 5GB | **$0.22/h** | API | 기본 사용, 옵트아웃 가능 | API 정상 | **최우선** |
| **Gemini 3.5 Transcribe** | ○ | ○ / 8(3+ 실험적) / 지정 불가 | 단어(정확도 저하 경고) | ✕ | 1h, **화자·TS 켜면 30분** | ≈$0.30/h(추정) | API | 무료=학습, **유료=미사용** | API 정상 | **높음** |
| **Gemini 오디오 이해(3.8 Flash)** | ○ | 프롬프트 방식 / 명시 없음 | 구간(MM:SS) | **○(한 번에)** | 9.5h, 20MB 인라인 | 입력 ≈$0.09/h+출력(12월 이후 2배) | API | 위와 동일 | API 정상 | **높음** |
| Cloud STT v2 Chirp 3 | ○ | ○ / 상한 미확인 / min·max 지정 | 단어(20분 제한) | ✕ | 배치 1h, TS 시 20분 | $0.016/분(배치 $0.003/분) | API(GCS·서비스 계정) | 기본 로깅 안 함 | API 정상 | 낮~중 |
| OpenAI `gpt-transcribe` | △ 목록 없음 | ✕(문서 없음) | ✕(문서 없음) | ✕ | 25MB | **$0.27/h** | API | 학습 안 함, 보관 없음 | API 정상 | 중(기준선) |
| OpenAI `gpt-4o-transcribe-diarize` | △ | ○ / 미확인 / 참조 클립 4개 | 세그먼트 | ✕ | 25MB | $0.36/h | API | 위와 동일 | API 정상 | 중(**2027-02-26 종료**) |
| ChatGPT 앱(Plus/Pro) | ○(영어 위주) | △(업로드 불안정 명시) | 미확인 | ○ | 512MB, Record는 macOS 4h | Plus $20/월, Pro $100~500/월 | **앱 전용**, 브라우저 | 옵트아웃 가능 | **금지** | 제외 권장 |
| Gemini 앱(Pro/Ultra) | ○ | 프롬프트 방식 | 프롬프트 | ○ | 3h·100MB(무료 10분) | Pro 금액 확인 못 함, Ultra ₩119,000~ | 앱 전용, 브라우저 | Keep Activity 설정, 최대 3년 | 명시 금지 문구 확인 못 함(회색) | 조건부(수동) |
| AssemblyAI | △ Universal-2만 | ○(2024 공지) / 30 / 정확·범위 지정 | 단어 | LLM Gateway 별도 | 확인 못 함 | $0.15/h + 화자 $0.02/h | API | 기본 일부 학습, 옵트아웃 | 확인 못 함 | 낮음 |
| Deepgram Nova-3 | △ 최하위 벤치 | ○ / 미확인 / 지정 불가 | 단어 | 별도 과금 | 2GB, 처리 10분 504 | $0.258/h(화자 포함) | API | **기본 MIP 학습**, `mip_opt_out` | 확인 못 함 | 낮음 |
| Speechmatics | ○(`ko`) | ○ / 미확인 / 민감도만 | 단어 | Summaries $0.12/h | 1GB 본문 | Melia $0.24/h, Enhanced $0.75/h | API | 7일 삭제, 학습 확인 못 함 | 확인 못 함 | 낮~중 |
| Google Recorder | ✕(Pixel 전용) | – | – | – | – | – | – | – | – | 없음 |

---

## 10. 추천 실측 순서 (비용·자동화·정확도 기준)

1. **ElevenLabs Scribe v2** (`diarize=true`, `timestamps_granularity=word`, 옵트아웃 설정) — 전사+화자를 한 번에.
2. **Gemini 3.5 Transcribe** (유료 티어, 30분 분할 + 화자 일관성 확인) + **Gemini 3.8 Flash 오디오 이해**(요약·할 일까지) — Google 계열 두 방식 비교.
3. **OpenAI `gpt-transcribe`**: 텍스트 정확도 기준선(화자 없음). 필요하면 `gpt-4o-transcribe-diarize`는 한 번만.
4. 시간이 남으면 Cloud STT Chirp 3 1~2건, Speechmatics $100 크레딧으로 1~2건, AssemblyAI U3.6 Pro Preview.
5. 제외: ChatGPT 앱 자동화(약관), Deepgram(한국어 근거 최하위), Google Recorder(Pixel 전용). Gemini 앱은 수동 샘플만.

공통 측정 권장: 한국어 CER, 화자 수 정확도, `cpCER`(화자 포함 CER) 또는 수동 라벨 DER, 긴 녹음(≥30분) 안정성, 가격/시간, 학습 옵트아웃 확인.
