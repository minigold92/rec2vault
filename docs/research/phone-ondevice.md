# 갤럭시 S25 Ultra 폰 안에서 한국어 전사·화자 분리 — 온디바이스 경로 조사

- 조사·확인일: **2026-11-09** (모든 URL을 이 날짜에 열람. 열람하지 못하고 검색 요약만 본 것은 "(검색 요약만)"으로 표시)
- 표기: **[원문]** 공식 문서·저장소 README·릴리스 노트 / **[커뮤니티]** 사용자·블로그·Reddit·GitHub 이슈/디스커션(작성일 병기) / **[추정]** 이 문서 작성자의 계산·추론 / "확인 못 함"
- 대상 기기: 갤럭시 S25 Ultra(SM-S938N). SoC = Snapdragon 8 Elite for Galaxy(Hexagon v79 — [원문] Tether QVAC 문서가 "Galaxy S25 (Snapdragon 8 Elite, Hexagon v79)"로 표기). RAM 12GB는 사용자 진술, 미확인.
- 이미 조사한 Mac용 모델(Whisper large-v3, Qwen3-ASR, MOSS, VibeVoice, Nemotron, pyannote 등)은 `docs/research/local-stt.md`에 있음. 여기서는 중복 설명하지 않고 그 수치만 인용한다(인용 시 "local-stt §번호").
- **이번 조사의 가장 큰 한계**: S25 Ultra에서 **한국어 대화 녹음**을 돌린 정량 결과(CER/DER/RTF)를 공개한 자료는 **하나도 찾지 못했다.** 아래 속도 수치는 전부 영어·중국어·스페인어 오디오 또는 모델 단독 프로파일이다.

---

## 0. 결론 요약

1. **삼성 기본 앱(음성 녹음 → 텍스트 변환 어시스트)** 은 설치 없이 한국어·화자 구분(Speaker 1/2)이 되고, "기기에서만 데이터 처리"를 켜도 전사는 된다는 보고가 있다(TechWiser 2024, SamMobile 2025). 그러나 ① 요약은 클라우드가 필요하고, ② 한국어 정확도 평가가 사용자마다 엇갈리며(2024 혹평, 2025 호평, 정량 비교 없음), ③ **삼성 앱으로 녹음한 파일만 대상**이라는 삼성 문구가 있어 외부 파일 일괄 처리·자동화가 안 된다. → §1
2. **Google 온디바이스(ML Kit GenAI Speech Recognition, Gemini Nano)** 는 ko-KR·파일 전사를 지원하지만 **앱을 직접 만들어야** 하고 화자 분리가 없으며 alpha다. S25가 Advanced 모드 대상인지는 문서상 칩셋(SM8750) 기준으로만 암시된다. 한국어 정확도 수치 없음. → §2
3. **지금 바로 설치해서 쓸 수 있는 "폰 안 STT + 화자 분리" 완성형은 Recly 하나**(Qwen3-ASR **0.6B** + pyannote 3.0/ERes2Net, 한국어 선택 가능, AGPL-3.0). 다만 제3자 한국어 벤치에서 0.6B는 평균 CER 17.29, 저음질 전화 59.62로 약하다(local-stt §2-1). 폰 속도·발열 실측은 공개돼 있지 않다. → §3
4. **속도가 되는 경로는 NPU(Hexagon)**: Qualcomm AI Hub Whisper-large-v3-**turbo**는 8 Elite for Galaxy에서 인코더 약 305–312 ms/30초 창, 디코더 약 6.7 ms/토큰(프로파일). Tether QVAC은 **S25**에서 MOSS-Transcribe-Diarize(STT+화자 일체형) q8_0를 RTF 0.18–0.20(160–191초 클립)으로 측정했다. 하지만 둘 다 **개발자 빌드**가 필요하고, turbo는 한국어에서 large-v3보다 열세(local-stt §2-1: 평균 9.36 vs 7.83, 저음질 전화 10.00 vs 5.34), MOSS는 한국어 미검증이다. → §4, §6
5. **Whisper large-v3 자체를 폰 CPU에서 돌린 사례**는 Reddit 한 줄(S24 Ultra, Termux, "large 모델로 1분 오디오 1분", 양자화·언어 미상, 2025-05)뿐이다. RTF≈1이면 1시간 녹음 = 약 1시간 점유. 배터리·발열 수치는 없다. → §5
6. **핵심 질문에 대한 답(§9 상세)**: *large-v3 가중치를 폰에서 돌리는 것은 가능하다(정확도 천장은 같음). 그러나 속도(≈실시간)·발열 비용이 크고, 빠른 NPU 경로는 turbo/소형 모델이라 정확도가 내려가며, 화자 분리까지 포함한 완성형은 0.6B(Recly)다.* "Mac large-v3 + 별도 diarizer"급 한국어 결과를 폰에서 같은 편의성으로 얻는다는 **공개 근거는 없다.**

---

## 1. 삼성 기본: Galaxy AI 텍스트 변환 어시스트 / 키보드 음성 입력

### 1-1. 음성 녹음 앱 — 텍스트 변환 어시스트 (파일 전사)

**무엇인가**: 삼성 음성 녹음 앱에서 녹음 파일을 열어 "텍스트 변환" → 전사, 번역, 요약. One UI 7부터 삼성 전화 앱 통화 녹음도 자동 전사 가능(자동 전사 스위치).

**한국어 지원·품질 근거**
- 한국어 지원 명시 [원문]: Transcript assist 지원 언어에 Korean 포함 — https://www.samsung.com/us/support/answer/ANS10000942 (Voice Recorder 안내), 통화 전사 언어에도 Korean 포함 — https://www.samsung.com/us/support/answer/ANS10004613/
- 품질 — 서로 엇갈린 사용자 보고(정량 비교 없음):
  - [커뮤니티, 2024-02-02] 삼성 멤버스 "갤24 음성 텍스트 변환 품질 쓰레기": 에이닷>클로바노트(에이닷의 약 80%)>갤24 순, "서버 활용까지 활성화하고도" 단어가 이상하게 나옴. 삼성 운영 담당 답변(2024-02-05): "S24 음성녹음 앱에서는 최대 3시간까지 음성 녹음 및 텍스트 변환(On device)" — https://community.samsung.com/kr/conversations/s/%EA%B0%A424-%EC%9D%8C%EC%84%B1-%ED%85%8D%EC%8A%A4%ED%8A%B8-%EB%B3%80%ED%99%98-%ED%92%88%EC%A7%88-%EC%93%B0%EB%A0%88%EA%B8%B0/r1_25407964
  - [커뮤니티, 2025-02-05] 클리앙: 20분 상담 녹음을 발화자 구분 후 깔끔히 요약(작성자 S24 울트라, "클로바노트 바르는 수준"이라는 댓글과 "전에는 클로바노트보다 못하던데"라는 댓글 공존) — https://www.clien.net/service/board/park/18911645
  - [커뮤니티, 2026-07-20] Android Police 비교(영어 회의, Samsung vs Google Recorder): 전사 유용성은 "neck and neck", **둘 다 말이 빠르거나 음색이 비슷하면 화자 분리 실패**, 삼성은 Speaker 1/2 라벨 이름 변경 불가(필자 확인) — https://www.androidpolice.com/i-recorded-the-same-meeting-with-samsung-and-google-one-transcript-was-far-more-useful/ (한국어 아님)
  - 한국어 대화·소음·다화자에서의 CER 같은 수치는 **확인 못 함.**

**"기기에서만 데이터 처리" 설정에서 한국어 전사가 되는가** — 출처 간 상충
- 되는 쪽: [원문] Samsung US 설정 안내에 "Process data only on device" 스위치 존재(Settings > Galaxy AI), 전체 클라우드 차단 마스터 스위치 — https://www.samsung.com/us/support/answer/ANS10000753/ . [커뮤니티, 2025-09 캡처] SamMobile: 해당 스위치를 켠 상태에서 "Transcript Assist: Complete feature set"(S24+ 기준, S25는 다를 수 있다고 필자 명시) — https://www.sammobile.com/news/use-galaxy-ai-without-sending-data-to-samsung-heres-what-you-lose/ . [커뮤니티, 2024-03] TechWiser: "전사는 인터넷 없이 작동, 요약은 인터넷 필요 / 온디바이스 설정 시 요약이 멈춤" — https://techwiser.com/how-to-use-transcribe-assist-on-samsung-galaxy-s24/ . 삼성 멤버스 일반 회원 글(2024-02-23): 녹음 텍스트 변환은 삼성 자체 경량 모델로 온디바이스(공식 아님).
- 안 되는 쪽: [원문, 삼성 레반트 지원] "Transcription and Summary features for Transcript Assist require a network connection and Samsung Account login" — https://www.samsung.com/levant/support/mobile-devices/galaxy-ai-languages-usage-guide/ (검색 요약만). [커뮤니티, 2026-08-14] Subanana 블로그가 삼성서비스 한국 안내(https://www.samsungsvc.co.kr/solution/1847983)를 인용해 "네트워크 연결 및 삼성 계정 로그인 필요, 기내 모드에서는 안 된다"고 서술(블로그의 인용이며 해당 삼성 페이지는 이번에 직접 열람하지 못함; 이 블로그는 경쟁 서비스 홍보 글).
- 즉 **S25 Ultra + 한국어 + "기기에서만" + 비행기 모드에서 실제로 전사되는지는 문서로 확정할 수 없다. 기기에서 2분이면 확인 가능**(비행기 모드 + 스위치 ON + 한국어 녹음 파일 전사).
- 요약은 확실히 클라우드: 클리앙 댓글(2025-02-05)도 "요약을 위해서만 사용한다지만 서버로 보내야 하는 게 아쉽다"고 언급. 기기 내 요약은 이 경로에 없음.
- 신규 변경 [커뮤니티/뉴스, 2026-07-10]: SamMobile 보도를 인용한 Android Police — 음성 녹음 앱에 "Cloud transcription"(녹음을 클라우드로 올려 품질 향상)이 베타로 추가 예정, 당시 화면에 English·Cantonese·Mandarin 등만 표기(한국어 없음). 이 옵션을 켜면 회사 녹음이 밖으로 나가므로 사용하지 않아야 함 — https://www.androidpolice.com/samsung-voice-recorder-app-cloud-transcription-update/

**화자 분리**: 지원(Speaker 1/2…). TechWiser(2024-03, S24)는 라벨 이름 변경 가능·"Hide speaker labels" 설명, Android Police(2026-07)는 이름 변경 불가라고 상반되게 서술(버전 차이 [추정]). 화자 수 제한·DER 수치는 확인 못 함.

**속도·메모리**: 공개 실측 확인 못 함. 클리앙 댓글 [커뮤니티, 2025-02-05]: 갤럭시 폴드5에서 "좀 느린 것 같지만" 동작. 1시간 녹음 처리 시간·배터리 수치 확인 못 함. 공식: 최대 3시간(S24 기준 운영 담당 답변), One UI 8 안내 "3시간 미만"(VOMO 가이드 인용).

**설치·라이선스·가격**: 기본 탑재, 무료(삼성: 기본 Galaxy AI 무료 유지 입장). 삼성 계정 로그인 필요(US 안내).

**일괄 처리·자동화**: **불가에 가깝다.**
- [원문, 삼성 비즈니스] "Transcript Assist only available on the pre-installed Samsung Voice Recorder app or files recorded using the pre-installed Samsung Phone app, Samsung Notes app or Samsung Interpreter app" — https://www.samsung.com/ae/business/mobile/galaxy-ai/ (검색 요약만). VOMO 가이드(2026-10-30)도 삼성 자체 앱 녹음이 지원 대상이라고 서술.
- 통화 녹음은 전화 앱 설정에서 "Auto transcribe recorded calls" 자동 전사 가능([원문] ANS10004613) — 통화 한정.
- 공개 API 확인 못 함. 대화 녹음 폴더 감시형 자동화는 이 경로로 불가.
- 외부 파일을 음성 녹음 앱에 넣어 전사되는지: 확인 못 함.

### 1-2. 삼성 키보드 음성 입력 (오프라인 언어팩)
- [커뮤니티, 2025-08-14] GeeKorea: 삼성 키보드 > 음성 입력에서 "삼성 음성 입력" 선택 후 "오프라인 언어팩"을 받으면 인터넷 없이 음성 입력 가능. 한국어 팩 존재 여부·인식 품질은 글에 명시 없음 — https://geekorea.com/samsung-galaxy-keyboard-voice-input-settings/
- [원문, 삼성서비스 한국] "음성으로 메시지(문자) 입력은 네트워크가 연결되어야 합니다" — https://www.samsungsvc.co.kr/solution/36551 (이미지 날짜 2023-12; 오프라인 팩 이후 갱신 여부 확인 못 함).
- 성격상 **받아쓰기(짧은 발화 마이크 입력)** 용이며 저장된 녹음 파일 전사·화자 분리·1시간 처리에 쓸 수 없다([커뮤니티, 2026-10-26] Flint 블로그: "Voice typing doesn't keep the audio… can't transcribe something you've already recorded"). 한국어 오프라인 인식 정확도: 확인 못 함.

### 1-3. Google Recorder (Pixel 전용) 재확인
- Pixel 3 이상·Pixel Tablet 전용, 삼성에서 Play 스토어 설치 불가 — [커뮤니티, 2026-10-26] Flint 블로그 요약 https://flintvoice.app/blog/google-recorder-android (이 블로그는 자사 앱 홍보 글). Google Pixel Phone Help 원문 페이지는 이번에 직접 열람하지 못함. 결론: **S25 Ultra에서는 쓸 수 없음.**

---

## 2. Google 온디바이스: Gemini Nano(AICore) / ML Kit GenAI Speech Recognition / SpeechRecognizer

### 2-1. ML Kit GenAI Speech Recognition API
- **무엇인가** [원문]: 두 모드 — **Advanced**(온디바이스 Gemini 계열 GenAI 모델, 언어별 팩 다운로드 불필요, "broader language coverage and better overall quality") / **Basic**(기존 온디바이스 음성 인식 모델, SpeechRecognizer API와 유사). 의존성 `com.google.mlkit:genai-speech-recognition:1.0.0-alpha2`. "alpha, SLA·폐기 정책 없음, 호환성 깨지는 변경 가능". — https://developers.google.com/ml-kit/genai/speech-recognition/android?hl=en
- **한국어** [원문]: Advanced에 `ko-KR`(beta 표기 없음), Basic에 `ko-KR (beta)`("beta 언어는 단어 오류율이 약간 더 높을 수 있음"). 한국어 WER/CER 수치는 문서에 **없음**.
- **파일 전사** [원문]: `AudioSource.fromFile()`/`fromUri()`는 `ONE_SHOT`, MP3·WAV·FLAC·M4A·OGG를 기기에서 디코딩. **단어 타이밍은 스트리밍 입력에서만**(파일 입력에서 켜면 `IllegalArgumentException`). 파일 길이 상한은 문서에 명시 없음(확인 못 함).
- **S25 지원 여부**: Advanced 지원 기기 = "Pixel 10/11, plus devices with Gemini Nano on the following chipsets (including Galaxy S26, Z Flip8, Z Fold8): Qualcomm **SM8750**, SM8845, SM8850, …" [원문]. S25 Ultra의 SoC는 Snapdragon 8 Elite(SM8750 계열) [추정: 칩 코드명 매핑]이므로 **대상일 가능성이 높지만 문서가 S25를 직접 명시하지 않음.** 같은 사이트의 ML Kit GenAI 개요는 텍스트·이미지 과제 지원 기기에 "Galaxy S25, S25+, S25 Ultra"를 명시 — https://developers.google.com/ml-kit/genai?hl=en . Basic 모드는 API 31+ 기기면 가능(S25는 해당). 실제 가용성은 앱에서 `checkStatus()`로 확인(문서 권고). 잠긴 부트로더 필요(unlocked면 미지원).
- **화자 분리**: 없음(문서에 기능 없음).
- **프라이버시**: Gemini Nano는 AICore에서 온디바이스 실행, 입력·추론·출력이 로컬 처리(ML Kit GenAI 개요 문구, 검색 요약만). 모델 다운로드 시 네트워크 필요.
- **실행·속도·메모리**: 공개 실측 확인 못 함. 샘플 앱: https://github.com/googlesamples/mlkit/tree/master/android/speech — "Audio File" 데모(경로 입력), Speech Services by Google 최신 버전 필요, 파일 전사는 Android 11+ [원문].
- **설치·라이선스·가격**: Kotlin 앱 개발 필요(완성 앱 아님). 무료 SDK.
- **일괄 처리·자동화**: 직접 앱을 만들면 가능(FileObserver/WorkManager로 폴더 감시 후 `fromFile`). 공유된 사례는 확인 못 함.
- **한계**: 한국어 품질 근거 없음, 화자 분리 없음, 긴 파일 거동 불명, alpha.

### 2-2. Android SpeechRecognizer 온디바이스 / Google 음성 입력 오프라인 팩
- ML Kit 문서가 "Basic 모드 = 전통 온디바이스 인식 모델, 플랫폼 SpeechRecognizer와 유사"라고 밝힘 [원문]. VoicePing 벤치마크는 시스템 인식기를 **스피커→마이크 루프백**으로 시험(파일 직접 입력 아님)했고 부분 전사만 나옴(Galaxy S10, 2026-09-21 갱신) — https://voiceping.net/en/blog/research-offline-speech-transcription-benchmark → 파일 일괄 처리용으로는 부적합.
- Google 음성 입력의 한국어 오프라인 팩 존재·품질: 확인 못 함(검색 요약에서 "지원이 제한적일 수 있음"이라는 비근거 문구만).

---

## 3. 완성형 오픈소스 앱: Recly (폰 안 Qwen3-ASR + 화자 분리)

- **무엇인가** [원문]: Galaxy Watch/Apple Watch/폰/Mac/Windows용 녹음기. 녹음 후 **기기 안 전사**(Android·Windows는 **Qwen3-ASR 0.6B**, 약 1GB 일회 다운로드), 화자 분리는 Android에서 **pyannote 3.0 분할 + ERes2Net 임베딩 약 41MB, "문장 단위"**. 한국어 개발자 앱으로 보이며(README.ko.md, CLOVA·RTZR·Daglo 외부 API 옵션 포함, 인터페이스 한국어) Google Play 배포. 요구: Android 14+, 64비트, 보고 메모리 6GiB+(실질 8GB 폰). — https://github.com/rokrokss/recly , https://github.com/rokrokss/recly/blob/main/docs/setup.md
- **한국어**: "Spoken language"에서 **Korean and English(혼용)** 또는 단일 언어 선택(온디바이스는 언어 지정 필요) [원문]. 한국어 품질 수치 자체는 없음 → 모델(0.6B) 기준 제3자 수치(local-stt §2-1): 평균 CER 17.29, 회의 13.78, 상담 전화 8.49, 강의 12.79, **콜센터(저음질 전화) 59.62**, Kspon 17.62/13.47(30초 이하 발화·RTX 5090 서버 조건). **대화 녹음에서의 실제 품질은 확인 못 함.**
- **화자 분리**: 온디바이스 지원. 문장 단위라 문장 중간 교대·겹침 발화에 약할 수 있음 [추정]. 녹음 후 입력하는 "People in the room"은 문서상 외부 업체의 화자 분리를 돕는 용도로 서술되며, 온디바이스 diarizer가 이 입력을 쓰는지는 **확인 못 함**(setup.md의 "used on the device" 표는 Vocabulary(용어 최대 50개) 항목으로, Android 온디바이스에서 용어 힌트가 쓰인다는 뜻). DER 수치는 확인 못 함.
- **속도·메모리·발열·배터리**: Recly 공개 문서에 RTF·발열·배터리 수치 **없음**. 참고 가능한 근접 데이터: ① sherpa-onnx Qwen3-ASR 0.6B INT8 — 개발자 Mac에서 RTF 0.077–0.103(2–3 스레드, 중국어; 폰 값 아님) https://k2-fsa.github.io/sherpa/onnx/qwen3-asr/pretrained.html ② VoicePing(Galaxy S10, Exynos 9820, 2019년 기기) — Qwen3-ASR 0.6B ONNX INT8 30초 클립 15.9초(RTF 0.53), Whisper Turbo(sherpa-onnx) 17.9초(RTF 0.60), SenseVoice Small 1.7초(RTF 0.06), 영어 오디오·단일 실행·정확도 미평가. **S25 Ultra는 이보다 훨씬 빠를 것** [추정, 수치 근거 없음].
- **설치·라이선스·가격**: Play 스토어 또는 릴리스 APK 사이드로드. **AGPL-3.0**. "no Recly server, no monthly fee". 온디바이스 선택 시 "never falls back to a cloud service" [원문]. 외부 API 옵션은 오디오가 업체로 나가므로 **회사 녹음에는 선택 금지.** 요약은 별도(ChatGPT 연동, 텍스트가 OpenAI로 감) — 비활성 유지 필요.
- **일괄 처리·자동화**: 파일 가져오기(오디오·비디오, "Import audio") 지원, 저장 위치 로컬 폴더/Google Drive, 전사 결과는 오디오 옆 파일(문서화된 `spec/` 포맷). Drive 업로드·recly-events(ChatGPT 에이전트 이벤트)는 클라우드 경유이므로 사용하지 않음. 폴더 감시 자동 전사 기능은 문서에서 확인 못 함(녹음 종료 시 자동 전사는 있음).
- **출처**: https://github.com/rokrokss/recly/blob/main/docs/faq.md

---

## 4. 런타임·프레임워크별 후보

### 4-1. sherpa-onnx (Apache-2.0) — Android APK·한국어 모델·화자 분리
- **무엇인가** [원문]: k2-fsa의 ONNX Runtime 기반 STT/TTS/VAD/화자 분리/화자 식별 툴킷, Android arm64-v8a 등 지원. 사전 빌드 Android APK: 스트리밍 ASR, 시뮬레이트 스트리밍 ASR(VAD+오프라인 모델, 파일 디코딩), **화자 분리(Speaker diarization) APK** — https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/apk.html , 전체 목록 README https://github.com/k2-fsa/sherpa-onnx
- **한국어 모델** [원문]: `sherpa-onnx-zipformer-korean-2024-06-24`(오프라인 transducer, 학습 데이터 = AI Hub KsponSpeech, 체크포인트 johnBamma/icefall-asr-ksponspeech-zipformer-2024-06-24), `sherpa-onnx-streaming-zipformer-korean-2024-06-16`, SenseVoice(zh/en/ja/**ko**/yue), Whisper 계열, **Qwen3-ASR-0.6B int8**(2026-03-25; 1.7B는 GitHub 2GB 업로드 한도 때문에 공식 배포 없음 — issue #3535, 2026-04-22; 1.7B float은 ModelScope 링크). Kspon 학습 Zipformer의 대화·소음 일반화 근거는 확인 못 함(30초 이하 낭독/자발화 데이터).
- **화자 분리**: 지원(pyannote-segmentation-3.0 + CAM++/ERes2Net/3D-Speaker 임베딩). 단 diarization APK(`SherpaOnnxSpeakerDiarization`)는 이름·README상 화자 구간 분리 데모로 보이며 STT와 결합하려면 앱 코드가 필요할 것으로 [추정]. 한국어 대상 DER 근거 없음. local-stt §3-6에 인용한 사용기: 2~4명 회의를 3~9명으로 과분할(wendao 문서) → 화자 수 고정 불가한 점이 약점.
- **실행 속도 실측(폰)**: 위 VoicePing(Galaxy S10) 표 외 S25 Ultra 한국어 값 확인 못 함. 같은 표에서 sherpa-onnx ONNX는 whisper.cpp(GGML) 동일 Tiny 대비 51배 빨랐다(2.1초 vs 105.6초, 모델 패키지·양자화가 달라 단정 금지 — 저자 명시).
- **설치·가격**: APK 다운로드 또는 Android Studio 빌드. 무료.
- **일괄 처리**: 파일 디코딩 가능한 APK 있음(시뮬레이트 스트리밍). 폴더 감시·자동화는 직접 구현.
- **완성형 앱 사례** — `qutschwalze/meeting-transcriber-sherpa`([커뮤니티, sherpa-onnx Show-and-tell 2026-08-26] https://github.com/k2-fsa/sherpa-onnx/discussions/3900): Kotlin/Compose, 오프라인 STT + **실시간 화자 분리**(ReVerb v1 분할 + ERes2Net, 15초 청크, 2–4명), 화자 DB, 오디오 가져오기(WhatsApp 등, 30분 제한), **ThermalGuard(발열 시 diarization 일시 정지)**, MIT. **ASR 모델이 독일어 Kroko Zipformer(+영어)라 한국어 불가**(한국어 ASR 모델로 교체하려면 코드 수정 필요 [추정]). 저자 검증은 독일어 팟캐스트 3인. 한국어 근거 없음.
- 한국어 전용 비교 수치 없음 → local-stt §3-6의 "sherpa-onnx diarizer 과분할" 판단은 그대로 유효.

### 4-2. Qualcomm AI Hub Whisper (QNN / Hexagon NPU)
- **무엇인가** [원문]: Qualcomm이 Whisper를 NPU용으로 재구성(MHA→SHA, linear→conv)해 인코더/디코더 분리 배포. 카탈로그(HF `qualcomm/*` API로 확인, 2026-11-09): Whisper-Tiny/Base/Small/**Medium**(+Quantized)/**Large-V3-Turbo**(+Quantized)/Distil-Whisper. **large-v3(비-turbo) 패키지는 없음.** Apache-2.0 표기. 배포 형식: PRECOMPILED_QNN_ONNX, QNN_CONTEXT_BINARY, VOICE_AI(Voice AI SDK는 Qualcomm Package Manager에서 내려받도록 안내 — 계정·약관 조건은 확인 못 함). README Option 2: **사용자 가중치(파인튜닝 체크포인트)로 export 가능**. — https://huggingface.co/qualcomm/Whisper-Large-V3-Turbo (v0.66.0, 열람 시점 "4 days ago")
- **Snapdragon 8 Elite for Galaxy(=S25) 프로파일** [원문, Whisper-Large-V3-Turbo float, QNN_CONTEXT_BINARY 기준]: 인코더 305.2 ms(30초 창, 1–15MB 피크), 디코더 6.74 ms/토큰, 입력 128×3000, **최대 디코드 200토큰**. 8 Elite Gen 5 for Galaxy는 인코더 282.7 ms/디코더 6.48 ms. (호스팅 장비 프로파일이며 앱 end-to-end가 아님: mel 계산·VAD·모델 로드·KV 루프 오버헤드 미포함.)
- **한국어**: Qualcomm 카드에 언어별 수치 없음. 가중치는 원본 openai/whisper-large-v3-turbo → 한국어 정확도는 제3자 표(local-stt §2-1)의 turbo 값이 그대로 적용(평균 CER 9.36, 콜센터 10.00, Kspon clean 17.96, large-v3는 7.83/5.34/14.16). **즉 NPU로 얻는 것은 large-v3가 아니라 turbo 정확도.**
- **화자 분리**: 없음(별도 모델 필요).
- **실측(폰·앱 수준)**:
  - [커뮤니티/저장소, 2026-07-21] `thedevguy/whisper-htp-android`: AI Hub 사전 컴파일 Large-V3-Turbo(fp16)/Small-Quantized를 ORT QNN EP로 구동. "passively cooled v79 XR device(XREAL Aura, Android XR)"에서 **인코더 약 0.8초/30초 창, 디코드 약 12 ms/토큰**, `high_performance` 모드. `burst`는 속도 동일(790 vs 785 ms)이나 연속 캡셔닝 시 몇 시간 내 skin temperature thermal-emergency → burst 사용 금지 권고. 필수 설정: 매니페스트 `<uses-native-library android:name="libcdsprpc.so" android:required="false"/>`. MIT. 포르투갈어 데모 — https://github.com/thedevguy/whisper-htp-android
  - [커뮤니티/저장소, 벤치 2026-06-13] `AlexMelanFromRingo/npu-lab`(Galaxy **S26 Ultra**, SM8850): Whisper Base/Small/Large-v3-Turbo를 앱에서 구동, **녹음 최대 2분(30초 창)**, Base 인코더 24.6 ms, 디코드 185–222 tok/s, RU/EN/UK/DE 검증(한국어 없음). 컨텍스트 바이너리는 SM8850 전용 — https://github.com/AlexMelanFromRingo/npu-lab
  - WhisperKit Android(Argmax×Qualcomm, 2024-10-22 발표 시 alpha, 문서상 "NPU on Snapdragon, GPU on others") — https://www.argmaxinc.com/blog/android — 현재 S25·한국어 실측은 확인 못 함(HF Space 벤치 페이지는 열람 못 함).
- **1시간 녹음 처리 가능성 [추정]**: 30초 창 120개. 창당 = 인코더 0.3–0.8 s + 디코더 (토큰 수 × 6.7–12 ms). 한국어 30초당 토큰 수를 100–200으로 **가정**하면 창당 약 1.0–2.6 s → **전체 약 2–5분(RTF 0.04–0.09)**, 단 VAD·mel·모델 로드·화자 분리·200토큰 상한(빽빽한 구간 잘림 가능)은 별도. 수치 자체는 위 두 개의 공개 프로파일에서 온 산술이고 한국어 토큰 수 가정이 실측이 아니다.
- **설치 난이도**: **높음.** 완성 앱 없음(참고 구현만). QNN/ORT-QNN, 컨텍스트 바이너리 SoC 매칭, Kotlin+JNI 작성 필요.
- **일괄 처리·자동화**: 직접 구현.

### 4-3. whisper.cpp / Termux / GPU / FUTO·Transcribro 류
- **whisper.cpp 일반(CPU)**: README에 Android 예제 있음. 한국어 large-v3 q5_0의 정확도는 local-stt §5-2(제3자 CER 5.76, 하드웨어 미명시).
- **폰 속도 실측(공개)**:
  - [커뮤니티, 2025-05-05] r/LocalLLaMA — 질문자가 **S25 Ultra** 보유자로, 폰(Whisper) vs 집 서버(Mac mini M4 16GB, 감시 디렉터리) 두 안을 고민. 답변: "whisper.cpp를 Termux에서 돌리면 **S24Ultra가 large 모델로 1분 오디오를 1분에** 전사"(모델 버전·양자화·언어·스레드 미상) → RTF≈1 — https://old.reddit.com/r/LocalLLaMA/comments/1kf86st/whisper_transcription_workflow_home_server_vs
  - [커뮤니티, 2026-07-17] whisper.cpp Discussion #3943: **Honor Magic 8 Pro(Snapdragon 8 Elite Gen 5, 12GB)**, Termux(F-Droid), 루트 없음. 120초 영어 오디오, **small 모델**: Vulkan(Adreno 840, Turnip/Mesa 드라이버) **27.8초(RTF≈0.23)** vs CPU(6스레드) **2분 0.8초(RTF≈1.0)** → GPU 4.3배. 제조사 Vulkan 드라이버는 크래시해 Turnip 필요, shaderc 빌드 패치 필요, Termux가 백그라운드에서 SIGKILL될 수 있어 wake-lock·포그라운드 필요(작성자 "AI 어시스턴트 도움 받았으나 모든 수치는 실제 기기 출력"이라고 명시) — https://github.com/ggml-org/whisper.cpp/discussions/3943 . S25는 Adreno 830이며 이 방법의 S25 재현 보고는 확인 못 함.
  - [커뮤니티, 2025-12-16] whisper.cpp Discussion #3567(미답변 후 2026-10-07 답글): tiny q8_0, CPU 4스레드로 안드로이드 **스트리밍 반복 호출 시 1초 오디오에 5–7초** — 호출마다 전체 파이프라인 재실행 때문(답글). 일괄(배치) 모드는 빠름.
  - VoicePing(S10, 2019): whisper.cpp GGML Tiny 30초 클립 105.6초(RTF 3.52) vs sherpa-onnx Tiny 2.1초 — 구형 기기·패키지 상이.
- **FUTO Voice Input/Keyboard** [원문 README 미러 + 이슈 2026-08-02]: whisper.cpp 포크 **CPU 전용**(`use_gpu=false`), 자체 ACFT 파인튜닝 모델, 모델 tiny/base/small(Multilingual-244 등), UI 언어에 **Korean 포함**(학습 1,000시간 이상 언어만 노출), 기본 30초 제한(Long-form 설정으로 해제, 품질 저하 경고). **받아쓰기 키보드 용도**이며 파일 일괄 전사·화자 분리 없음. 2019년 폰에서 문장당 3–10초라는 이슈 인용. — https://github.com/lrq3000/futo-voiceinput-whisper (미러), https://github.com/futo-org/voice-input/issues/168
- **Transcribro**: whisper.cpp + Silero VAD 키보드, **README상 영어만 지원**(다른 언어는 이슈 #18 계획) — https://github.com/soupslurpr/Transcribro . **WhisperIME**: Reddit 답변에서 이름만 언급, 한국어·성능 확인 못 함.
- **Termux 스크립트형 래퍼**: `itsmuaaz/termux-whisper`, `talk2harsh1/termux-whisper`(파일 선택·배치·자막, 모델 tiny~large-v3-turbo) — 검색 결과 상 존재만 확인, 한국어·속도 실측 확인 못 함. HF 블로그 가이드(Javed Alam, 2025-08-27, Samsung 태블릿): Termux에서 whisper.cpp 빌드·`large-v2`까지 모델 교체 안내, **속도 수치 없음** — https://huggingface.co/blog/Javedalam/wwhisper-cli
- **Hexagon/OpenCL 빌드(qvac-fabric-speech.cpp)**: Whisper tiny/base 검증 문서(WHISPER-HEXAGON.md); **large-v3는 Hexagon에서 검증된 문서 없음**(확인 못 함). 빌드에 Qualcomm Hexagon SDK 필요.
- **설치 난이도**: Termux 경로 중간(빌드 수십 분, 패치 필요), 앱 경로(FUTO) 쉬움이나 용도가 다름. 라이선스 MIT(Whisper·whisper.cpp).
- **일괄 처리·자동화**: Termux는 가능. 아래 §7 참고.

### 4-4. MOSS-Transcribe-Diarize on S25 (Tether QVAC `qvac-fabric-speech.cpp`)
- **무엇인가** [원문]: STT+화자+타임스탬프 일체형 MOSS-Transcribe-Diarize(공개 0.9B, local-stt §4-1)를 ggml GGUF로 포팅, `--backend hexagon|opencl|cpu`. https://github.com/tetherto/qvac-fabric-speech.cpp (문서: engines/parakeet/docs/moss-transcribe.md)
- **S25 실측** [원문, 같은 폰 `moss-transcribe`, CPU 6스레드, 각 긴 클립은 thermal status 0에서 시작, q8_0 3회 중앙값]:

| 오디오 | 백엔드 | 총 시간 | RTF |
|---|---|---|--:|
| 27.3 s | CPU q8_0 | 11.7 s | 0.428 |
| 27.3 s | OpenCL(Adreno 830) q8_0 | 7.1 s | 0.259 |
| 27.3 s | **HTP0(Hexagon) q8_0** | 3.5 s | **0.130** |
| 160.6 s | CPU / OpenCL / **HTP0** (q8_0) | 112.3 / 53.0 / **29.4 s** | 0.699 / 0.330 / **0.183** |
| 191.2 s | CPU / OpenCL / **HTP0** (q8_0) | 137.8 / 67.9 / **37.7 s** | 0.721 / 0.355 / **0.197** |
| 191.2 s | HTP0 f16 | 49.3 s | 0.258 |

  병목은 디코딩(메모리 대역폭): HTP0는 인코더 19–28배 빠르지만 디코더는 1.06–1.33배. CPU와 HTP0 전사 결과의 단어·화자 라벨 동일(타임스탬프 차이 ≤0.05 s). 인코더 상태 코사인은 HTP0 q8_0가 CPU보다 레퍼런스에 가까움(0.9975 vs 0.9933).
- **한국어**: 이 문서의 검증 언어는 **스페인어·중국어**(장문 FLEURS 연결 2–30분: 스페인어 WER 2.1–3.9%, 중국어 CER 9.4–12.1%, Metal·M1 Ultra 등 Mac 기준)이며 **영어는 장문에서 구간을 건너뛴다**고 문서가 명시(레퍼런스 모델도 동일). **한국어는 미검증.** 공개 0.9B의 한국어 수치 부재는 local-stt §4-1 그대로.
- **화자 분리**: 모델이 `[Sxx]` 라벨 직접 출력(일체형).
- **1시간 녹음 [추정]**: RTF 0.18–0.20을 선형 외삽하면 60분 ≈ 11–12분(가장 긴 실측이 191초라 외삽). 문서가 "기본 컨텍스트 5120은 15분 이상 녹음에 짧다"는 취지(Mac 서술)를 적고 있어 분할 처리·`workload-too-large` 오류 대비 필요. 발열·배터리 실측은 없음("thermal status 0에서 시작"이라는 조건만 기재).
- **설치 난이도**: **매우 높음.** Android NDK + Hexagon SDK 6.6 + Hexagon Tools, 특정 ggml 커밋(`qvac-ext-ggml` speech 브랜치) 필요, q8_0/f16 GGUF만(q5_0 거부). 완성 앱 없음(QVAC SDK는 JS/Python 개발 프레임워크).
- **라이선스**: 엔진 Apache-2.0, 모델 Apache-2.0(MOSS) — 문서상. **일괄 처리**: CLI·C++ API로 직접 구현.

### 4-5. Moonshine Voice (한국어 지원 소형)
- **무엇인가**: 저지연 온디바이스 STT, Android(Maven `ai.moonshine:moonshine-voice`)·iOS 등. README: STT 지원 언어에 **Korean 포함**. — https://github.com/moonshine-ai/moonshine
- **한국어 수치** [원문]: 모델 문서 Korean Tiny 26M, **6.46%**, 라이선스 **Community**(비상업 — "legacy non-streaming models for languages other than English stay under the non-commercial license"), **한국어 스트리밍 모델 아직 없음**; 점수는 구 풀 FLEURS 방식이라 스트리밍 행과 비교 불가 — https://moonshine-voice.readthedocs.io/en/stable/models/available-models/ . HF `UsefulSensors/moonshine-tiny-ko`(2025-09): FLEURS CER 8.9 / Common Voice 17 CER 14.94 vs whisper medium 6.99 / 9.38 — https://huggingface.co/UsefulSensors/moonshine-tiny-ko
- **화자 분리·1시간·실측(폰)**: 없음/확인 못 함. 정확도가 Whisper medium급에도 못 미침 → "large-v3급" 목표와 거리가 큼. 개인 사용 가능 여부는 라이선스 문구 재확인 필요.

### 4-6. Gemma 3n / Gemma 4 오디오 입력(LiteRT-LM)
- [원문 Google] Gemma 4 E2B/E4B/12B는 오디오 ASR 학습, **오디오 최대 30초**, 초당 25토큰, 모노 16kHz — https://ai.google.dev/gemma/docs/capabilities/audio . Android는 LiteRT-LM으로 구동(Google AI Edge Gallery 등).
- 한국어: [커뮤니티, 2026-06-06] HF `gemma-4-12B-it` 토론: llama-server(Q4_K_M)에서 약 10초 한국어 통화 클립이 정확히 전사, "30초 상한, 길면 열화" — 폰 구동 아님, 표본 1개. 폰 속도·1시간 처리·화자 분리 확인 못 함. 청크 분할 파이프라인을 직접 만들어야 함. **일체형 요약은 가능하나 전사 용도로는 증거가 부족.**

### 4-7. ExecuTorch Whisper Android 예제 / MLC / MediaPipe
- ExecuTorch: Whisper Android 예제 앱 존재(녹음→전사, XNNPACK·Qualcomm 백엔드) — https://github.com/meta-pytorch/executorch-examples/tree/main/whisper/android/WhisperApp , PyTorch 블로그 https://pytorch.org/blog/building-voice-agents-with-executorch-a-cross-platform-foundation-for-on-device-audio/ . S25·한국어·large 모델 속도 공개 수치 확인 못 함(검색 요약에 나온 Galaxy tok/s 수치는 LLM 얘기로 Whisper와 무관해 제외).
- MLC·MediaPipe로 Whisper/Qwen3-ASR을 폰에서 돌린 사례: 이번 조사에서 한국어·S25 관련 확인 못 함. llama.cpp의 Qwen3-ASR 지원 발표는 있었으나(Xuan-Son Nguyen X 게시물, 검색 요약만) 폰 실측 확인 못 함.
- Qwen3-ASR-1.7B의 Snapdragon NPU 사전 컴파일 사례: `diarizeapp/qwen3-asr-1.7b-onnx-qnn` — **Snapdragon X Elite(PC) 전용, 영어·일본어 4클립 측정(RTF 0.489)**, 한국어 아님·폰 아님 — https://huggingface.co/diarizeapp/qwen3-asr-1.7b-onnx-qnn

### 4-8. NVIDIA Nemotron 3.5 ASR Streaming 0.6B (폰 사례)
- local-stt §5-6에서 한국어 지원(FLEURS WER 7.12, CER 아님). 폰 사례: `catfewd/nemotron-voice-keyboard`(MIT, ONNX Runtime INT8 안드로이드 음성 입력 키보드·실시간 자막)가 존재하나 한국어 사용·속도 확인 못 함(README에 언어 언급 없음). transcribe.cpp 문서상 ko-KR locale 지원 문구는 있으나 Android 공식 빌드 없음(FUTO 이슈 2026-08 기준). 화자 분리 없음.

---

## 5. 폰 위에서 "Mac large-v3급" 정확도를 노릴 때의 실제 선택지 (속도·자원 관점 정리)

| 경로 | 정확도 천장(한국어, 제3자) | 폰 속도 근거 | 화자 분리 | 비고 |
|---|---|---|---|---|
| whisper.cpp large-v3 (CPU, Termux) | large-v3 그대로(평균 CER 7.83) | S24U "1분→1분"(RTF≈1, 2025-05, 상세 미상) | 별도 | 1시간 ≈ 1시간 [추정]. 발열·배터리 수치 확인 못 함 |
| whisper.cpp large (Vulkan/Turnip) | large-v3 그대로 | small로만 Magic 8 Pro RTF 0.23(영어) | 별도 | large 값·S25 값 확인 못 함 |
| AI Hub Whisper-large-v3-**turbo** (NPU) | turbo(평균 CER 9.36, 콜센터 10.00) | 인코더 305 ms/30초 + 6.7 ms/토큰(프로파일) | 별도 | 개발 필요, 200토큰 상한 |
| AI Hub Whisper-**medium** (NPU) | 한국어 medium은 평균 CER 16.53(약함) | 프로파일 미열람 | 별도 | 비권장 |
| MOSS-Transcribe-Diarize (HTP, QVAC) | 한국어 미검증 | S25 RTF 0.18–0.20 | **일체형** | 개발자 빌드 |
| Recly (Qwen3-ASR 0.6B) | 평균 CER 17.29, 전화 59.62 | 폰 값 없음 | 온디바이스(문장 단위) | 설치 쉬움 |
| Samsung 텍스트 변환 | 비공개 | 비공개 | Speaker 1/2 | 삼성 앱 녹음 한정 |

(한국어 CER 열은 local-stt §2-1 표 인용: AI Hub 데이터·CV15·FLEURS·KsponSpeech의 30초 이하 발화, RTX 5090 서버 측정. 폰·장문·다화자 조건 아님.)

---

## 6. 속도 · 발열 · 배터리 · 1시간 녹음 — 공개된 것만

| 근거 | 기기 | 조건 | 값 | 출처/날짜 |
|---|---|---|---|---|
| Qualcomm AI Hub 프로파일 | Snapdragon 8 Elite For Galaxy(호스팅 장비) | Whisper-L-v3-turbo float, QNN | 인코더 305 ms/30 s, 디코더 6.74 ms/tok | HF README v0.66.0 (2026-11 초) |
| whisper-htp-android | v79 XR 기기(수동 냉각) | 동일 모델, high_performance | 인코더 ~0.8 s/창, ~12 ms/tok; burst는 속도 동일·열 위험 | 저장소 2026-07-21 |
| QVAC MOSS | **Galaxy S25** | q8_0, HTP0/OpenCL/CPU | RTF 0.18–0.20 / 0.33–0.36 / 0.70–0.72 (160–191 s) | 문서(2026-10) |
| Reddit | S24 Ultra | whisper.cpp large(상세 미상), CPU | ≈1분/분 | 2025-05-05 |
| whisper.cpp #3943 | Honor Magic 8 Pro (8 Elite Gen 5) | small, 영어 120 s | GPU 27.8 s / CPU 120.8 s | 2026-07-17 |
| VoicePing | Galaxy S10(2019) | sherpa-onnx, 영어 30 s | Whisper Turbo 17.9 s(RTF 0.60), Qwen3-ASR 0.6B 15.9 s(0.53), SenseVoice 1.7 s(0.06), Small 12.3 s(0.41) | 2026-09-21 갱신 |
| whisper.cpp #3567 | 미상 안드로이드 | tiny q8_0, 스트리밍 | 1초당 5–7초(구조 문제) | 2025-12-16 |

- **배터리 소모량(%/시간, mAh) 실측**: 이번 조사에서 한 건도 **확인 못 함.** npu-lab 문서의 "NPU ≈3W vs 데스크톱 GPU ≈250W"는 저자 추정치(문서에 "оценка")이며 측정이 아님.
- **발열**: 근거는 ① whisper-htp-android(burst 모드 연속 사용 시 thermal emergency) ② meeting-transcriber-sherpa의 ThermalGuard(제어 설계 존재) ③ QVAC 문서가 측정을 "thermal status 0에서 시작"으로 한정하고 5분 이상 반복 측정 절차를 권고(WHISPER-HEXAGON.md). **S25 Ultra 1시간 연속 처리 시 스로틀링 발생 여부·정도는 확인 못 함.**
- **1시간 녹음 처리 가능성 — 정리**: 가능하다는 "공개 실측"은 없고, 산술 [추정]만 있다. NPU turbo 약 2–5분, MOSS(HTP) 약 12분, CPU large 약 60분. 메모리는 12GB 기준 여유(whisper large ≈3.9GB, local-stt §5-2 인용).

---

## 7. 녹음 저장 → 폰에서 자동 전사: 공유된 사례

- **삼성 통화 녹음 자동 전사**: [원문] 전화 앱 설정 "Auto transcribe recorded calls"(ANS10004613). 통화 한정.
- **Recly**: 녹음 종료 시 자동 전사(앱 내부 녹음), 외부 파일은 수동 "Import". 폴더 감시 자동화는 문서에서 확인 못 함.
- **Termux + inotifywait + whisper-cli** 스크립트 예시는 검색 도구 요약에 등장했으나(검색 요약만, 출처 한 곳도 사용자 실측 공유 아님) **"삼성 음성 녹음 폴더를 감시해 자동 전사했다"는 사용자 공유 사례는 확인 못 함.** 근접 사례: whisper.cpp #3943의 완성 파이프라인 스크립트(yt-dlp→whisper.cpp GPU→번역→ffmpeg, 영어 입력, 폴더 감시 아님). 해당 글이 안드로이드의 phantom process killer로 Termux 빌드·실행이 SIGKILL될 수 있다고 명시(포그라운드·wake-lock 권고).
- **폰→서버 감시 디렉터리 안**: r/LocalLLaMA 2025-05 글에서 질문자가 제안한 구성(Mac mini M4에 감시 디렉터리 + 폰에서 전송 앱) — 실제 구축 결과 공유는 확인 못 함. 이 안은 "녹음이 폰을 떠난다"는 점에서 사용자 요건(Mac mini는 개인 장비라 허용)과 별개로 평가해야 함.
- 삼성 Voice Recorder의 파일 위치: My Files > Internal storage > Recordings > Voice Recorder(Flint 블로그 2026-10-26)라서 외부 도구가 읽을 수는 있으나, 삼성 앱 자체 전사를 외부에서 트리거하는 방법은 확인 못 함.

---

## 8. "실측해 볼 가치" 판단표

판단 기준: 사용자 목표(한국어, 2인 이상, 녹음이 밖으로 안 나감, 가능하면 화자 분리·요약). ◎ 지금 해볼 가치 큼 / ○ 조건부 / △ 낮음 / × 비권장.

| 후보 | 한국어 근거 | 화자 분리 | 폰 속도 근거 | 노력 | 판단 | 첫 실험(소요) |
|---|---|---|---|---|---|---|
| **삼성 텍스트 변환 어시스트(기기 전용 모드)** | 공식 지원, 사용자 평가 엇갈림 | ○ (Speaker N) | 비공개 | 5분, 설정만 | **◎** | 비행기 모드+"기기에서만 처리" ON으로 10–20분 실제 녹음을 전사 → 정답과 비교. 안 되면 탈락, 되면 기준선 |
| **Recly(Qwen3-ASR 0.6B + diarizer)** | 모델 0.6B: 전화 저음질 약함, 회의 13.78 | ○ (문장 단위) | 없음 | 설치 쉬움 | **◎** | 같은 녹음 파일 Import → 시간·발열·CER·화자 오류 측정. Drive·외부 API·ChatGPT 연동은 끈 상태 |
| **Google ML Kit GenAI Speech (Advanced, ko-KR)** | 수치 없음, Gemini Nano 기반 | × | 없음 | 소형 앱 개발(샘플 앱 있음) | ○ | googlesamples/mlkit speech 샘플을 빌드해 `checkStatus()`로 S25 가용성, "Audio File" 데모로 한국어 파일 전사 |
| **AI Hub Whisper-large-v3-turbo(NPU)** | turbo 한국어 열세(local-stt) | × | 프로파일 있음(가장 유리) | 높음(QNN 통합) | ○ | 개발 투자 전에 Mac mini에서 turbo vs large-v3 vs Qwen3-ASR 1.7B로 사용자 녹음 CER을 비교해 turbo 정확도가 허용 가능한지 먼저 판단 |
| **MOSS-Transcribe-Diarize on HTP(QVAC)** | 한국어 미검증 | ◎ 일체형 | **S25 실측 있음(RTF≈0.2)** | 매우 높음 | △(Mac에서 먼저 한국어 검증 후 판단) | local-stt §7 조합 C에서 한국어 CER/cpCER가 나오면 그때 폰 이식 가치 평가 |
| **whisper.cpp large-v3 (Termux, CPU)** | large-v3 천장 | × | RTF≈1(1건 Reddit) | 중간(빌드) | ○ | 10분 한국어 녹음으로 RTF·배터리%·온도 직접 측정 — 유일하게 "large-v3 정확도를 폰에서" 얻는 경로 |
| whisper.cpp small (Vulkan/Turnip) | small은 한국어 약함(medium 16.53) | × | 8 Elite Gen5 small RTF 0.23 | 높음(패치) | △ | 정확도 부족으로 비권장 |
| sherpa-onnx + SenseVoice/Zipformer-Kspon/Whisper (APK) | 한국어 모델 있음, 대화 수치 없음 | diarization APK 별도(과분할 사용기) | S10 값만 | 중간 | △ | 정확도 비교용 보조(속도는 빠름) |
| Moonshine Voice Korean | tiny 6.46%(FLEURS, 구방식) | × | 값 없음 | 중간 | × | 정확도·라이선스(비상업) 문제 |
| FUTO Voice Input / Samsung 키보드 / Transcribro | 받아쓰기 용도, Transcribro 영어만 | × | 값 없음 | 쉬움 | × | 파일 전사 불가 |
| Gemma 4 E2B/E4B 오디오 | 표본 1개, 30초 제한 | × | 값 없음 | 높음 | × | 전사 전용으로는 증거 부족 |
| Google Recorder | - | - | - | - | × | Pixel 전용 |

권고 실측 순서(근거에 따른 제안이며 결론은 아님): **① 삼성 기기 전용 모드 → ② Recly → ③ Termux whisper.cpp large-v3(RTF·발열 측정) → ④ Mac 쪽 결과와 비교.** 모두 같은 10–20분 한국어 대화 녹음 2–3개와 사람이 만든 정답 전사로 CER·cpCER·DER·발열·배터리%를 잰다(local-stt §7과 동일 평가세트).

---

## 9. 핵심 질문: "S25 Ultra에서 Mac의 Whisper large-v3급 한국어 정확도를 얻을 수 있는 경로가 있는가? 있다면 속도·배터리 비용은?"

**근거로 한 답**

1. **정확도 천장 자체는 도달 가능.** Whisper large-v3 가중치(약 3.9GB 메모리)는 12GB 폰에서 whisper.cpp CPU로 구동 가능하며, 실제로 S24 Ultra에서 large 모델을 돌렸다는 보고가 있다([커뮤니티] r/LocalLLaMA 2025-05). 같은 가중치이므로 이론적 정확도는 Mac의 mlx-whisper large-v3와 같다(양자화 손실은 별개 — 한국어 q5_0 beam5는 오히려 좋았다는 제3자 수치 local-stt §5-2, 하드웨어 미명시). **다만 S25 Ultra·한국어 대화에서 실제로 측정한 결과는 공개 자료로 확인 못 함.**
2. **비용은 크다.** 폰 CPU RTF≈1(1시간=약 1시간)로 보고됐고(1건, 조건 불명), 배터리 %·발열 수치는 **공개 자료 0건.** whisper-htp-android의 열 경고(연속 burst 사용 시 thermal emergency)는 NPU 경로 기준이지만 동일 SoC 계열의 지속 부하 위험을 시사한다 [추정].
3. **빠른 경로는 정확도를 양보한다.** NPU 공식 패키지는 large-v3가 아니라 **turbo**(+medium 이하)뿐이고, 제3자 한국어 표에서 turbo는 large-v3보다 평균·저음질 전화에서 뚜렷이 약하다(9.36 vs 7.83, 10.00 vs 5.34). 속도는 2–5분/시간 수준 [추정]까지 내려가지만 개발 난이도가 높고 화자 분리는 별도다. 한국어 파인튜닝 turbo(예: ghost613, local-stt §5-4)를 AI Hub `custom weights`로 export하는 방법은 문서상 가능하나 그 사례는 확인 못 함.
4. **화자 분리 일체형(MOSS on HTP)은 S25에서 RTF≈0.2로 실측됐지만 한국어가 검증된 적이 없다.** 정확도 천장 비교 불가.
5. **즉시 쓸 수 있는 완성형은 Qwen3-ASR 0.6B(Recly)이며 이는 Mac의 large-v3/Qwen3-ASR-1.7B보다 한국어 대화·전화 녹음에서 낮은 모델**이라는 제3자 수치가 있다(local-stt §2-1). 삼성 기본 앱은 정확도·속도 모두 비공개라 **기기에서 직접 비교해야만** 알 수 있다.

**요약 판정**: *"large-v3급 한국어 정확도 + 화자 분리 + 1시간 녹음 + 완성된 사용성"을 동시에 만족하는 폰 단독 경로를 뒷받침하는 공개 근거는 없다.* 정확도만 보면 폰 CPU large-v3(느림, 발열 미확인), 속도만 보면 NPU turbo/MOSS(개발 필요, 정확도 열세 또는 미검증), 편의성만 보면 삼성 기본·Recly(정확도 미확정/소형 모델)로 갈린다. 폰 전용으로 가려면 §8의 ①②③을 사용자 실제 녹음으로 측정해 결정해야 하며, 그 결과가 Mac mini/M3 Max의 local-stt §7 조합 A/B 결과보다 얼마나 나쁜지가 최종 기준이 된다.

---

## 10. 확인 못 한 것 (재조사 필요 시 목록)

- S25 Ultra에서 한국어 **삼성 텍스트 변환의 "기기에서만" + 오프라인** 동작 여부와 CER, 화자 분리 정확도.
- ML Kit GenAI Speech(Advanced)의 S25 지원 여부 직접 확인, 한국어 WER, 긴 파일 거동.
- Recly의 폰별 RTF·발열·배터리, 온디바이스 diarizer의 한국어 DER.
- 한국어 전사에 대한 NPU Whisper-turbo의 end-to-end 앱 수준 RTF·발열(S25 기준). Qualcomm Voice AI SDK(QPM 배포)의 계정·라이선스 조건.
- whisper.cpp large-v3의 S25 Ultra 실측(RTF·배터리%·온도·양자화별).
- Samsung 음성 녹음 앱이 외부에서 가져온 오디오 파일을 전사하는지.
- 폴더 감시형 자동 전사의 실사용자 공유 사례(Termux+Tasker 등).
- WhisperKit Android 최신 상태·한국어·S25 벤치(HF Space 미열람), MLC/MediaPipe Whisper·Qwen3-ASR 폰 사례, llama.cpp Qwen3-ASR 폰 실측.
- Samsung 서비스센터 문서(samsungsvc.co.kr/solution/1847983)와 Samsung Levant 문서 원문 직접 열람(Subanana/검색 요약 경유로만 확인).
