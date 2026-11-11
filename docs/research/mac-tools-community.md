# Mac 로컬 전사 + 화자 분리: 완성 도구 · 사용자 실측 · 한국어 사용기

- 조사 기준일: **2026-11-09**. 모든 URL은 이 날짜에 직접 열람했다. 열람 실패·미열람은 "확인 못 함", 추정은 `[추정]`.
- 범위: `docs/research/local-stt.md`(모델 수치)와 겹치지 않게, **Mac용 완성 앱·CLI**, **사용자 공유 실측·후기**, **한국어 사용기**, **폰 녹음 → Mac 자동화 사례**만 다룬다.
- 출처 표기: **[원문]** 공식 문서·저장소 README·릴리스 노트 / **[커뮤니티]** Reddit·GitHub 이슈·GeekNews·블로그·포럼(작성일 병기) / **[벤더]** 경쟁·판매 목적의 비교글(편향 가능) / **[2차]** 다른 글을 인용한 글.
- 도구 한계(근거 약화 요인): Reddit은 직접 접속이 안 돼 미러(Redlib/Arctic Shift)로 읽었다(점수·최신 댓글 지연 가능). 클리앙·디시 2026년 글은 검색에서 찾지 못했다(아래 §4-4). 검색 도구가 두 번 "AI 요약 답변"으로 대체돼, 그 답변은 **단서로만** 쓰고 직접 열람한 원문만 근거로 삼았다.

## 0. 결론 요약

1. **한국어 + 화자 분리를 한 번에 해 주는 완성 앱은 사실상 두 갈래**다. (a) MacWhisper Pro·Vibe·OpenWhispr·Buzz처럼 Whisper 계열 ASR 위에 화자 분리를 얹은 GUI/CLI 앱, (b) Recap·whosaid·Meetnote·treesoop 같은 **개인 오픈소스 파이프라인**. 한국어를 명시적으로 겨냥한 것은 (b)의 Recap, Meetnote, treesoop뿐이다.
2. **Mac 앱 다수가 ASR로 Parakeet v3를 쓰는데 Parakeet v3는 한국어가 없다**(FluidAudio README: 유럽 25개 언어 + 일본어, 중국어는 SenseVoice/Paraformer). VoiceInk·Hex·Talat 등은 한국어 회의용으로 부적합하고, 한국어에는 Whisper large-v3/turbo 또는 Qwen3-ASR을 고를 수 있는 앱만 후보다. 예: Anarlog의 로컬 모델(Soniqo)은 문서상 한국어가 없다.
3. **한국어 다화자 로컬 조합에서 "화자 분리까지 만족했다"는 공개 후기는 찾지 못했다.** 전사 품질에 대한 만족(Whisper large-v3/turbo, Qwen3-ASR)은 여러 개인 글에 있으나, 화자 분리는 "약하다", "과분리", "추임새에서 흔들림", "사람 손을 타야 한다"는 보고가 반복된다.
4. **한국어 실대화를 대상으로 한 거의 유일한 정량 비교는 soma0sd(2026-10-01)** 이며 NVIDIA GPU(RTX 3090 Ti)·실제 2인 대화뿐이다. 그 결과 cpCER 최저 조합은 Nemotron-3 Diarization + Qwen3-ASR 1.7B(KCSC 18.0%, Nexdata 12.5%)였고, 통합형 VibeVoice-ASR은 Nexdata에서 11.3%로 더 낮았지만 13~16배 느렸다. Apple Silicon 측정이 아니다.
5. **클로바노트와의 정량 비교(로컬 vs 클로바, 한국어 회의)는 확인 못 함.** 찾은 것은 ① 경쟁사(티로) 블로그의 영상 1편 비교, ② 2023년 클리앙 일화(Whisper large-v2가 낫다는 1인 후기), ③ 2년 전 자료를 인용한 Threads 글. 모두 근거가 약하다. 한국어 다화자 화자 분리는 **클라우드(클로바·다글로)가 낫다는 의견**이 GeekNews 댓글에 있고, 로컬이 낫다는 근거는 없다.
6. **Mac mini M4 16GB에서 돌려 본 한국어 파이프라인 실측은 Recap 하나뿐**이고 표본이 작다(3~15분 업무 회의, 정답은 사람이 아닌 모델 출력). 1시간 회의 기준 전사(mlx-whisper) 약 3분, pyannote(CPU)는 527초 파일에 434~463초가 걸렸다고 적혀 있고, 기본값은 Senko(CoreML)로 바뀌었으나 사람 정답 검증은 "대기 중"이다.
7. **폰 → Mac 자동 전송 공개 사례**는 Android → Syncthing → 데스크톱 Whisper(Yuki Sato, 2025-12, 데스크톱은 Ubuntu·화자 분리 없음), iPhone 음성 메모 → launchd 감시(whosaid)가 있다. **갤럭시 → Mac → 한국어 화자 분리까지** 이은 공개 사례는 확인 못 함.
8. 화자 분리 품질을 가장 크게 좌우한다고 여러 사용자가 지적한 것은 **모델보다 녹음 방식**이다(채널 분리 녹음, 마이크 거리, 겹침 발화, 블루투스 모노 혼합). 이는 사용자가 갤럭시 한 대로 대면 녹음을 한다는 조건과 직결된다.

## 1. 완성 앱·CLI 후보

한 줄 요약표(자세한 근거는 §1-1 이하).

| 도구 | 유형 | 한국어(근거) | 화자 분리 | 폴더 일괄·CLI | 라이선스·가격 |
|---|---|---|---|---|---|
| MacWhisper | GUI + `mw` CLI | Whisper 모델 경유(2차 출처), Qwen3-ASR 추가(22개 언어, 한국어 포함 여부 확인 못 함) | ✓ Nemotron 3 Diarization 최대 8명(15.2, 2026-09-23) | ✓ `mw transcribe 폴더 --recursive`, 감시 폴더(Pro, 베타) | 폐쇄, Pro 64유로 1회 |
| Anarlog(구 Hyprnote/Char) | GUI(Tauri) + CLI/MCP | **로컬 Soniqo 목록에 한국어 없음**, Apple Speech(라이브)·whisper.cpp(.bin 파일)는 가능 | 무료 플랜은 수동 라벨 `[벤더]` | ✓ 로컬 CLI·MCP | MIT(커뮤니티 앱), Pro $14/월 |
| Meetily | GUI(Tauri) | Whisper/Parakeet, 한국어 명시 확인 못 함 | **무료판 없음**(Pro 기능) | 가져오기(베타) | MIT, Pro $10/월(WIRED) |
| Vibe | GUI(Tauri) + CLI + HTTP API | Whisper 경유, 한국어 근거 확인 못 함 | ✓ Sortformer v2.1 **4명 한도**(이슈) | ✓ 일괄 전사, 폰 QR 녹음 | MIT, 무료 |
| Buzz | GUI(Qt) + CLI | Whisper 경유, 한국어 근거 확인 못 함 | ✓ "Speaker identification"(구현 세부 확인 못 함) | ✓ 감시 폴더 + CLI | MIT, 무료 |
| OpenWhispr | GUI(Electron) | Whisper/Parakeet/Cohere, 한국어 근거 확인 못 함 | ✓ 로컬(sherpa-onnx 계열), Apple Silicon만 | ✓ 일괄 업로드, API·MCP | MIT, 무료(클라우드 옵션 유료) |
| VoiceInk | 받아쓰기 앱 | Whisper·Parakeet·SenseVoice | README에 언급 없음(확인 못 함) | 확인 못 함 | GPL-3.0, 유료 라이선스 |
| speech-swift(Soniqo) | Swift 라이브러리 + `speech` CLI | Qwen3-ASR(52개 언어)·Whisper CoreML·MOSS-Transcribe-Diarize | ✓ pyannote/Sortformer, **전사와 별도 명령** | ✓ `speech transcribe-batch` | Apache-2.0, 무료 |
| FluidAudio | Swift SDK + CLI | **ASR에 한국어 없음**(Parakeet v3, SenseVoice=중국어) | ✓ pyannote/Sortformer/Nemotron 3(≤8) | ✓ `fluidaudiocli` | Apache-2.0, 무료 |
| WhisperKit/SpeakerKit(Argmax) | Swift SDK + CLI + 로컬 서버 | Whisper 경유 | ✓ SpeakerKit(pyannote) | CLI·서버 ✓, 일괄 옵션 확인 못 함 | MIT; Pro SDK는 유료 |
| Senko | Python 화자 분리 | 언어 무관이나 임베딩이 영어+중국어 학습 | ✓ 단독 diarizer | Python API | MIT(저장소 표기) |
| whisper-diarization | Python 파이프라인 | `--language` 지정, 한국어 근거 확인 못 함 | ✓ NeMo(MarbleNet+TitaNet) | CLI | 확인 못 함(저장소 README 미표기) |
| whosaid | CLI | MLX Whisper large-v3, 한국어 화자 임베딩 확인 못 함 | ✓ sherpa-onnx(영어 TitaNet 기본) | ✓ launchd 감시, 음성 메모 | MIT |
| Recap(notadev-iamaura) | 웹 UI + 메뉴바 | **한국어 전용 설계** | ✓ Senko(기본)/community-1/speakrs | ✓ 폴더 감시 | MIT |

### 1-1. MacWhisper

- **무엇**: 인디 개발자 Jordi Bruin의 Mac 전사 앱. 2026-09-23 v15.2에서 NVIDIA Nemotron 3 Diarization(최대 8명)을 도입하고, 실시간 회의 전사·Qwen3-ASR(22개 언어)·폴더/서브폴더를 추가. 출처 [커뮤니티·언론] https://9to5mac.com/2026/09/23/macwhisper-update-brings-real-time-meeting-transcripts-improved-speaker-recognition-more/ (2026-09-23).
- **한국어**: 앱이 Whisper 계열 로컬 모델(Tiny~Large-v3), Parakeet, 클라우드를 지원한다(https://www.macwhisper.org/ 설명). 한국어 품질을 따로 측정한 글은 확인 못 함. Qwen3-ASR 22개 언어에 한국어가 들어 있는지는 확인 못 함.
- **화자 분리**: [원문] 문서(2025-07 갱신)는 "WhisperKit 엔진 모델과 ElevenLabs·Deepgram에서만" 자동 화자 인식이 된다고 적고 있다(https://docs.macwhisper.com/article/32-automatic-speaker-recognition-in-macwhisper). 15.2에서 Nemotron 3 Diarization으로 교체된 뒤에도 같은 모델 제약이 유지되는지는 확인 못 함. 화자 이름 변경·병합·세그먼트 이동 UI가 있다.
- **사용자 평가**: r/macapps 2026-05-17(질문자 회의 참석자 12명 이상): 한 사용자는 "MacWhisper + Claude 요약이 8명 아침 회의에 잘 맞는다", 다른 사용자(CtrlAltDelve)는 "diarization을 꺼 둔다. 정말 잘 작동하지 않는다고 생각한다"며 마이크를 별도 녹음해 "microphone = me"로 처리한다고 했다. https://www.reddit.com/r/macapps/comments/1tg15y0/survey_whats_your_current_goto_for_meeting 언어는 명시되지 않았고 영어권 업무 회의로 보인다 `[추정]`. 한국어 근거 없음.
- **일괄·자동화**: [원문] `mw` CLI(설정 → 고급에서 설치). `mw transcribe 폴더 --recursive --output-dir 출력 --speakers --format json`, `--model`, `--language <ISO>`. txt/srt/vtt/csv는 무료, json·md·html은 Pro. CLI는 실행 중인 앱과 소켓으로 통신(앱이 꺼져 있으면 자동 실행). 감시 폴더는 Pro 기능이며 문서가 "베타"로 표기. https://docs.macwhisper.com/article/57-macwhisper-command-line-tool , https://docs.macwhisper.com/article/35-automatically-transcribing-files-in-watch-folders
- **가격·라이선스**: 폐쇄 소스. Pro 64유로 1회(여러 2차 출처 일치, 예: https://www.promptquorum.com/ko/power-local-llm/macwhisper-review).
- **판단**: 설치·자동화(CLI/감시 폴더)가 가장 쉬운 상용 후보. 한국어 화자 분리 결과는 직접 돌려 봐야 한다.

### 1-2. Anarlog (구 Hyprnote → Char → Anarlog)

- **이름 변천**: Hyprnote → 2026 초 v1.0.14에서 Char → 2026-05-03 Anarlog 발표, 2026-08 이전 완료. Char 이름은 현재 같은 팀의 다른 제품(char.com)이 쓰고, 회의 메모 커뮤니티 앱은 anarlog(MIT)로 유지된다. 출처 [원문] https://github.com/fastrepl/anarlog README(미러 https://github.com/Sokori-Inc/char 로 열람), [벤더] https://www.transcribex.io/vs/hyprnote (2026-10 확인 주장).
- **한국어**: [원문] 로컬 모델 안내에서 **Soniqo는 유럽 25개 언어만 나열**(한국어 없음). Apple Speech는 한국어 가능하나 라이브 전사에서 한 번에 한 언어. "On-device file"은 선택한 whisper.cpp `.bin`의 언어 목록을 따른다. https://docs.anarlog.so/languages
- **화자 분리**: 무료 플랜은 수동 라벨(경쟁사 비교글 기준, 자동 화자 인식 확인 못 함). 
- **자동화**: 로컬 CLI·MCP·API·웹훅(README, 비교글).
- **사용자 평가**: WIRED(2026-08-09)는 "설정이 Meetily보다 번거로웠다"고 평가. 한국어 근거 없음.
- **판단**: Korean 로컬 전사 + 자동 화자 분리 용도로는 우선순위 낮음.

### 1-3. Meetily

- [원문] MIT, 별 32.5k. macOS(Apple Silicon)·Windows. 로컬 Whisper/Parakeet 전사 + Ollama 요약. "Import & Enhance"는 베타(기존 오디오 전사). **화자 식별은 Pro 기능**. https://github.com/Zackriya-Solutions/meetily
- [커뮤니티·언론] WIRED 2026-08-09: "무료판은 누가 말했는지 라벨이 없다. 이 기능을 일관되게 하는 무료 오픈소스 도구는 찾지 못했다." 대안으로 noScribe(파일 변환 전용, 화자 식별 가능)를 언급. https://www.wired.com/story/meetily-lets-you-transcribe-and-summarize-meetings-without-a-subscription-heres-how/
- 한국어 근거 없음. 판단: 제외.

### 1-4. Vibe (thewh1teagle/vibe)

- [원문] MIT, 별 8k. Whisper·Nemotron 3.5·Parakeet TDT v3, 폴더 일괄 전사, SRT/VTT/JSON/DOCX 등 내보내기, CLI(`--help`), HTTP API, Ollama 요약, **폰으로 QR 코드를 스캔해 녹음하면 컴퓨터가 전사해 텍스트를 돌려주는 기능**(README 문구, 동작 방식 세부는 확인 못 함). https://github.com/thewh1teagle/vibe
- 화자 분리: README에 ✓. [커뮤니티(GitHub 이슈)] #1030(2026-03-24 작성, 열림)은 현재 구현이 Sortformer 4spk v2.1이라 **4명 한도**라고 지적. https://github.com/thewh1teagle/vibe/issues/1030 / #953(2026-02-12)은 macOS 공식 빌드에서 `sona-diarize failed` 반복, 개발 모드에서는 정상. 2026-09-01 댓글: "v3.1.6, macOS 27.0 베타, M4 mini 64GB에서 화자 분리가 완벽히 작동" https://github.com/thewh1teagle/vibe/issues/953
- 한국어 근거 없음(언어 지원은 Whisper 계열에 의존). 판단: 2명 위주 통화·대화에는 시험 가능, 5명 이상 회의에는 한도 문제.

### 1-5. Buzz (chidiwilliams/buzz)

- [원문] MIT, 별 22.5k. Whisper(Apple Silicon 지원, whisper.cpp/Hugging Face), **감시 폴더·CLI**, "Speaker identification in transcribed media", 전사 전 음성 분리, AI 요약 플러그인. macOS는 Apple Silicon 필요(마지막 Intel 지원판 1.4.5). 저장소 트리에 `whisper_diarization`(MahmoudAshraf97) 서브모듈이 있어 같은 계열로 보이나 `[추정]`. https://github.com/chidiwilliams/buzz
- 한국어·화자 분리 품질·Mac 속도 후기: 확인 못 함.

### 1-6. OpenWhispr

- [원문] MIT. 데스크톱 받아쓰기 + 회의 전사(라이브 화자 분리·음성 지문), 오디오 가져오기(일괄 업로드, 선택적 화자 감지), MCP·API. 로컬 화자 분리는 ONNX Runtime 의존이라 **Intel Mac에서는 불가**. 기술 스택에 whisper.cpp·sherpa-onnx. https://github.com/OpenWhispr/openwhispr
- 한국어·화자 분리 품질 사용기: 확인 못 함. 판단: 시험 후보(2차).

### 1-7. VoiceInk

- [원문] GPL-3.0, macOS 15+. 받아쓰기(단축키) 중심. whisper.cpp·FluidAudio(Parakeet)·SenseVoice Small 사용. README에서 화자 분리·일괄 처리 언급을 찾지 못했다(확인 못 함). 한국어 회의 파일 전사 용도로는 부적합 `[추정]`. https://github.com/Beingpax/VoiceInk

### 1-8. speech-swift (Soniqo)

- [원문] Apache-2.0, 별 1.3k. Qwen3-ASR(MLX/CoreML, 52개 언어), Whisper Large-v3 Turbo(CoreML), MOSS-Transcribe-Diarize(CoreML/MLX, INT5/INT8, 128K 컨텍스트), Nemotron 스트리밍(40 로케일), Parakeet, 화자 분리(pyannote, Sortformer). Anarlog도 이 패키지를 참조. https://github.com/soniqo/speech-swift
- CLI: `speech transcribe a.wav`, `speech diarize a.wav --json`, 폴더 일괄 `speech transcribe-batch recordings/ --extensions wav --output-dir transcripts/`. **사이트가 "두 명령은 별도 결과를 내며 화자 라벨 달린 전사문을 만들지 않는다"고 명시**. https://soniqo.audio/transcription (병합은 직접 구현해야 함). 
- 한국어: 모델 수준 지원(Qwen3-ASR·Whisper). 한국어 DER·CER 측정은 확인 못 함. 영어 측정 수치는 `local-stt.md` §2-3 참조.

### 1-9. FluidAudio

- [원문] Apache-2.0, 별 3.3k. CoreML/ANE. 화자 분리: pyannote, Sortformer, LS-EEND, Nemotron 3 Diarization(≤8명). ASR: Parakeet TDT v3(유럽 25개 언어 + 일본어), SenseVoice·Paraformer(중국어), "Nemotron 3.5 Transcribe Lite". **Lite는 문서 첫 문장이 "Long-form English transcription"** 이며 AMI 영어 회의에서 WER 26.4%, cpWER 28.7%(M5 Pro, 49.5분을 5.5초). 한국어 불가로 보는 것이 맞다. https://github.com/FluidInference/FluidAudio , https://raw.githubusercontent.com/FluidInference/FluidAudio/main/Documentation/ASR/NemotronTranscribeLite.md
- 쇼케이스 앱 수십 개(VoiceInk, Hex, Talat, TranscribeX 등)가 이를 쓰므로 "Mac에서 화자 분리가 된다"는 대부분 이 계열(pyannote/Sortformer/Nemotron 3의 CoreML 변환)이다. r/macapps 댓글도 같은 지적: "Mac의 로컬 diarization은 거의 같은 pyannote segmentation + embedding을 CoreML로 바꾼 것이며, 화자 1/2 병합은 클러스터링 임계값·최소 세그먼트 길이 설정에서 온다"(2026-09-02). https://www.reddit.com/r/macapps/comments/1w3zrzd/best_transcription_app_with_speaker_diarization

### 1-10. WhisperKit / SpeakerKit (argmax-oss-swift)

- [원문] MIT, 별 6.4k. WhisperKit(Whisper), SpeakerKit(pyannote 화자 분리), TTSKit. `brew install whisperkit-cli`, 로컬 OpenAI 호환 서버. 긴 파일용 `incremental` 로딩, VAD 청킹. 실시간 화자 포함 전사·사용자 어휘는 **Argmax Pro SDK(유료)**. https://github.com/argmaxinc/argmax-oss-swift
- Argmax OpenBench(2026-09-22 갱신)에 SpeakerKit(community-1) 실행 결과가 있으나 이번에 수치를 읽지 않았다(확인 못 함). https://github.com/argmaxinc/OpenBench/blob/main/BENCHMARKS.md
- 사용 사례: 한국어 개발자가 만든 iOS/macOS 앱 "추로"(GeekNews 2026-09-28)는 WhisperKit large-v3(626MB) + FluidAudio 화자 분리 + Apple Foundation Models 요약. 개발자 실측: 60분 연속 녹음에서 메모리 137MB→93MB로 안정, 30분 회의 요약 25초(iPhone 17 Pro). **한국어 정확도·화자 분리 품질 수치는 없음.** https://news.hada.io/topic?id=34400

### 1-11. Senko (narcotic-sh/senko)

- [원문] Python 화자 분리 파이프라인(VAD → fbank → CAM++ 임베딩 → 클러스터링). Apple M3에서 1시간 7.7초, VoxConverse DER 13.5%, AISHELL-4 13.3%, AMI-IHM 26.5%. Mac은 CoreML(ANE+CPU). **임베딩은 영어+중국어 혼합 학습이라 영어·중국어에서 가장 잘 맞을 것**이라고 저자가 명시, 겹침 발화는 출력하지 않음, 소음·저음질에서 크게 열화. https://raw.githubusercontent.com/narcotic-sh/senko/main/README.md
- 한국어 DER: 확인 못 함. 사용처: Recap 기본 화자 분리, trailofbits/scribe 등.

### 1-12. whisper-diarization (MahmoudAshraf97), WhisperX 계열

- [원문] Demucs 보컬 분리 → Whisper → CTC 정렬 → MarbleNet VAD → TitaNet 임베딩. `--device`는 CUDA 우선, README에 Mac/Apple Silicon 언급 없음(확인 못 함). 겹침 발화 미해결 명시. 기본 Whisper 모델 `medium.en`. https://raw.githubusercontent.com/MahmoudAshraf97/whisper-diarization/main/README.md
- Mac에서의 사용기: 직접 열람한 것은 없음. 한국어 개발자 이슈(baekenough/second-brain #111, 2026-06)는 C안(NeMo 계열)을 "CUDA 지향·ARM64 미지원"이라 판단해 배제했다(그 팀의 분석이며 실측 아님). https://github.com/baekenough/second-brain/issues/111
- **whispermlx**(WhisperX의 mlx-whisper 포크)·한국어: treesoop은 "whispermlx 단독 사용 시 한국어에서 hallucination('Jelly Jelly…' 반복)이 발생해, 전사는 mlx-whisper(`--hallucination-silence-threshold`), 화자 분리만 whispermlx에서 가져와 병합"한다고 README에 적었다. https://github.com/treesoop/whisper_transcription
- WhisperX 자체의 Mac(CPU 전용) 제약은 `local-stt.md` §5-3 참조.

### 1-13. whosaid (sblattj/whosaid)

- [원문] MIT. MLX Whisper **large-v3 기본**(turbo는 `--fast`) + sherpa-onnx 화자 분리(pyannote segmentation-3.0 + **영어 NeMo TitaNet-small 기본 임베딩**). 토큰·계정 불필요. 15분 넘는 녹음은 병렬 윈도우로 분리 후 음성 지문으로 이어 붙임. **음성 메모 폴더에 launchd 감시**(`whosaid watch install`), `whosaid ingest`, MCP, 일괄 `whosaid <audio>…`. 명시 문서: "임베딩 모델은 말하는 언어와 맞아야 한다. 영어 모델이 만다린에서 서로 다른 사람을 합친다"(만다린용 모델 옵션만 문서화). **한국어용 임베딩 옵션은 문서에 없다** → 한국어 화자 분리 품질은 확인 못 함. https://github.com/sblattj/whosaid
- 속도: 저장소 문구 "80분 회의가 수십 분이 아니라 수 분"(구체 기기 수치 확인 못 함).

### 1-14. Recap (notadev-iamaura/meeting-transcriber) — 한국어 전용 Mac 파이프라인

- [원문+커뮤니티] GeekNews Show GN 2026-06-09 + 저장소(MIT, 별 22, 생성 2026-03-05). Apple Silicon 전용(MLX), **M4 16GB를 목표 환경**으로 명시. 기본 STT `mlx-whisper large-v3-turbo`, 한국어 파인튜닝 3종(komixv2 등) 선택 가능, 화자 분리 Senko(CoreML, 기본)/community-1(pyannote, CPU)/speakrs, 교정·요약은 Gemma 4 E4B 또는 EXAONE 3.5(로컬 MLX), 폴더 감시 자동 처리, BlackHole로 Zoom 녹음, ChromaDB 검색. 선택적으로 OpenAI `gpt-4o-transcribe-diarize` 클라우드 옵션(기본 OFF, 동의 필요). https://github.com/notadev-iamaura/meeting-transcriber , https://news.hada.io/topic?id=30315
- **저자가 적은 실측**(M4 16GB, 3~15분 업무 회의, 단일 기기): https://raw.githubusercontent.com/notadev-iamaura/meeting-transcriber/main/docs/BENCHMARK.md
  - 1시간 회의: 전사(mlx-whisper GPU) 약 3분, LLM 보정 약 2분, 요약 약 30초(README 표). 화자 분리 시간은 "엔진·길이·최초 로드에 따라 다름".
  - 527초 회의 pyannote 화자 분리(CPU): 3.1 463초, community-1 434~461초(자동 화자 수는 579~695초, 느려짐). 3.1은 보조 화자 하나를 둘로 **과분리**, community-1은 3명으로 수렴. 화자 범위는 기본 2~4명 자동.
  - README ETA 힌트 RTF: Senko 0.01, speakrs 0.05, community-1 0.25. 2026-09-29 M4 "의사 정답(pseudo-GT) A/B"에서 Senko가 DER·JER·속도 1위여서 기본값 변경, **사람 RTTM 검증은 대기 중**.
  - STT 6회의 108분: large-v3-turbo CER 49.8% vs komixv2 66.2%. **정답이 OpenAI gpt-4o-transcribe 출력이라 절대값 의미 없음**(저자도 한계 항목에 적음). 4bit 한국어 파인튜닝(seastar/ghost613)은 "무음 구간 환각, 커버리지 42~63%". VAD(silero) 켜면 mlx-whisper에서 실행 3~6배 느려지고 커버리지 하락.
  - 한계(저자): 단일 하드웨어, 표본 작음(정답지 44발화 2샘플), 1:1 면담·장시간·전화·소음은 미검증.
- 판단: **한국어 Mac 로컬 파이프라인의 구성(어떤 선택지를 어떤 순서로 비교했는가)을 참고하는 가치**가 크다. 정확도 결론으로 쓰기에는 정답 데이터가 약하다.

### 1-15. 기타 개인 구현(참고)

- **Meetnote**(changsu-jin, Obsidian 플러그인): mlx-whisper large-v3-turbo + pyannote 3.1 + wespeaker 임베딩(화자 DB 누적 학습, 코사인 0.70), Claude CLI/Ollama 요약. 저자 서술: "Apple Silicon 60분 회의 약 5분, CPU만이면 40분". 환각은 `no_speech_prob`·`compression_ratio`로 필터, LLM 보정으로 고유명사 개선. 정확도 수치 없음. 한국어 명시 없음(한국어 블로그). [커뮤니티] https://42class.com/posts/meetnote-retrospective (2026-04-05)
- **treesoop/whisper_transcription**(TreeSoop, 한국 AI 개발사): mlx-whisper(large-v3) + whispermlx 화자 분리. README 표 "20분 한국어 미팅": 로컬이 유료 Notta보다 전사 정확도 "높음", 고유명사·약어 "정확"(Notta는 누락/오인식 많음), 문장 분리 깔끔, **화자 분리는 "있음(짧은 추임새 간혹 흔들림)" vs Notta "있음(안정적)"**. 수치·표본·정답 없음, 자사 STT 서비스 홍보를 겸하는 글 [벤더 성격]. `--language` 지정 비권장(한영 혼용 회의에서 자동 감지가 낫다는 주장), 30분 단위 분할 권장. https://treesoop.com/blog/whisper-transcription-local-korean-stt-2026 (2026-04-17), https://github.com/treesoop/whisper_transcription
- **KYankee6/advanced-audio-recorder-fork**(Obsidian 플러그인, 한국어 화자 분리): velog 글(§4-1)에서 링크만 확인, 저장소는 열람하지 않음.
- **gggg8657/meeting-local**(faster-whisper + sherpa-onnx, 폐쇄망 setup): 검색에는 나왔으나 저장소 열람 시 404 → 평가 제외.

### 1-16. TranscribeX·Whisper Notes·AnythingLLM 회의 도우미 등 (판매 앱, 참고)

- **TranscribeX**(Mac, $39 1회, 무료판 있음): 자체 비교글에 "pyannote community-1을 Neural Engine에서 실행, 화자 수 제한 없음, Voice Profiles로 이후 회의에서 이름 자동", Whisper/Parakeet/Qwen3 ASR/Nemotron 선택, CLI·MCP. 한국어 근거 없음. [벤더] https://www.transcribex.io/vs/hyprnote
- **Whisper Notes**(iPhone/Mac, Mac 무료판 주 5,000단어): 자체 FLEURS 한국어 CER Qwen3-ASR 3.54% vs Whisper Large V3 Turbo 4.25%(M5 MacBook Air 32GB, 낭독체 약 150문장, 오차 범위 안이라 "동률"로 해석). 속도 9.6배 vs 2.6배, 최대 메모리 2.43 vs 1.87GiB. **저자 스스로 "낭독 순위가 실제 회의에서 두 번 뒤집혔다"며 회의 평가는 별도 글로 예고.** [벤더] https://whispernotes.app/blog/qwen3-asr-vs-whisper (2026-11-07 갱신)
- **AnythingLLM 회의 도우미 v1.17.0**: Nemotron 3 Diarization + Parakeet Redux(영어·유럽어, 한국어 없음). 자체 테스트에서 pyannote 3.1은 "2인 9분 통화를 1명으로, 3인 1시간 회의를 1명+잡음으로, 다른 기기에서는 같은 회의를 6명으로" 출력, Nemotron 3은 "모든 녹음에서 화자 수 일치". 언어·표본 수 미공개. [벤더] https://anythingllm.com/blog/meeting-assistant-engine (2026-10-01)
- 그 밖에 r/macapps에 Biscotti, Humla(오픈소스), Talat, Thoth, Transcripted 등이 거론되나 한국어 근거는 없다. 한 사용자는 "Thoth가 MBP에서는 되는데 Mac mini에서는 잘 안 됐다"고 적었다(기종 미상, 2026-09-01).

## 2. 사용자 실측·비교 (Apple Silicon 중심, 영어권 포함)

| 날짜 | 출처 | 누가·무엇을·어떤 조건 | 결과 | 한국어? |
|---|---|---|---|---|
| 2026-02-15 | r/LocalLLaMA https://www.reddit.com/r/LocalLLaMA/comments/1r56ak1/groundup_mlx_reimplementation_of_qwen3asr_for/ | mlx-qwen3-asr(moona3k) 개발자, M4 Pro, 0.6B fp16 | 10초 클립 0.83초 지연, RTF 0.08, 4bit 4.7배 빠르고 WER 2.29→2.72%, 메모리 약 1.2GB(0.6B)/3.4GB(1.7B) | 확인 못 함 |
| 2026-04-02 | 같은 스레드 댓글(goro-n) | 같은 구현을 자기 Mac에서 | **메모리 37GB, Whisper보다 느림** (기기 미상, 스크린샷 이미지) | 확인 못 함 |
| 2026-03-10 | r/LocalLLaMA https://www.reddit.com/r/LocalLLaMA/comments/1rq118c/qwen3_asr_seems_to_outperform_whisper_in_almost/ | 한국어 사용자: Whisper Large Turbo·Voxtral Mini 3B·Qwen3-ASR 1.7B, Tesla P40/RTX 5070 Ti | "한국어 전사 품질이 상용 서비스에 거의 필적", 수치 없음. 실시간 vLLM에서는 시간이 지날수록 정확도 저하. 반례: 영어 TV 방송에서 Qwen3-ASR이 일부 구간을 놓치고 환각(uutnt), "벤치를 믿지 말고 직접 테스트" | **✓(주장만)** |
| 2026-03 | 같은 스레드 | 다수 사용자 | Parakeet v3는 속도·독일어 만족 후기(한국어 미지원) | ✗ |
| 2026-09-01 | r/macapps https://www.reddit.com/r/macapps/comments/1w3zrzd/best_transcription_app_with_speaker_diarization | 클라이언트 통화 녹음 요구(M2 + iPhone 16) | 합의: ① 겹침·스피커폰 녹음으로 직접 시험, ② 병합 오류는 **단어 단위 정렬 여부**, ③ **채널 분리 녹음이면 어느 도구든 화자 분리가 쉬움**, ④ 블루투스 모노 혼합이 가장 어려움, ⑤ 오디오는 보관(재처리 가능) | 영어 `[추정]` |
| 2026-05-17 | r/macapps 설문(위 §1-1) | 회의 12명 이상 | "10명 이상 화자 식별은 미해결", 호스트 플랫폼 내장 전사(Gemini/Meet, Teams)가 가장 정확 | 확인 못 함 |
| 2025-01-17 | r/LocalLLaMA https://www.reddit.com/r/LocalLLaMA/comments/1i3px18/current_sota_for_local_speech_to_text_diarization/ | 질문+댓글(2025, 오래됨) | "pyannote 3.1은 화자를 너무 많이 만든다", Whisper 세그먼트마다 임베딩을 뽑아 매칭해 과분리를 줄임 | 확인 못 함 |
| 2026-09/10 | Vibe 이슈 #953, #1030 | 앞 §1-4 | 4명 한도, 패키지 빌드 실패 사례, M4 mini 64GB 정상 사례 | 확인 못 함 |
| 2026-10-01 | AnythingLLM(벤더) | 앞 §1-16 | 화자 수 판정 개선 주장 | ✗(한국어 모델 아님) |
| 2025-12(블로그) | Yuki Sato https://yukisato.dev/posts/lifelog-audio-workflow-vad-whisper | Ubuntu 데스크톱 GPU, Silero VAD + Whisper | 7시간46분 녹음: small 317초(약 88배속), large-v3 486초(약 57배속). **Mac 아님, 화자 분리 없음** | 확인 못 함 |
| 날짜 확인 못 함 | VibeVoice-ASR Mac 사용기(Shuichi346, GitHub README) https://github.com/Shuichi346/vibevoice-asr-long-audio | Mac mini(통합 메모리 24~25GB), mlx-community/VibeVoice-ASR-4bit, **일본어** 오디오 | 55분을 한 번에 넣으면 OOM, 오디오 인코더 중간 텐서 25~30GB가 원인. 인코더만 청크(10분)로 쪼개고 LLM은 단일 패스로 두면 화자 ID가 유지된다고 주장(저자 서술, 검증 수치 없음). 16GB Mac은 2분 청크 권장 | ✗(일본어) |

해석: **Apple Silicon에서 화자 분리·한국어·장시간을 한 번에 측정한 제3자 글은 없다.** Qwen3-ASR MLX는 구현마다 메모리 편차(1.2~3.4GB vs 37GB)가 크므로 16GB mini에서는 직접 확인이 필요하다. VibeVoice-ASR은 16GB mini에서 4bit여도 청크 처리가 필요하다는 보고가 있다.

### 2-1. 한국어 실대화 비교 — soma0sd (2026-10-01, NVIDIA GPU)

출처 [커뮤니티·개인 블로그] https://soma0sd.dev/blog/korean-speaker-transcription-models . 조건: **RTX 3090 Ti 24GB, Docker, 파일 전체 처리(실시간 아님)**. 데이터: KCSC 실제 대화 11개(2.69시간, 2인), Nexdata 실제 대화 3개(0.89시간, 2인), 합성 대화 15세션(Zeroth 낭독 문장을 이어 붙인 2~6인). **3인 이상 실제 한국어 대화는 평가하지 않았다**(공개 데이터 부재). 정답 표기 규칙 차이(구어 표기, 숫자, 간투사)가 오류에 포함돼 절대값보다 상대 비교로 해석하라고 저자가 명시.

화자 분리 DER:

| 모델 | KCSC | Nexdata | 합성 전체 | 합성 5~6인 | RTF | VRAM |
|---|---|---|---|---|---|---|
| Nemotron-3-Diarization | 11.5 | 16.2 | 8.9 | 10.6 | 0.0027 | 1.5GB |
| Sortformer v2 | 11.5 | 17.2 | 13.7 | 20.7 | 0.0031 | 1.7GB |
| Sortformer v2.1 | 13.7 | 19.8 | 14.6 | 23.0 | 0.0030 | 1.7GB |
| pyannote community-1 | 17.8 | 21.5 | 5.9 | 7.3 | 0.0158 | 10.4GB |
| DiariZen v2 범용(비상업 가중치) | 14.1 | 14.3 | 5.8 | 7.8 | 0.0365 | 12.5GB |

ASR CER와 조합 cpCER(KCSC / Nexdata / 합성):

| 조합 | KCSC | Nexdata | 합성 | 비고 |
|---|---|---|---|---|
| Sortformer v2 + WhisperX turbo | 21.9 | 19.0 | 23.5 | |
| Nemotron-3 + WhisperX turbo | 22.0 | 16.6 | 13.7 | |
| Nemotron-3 + BuzzASR-ko | 20.0 | 14.0 | 13.2 | |
| **Nemotron-3 + Qwen3-ASR 1.7B** | **18.0** | **12.5** | 13.3 | 저자가 서비스에 채택, 1시간 녹음 약 2분 |
| DiariZen + Qwen3-ASR 1.7B | 17.1 | 13.2 | 9.3 | 가중치 비상업 |
| VibeVoice-ASR(4bit LM) | — | **11.3** | 13.9 | Nexdata DER 26.8%, RTF 0.47~0.59, 합성 15개 중 9개만 화자 수 일치 |

단독 ASR CER(KCSC / Nexdata): Qwen3-ASR 1.7B 15.7 / 11.3, BuzzASR-ko 16.3 / 10.6, WhisperX large-v3-turbo 18.8 / 13.1, large-v3 19.6 / 14.3, Nemotron 3.5 ASR 0.6B 19.2 / 16.5. → 이 데이터에서는 **turbo가 large-v3보다 낮게** 나와, `local-stt.md` §2-1(seastar 표: large-v3 우세)과 방향이 다르다(데이터·정규화 차이). 직접 측정이 필요한 이유.

시사점(이 글 한정): ① 실제 2인 대화에서 화자 분리는 Sortformer 계열이 정확·빠름, 5인 이상은 Nemotron-3(≤8명)·pyannote/DiariZen. ② 실대화 cpCER은 **ASR 선택이 좌우**(Qwen3-ASR 1.7B가 turbo보다 4~5%p 낮음). ③ Qwen3-ASR은 긴 녹음을 **30초 단위로 쪼개 넣어야** 합성 대화 CER이 12.9%→5.8%로 개선(저자 예비 시험). Whisper 계열 환각은 이 글에서 별도 다루지 않음.

## 3. 사용자 실측 보고에서 반복되는 패턴

- **화자 과분리**: pyannote 3.1이 보조 화자를 둘로(Recap 2026-06-22), 2인 통화를 1명 또는 3인을 6명으로(AnythingLLM), "너무 여러 명으로 뽑혀서"(velog 2026-09-10), "화자를 너무 많이 만든다"(LocalLLaMA 2025-01). 대응: 화자 수 힌트(통화는 2명), 범위 제한(Recap 2~4명), 임베딩 매칭 병합(LocalLLaMA 댓글, whosaid 흡수 임계값).
- **짧은 맞장구·겹침**: soma0sd(오류 대부분이 겹침·1초 미만 맞장구, 경계 0.25초를 제외하면 DER 2% 안팎), treesoop("짧은 추임새 간혹 흔들림"), r/macapps(겹침이 문제), Senko·whisper-diarization README(겹침 미지원).
- **Whisper 환각·반복**: Recap(4bit 파인튜닝 무음 환각, 커버리지 42~63%), velog("네, 네, 네" 반복 → **7분 단위로 잘라 전사해 해결**), treesoop("Jelly Jelly" 반복 → 환각 침묵 임계값), Meetnote(`no_speech_prob`·`compression_ratio` 필터). 긴 녹음은 30분(treesoop)·7분(velog) 분할이 쓰이고 있다.
- **전사와 화자 병합 단계의 오류**: r/macapps "화자 1/2 문장이 이어 붙는 건 모델이 아니라 병합"(세그먼트 단위 vs **단어 단위 정렬**).
- **녹음 조건이 모델보다 크다**: "채널 분리 두 트랙이면 화자 분리는 사소해진다", "마이크는 두 사람 사이에", "블루투스 모노 혼합이 최악"(r/macapps 2026-09).

## 4. 한국어 사용자 실사용기

### 4-1. 직접 쓴 후기(회의·통화 로컬 전사)

| 날짜·출처 | 누가·조건 | 쓴 것 | 보고된 점 | 평가 |
|---|---|---|---|---|
| 2026-09-27 velog(petit-prince) https://velog.io/@petit-prince/너-회의에서-결정한거-까먹지-들어와봐 | 직장인 1인, 한국어 팀 회의. **사내 VPN 때문에 클로바 접근 불가**가 로컬 전환 이유. MacBook 로컬 | whisper.cpp large-v3-turbo + pyannote, Obsidian 플러그인 자작 | **"전사 퀄리티는 좋은데 발화자 분리 기능이 약하다"**(9월 10일), 발화자가 너무 많이 뽑힘. 전사 중 끊겨 녹음이 날아간 적, "네 네 네" 반복(7분 분할로 해결). 최종적으로 "현재 워크플로우에 굉장히 만족"하나 화자 분리 개선 과정을 계속 수정한 기록. 정량·표본 수 없음 | 전사 만족 + 화자 분리 불만의 대표 사례 |
| 2026-04-17 TreeSoop 블로그 | 개발사, "30분 한국어 회의", M1 Pro 이상 | mlx-whisper large-v3 + 후처리, 화자 분리는 별도 | 유료 Notta는 전문 용어·고유명사 절반 이상 수정, 로컬 Whisper는 전문 용어 높음·가독성 좋음, "M1 Pro 이상 실시간보다 빠름", **VibeVoice는 Mac에서 안정적으로 안 돌아 제외** | [벤더 성격], 수치 없음 |
| 2026-04-05 42class(Meetnote 저자) | 개인 개발자 | mlx-whisper turbo + pyannote 3.1 | "60분 5분(Apple Silicon)", "LLM 보정이 고유명사 정확도에 체감", 화자 임베딩 DB로 누적 학습 만족 | 정량 없음 |
| 2026-06-09 GeekNews(Recap 저자) | 개인, 업무 환경상 외부 AI 불가 | Whisper turbo + Senko/pyannote + Gemma/EXAONE | "초기 베타", "설치가 가볍지 않다"(pyannote 약관·토큰) | 사용자 평가 댓글 없음 |
| 2026-06-14 GitHub second-brain #111 | 개인 개발자, 통화 녹음(모노 AAC 44.1kHz 2인) | pyannote 로컬 파이프라인 구현 후 **활성화 보류**, 이후 **OpenAI gpt-4o-transcribe-diarize로 전환**("로컬 추론 금지 정책") | 한국어 로컬 diarization **실측 0건**이라고 스스로 적음(Mac mini ARM64 RTF 미지) | 로컬 근거 없음 |
| 2026-09-28 GeekNews(추로) | iOS/macOS 앱 개발자 | WhisperKit large-v3 + FluidAudio | "한국어 문장 속 영어는 소리대로 적힌다(deploy→데플로이)" | 화자 분리 품질 언급 없음 |

### 4-2. 질문·토론 (GeekNews)

- **"한국어 다중화자 구분을 잘하는 모델이 있을까요?"** (2026-05-12, https://news.hada.io/topic?id=29417): 질문자는 Whisper·NCP Clova를 써 봤는데 "한국어 다중화자 구분이 생각보다 많이 어렵다". 댓글: "다중 화자는 Clova가 잘 해 준다. 리턴제로도 괜찮다. STT가 좀 딸려도 성능 좋은 LLM에 넘기면 만족스럽다"(sungwoo), "화자 구분은 다글로가 잘하는 것 같았다"(yunsub2), 리턴제로(RTZR) API 안내(arthurk). **로컬 모델 추천 댓글은 없음.**
- **후속**(2026-05-28, https://news.hada.io/topic?id=29954): 드라마·예능 대상. Whisper API + pyannote(구독 $19/월이라 포기) + AssemblyAI → Deepgram Nova-3 + Replicate pyannote로 "얼추 분리된다". 연구 경험자 댓글: 얼굴 인식까지 결합하면 정교해지지만 "80~90% 정확도는 누구나 만들고 나머지 10%가 사업의 본질", **"자동화로는 한계, 태깅·매핑은 사람 손을 타야 한다"**. 대상이 방송 콘텐츠라 회의와 조건이 다르다.
- **kocer**(2026-11-03, https://news.hada.io/topic?id=36492): 한국어 CER에서 공개 모델 7개 설정·테스트셋 3개 기준 **기존 CER 오류의 46~65%가 표기 차이**(띄어쓰기·문장부호·숫자·영문)라는 도구. 한국어 STT 비교 시 CER 해석에 주의하라는 근거. soma0sd의 "표기 규칙 차이" 지적과 일치.
- NVIDIA **Nemotron 3.5 Transcribe**(2026-10-29, https://news.hada.io/topic?id=36196): 한국어 포함 40개 언어, 한국어 화자 구분·영어 번역 지원, 최대 1시간·8명, 단 양자화·로컬 배포 지원은 "예정 단계". 한국어 사용자 후기 댓글은 없고, 붙은 Hacker News 의견은 영어·독일어·일본어 위주(한국어 근거 없음).

### 4-3. 클로바노트와의 비교글

| 글 | 성격 | 내용 | 신뢰도 |
|---|---|---|---|
| 티로 블로그(2026-08 전면 개정, 최종 수정 2026-10-30) https://tiro.ooo/ko/blog/-음성-인식-ai-정확도-비교-클로바노트-vs-다글로-vs-티로-31174 | **[벤더]** 티로 판매사 | 영상 1편(영화감독 인터뷰, 약 2~3분)을 세 서비스에 넣음. 클로바는 "전체 이해에는 지장 없음, 고유명사·외국어 이름 한계, 문장부호 없음", 다글로·티로가 우세. 화자 분리는 티로가 $13 Pro부터. 저자 스스로 "영상 한 편 결과라 일반화 불가" | 낮음 |
| AI레포토 블로그(2025-05-29) https://www.airepoto.com/ko/blog/insight/airepoto_compare | **[벤더]** | "클로바노트가 화자 분리 정확도에서 가장 우수"(토론·인터뷰 시험) | 낮음 |
| 클리앙(2023-06-01) https://www.clien.net/service/board/park/18111412 | **[커뮤니티, 오래됨]** | Whisper **large-v2**로 변환해 보니 "평소 쓰지 않는 단어는 클로바가 거의 틀리고 Whisper는 맞춘다", 한영 혼용·콩글리시도 Whisper 우세. 그래도 음성 저장 때문에 클로바를 계속 쓸 것. 표본·조건 불명 | 낮음(3년 전, 모델·클로바 모두 변경) |
| Threads lunamoth(2025-01-14) https://www.threads.com/@lunamoth/post/DE1rZEmpIvN | **[2차]** | rtzr/Awesome-Korean-Speech-Recognition의 "2년 전 자료"를 인용해 "에러율 Whisper 11.39%, 네이버 클로바 스피치 9.52%". **원 저장소는 열람하지 않음**(확인 못 함) | 낮음 |
| 개인 블로그 fuerte(2026-08-22) https://fuerte.tistory.com/548 | 개인(수치 없음) | "Whisper와 클로바 중 어느 쪽이 정확한지는 녹음마다 다르다", "화자 분리와 문장 다듬기 때문에 체감 품질이 뒤집히는 경우가 많다"는 **주장**, 직접 3~5분 정답을 만들어 채점하라는 방법론 글 | 일반론 |
| 클로바노트 요금 변화 | 일부 2차 글이 "개인 유료 없어졌다(2026)"를 주장(검색 결과 제목, 미열람) | 확인 못 함 | - |

종합: **같은 녹음으로 로컬(Whisper/Qwen)과 클로바노트를 정량 비교한 한국어 글은 찾지 못했다.** "클로바가 낫다/로컬이 낫다"는 주장은 모두 벤더 글, 3년 전 일화, 이미지 한 장 수준이다.

### 4-4. 못 찾은 것

- 클리앙·디시(맥북/AI 갤러리)·뽐뿌의 **2026년** 로컬 회의 전사·화자 분리 후기: 검색에서 찾지 못함(2023년 클리앙 글 1건만). 포럼 내부 검색은 이용하지 못함.
- 한국어 3인 이상 **실제 회의** 로컬 화자 분리 정량 보고: 확인 못 함(soma0sd가 공개 데이터가 없다고 명시).
- Mac mini M4 16GB에서 한국어 전사+화자 분리 풀 파이프라인의 제3자 실측: Recap 저자 외 확인 못 함.

## 5. 폰 녹음 → Mac 자동 전사·요약 공개 사례

| 사례 | 흐름 | 한국어·화자 분리 | 비고 |
|---|---|---|---|
| Yuki Sato(2025-12) https://yukisato.dev/posts/lifelog-audio-workflow-vad-whisper | **Android 녹음 앱(Smart Voice Recorder, 16kHz 모노 WAV) → Syncthing → Ubuntu 데스크톱 감시 → Silero VAD → Whisper large-v3 → 일별 JSONL → AI 요약** | 한국어 ✗, 화자 분리 ✗ | 폰→PC 자동 동기화 패턴의 가장 구체적 공개 사례. 데스크톱이 Mac이 아님. "자동화는 하지 않기로 함"(요약 단계) |
| whosaid `watch` | iPhone 음성 메모 폴더(또는 임의 폴더) launchd 감시 → 전사·화자 분리·요약·검색 | 한국어 임베딩 미지원(위 §1-13) | 지문(음성 등록)·MCP |
| Recap | 지정 폴더 감시 자동 처리 + 웹 UI(`uploads`) | **한국어 ✓** | Mac mini 상시 서버 구성과 가장 가까움. 갤럭시 파일 반입은 직접 해야 함 |
| MacWhisper | 감시 폴더(Pro, 베타) + `mw` CLI 일괄 | 화자 분리 `--speakers` | Syncthing 등으로 폴더에 떨어뜨리면 동작 `[추정]` |
| Vibe | **폰으로 QR을 스캔해 녹음하면 컴퓨터가 전사해 텍스트를 돌려줌**(iOS/Android, 앱 설치 불필요라고 README 주장) | 한국어 근거 없음 | 대면 녹음을 폰 브라우저로 할 때만 해당, 갤럭시 기본 녹음 앱과는 다른 경로 |
| Buzz | 감시 폴더 + CLI | 한국어 근거 없음 | |
| r/macapps(2026-09-01) | iPhone 음성 메모/통화 녹음 → AirDrop → Mac에서 전사 | - | 통화 상대 음성은 폰에서 녹음해야 한다는 제약 논의 |
| storycompiler 블로그(2026-03-19, **DGX Spark** 환경) https://storycompiler.tistory.com/329 | Whisper large-v3 + pyannote 3.1 | 한국어 예문, **갤럭시 기본 녹음 앱은 m4a(AAC)이고 pyannote(soundfile)가 m4a를 못 읽어 `ffmpeg -ar 16000 -ac 1 wav` 변환 필요** | Mac 아님. 실측: 45분 녹음 Whisper 약 6분, pyannote 약 2분(GPU) |

관련 참고: 갤럭시 통화 녹음 파일 위치 안내(내 파일 → Recordings → Call, 안드로이드 12 이하/13 이상 경로 차이) https://iflue.tistory.com/394 (2026-10-31, 개인 블로그).

**확인 못 함**: 갤럭시(One UI) 녹음 → Mac(Syncthing, Google Drive, Quick Share 등) → 한국어 전사·화자 분리를 모두 이은 공개 저장소·글.

## 6. 핵심 질문: 한국어 다화자 녹음에서 사람들이 실제로 만족한 로컬 조합과 클로바노트 대비 체감 차이

**근거로 답할 수 있는 범위만 쓴다.**

### 6-1. "만족했다"고 보고된 로컬 조합

1. **전사 단계의 만족 보고는 Whisper large-v3 / large-v3-turbo(mlx-whisper 또는 whisper.cpp)에 집중**된다. velog(MacBook, 2026-09), TreeSoop(M1 Pro 이상, 2026-04), Recap(M4 16GB 기본값, 2026-06), Meetnote(2026-04). 모두 개인·벤더 서술이고 정량 근거는 약하다. Qwen3-ASR을 한국어에서 만족스럽게 쓴다는 보고는 GPU 환경(Reddit 2026-03, soma0sd 2026-10)이며 Mac 보고는 없다.
2. **화자 분리까지 만족했다는 한국어 보고는 확인 못 함.** 한국어 사용자의 직접 언급은 "화자 분리가 약하다"(velog), "짧은 추임새에서 흔들린다"(treesoop), "한국어 다중화자 구분이 어렵다"(GeekNews)다. Recap 저자도 사람 정답 검증이 끝나지 않았다고 적었다.
3. **측정으로 가장 좋았던 조합**(한국어 실제 2인 대화, GPU): Nemotron-3 Diarization + Qwen3-ASR 1.7B(cpCER 18.0 / 12.5%), 통합형 VibeVoice-ASR(Nexdata 11.3%, 느림·화자 수 오판 사례). 이 조합 자체의 Apple Silicon 측정은 확인 못 함.
4. **Mac 앱에서 이미 쓸 수 있는 근접 구성**: MacWhisper 15.2(Nemotron 3 Diarization + Whisper/Qwen3-ASR), speech-swift(Qwen3-ASR + Sortformer/pyannote, 병합은 직접), Recap(turbo + Senko).

### 6-2. 클로바노트 대비 체감 차이 — 보고된 방향

| 항목 | 로컬 쪽 보고 | 클라우드(클로바 등) 쪽 보고 | 근거 수준 |
|---|---|---|---|
| 고유명사·전문 용어·영어 혼용 | 로컬 Whisper가 낫다는 보고(TreeSoop vs Notta, 클리앙 2023 vs 클로바) | 클로바는 "고유명사·외국어 이름에 한계"(티로 벤더 글) | 약함(한 번 비교, 조건 불명) |
| 문장 가독성 | Whisper 출력이 줄 단위로 깔끔(TreeSoop), 문장부호 있음 | 클로바는 문장부호 없음(티로) | 약함 |
| **다화자 화자 분리 안정성** | 과분리·추임새 흔들림(velog, TreeSoop, AnythingLLM, Recap) | **클로바·다글로가 낫다는 의견**(GeekNews 댓글 2026-05, AI레포토 벤더), Notta도 안정적(TreeSoop) | 중간(여러 출처가 같은 방향이나 모두 정성) |
| 즉시 사용·요약 | 설치·토큰·약관·모델 선택이 번거롭다(Recap, whosaid 설치 설명) | 업로드만으로 완료 | 중간 |
| 보안·접속 | 사내 VPN으로 클로바 접근 불가라 로컬로 전환(velog), 외부 전송 금지 환경 목적 다수 | 클라우드 | 사용 동기로 일관 |

→ **체감 차이를 한 줄로 요약하면**: 한국어에서 *전사 자체*는 로컬 Whisper 계열도 "쓸 만하다/더 낫다"는 개인 보고가 있으나, *다화자 화자 분리*는 클라우드가 더 안정적이라는 정성 보고가 우세하고, 로컬이 따라잡았다는 근거는 없다. 이 결론의 근거 수준은 "개인 후기 + 벤더 글"이며 **통제된 로컬 vs 클로바 비교는 확인 못 함**.

### 6-3. 사용자의 조건(갤럭시 한 대, 2명 이상 대화)에서 주목할 점

- 대면 녹음은 **모노 혼합**이라 r/macapps가 "가장 어려운 경우"로 꼽은 조건이다. 통화는 2명이라 `num_speakers=2` 같은 힌트가 효과적이라는 주장이 반복된다(second-brain #111 기획, local-stt.md 인용). 
- 겹침·짧은 맞장구는 모델을 바꿔도 남는 오류라는 보고가 일관된다(soma0sd, treesoop, Senko).
- 한국어 화자 분리용 임베딩이 따로 있는 도구는 찾지 못했다(Senko는 영어+중국어, whosaid 기본은 영어, Anarlog 로컬은 한국어 미지원). Nemotron 3 Diarization(Sortformer 계열)은 임베딩 클러스터링이 아니라 한국어 실대화 DER이 soma0sd에서 11.5~16.2%로 측정된 유일한 후보다(GPU 측정).
- 속도·메모리: Mac mini M4 16GB 한국어 실측은 Recap(전사 1시간 약 3분 + LLM 후처리)뿐이고, Qwen3-ASR MLX는 구현별 메모리 편차(1.2~3.4GB vs 37GB 보고)와 VibeVoice 4bit의 청크 필요 보고가 있어 **직접 측정이 필요하다**.

## 7. 실측해 볼 가치 판단

판정: ◎ 우선 실측 / ○ 시간 되면 / △ 조건부 / × 제외. 전제: 사용자의 실제 갤럭시 녹음 10~20분 분량 2~3개를 사람이 정답 전사·화자 라벨링 → CER/cpCER·DER·환각 횟수·RTF·최대 메모리 측정(`local-stt.md` §7과 동일).

| 후보 | 판정 | 이유(근거) | 확인할 것 |
|---|---|---|---|
| mlx-whisper large-v3 + Nemotron 3 Diarization / Senko / community-1 (직접 구성, Recap·treesoop 구성 참고) | ◎ | 한국어 사용자 보고의 중심, 단어 단위 정렬 직접 제어, 화자 수 힌트·범위 제한 가능 | 병합 방식(세그먼트 vs 단어), 환각(7분·30분 분할), 추임새 처리 |
| MacWhisper Pro 15.2 (Nemotron 3 Diar. 내장) | ◎ | 설치·CLI·감시 폴더가 가장 쉽고 2026-09에 화자 분리 교체, 64유로 | 한국어 모델과 화자 분리 동시 사용 여부, Qwen3-ASR 한국어 포함 여부, `mw --speakers` 일괄 |
| Recap (notadev-iamaura) | ○ | 한국어 전용 Mac 파이프라인, M4 16GB 목표, 폴더 감시·요약까지 포함 | 설치 부담(Python 3.11/3.12, 토큰), 화자 분리 품질은 직접 검증 필요, 사람 정답 검증은 저자도 미완 |
| speech-swift(Soniqo) + 직접 병합 | ○ | Qwen3-ASR·Whisper CoreML·MOSS 모두 CLI 일괄 처리, Apache-2.0 | 전사·화자 분리가 별도 명령 → 병합 스크립트 필요 |
| MOSS-Transcribe-Diarize를 Soniqo CoreML/MLX로 | ○ | 사용자가 이미 보유한 일체형을 Mac 네이티브 런타임으로 비교 가능 | 한국어 정확도(이번 조사에서 새 근거 없음, `local-stt.md` §4-1) |
| Qwen3-ASR 1.7B + 30초 분할 (soma0sd 구성) | ○ | 한국어 실대화 CER 최저(GPU), 30초 분할이 장문 품질을 크게 개선 | MLX 구현 메모리(37GB 보고 vs 1.2~3.4GB), 16GB mini 안정성 |
| VibeVoice-ASR 4bit (mlx-audio) | △ | Nexdata cpCER 11.3% 최저지만 느리고 화자 수 오판, Mac 보고는 OOM·불안정 | M3 Max에서 BF16 상한 확인용으로만 |
| Vibe | △ | GUI·CLI·일괄·API, 4명 한도, 한국어 근거 없음 | 2인 대화 한정 시험, macOS 서명 빌드 문제 재현 여부 |
| OpenWhispr, Buzz | △ | 로컬 화자 분리 지원 주장, 한국어·Mac 후기 없음 | 한국어 임베딩 품질(영어·중국어 학습 가능성) |
| whosaid | △ | 감시 폴더·CLI 완성도 높음, **한국어 화자 임베딩 옵션 없음** | 한국어에서 서로 다른 사람이 합쳐지는지 |
| Anarlog, Meetily | × | 한국어 로컬 모델 근거 없음(Anarlog) / 화자 분리 Pro 전용(Meetily) | - |
| VoiceInk, Hex, Talat 등 Parakeet v3 계열 앱 | × | 한국어 ASR 미지원 | - |
| FluidAudio Nemotron 3.5 Transcribe Lite | × | 영어 전용 | 단, FluidAudio의 diarizer는 직접 구성에 부품으로 사용 가능 |
| WhisperKit/SpeakerKit | ○(부품) | Swift 앱 제작 시, SpeakerKit·community-1 CoreML | OpenBench 수치 미확인 |
| whisper-diarization | × | Mac 근거 확인 못 함, CUDA 지향 | - |

## 8. 이번 조사에서 확인하지 못한 항목

- MacWhisper Qwen3-ASR 22개 언어에 한국어 포함 여부, Nemotron 3 Diarization 사용 시의 모델 제약, 한국어 화자 분리 후기.
- Vibe·Buzz·OpenWhispr·Meetily의 한국어 전사·화자 분리 품질.
- Senko·FluidAudio·WhisperKit SpeakerKit·OpenBench의 한국어 DER, SpeakerKit OpenBench 수치.
- 갤럭시 → Mac 자동 전송 + 한국어 화자 분리 공개 사례.
- 2026년 클리앙·디시·뽐뿌의 로컬 회의 전사 후기.
- 한국어 로컬 vs 클로바노트 통제 비교(같은 녹음, 같은 정답).
- rtzr/Awesome-Korean-Speech-Recognition 원자료(2차 인용만 확인).
- gggg8657/meeting-local(404), KYankee6/advanced-audio-recorder-fork(미열람).
