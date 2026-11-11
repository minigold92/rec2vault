# 유사·인접 오픈소스 조사 + 저장소 이름 후보 검토

- 작성일/확인일: 2026-11-09 (모든 스타 수·마지막 커밋·라이선스는 이 날짜에 GitHub API로 직접 조회)
- 검증 수준: **README·GitHub API 열람으로 확인** (코드 실행·설치·실제 녹음 입력 검증은 하지 않음). "README에 없음" = 기능이 없다는 뜻이 아니라 **확인 못 함**.
- 조회 방법: `https://api.github.com/repos/<owner>/<repo>` (stars, license, created), `.../commits?sha=<default branch>&per_page=1` (마지막 커밋 날짜), `.../readme` (본문). 후보 발굴은 `https://api.github.com/search/repositories?q=...` 및 웹 검색.
- 표기: `[추정]` = 근거 문서에 직접 없고 내가 추론한 것. `확인 못 함` = 접근 가능한 문서에서 못 찾음.
- 한국어 지원 판단 기준: (1) README/문서에 한국어 명시, (2) 엔진 자체가 한국어 지원(Whisper: `"ko": "korean"` — https://github.com/openai/whisper/blob/main/whisper/tokenizer.py 16행, Qwen3-ASR: README 언어표에 Korean — https://github.com/QwenLM/Qwen3-ASR, Parakeet TDT v3: 25개 유럽어, 한국어 없음 — https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 태그). 프로젝트 README가 한국어를 말하지 않으면 "엔진 기준 [추정]"으로만 적었다.

---

## 1. 결론 먼저

1. **이 조합 전체(안드로이드 기본 녹음 앱 → Syncthing → Mac mini 무인 처리 → Qwen3-ASR(+ForcedAligner) 한국어 → Nemotron 3 Diarization(MLX) → 구독 CLI 보정·요약 → 한국어 properties + 근거 시각 블록 링크 Obsidian 노트)를 그대로 하는 공개 프로젝트는, 내가 GitHub 검색(수십 개 쿼리)·웹 검색으로 찾은 범위에서는 발견하지 못했다.** 단 "없다"의 증명은 아니다(GitHub 검색·README 기준, 비공개/비영어권 저장소 누락 가능).
2. 하지만 **조각 대부분은 이미 따로 공개돼 있고, 일부는 매우 가깝다.** 2026년 하반기에 비슷한 개인 프로젝트가 급증했다(대부분 스타 0~10, 2026-06 이후 생성). 차별점을 "이런 건 없다"로 내세우면 안 된다.
3. **가장 가까운 것 3개**
   - `silverstein/minutes` — Android+Syncthing 등 폴더 동기화 → 감시 폴더 → 로컬 전사 → pyannote-rs 화자 분리 → `claude/codex/opencode/pi` 구독 CLI 요약 → Markdown(Obsidian 호환). 가장 넓은 겹침. 한국어 특화·Qwen3-ASR·Nemotron·근거 블록 링크는 확인 못 함.
   - `sjoon21/Tractus` — Apple Silicon MLX + Qwen3-ASR 한국어 + 화자 감지 + Obsidian 보내기 + 요약 항목→오디오 시각 링크. 단, 데스크톱 앱(녹음/파일 가져오기)이고 폴더 감시·Syncthing은 README에서 확인 못 함.
   - `mindrepublic2018/plaud-obsidian-pipeline` + `libaoming/meet-scribe` — 한국어 기본값·`claude -p`/`codex exec` 구독 경로·Obsidian·launchd 무인화. 입력이 Plaud 기기(전자) / iPhone iCloud(후자).
4. **안 겹치는(= 이 프로젝트가 내세울 수 있는) 지점**: (a) "삼성 갤럭시 기본 녹음 앱 그대로 + 아무 앱도 설치 안 함"을 전제로 한 안드로이드 쪽 설계, (b) Nemotron 3 Diarization MLX + Qwen3-ASR 1.7B/ForcedAligner 한국어 조합, (c) Gemini 계열 CLI까지 포함한 구독 CLI 요약, (d) 한국어 properties와 블록 링크 근거 표기, (e) SQLite 작업 상태·재시도·1분 launchd. 이들 각각은 부분적으로 타 프로젝트에 있으나 **한 번에 묶어 한국어로 문서화한 것은 못 찾음**. 이 문장도 "찾지 못함" 수준으로만 써야 한다.
5. 안드로이드+Syncthing 무인 처리에서 실제 사고가 문서화돼 있다: Syncthing이 쓰는 중인 m4a(moov atom 없음)를 감시기가 옮기거나 지우면 삭제가 폰으로 역전파됨 — https://github.com/surfnterd/syncthing-partial-recordings (확인 2026-11-09). 이 프로젝트의 "정상·비정상 입력 처리 방침/테스트" 문서에 그대로 반영할 가치가 있다.
6. **이름**: `local-meeting-notes`는 Obsidian 커뮤니티 플러그인 id와 GitHub 동명 저장소 다수와 충돌 → 비추. `galaxy-minutes`는 충돌은 없으나 Samsung GALAXY 상표(미국 등록 5241602, 휴대폰 등) 혼동 위험 → 비추. `rec2note`는 GitHub에 동명 저장소(`YutoShimmyo/rec2note`, 같은 목적) 존재 → 비추. **추천: `rec2vault`(GitHub/PyPI/npm/crates/Homebrew/Obsidian 목록 모두 0건), 차선 `phone2minutes`.** 상세는 4절.

---

## 2. 프로젝트 표

범례: ★ = GitHub stars(2026-11-09), 커밋 = 기본 브랜치 마지막 커밋 날짜(UTC 날짜), 생성 = 저장소 생성일.
ID 접두: A 폰/웨어러블/전용 녹음기→서버, B 데스크톱 회의 앱, C 폴더 감시·파이프라인·엔진, D Obsidian 플러그인, E 구성요소(모델·라이브러리).

### 2-1. 식별·현황

| ID | 저장소 | 한 줄 설명 | 라이선스 | ★ | 마지막 커밋 | 생성 | 플랫폼 |
|---|---|---|---|---|---|---|---|
| A1 | https://github.com/BasedHardware/omi | 목걸이형 오픈소스 AI 웨어러블 + 폰/데스크톱 앱 + 백엔드(대화를 기억으로) | MIT | 13,930 | 2026-11-09 | 2024-03-22 | iOS/Android(Flutter), macOS, Windows, 펌웨어 nRF/ESP32 |
| A2 | https://github.com/guzus/open-plaud | Plaud 대안: DIY 하드웨어 + 전사→화자분리→요약 파이프라인 | MIT | 22 | 2026-10-15 | 2026-06-07 | Python 서버, iOS 온디바이스 전사 패키지; Android 확인 못 함 |
| A3 | https://github.com/suyiiyii/alldayrec | 셀프호스트 종일 녹음·화자 인식·요약·MCP 서버(중국어 중심) | MIT | 13 | 2026-11-09 | 2026-10-23 | 서버(Docker/PyPI), Android APK, iPhone 앱, 웹 |
| A4 | https://github.com/skyhong2002/localplaud | Plaud 녹음을 미러링해 자체 전사·화자·노트·Q&A | MIT | 4 | 2026-11-04 | 2026-07-09 | 서버(Apple Silicon/NVIDIA/CPU), 웹 UI |
| A5 | https://github.com/riffado/riffado (구 openplaud/openplaud, API가 이 이름으로 리다이렉트) | Plaud 기기 클라우드에서 동기화해 자체 전사하는 셀프호스트 앱 | AGPL-3.0 | 442 | 2026-09-18 | 2025-11-26 | Docker(Linux/macOS), 웹 |
| A6 | https://github.com/floatboatai/OpenMinutes | MemoTalk S1 녹음기 MP3 가져오기·전사·분류·검색 워크벤치 | MIT | 106 | 2026-11-08 | 2026-10-28 | Floatboat Workbench 앱(UI 중국어) |
| B1 | https://github.com/Zackriya-Solutions/meetily | 프라이버시 우선 회의 노트(Granola/Otter 대안), 온디바이스 | MIT(+유료 PRO) | 32,548 | 2026-11-02 | 2024-12-26 | Windows, macOS(Apple Silicon), Linux는 소스 빌드 |
| B2 | https://github.com/fastrepl/anarlog (구 Hyprnote; fastrepl/hyprnote이 이 이름으로 리다이렉트) | 봇 없는 로컬 우선 회의 노트(Granola 대안). 팀은 현재 char.com 개발 | MIT(+상용 엔터프라이즈 구성요소) | 9,830 | 2026-11-05 | 2024-12-09 | macOS, Windows, Linux |
| B3 | https://github.com/RecapAI/Recap | macOS 네이티브 회의 요약(Core Audio Taps + WhisperKit + Ollama) | MIT | 719 | 2026-02-07 | 2025-08-02 | macOS |
| B4 | https://github.com/thewh1teagle/vibe | 로컬 전사 GUI/CLI/HTTP API; QR로 폰 녹음→PC 전사 | MIT | 8,038 | 2026-10-30 | 2024-01-08 | macOS, Windows, Linux |
| B5 | https://github.com/rishikanthc/Scriberr | 셀프호스트 오디오 전사 웹앱(Parakeet/Canary/Whisper) | MIT | 3,143 | 2026-09-20 | 2024-10-04 | Docker/Homebrew(macOS·Linux), 웹 |
| B6 | https://github.com/kaixxx/noScribe | Whisper+pyannote GUI 전사(인터뷰·연구용) | GPL-3.0 | 2,234 | 2026-11-07 | 2023-05-12 | Windows, macOS, Linux |
| B7 | https://github.com/sblattj/whosaid | Apple Silicon 로컬 Whisper+화자 분리 CLI | MIT | 9 | 2026-11-09 | 2026-07-22 | macOS Apple Silicon |
| B8 | https://github.com/chidiwilliams/buzz | Whisper 기반 오프라인 전사·번역 데스크톱 앱 | MIT | 22,540 | 2026-11-09 | 2022-09-24 | macOS(Apple Silicon 필요), Windows, Linux |
| B9 | https://github.com/OpenWhispr/openwhispr | 음성 받아쓰기+회의 전사+노트(로컬/클라우드 선택) | MIT | 11,075 | 2026-11-09 | 2025-06-19 | macOS, Windows, Linux |
| B10 | https://github.com/sjoon21/Tractus | Mac 로컬 AI 노트(한국어·영어), 시각 근거 링크, MCP | Apache-2.0 | 5 | 2026-11-06 | 2026-10-02 | macOS Apple Silicon |
| B11 | https://github.com/Baladhurgesh/minutes | Apple Silicon 로컬 회의 노트: Parakeet + Nemotron 3 Diarization + Qwen3-0.6B | MIT | 2 | 2026-09-26 | 2026-09-26 | macOS 14+ Apple Silicon |
| B12 | https://github.com/jmmi/meeting-moa | 미팅모아: 한국어 UI Mac 회의 노트, 요약은 Codex/Claude Code CLI | MIT | 0 | 2026-10-04 | 2026-09-26 | macOS 14+(소스 빌드, v0.2 개발 미리보기) |
| B13 | https://github.com/teconomix/local-transcriber | 메뉴바 녹음·전사·화자 인식·폴더 감시·MCP | MIT | 11 | 2026-11-02 | 2026-10-10 | macOS Apple Silicon |
| B14 | https://github.com/mameli/Takku | 메뉴바 회의 녹음→로컬 전사→요약을 Markdown/Obsidian에 기록 | MIT | 6 | 2026-11-06 | 2026-10-05 | macOS 15+ Apple Silicon |
| B15 | https://github.com/homelab-00/TranscriptionSuite | 로컬 STT 서버+대시보드(다중 모델, 화자 분리, 캘린더) | GPL-3.0 | 810 | 2026-09-24 | 2025-04-25 | Windows 11, Linux, macOS(MLX) |
| C1 | https://github.com/silverstein/minutes | 로컬 우선 회의·음성메모·받아쓰기 "대화 기억", 폰 메모 파이프라인 문서화, MCP | MIT | 1,596 | 2026-11-09 | 2026-03-18 | macOS 데스크톱 앱+CLI(Rust); 타 OS 확인 못 함 |
| C2 | https://github.com/fryktik99/local-first-daily-assistant | Syncthing 인박스→whisper.cpp→로컬 LLM→Telegram, 무인 파이프라인 | MIT | 1 | 2026-09-24 | 2026-08-10 | macOS(Metal)/CUDA |
| C3 | https://github.com/surfnterd/syncthing-partial-recordings | (소프트웨어 아님) Android 녹음+Syncthing 감시기 함정(불완전 m4a, 삭제 역전파) 설명 | MIT | 1 | 2026-09-08 | 2026-09-08 | 문서 |
| C4 | https://github.com/libaoming/meet-scribe | launchd WatchPaths→WhisperX+pyannote→`claude -p`→Obsidian | MIT | 0 | 2026-08-12 | 2026-07-16 | macOS |
| C5 | https://github.com/mindrepublic2018/plaud-obsidian-pipeline | Plaud 녹음→전사→6섹션 회의록→Obsidian(한/영 README), 구독 CLI 옵션 | MIT | 0 | 2026-11-07 | 2026-06-10 | macOS |
| C6 | https://github.com/hele211/voice2note | macOS Voice Memos→whisper.cpp→`codex exec`→Obsidian | MIT | 0 | 2026-06-17 | 2026-06-17 | macOS |
| C7 | https://github.com/eitanfire/memnon | iPhone 음성메모→iCloud→whisper.cpp→OpenAI/Ollama→Obsidian, MCP | 없음(미명시) | 2 | 2026-11-07 | 2026-05-16 | macOS(launchd 1분) |
| C8 | https://github.com/josephiznot/local-transcriber | 폴더에 파일 떨구면 faster-whisper+화자 레이블 전사 | MIT | 0 | 2026-07-16 | 2026-07-04 | Windows(GPU) |
| C9 | https://github.com/antonizick/MeetingMaster3 | WhisperX+pyannote 화자 전사→Obsidian 네이티브 노트, localhost 웹 | Apache-2.0 | 0 | 2026-10-31 | 2026-10-31 | 로컬 웹 서비스 |
| C10 | https://github.com/m-bain/whisperX | (엔진) Whisper 단어 타임스탬프+pyannote 화자 분리 | BSD-2-Clause | 25,165 | 2026-10-22 | 2022-12-09 | CUDA 중심(Linux/Windows) |
| D1 | https://github.com/changsu-jin/meetnote | Obsidian 플러그인: 녹음→로컬 전사·화자 구분·AI 요약(한국어 README) | 없음(미명시) | 4 | 2026-08-03 | 2026-03-29 | macOS AS(MLX/MPS), Linux/Windows+NVIDIA(Docker); 커뮤니티 목록 미등재(BRAT) |
| D2 | https://github.com/DavidBellamy/steno | Obsidian 플러그인: 녹음/가져오기+클라우드 화자 분리+LLM 처리 | MIT | 1 | 2026-03-15 | 2026-03-14 | Obsidian 데스크톱·모바일; 커뮤니티 목록 미등재 |
| D3 | https://github.com/vincentbavitz/obsidian-vox | Obsidian 플러그인: 감시 폴더 음성메모 자동 전사(로컬 Docker 백엔드) | MIT | 83 | 2026-06-11 | 2023-05-30 | Obsidian + Docker; 커뮤니티 목록 id `vox` |
| D4 | https://github.com/jiaoyingxing/resojot | Obsidian 플러그인(응声记): 녹음·전사·정리, 모바일 포함 | NOASSERTION(미감지) | 50 | 2026-11-08 | 2026-04-04 | Windows, macOS, iPhone, Android; id `resojot`; 일부 기능 인증코드 필요 |
| D5 | https://github.com/dloomis/WhisperCal | Obsidian 플러그인: 캘린더+녹음+화자 태깅+LLM CLI 후처리 | NOASSERTION(미감지) | 6 | 2026-11-06 | 2026-03-07 | macOS, Windows(일부 macOS 전용); 커뮤니티 목록 미등재 |
| D6 | https://github.com/brittain9/speech-kit-obsidian-plugin | Obsidian 플러그인: 로컬 받아쓰기·파일 전사·번역·TTS | MIT | 27 | 2026-11-09 | 2026-04-10 | Obsidian; id `local-dictation` |
| E1 | https://github.com/QwenLM/Qwen3-ASR | (모델) Qwen3-ASR 0.6B/1.7B + Qwen3-ForcedAligner-0.6B | Apache-2.0 | 3,863 | 2026-06-26 | 확인 못 함 | 모델/파이썬 툴킷 |
| E2 | https://github.com/9clg6/nemotron-diar-mlx | (구성요소) NVIDIA Nemotron 3 Diarization의 MLX 포팅 | Apache-2.0 | 0 | 2026-10-15 | 2026-10-15 | macOS Apple Silicon(MLX) |
| E3 | https://github.com/soniqo/speech-swift | (라이브러리) Apple Silicon용 ASR/TTS/화자 분리(MLX·CoreML), Qwen3-ASR 포함 | Apache-2.0 | 1,266 | 2026-10-30 | 2026-02-04 | macOS/iOS |

참고(표에서 뺀 것, 같은 날 확인): `skyhong2002`류 Plaud 미러(A4)·`openplaud`(A5)는 Plaud 기기/클라우드 의존이라 "폰 기본 녹음 앱" 경로와 직접 비교 대상은 아님. `stevyhacker/LokalBot`(GPL-3.0, ★89, 2026-11-09), `tancheng33/tingo`(MIT, ★43, 2026-11-09, 중국어 FunASR), `seacen/meetcap`(NOASSERTION, ★303, 2026-11-09)은 조사 중 발견했으나 상세 열람 생략.

### 2-2. 기능·입력·처리 위치

| ID | 입력 경로 | 처리 위치 | 화자 분리(엔진) | 요약 LLM | 결과 형식·연동 | 한국어 지원 근거 |
|---|---|---|---|---|---|---|
| A1 | Omi 웨어러블(BLE), 폰 앱, macOS 앱 | **클라우드 백엔드**가 기본(README: Firebase·Redis·GPU STT/VAD/Diarizer). 로컬 풀스택 개발 구성은 있음 | 백엔드 `Diarizer(GPU)` 구성요소 명시. 엔진명 확인 못 함 | 백엔드 LLM(제공자 확인 못 함) | 앱 내 메모리·대화. Obsidian 연동 확인 못 함 | 확인 못 함 |
| A2 | DIY 녹음기→수집; iOS 온디바이스 전사 | 선택: OpenAI Whisper(클라우드) 또는 whisper.cpp(로컬) | 선택: pyannote/whisperx | Claude(API) 또는 Ollama(로컬) | 서버 파이프라인 산출물. Obsidian 확인 못 함 | Whisper 기준 [추정] |
| A3 | Android/iPhone 앱·웹·飞书录音豆·개방형 녹음기·파일 가져오기 | 서버 셀프호스트. 정식 전사는 클라우드 ASR이 기본(알리바바 百炼 Qwen), `ENGINE=local` 로컬 가능 | "화자 인식·본인 인식" 제공. 엔진 확인 못 함 | 대형 모델 요약(제공자 확인 못 함) | 웹·MCP·CLI | 확인 못 함 |
| A4 | Plaud 클라우드 오디오 미러 또는 파일 업로드 | 단계별 선택: 로컬/자체 워커/클라우드 | Whisper large-v3-turbo + pyannote | 템플릿 노트(제공자 선택) | TXT/SRT/VTT/DOCX/PDF/Markdown | 확인 못 함 |
| A5 | Plaud 클라우드 동기화 | OpenAI 호환 API 또는 브라우저 내 전사 | ElevenLabs Scribe(클라우드) 화자 레이블 | OpenAI 호환 | 로컬/S3 저장 | 확인 못 함 |
| A6 | MemoTalk S1 녹음기(SDK) | Floatboat 음성 인식(위치 확인 못 함) | `speaker_diarization` 설정(기본 1). 엔진 확인 못 함 | AI 분류·정리 | 앱 내 검색 | UI 중국어, ASR `asr_language` 설정만 확인 |
| B1 | 마이크+시스템 오디오, 파일 가져오기 | **로컬** Whisper/Parakeet | README 상충: 저장소 설명에는 diarization 명시, README 본문은 "Speaker Identification"을 **PRO(유료)** 기능으로 나열 → 커뮤니티판 포함 여부 확인 못 함 | Ollama(로컬)/Claude/Groq/OpenRouter/OpenAI 호환 | 앱 내. Markdown 내보내기는 PRO 기능으로 기재(동 README) | Whisper 경유 [추정]; Parakeet v3는 한국어 없음 |
| B2 | 기기 오디오, 파일 | 온디바이스 모델 또는 선택한 제공자 | 확인 못 함 | 로컬/BYO 키/호스티드 | 로컬 SQLite+파일, Markdown 내보내기 | 확인 못 함 |
| B3 | 시스템 오디오+마이크 | 로컬 WhisperKit(MLX) | README에 없음(확인 못 함) | Ollama(로컬)/OpenRouter | 앱 내; README가 "POC에 가깝다"고 기술 | 확인 못 함 |
| B4 | 파일, 마이크, 시스템 오디오, **QR로 폰 브라우저 녹음** | 로컬(Whisper/Nemotron 3.5/Parakeet TDT v3) | 지원(엔진 확인 못 함) | Claude API 또는 Ollama | SRT/VTT/TXT/HTML/PDF/JSON/DOCX, HTTP API, CLI | 확인 못 함(Whisper 경유 [추정]) |
| B5 | 파일 업로드(웹) | 로컬(Parakeet/Canary/Whisper) | 지원: README에서 PyAnnote·NVIDIA NeMo 모델 언급 | Ollama/OpenAI 호환(채팅·요약) | 웹 UI | 확인 못 함 |
| B6 | 파일 | 로컬(faster-whisper) | pyannote | 없음 | 편집 가능 전사 | README "약 60개 언어"(한국어 포함 여부는 문서에서 확인 못 함) |
| B7 | 파일(배치 `ingest`), 마이크/시스템 | 로컬: mlx-whisper + sherpa-onnx 오프라인 diarization(pyannote segmentation-3.0 ONNX + 화자 임베딩, 기본 NeMo TitaNet-small **영어용**) | 위와 동일(README: 임베딩 모델은 말하는 언어에 맞춰야 함) | 선택적 claude 엔진(텍스트만 전송) | 화자 라벨 txt, 회의 폴더 | `-l` 언어 지정 옵션만 확인; 한국어 화자 임베딩 성능 확인 못 함 |
| B8 | 파일, 마이크 | 로컬 Whisper 계열 | "Speaker identification" 기재 | 확인 못 함 | 전사 파일 | Whisper 경유 [추정] |
| B9 | 마이크 핫키, 회의 자동 감지, 파일·URL | 로컬(Parakeet/Whisper) 또는 클라우드 선택 | 로컬 라이브 화자 분리+목소리 지문(ONNX Runtime) | GPT/Claude/Gemini/로컬 | 앱 내 노트 | 확인 못 함 |
| B10 | 앱 녹음(마이크/시스템), 파일 드롭 | **로컬 MLX** | 자동 화자 감지+목소리 프로필(엔진 확인 못 함; 9명↑는 별도 `tractus-diar`) | 사용자가 고른 LLM 서비스(텍스트만 전송). Claude Code/Codex/agy는 MCP 질의·요약 연동 문서 | 일반 파일(JSON/Markdown/SRT 등), **Send to Obsidian**, 요약 항목→오디오 시각 링크 | **Qwen3-ASR로 한국어·영어 자동 감지.** README의 자체 벤치마크: 한국어 회의 CER 9.49 vs Whisper-large-v3-turbo 14.92(자체 측정, 독립 검증 아님) |
| B11 | 마이크+시스템 오디오, 파일 업로드 | **로컬**(MLX; 화자 분리는 FluidAudio CoreML/Neural Engine) | **Nemotron 3 Diarization**(최대 8명) | Qwen3-0.6B(로컬, MLX) | 앱 내, Markdown 내보내기 | ASR이 Parakeet TDT v3(유럽 25개 언어) → **한국어 미지원** |
| B12 | Mac 마이크 녹음, 파일 가져오기 | 로컬(whisper-cpp) | 로컬 발화자 구분(엔진 확인 못 함) | **Codex CLI 또는 Claude Code CLI**(로그인) | Markdown 내보내기, 시각 클릭→원문 재생, 근거 시각 표시 질의응답 | **한국어 전사·한국어 UI 명시** |
| B13 | 마이크+시스템 오디오, **폴더 감시** | 로컬(Whisper large-v3-turbo MLX) | pyannote + 학습형 목소리 DB | Ollama/LM Studio/클라우드(클릭 시, 이름 치환) | txt/Markdown/JSON/SRT | 확인 못 함 |
| B14 | 마이크+시스템 오디오, 파일 가져오기 | 로컬(Parakeet/Whisper) | "Speaker 1,2…" 목소리 기반 | 로컬 모델/OpenAI 호환/**코딩 에이전트 CLI(Codex, Copilot, Claude Code, OpenCode, Pi)** | Markdown 노트+별도 전사, Obsidian 가능 | 확인 못 함 |
| B15 | 파일, 마이크 | 로컬(Docker 또는 macOS 네이티브) | PyAnnote(Whisper/NeMo) 등 | 확인 못 함 | 대시보드, OpenAI 호환 API | README: Whisper 90+ 언어 |
| C1 | **감시 폴더** `[watch].paths`. 문서가 Android→Dropbox/Google Drive/**Syncthing**/폴더 동기화를 명시 | 캡처·전사·저장 로컬 | pyannote-rs(ONNX; segmentation-3.0+CAM++ 또는 community-1+WeSpeaker) | `engine="agent"`: `claude`/`codex`/`opencode`/`pi` 구독 CLI, 또는 Ollama. Gemini CLI를 agent 엔진으로 쓰는지는 확인 못 함(MCP 클라이언트로는 언급) | Markdown(YAML frontmatter), Obsidian/Logseq 호환, MCP | Parakeet v3 문서는 유럽어 한정, "범위 밖 언어는 Whisper" 명시 → 한국어는 Whisper 경유 [추정]. 저장소 코드 검색 "korean" 히트 5건(로케일 파일 등)이었으나 한국어 지원을 말하는 문서는 못 찾음 |
| C2 | **폰/워치 기본 녹음 앱** → Syncthing 인박스 | 로컬 whisper.cpp(Metal/CUDA)+로컬 llama-server LLM | **음향 화자 분리 안 함**: 문법·담화 단서로 LLM이 화자 추정 | 로컬 27B(구독 CLI 아님) | Telegram 전달(Obsidian 확인 못 함). SQLite 중복·리스·아웃박스, 파일 안정화 배리어 | 확인 못 함(문법적 성별 일치 단서 언급 → 한국어 아닐 가능성 [추정]) |
| C3 | Android 녹음기(Fossify 등)+Syncthing | — | — | — | 감시기가 불완전 m4a를 **옮기거나 지우면 Syncthing이 삭제를 폰으로 전파** 한다는 경고, 안정화 대기·untrunc 복구 | 해당 없음 |
| C4 | Mac 마이크(`meet start/stop`) 또는 iPhone 음성메모→iCloud Drive 폴더, launchd WatchPaths | 로컬 WhisperX(CT2 large-v3-turbo)+pyannote community-1 | pyannote | **`claude -p`** | `~/ObsidianVault/meetings/`, inbox/processing/archive/error 디렉터리 상태기계 | README 예시는 `zh`. 한국어 확인 못 함 |
| C5 | **Plaud 기기** 녹음 | 전사 기본 로컬 Whisper, 옵션 WhisperX+pyannote(HF 토큰), 표의 다른 옵션도 있음 | 옵션(WhisperX+pyannote community-1) | Claude API 기본, `*_VIA=subscription`이면 **`claude -p`/`codex exec`** 우선·API 폴백, GPT 교차검증 옵션 | Obsidian 노트(6섹션), 화자별 전문 | **기본 `WHISPER_LANG=ko`, 한국어 README** |
| C6 | macOS 음성메모(CloudRecordings.db) | 로컬 whisper.cpp | 없음 | **`codex exec`**(구독 로그인, API 키 불필요) | 메모별 노트+데일리 노트 요약, launchd ~2시간 | 확인 못 함 |
| C7 | iPhone 음성메모→Shortcut→iCloud | 로컬 whisper.cpp | README에 없음 | OpenAI API 또는 Ollama | Obsidian 노트+TypeScript MCP 서버, launchd 1분 | 확인 못 함 |
| C8 | **감시 인박스** 폴더(README: 예전 Syncthing 페어 인박스 레이아웃 호환) | 로컬 GPU faster-whisper large-v3 | sherpa-onnx 로컬(CPU) | 없음 | `.txt`/`.srt`, processed/failed 폴더 | 확인 못 함 |
| C9 | 웹 업로드 | 로컬 WhisperX+pyannote | 지원 + 화자 이름 지정·목소리 지문(옵션) | Ollama 기본, BYO 클라우드 | Obsidian 네이티브(frontmatter·wikilink·체크박스) | 확인 못 함 |
| C10 | 파일 | 로컬 | pyannote(HF 토큰 필요) | 없음 | 단어 타임스탬프 전사 | README 언어 설명 없음(Whisper 기준 [추정]) |
| D1 | 플러그인 내 녹음 | 로컬(MPS/MLX, CUDA) | pyannote-audio 3.1+화자 임베딩 DB | **Claude CLI** 또는 Ollama | 마크다운 회의록, 액션아이템 | **한국어 README**; ASR 모델 한국어 성능 확인 못 함 |
| D2 | 플러그인 녹음, 파일 가져오기, iOS Shortcut | **클라우드**(AssemblyAI/Deepgram) | 클라우드 | OpenAI/Anthropic/Gemini API | 노트 추가/신규 노트 | 확인 못 함 |
| D3 | **감시 폴더**(README: Syncthing 등으로 동기화 권장) | 로컬 Docker 백엔드 | README에 없음 | Ollama(로컬) | frontmatter·태그가 있는 노트 | **README가 "영어에 맞춰 파인튜닝, 타 언어 부진 가능"이라 명시** |
| D4 | 플러그인 녹음(모바일 포함), 볼트 내 기존 오디오 | 로컬 OpenAI 호환 서비스, FunASR 또는 클라우드 | 확인 못 함 | 다수 제공자(Ollama 포함) | 한 노트에 전사·정리·할 일 | 중국어 중심; 한국어 확인 못 함 |
| D5 | 캘린더 연동, 로컬 녹음 API | 로컬(Tome 포크) | 음향 목소리 지문+LLM 태깅 | **LLM CLI(`claude`만 실사용)** | 회의 노트, 화자 태깅 | 확인 못 함 |
| D6 | 마이크 받아쓰기, 파일 전사 | 로컬(Moonshine/Parakeet 등) | README에 없음 | 로컬 또는 선택 제공자 | 현재 노트에 삽입 | 확인 못 함 |
| E1 | 오디오 파일 | 로컬 | — | — | ASR+강제 정렬 | **README 언어표에 Korean(ASR 52개 언어·방언; ForcedAligner 11개 언어 중 Korean)** |
| E2 | 오디오 파일 | **로컬 MLX**(PyTorch 불필요) | **Nemotron 3 Diarization** 최대 8명, 스트리밍/오프라인 | — | `start end speaker` 목록, 단어 타임스탬프와 결합 "누가 말했나" | 언어 무관 여부 확인 못 함 |
| E3 | 오디오 | 로컬(MLX/CoreML) | VAD·diarization·화자 식별 포함 | — | 라이브러리(Swift) | README 한국어 번역본 존재(기능 지원과는 별개), Qwen3-ASR 포함 |

---

## 3. 이 프로젝트와의 차이

### 3-1. 요소별 겹침 매트릭스 (가장 가까운 후보만)

기호: ○ = README/문서에서 확인, △ = 부분·조건부, × = 아님(문서상 다른 방식), ? = 확인 못 함.

| 요소 → | ① 안드로이드 기본 녹음 앱 입력 | ② Syncthing/폴더 무인 감시 | ③ Apple Silicon 로컬 ASR | ④ 한국어 ASR 근거 | ⑤ 로컬 화자 분리 | ⑥ 구독 CLI 요약 | ⑦ Obsidian 노트 | ⑧ 시각 근거 링크 |
|---|---|---|---|---|---|---|---|---|
| **이 프로젝트(목표)** | 삼성 기본 앱 | Syncthing+launchd 1분+SQLite+재시도 | MLX | Qwen3-ASR 1.7B+ForcedAligner(+Whisper large-v3 turbo 2차) | Nemotron 3 Diarization MLX | Codex CLI / Gemini 계열 CLI | 한국어 properties | 블록 링크 |
| C1 silverstein/minutes | △ 문서가 Android→Syncthing 등 폴더 동기화 안내(특정 앱 지정 아님) | ○ watch paths | △ 로컬 전사(Apple Silicon 최적화 여부 확인 못 함) | △ Whisper 경유 [추정] | ○ pyannote-rs | ○ claude/codex/opencode/pi (Gemini CLI는 ?) | ○ Markdown+frontmatter, Obsidian 호환 | ? |
| B10 Tractus | × 앱 녹음/드롭 | ? 폴더 감시 문서 못 찾음 | ○ MLX | ○ Qwen3-ASR | ○ (엔진 ?) | △ 지정 LLM 서비스, 에이전트는 MCP 연동 | ○ Send to Obsidian | △ 앱 내 시각 링크(Markdown 블록 링크 여부 ?) |
| C5 plaud-obsidian-pipeline | × Plaud 기기 | ? | △ 로컬 Whisper(Apple Silicon 가속 ?) | ○ `ko` 기본 | △ 옵션 WhisperX | ○ claude -p / codex exec | ○ | ? |
| C4 meet-scribe | × iPhone/iCloud | ○ launchd WatchPaths | ? | × 예시 zh | ○ pyannote | ○ claude -p | ○ | ? |
| C2 local-first-daily-assistant | ○ 기본 녹음 앱+Syncthing(안드로이드 한정은 아님) | ○ 안정화 배리어·SQLite·리스 | ○ whisper.cpp Metal | ? | × (LLM 추정) | × 로컬 LLM | × Telegram | ? |
| B12 meeting-moa | × | × (가져오기) | △ whisper-cpp | ○ 한국어 | ○ 로컬(엔진 ?) | ○ Codex / Claude Code | △ Markdown 내보내기 | ○ 앱 내 시각 |
| B11 Baladhurgesh/minutes | × | × | ○ MLX | × Parakeet v3 한국어 없음 | ○ Nemotron 3 | × 로컬 Qwen3-0.6B | △ Markdown 내보내기 | △ 앱 내 단어 클릭 재생 |
| B14 Takku | × | ? | ○ | △ Parakeet/Whisper | ○ | ○ Codex/Claude Code 등 | ○ | ? |
| C6 voice2note | × Voice Memos | ○ launchd | ○ whisper.cpp | ? | × | ○ codex exec | ○ | × |
| D1 meetnote | × 플러그인 녹음 | × | ○ | △ 한국어 README | ○ pyannote | ○ Claude CLI | ○ | ? |

### 3-2. 질문별 결론

| 질문 | 답 | 근거 |
|---|---|---|
| 폰 기본 녹음 앱 + Syncthing → Mac 무인 처리 자체가 새로운가? | **아니다.** 선행 사례 있음 | C1 문서(Android+Syncthing), C2, C3, D3 |
| 구독 CLI(`codex exec`/`claude -p`)로 요약하는 것이 새로운가? | **아니다.** 다수 존재 | C1, C4, C5, C6, B12, B14 |
| Obsidian 회의록 자동 생성이 새로운가? | **아니다.** | C4, C5, C6, C9, B14, D1 |
| Apple Silicon 로컬 한국어 ASR(Qwen3-ASR)이 새로운가? | **아니다.** B10이 Qwen3-ASR 한국어, B12가 한국어 | B10, B12 |
| Nemotron 3 Diarization MLX가 새로운가? | **아니다.** 포팅·응용 존재(대부분 생성 2026-09~10) | E2, B11 |
| **전부 결합 + 안드로이드 기본 앱 + 한국어 properties + 근거 시각 블록 링크?** | **찾지 못함.** 단 C1+B10을 합치면 상당 부분 재현 가능 → README에서 "최초" 류 표현 금지 | 위 매트릭스 |

### 3-3. 이 프로젝트가 실제로 다른 점 (사실 기반으로 쓸 수 있는 것)
- 입력 전제: **삼성 갤럭시 기본 녹음 앱 그대로**(추가 앱 불필요) — C1은 "특정 앱 불필요/폴더 동기화" 수준의 일반 안내이고, 갤럭시·한국어 맥락은 없음.
- 한국어 우선: Qwen3-ASR+ForcedAligner 조합과 한국어 properties/출력. 한국어 우선 프로젝트는 B10(한/영), B12, C5, D1이 있으나 입력 경로가 다름.
- 안정성 설계: 불완전 파일 대기, SQLite 상태, 재시도 — C2가 같은 방향(파일 안정화 배리어·SQLite 리스·아웃박스)이므로 "독자적"이라 쓰면 안 됨.
- 근거 시각 블록 링크: Markdown/Obsidian 블록 링크 형태로 근거를 남기는 선행 사례는 못 찾음(앱 내 시각 링크는 B10, B12에 있음).

### 3-4. 이 프로젝트 문서에 가져올 점 (제품 게이트 규칙 연계)
- 입력 유형별 처리 방침과 비정상·악의 입력 테스트는 C3(불완전 m4a·삭제 역전파)와 C2(안정화 배리어·중복 제거)를 참고 사례로 삼을 수 있다. 이 조사는 문서 열람 수준이며, 실제 samples/ 입력으로 검증한 것이 아님.

---

## 4. 이름 후보 검토

확인일 2026-11-09. 확인한 곳과 방법:
- GitHub 이름 검색: `https://api.github.com/search/repositories?q=<name>+in:name` (웹: `https://github.com/search?q=<name>&type=repositories`), 이름 어디서나 검색 `...?q=<name>`, 사용자/조직명 `https://api.github.com/search/users?q=<name>+in:login`
- PyPI: `https://pypi.org/pypi/<name>/json` (하이픈/언더스코어/무구분 3변형), 404 = 미등록
- npm: `https://registry.npmjs.org/<name>`; crates.io: `https://crates.io/api/v1/crates/<name>`; Homebrew: `https://formulae.brew.sh/api/formula/<name>.json`, `.../cask/<name>.json` (일부 이름만)
- Obsidian 커뮤니티 플러그인: `https://raw.githubusercontent.com/obsidianmd/obsidian-releases/master/community-plugins.json` (10,153개 항목, id·name 부분 일치 검색)
- **하지 못한 것**: 특허청(KIPRIS)·USPTO·EUIPO 상표 검색, 도메인 조회, Hugging Face·Docker Hub·VS Code Marketplace 검색 → 전부 "확인 못 함". 이 문서는 법률 자문이 아님.

### 4-1. 충돌 표

| 후보 | GitHub (이름 검색 / 어디서나) | PyPI·npm·crates·brew | Obsidian 플러그인 목록 | 상표·혼동 | 판정 |
|---|---|---|---|---|---|
| `galaxy-minutes` (요청 후보) | 이름 0건 / 이름 외 검색 21건이나 무관(Ansible Galaxy 등) | PyPI 3변형 404, npm 404, crates 404, brew 404 | `galaxy` 부분 일치 5건(Galaxy View, Agentage Galaxy, Galaxy Graph, Vault Galaxy, Galaxy Graph 3D — 전부 그래프 뷰 계열로 보임, 용도 무관) | **높음.** GALAXY는 Samsung Electronics 등록상표(US Reg. 5241602, 등록 2017-07-11, 분류 9: 휴대폰·스마트폰·태블릿) — https://www.trademarkia.com/galaxy-87310838 . Samsung Galaxy Store IP 체크리스트는 "삼성과 관계·보증이 있는 것처럼 오인시킬 내용"과 "Samsung 브랜드 식별자"를 허가 없이 쓰지 못하게 함 — https://developer.samsung.com/galaxy-store/ip-infringement.html . Samsung 미국 법무 문서도 "삼성 이름·상표 사용권을 주지 않는다" — https://www.samsung.com/us/common/legal . 설명적 사용(nominative use)이 허용될지는 확인 못 함 | 비추 |
| `rec2note` (요청 후보) | 이름 3건: **`YutoShimmyo/rec2note`(★1, push 2026-10-05, "sound data에서 minutes 텍스트 생성" = 같은 목적)**, `polskiTran/Rec2Note`(★0, 강의 녹음→Markdown), `alevuolo17/uni-rec2notes` | PyPI·npm·crates·brew 모두 404 | 일치 0건 | Samsung/Obsidian 등 제3자 상표 없음 | 비추(동명·동목적 저장소 존재, 검색 혼동) |
| `local-meeting-notes` (요청 후보) | 이름 22건(동명 다수: `ebcreation-cloud/local-meeting-notes`(macOS whisper.cpp), `BalinII/`, `phz-lab/`, `tokotoko090/`, `AviSharma01/`, `vignesh09/` 등) | PyPI 3변형·npm 404 | **`local-meeting-notes` = 기존 커뮤니티 플러그인 id** (`jmshinhwa/readystack-obsidian-meeting-notes`) | 상표 문제는 없으나 일반명사 조합(식별력 낮음) | **비추**(동명 다수+Obsidian id 충돌) |
| `rec2vault` (신규) | 이름 0 / 어디서나 0 / 사용자·조직 0 | PyPI 3변형·npm·crates·brew formula·cask 모두 404 | 일치 0건 | 제3자 상표 없음. "vault"가 Obsidian 용어라 Obsidian 한정처럼 읽힐 수 있음(Obsidian 명칭 자체는 사용 안 함). HashiCorp Vault와의 혼동 가능성은 [추정] 낮음 | **추천 1** |
| `voice2vault` (신규) | 이름 3건(소규모·무관: `Shahanahmedqureshi/Voice2Vault`(ERP), `miguelplanas/voice2vault`(설명 없음), `yiampoo-design/voice2vault-models`) | PyPI 3변형·npm 404 | `voice2` 일치 1건(`voice-text-input` = Voice2Text, 다른 이름) | 없음 | 보류(이름 선점 3건, 낮은 위험) |
| `inbox-minutes` (신규) | 이름 1건(무관 WordPress 미러) | PyPI 3변형·npm 404 | `inbox` 일치 다수(Inbox, Inbox Organiser 등, 다른 이름) | 없음. 'minutes'는 `silverstein/minutes`(★1,596) 등과 의미 겹침 | 차선(검색 혼동) |
| `pocket-minutes` (신규) | 이름 2건: **`demir-sama/pocket-minutes`(★0, push 2026-10-28, "기기 밖으로 나가지 않는 회의록, diarized transcript" = 같은 목적)**, `xuezhanying/PocketMinutes` | PyPI·npm 404 | `pocket` 일치 다수(다른 이름) | 'Pocket'은 Mozilla Pocket 등 기존 서비스명 [추정] | 비추 |
| `vault-minutes` (신규) | 이름 2건(무관: `SAHOOPRATISHRUTI/minutesVault-Book-A-Demo` 등); 어디서나 48건(대부분 HashiCorp Vault 튜토리얼) | PyPI 3변형·npm·crates·brew 404 | `vault-min` 일치 0건 | 없음. 'minutes'는 시간 단위·`silverstein/minutes`·`Baladhurgesh/minutes`와 의미 겹침 | 차선 |
| `phone2minutes` (신규) | 이름 0 / 어디서나 0 / 사용자·조직 0 | PyPI 3변형·npm·crates·brew 모두 404 | 일치 0건 | 없음 | **추천 2** |
| `syncminutes` (신규) | 이름 0 | PyPI 3변형·npm 404 | 일치 0건 | 없음. "sync minutes"는 시간 동기화로도 읽힘 | 보류 |

`minutes` 계열 선점 확인: GitHub 이름 검색 `minutes in:name` 상위에 `silverstein/minutes`(★1,596), `floatboatai/OpenMinutes`(★106), `Baladhurgesh/minutes`; Obsidian 목록에 `recording-minutes`, `dingtalk-minutes-sync`. PyPI `minutes`·`meeting-notes`·`rec2` 는 404지만 이름 조합이 흔함.

### 4-2. 후보별 장단점·추천

| 후보 | 장점 | 단점 |
|---|---|---|
| `rec2vault` | 입력(rec)→출력(Obsidian vault)이 한눈에 보임. 모든 레지스트리·목록에서 0건. 짧고 타이핑 쉬움. 안드로이드/갤럭시/Apple/Obsidian 상표어 없음 | "회의록"이라는 용도가 이름에 없음. vault=Obsidian 한정처럼 보일 수 있음. 영어 모국어자 외에는 "2" 표기 호불호 |
| `phone2minutes` | 폰→회의록 의미 명확, 모든 곳 0건 | 웨어러블·다른 입력은 제외된 느낌. 'minutes' 계열 선점 프로젝트가 있어 검색에서 섞임 |
| `galaxy-minutes` | 갤럭시 사용자에게 직관적 | **Samsung GALAXY 상표 혼동**, 삼성 제휴처럼 오인될 수 있고 Galaxy Store 정책 문서도 이를 금지 대상으로 열거 |
| `rec2note` | 짧음 | 동명·동목적 저장소 이미 존재 |
| `local-meeting-notes` | 설명적 | 동명 다수 + Obsidian 플러그인 id 충돌, 개성 없음 |
| `voice2vault` | `rec2vault`와 같은 구조, 의미가 더 넓음 | 동명 소규모 3건 선점 |
| `inbox-minutes` | Syncthing 인박스 개념과 맞음 | 'minutes' 혼잡, Obsidian 'Inbox' 플러그인과 혼동 |
| `pocket-minutes` | 휴대 이미지 | 동일 목적 저장소 선점 |
| `vault-minutes` | 의미 명확(볼트에 회의록) | 'minutes' 혼잡, 일반어 조합 |
| `syncminutes` | Syncthing 암시 | 시간 동기화로 오독 |

**추천**
1. **`rec2vault`** — 조사한 모든 색인에서 충돌 0, 상표어 없음. README 부제로 "Samsung Galaxy / Android recorder → Obsidian meeting notes"를 적되 "Samsung·Galaxy는 Samsung Electronics의 상표이며 본 프로젝트는 제휴 관계가 없다" 같은 면책 문구를 둔다(상표 사용 범위 판단은 확인 못 함, 필요 시 전문가 확인).
2. **`phone2minutes`** — 목적이 이름에 드러나는 차선. 'minutes' 혼잡이 단점.

공통 주의: 이름을 정한 뒤에도 (a) GitHub 저장소 생성 직전, (b) PyPI/npm 등록 직전에 재확인(2026년 하반기 유사 저장소 생성 속도가 빠름), (c) KIPRIS·USPTO 상표 검색은 아직 안 했음. 소유자/담당 미정.

---

## 5. 한계·미결 (닫을 때까지 목록 유지)

| # | 미결 | 필요한 행동 | 담당·시각 |
|---|---|---|---|
| 1 | 유사 프로젝트 전수 보장 불가(GitHub 검색 키워드 한계, 한·중·일 비영어 저장소 누락 가능) | 공개 직전 `syncthing`·`diarization`·`obsidian`·`회의록` 재검색 | 미정 — 담당·시각 지정 필요 |
| 2 | B1 Meetily 커뮤니티판의 화자 분리 포함 여부(설명 vs PRO 문구 상충) | 릴리스 노트/코드 확인 또는 "확인 못 함" 유지 | 미정 |
| 3 | C1 minutes의 Gemini CLI agent 엔진 지원, 한국어(Whisper 경유) 실제 동작 | 문서·코드 확인 | 미정 |
| 4 | B10 Tractus의 폴더 감시 유무·화자 분리 엔진, Markdown 블록 링크 여부 | 문서·코드 확인 | 미정 |
| 5 | 상표(KIPRIS/USPTO) 검색, 도메인, HF/Docker Hub | 선택 이름 확정 후 직접 조회 | 미정 |
| 6 | 스타·커밋 수치는 2026-11-09 스냅샷 | README에 쓸 땐 다시 조회 | — |
| 7 | 본 조사는 문서·API 열람만, 설치·실행·실제 입력 검증 없음 | 비교 주장은 "README 기준"으로 한정 | — |
