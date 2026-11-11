# QuietClerk Mac 앱 패키징 사실 조사 (셸·엔진 배포·업데이트·서명)

조사일 2026-11-11 · 작성: AppPackaging · 읽기 전용 조사(저장소 코드·문서 수정 없음, 임시 파일은 `/tmp`에서만 만들고 지움)

## 설계에 바로 쓰는 결론

1. **추천 조합**: Tauri v2 셸(메뉴 막대 + 기존 로컬 웹 화면을 창으로) + **(b) 엔진은 앱 안의 서명된 `uv`로 첫 실행 때 `~/Library/Application Support`에 venv 생성** + Developer ID 서명·공증 + 앱 업데이트는 Tauri updater(GitHub Releases) + 엔진은 앱 버전에 묶인 lock 해시로 버전별 폴더에 재동기화. **대안**: 같은 엔진 방식에 셸만 네이티브 SwiftUI(MenuBarExtra + WKWebView + SMAppService + Sparkle). 근거는 7절.
2. **(b)를 고른 결정적 실측 근거**: 이 구조의 `mlx-whisper 0.4.3`은 `numba`를 import하고, **하드닝 런타임(Team ID 서명, 전 Mach-O 재서명) 아래에서 `import numba`가 SIGKILL(137)** 된다. `allow-unsigned-executable-memory`를 줘야 풀린다(`allow-jit`만으로는 안 풀림). MLX 자체(GPU 행렬곱·`mx.compile`)는 하드닝 런타임에 예외가 필요 없었다. 번들(a)은 이 예외를 앱 전체 서명에 영구히 넣는다. (b)의 파이썬은 번들 밖·하드닝 아님이라 예외가 필요 없고, 하드닝된 부모 프로세스가 띄워도 동작함을 확인했다(2절 실측, 검증 수준: 가정으로 확인).
3. **서명·공증 없이 배포는 비개발자 대상에 부적합**: 처음 열 때 "Apple이 악성 소프트웨어를 확인할 수 없음"류 경고, 해제는 시스템 설정 > 개인정보 보호 및 보안 > "그래도 열기"(Apple 문서). Homebrew 공식 cask는 Gatekeeper 미통과 cask에 "2026-09-01 비활성화" 메시지를 달았다(시행 여부는 확인 못 함). → **Apple Developer Program 99 USD/년이 M4 A2의 선행 조건**. 지금 이 Mac에는 `Apple Development` 인증서만 있고 **Developer ID는 없다**(공증 실행은 못 해 봄).
4. **Mac App Store는 안 맞는다**: 샌드박스 필수, 가이드라인 2.4.5가 "로그인 시 자동 실행은 동의 필요·다른 추가 코드 내려받기 금지·업데이트는 Mac App Store로만"을 요구한다. 사용자가 구독한 외부 CLI(Codex·Claude Code) 실행과 첫 실행 때 파이썬 환경·모델 내려받기가 정면으로 걸린다. 직접 배포(DMG)만 본다.
5. **Tauri의 구멍 둘**: ① 번들러는 `Contents/Resources` 안 Mach-O를 서명하지 않는다(소스 `app.rs`에서 확인) → (b)에서는 `uv` 하나만 `externalBin`으로 넣으면 번들러가 서명한다. ② 자동 시작 플러그인은 macOS에서 `~/Library/LaunchAgents` plist 또는 AppleScript 방식이고 **SMAppService가 아니다**(플러그인 소스 확인) → 엔진 상주를 SMAppService 에이전트로 하려면 작은 네이티브 연결 코드가 필요하고, 이건 **아직 시험 못 한 가정**이다(9절 미결 1).
6. **업데이트 크기**: 번들(a)이면 앱 업데이트마다 엔진 전체를 다시 받는다. 이 의존성 집합의 설치 결과는 1.3GB, gzip 369MB이고, `torch`(570MB)를 빼면 site-packages가 701MB로 줄어든다(import만 확인, 모델 전사는 안 해 봄). (b)는 앱 ~수십 MB + 엔진은 lock이 바뀔 때만 받는다.
7. **공개 저장소 전제 확인 필요**: `gh api`로 본 `minigold92/rec2vault`는 2026-11-11 현재 **private, stars 0, 생성 2일**이다. GitHub Releases 기반 updater 엔드포인트와 Homebrew cask 신청(저장소 30일 이상, 30 fork/watcher 또는 75 star)은 공개 저장소가 필요하다. 배포 채널 계획 전에 공개 시점을 확정할 것.
8. **가장 가까운 선행 사례는 Tractus**(Tauri 2 + 파이썬 코어 + MLX): 옮길 수 있는 python-build-standalone과 의존성을 앱 안에 넣고 ad-hoc 서명한다(DMG 166MB, 서명·공증 안 함, 사용자에게 "그래도 열기"/`xattr` 안내). 정식 서명 때 하드닝을 켜면 ad-hoc 라이브러리를 못 불러온다고 코드 주석이 적고 있다. (b)가 아닌 (a)를 택한 사례이고, 우리는 같은 문제의 다른 선택을 한다.
9. **FDA(전체 디스크 접근)는 요구하지 않는 설계**: 폰 녹음 흐름은 마이크·시스템 오디오가 필요 없다. 폴더는 사용자가 고르게 하고(열기 패널은 사용자 의도 접근이라 TCC 대상이 아님), 기본 위치를 `~/Documents`·`~/Desktop` 밖에 둔다. 단 launchd 에이전트의 파이썬 자식 프로세스가 TCC에서 누구로 보이는지는 **확인 못 함**(미결 3).
10. 미결 7건은 9절에 담당·확인 시점(제안)과 함께 있다.

## 0. 근거 표기와 검증 수준

- 날짜는 모두 2026-11-11 확인. URL은 문장 끝 또는 부록 A.
- **[문서]** 공식 문서·README를 읽음 · **[코드]** 저장소 파일을 직접 읽음 · **[실측]** 이 MacBook(Apple M3 Max, macOS 27.0.1, uv 0.13.1, Python 3.12.9 python-build-standalone)에서 실행 · **[추정]** 근거 없는 추론 · **확인 못 함**.
- **검증 수준**(이번 조사에서 실행한 것은 전부 "가정으로 확인"이다):
  - *실행만*: 명령이 에러 없이 끝남.
  - *가정으로 확인*: 합성 입력(작은 행렬, 정수 JIT 함수, import)으로 동작을 봄. **이번 [실측]은 전부 여기**.
  - *실제 입력으로 확인*: 실제 회의 녹음·실제 모델(5.2GB)로 끝까지 전사하고 노트가 나옴. **이번 조사에서는 하지 않음.** 따라서 "하드닝 런타임에서 모델 전사가 된다"와 "공증을 통과한다"는 주장하지 않는다.
- 이번 조사의 한계: Developer ID 인증서가 없어 **공증(notarytool) 실행 불가**. 하드닝 실측은 `Apple Development` 인증서(Team ID 있음)로 서명한 결과이며, Developer ID와 같은 하드닝 런타임 규칙이 적용된다고 **[추정]**한다.

## 1. 셸 기술 비교

| 항목 | Tauri v2 | 네이티브 SwiftUI 메뉴 막대 앱 (+WKWebView, SMAppService, Sparkle) | Electron |
|---|---|---|---|
| 파이썬+MLX 엔진 담는 법 | `externalBin`(타깃 트리플 접미사 필요, 문서가 "pyinstaller로 묶은 파이썬 CLI·API 서버"를 대표 용도로 적음) 또는 `bundle.resources`로 디렉터리 통째(Tractus가 `runtime/`을 이렇게 넣음). 임의 하위 프로세스는 `shell` 플러그인 sidecar/Rust `Command`로 띄움 [문서][코드] | 앱 번들 `Contents/Resources`나 `Contents/Helpers`에 넣고 `Process`로 실행. 헬퍼 plist는 `Contents/Library/LaunchAgents`(SMAppService) [문서] | `extraResources`로 넣고 `child_process`로 실행 (OpenWhispr가 whisper.cpp·sherpa-onnx 등 네이티브 바이너리를 이렇게 넣음; 파이썬 사례는 이번 8개 중 없음) [코드] |
| 앱 크기(셸+자기 자산) | 공개 릴리스 DMG: vibe 38MB, Meetily 48MB, Minutes 62MB(Rust 사이드카 포함), Tractus 166MB(파이썬 코어 포함) [실측: `gh api`] | 확인 못 함(이번 8개 중 Recap만 순수 Swift인데 릴리스 없음). Swift 앱은 시스템 WKWebView를 써서 셸 자체는 작다 [추정] | OpenWhispr DMG 343MB(네이티브 헬퍼·진단 모델 포함이라 순수 Electron 오버헤드 아님). 이 Mac에 설치된 Electron 앱 Obsidian 1.14.4가 디스크 529MB [실측] |
| 서명·공증 난이도 | Developer ID 서명·공증을 `tauri build`가 환경변수(`APPLE_CERTIFICATE`·`APPLE_API_*`)로 수행 [문서]. **`Resources` 안 Mach-O는 서명 대상이 아님**(소스: `sign_paths`는 프레임워크+externalBin+앱만) → 별도 `beforeBundleCommand` 서명 스크립트 필요(Speedwave ADR-037도 같은 결론, 단 그쪽은 "unverified"로 표기). 사이드카 서명 실패 사례(#11992: 인증서 신뢰 설정 문제로 해결) [코드][문서] | Xcode Archive → Developer ID → 공증이 표준 경로. Sparkle 프레임워크의 XPC·헬퍼도 Archive 때 같이 재서명 [문서] | electron-builder `notarize: true`로 자동(OpenWhispr 설정). 앱이 크고 Mach-O가 많아 공증 업로드가 큼 [코드] |
| 로그인 시 자동 시작·상주 | `autostart` 플러그인: macOS는 **LaunchAgent plist(기본) 또는 AppleScript 로그인 항목**, SMAppService 아님 [코드: 플러그인 `lib.rs`]. 트레이 `tray-icon` 기능, 창 닫아도 앱 유지는 Tractus가 구현(`tray.rs`) [문서][코드] | `SMAppService.mainApp/.agent/.loginItem`로 로그인 항목·에이전트 등록, 상태가 `requiresApproval`이면 시스템 설정으로 안내(`openSystemSettingsLoginItems`). `MenuBarExtra`(macOS 13+) [문서] | `app.setLoginItemSettings`가 macOS에서 `mainAppService`·`agentService` 유형을 지원(이름이 SMAppService 유형과 대응, 내부 구현은 확인 못 함). 서명·공증 안 된 앱은 조용히 실패할 수 있다고 문서가 경고 [문서] |
| 권한(마이크·화면·FDA) | 코어에 권한 API 없음. `Info.plist` 사용 설명 + 하드닝 시 `device.audio-input` 엔타이틀먼트를 직접 넣음(Tractus·Vibe·Meetily·Anarlog가 이렇게 함). 시스템 오디오(Core Audio tap)는 `NSAudioCaptureUsageDescription`만, 화면 녹화 방식은 `NSScreenCaptureUsageDescription`(Tractus·Meetily 주석/plist) [코드] | 네이티브 API 직접 사용(AVCaptureDevice, TCC 요청). 번들 서명 신원이 TCC 주체가 되어 가장 단순 [추정] | Info.plist·엔타이틀먼트 직접(OpenWhispr가 마이크·오디오 캡처·접근성·캘린더 설명 키를 넣음) [코드] |
| 폴더 선택·알림 | `dialog` 플러그인(폴더 선택), `notification` 플러그인(Meetily의 capabilities에 notification 권한이 있음) [문서][코드] | `NSOpenPanel`, `UserNotifications` | `dialog.showOpenDialog`, `Notification` |
| 기존 로컬 웹 화면 재사용 | `WebviewUrl::External`로 `http://127.0.0.1:포트` 로드 가능(docs.rs). IPC는 기본적으로 번들 코드에만 열림이므로 원격 URL에 권한을 주지 않으면 화면이 Rust 명령을 못 부름 [문서] | WKWebView에 로드, 가장 직접적 | `BrowserWindow.loadURL` |
| 이후 Windows | 같은 코드베이스로 NSIS/MSI. Windows 서명은 OV 인증서·Azure Key Vault·Azure Artifact Signing 경로 문서화, 미서명 시 SmartScreen 경고 [문서] | **없음**. Windows는 셸을 새로 만들어야 함. 단 QuietClerk UI는 엔진이 서빙하는 웹 화면이라 셸이 얇아 재작성 비용이 작다 [추정] | 가능, 대신 용량·메모리 큼 |
| 앱 자체 업데이트 | `tauri-plugin-updater`(minisign 계열 서명 키, GitHub Releases의 `latest.json`) | Sparkle 2(EdDSA, appcast, 델타 업데이트) | `electron-updater`(OpenWhispr, `latest-mac.yml`) 또는 Squirrel.Mac(서명 필수) |
| 팀 기술 요건 | Rust 최소 + 웹. 현재 스택(파이썬+웹)과 거리 중간 | Swift/AppKit 필요. 이 프로젝트에 Swift 코드 없음 | Node/JS. 파이썬 엔진과 별 영역 |

출처: [Tauri sidecar](https://v2.tauri.app/develop/sidecar/), [Tauri tray](https://v2.tauri.app/learn/system-tray/), [Tauri autostart](https://v2.tauri.app/plugin/autostart/), [autostart 소스](https://raw.githubusercontent.com/tauri-apps/plugins-workspace/v2/plugins/autostart/src/lib.rs), [Tauri bundler `app.rs`](https://raw.githubusercontent.com/tauri-apps/tauri/dev/crates/tauri-bundler/src/bundle/macos/app.rs), [Tauri macOS 서명](https://v2.tauri.app/distribute/sign/macos/), [Tauri Windows 서명](https://v2.tauri.app/distribute/sign/windows/), [Tauri capabilities](https://v2.tauri.app/security/capabilities/), [WebviewUrl](https://docs.rs/tauri/latest/tauri/enum.WebviewUrl.html), [Tauri #11992](https://github.com/tauri-apps/tauri/issues/11992), [SMAppService](https://developer.apple.com/documentation/servicemanagement/smappservice), [Apple 헬퍼 실행 파일 갱신](https://developer.apple.com/documentation/servicemanagement/updating-helper-executables-from-earlier-versions-of-macos), [MenuBarExtra](https://developer.apple.com/documentation/swiftui/menubarextra), [Electron app API](https://www.electronjs.org/docs/latest/api/app), [Electron autoUpdater](https://raw.githubusercontent.com/electron/electron/main/docs/api/auto-updater.md), [Speedwave ADR-037](https://github.com/speednet-software/speedwave/blob/dev/docs/adr/ADR-037-code-signing-and-bundled-binary-signing.md).

**셸 선택에서 정직하게 짚을 점**
- 이 제품의 UI는 엔진이 서빙하는 웹 화면(설계 2.2절 A)이라, 셸이 하는 일은 메뉴 막대 아이콘·창·로그인 시 시작·업데이트·폴더 선택 정도다. 그래서 "Windows 확장성" 하나로 Tauri와 네이티브가 크게 갈리지는 않는다 [추정]. 갈림은 오히려 **SMAppService·Sparkle 같은 macOS 일급 기능을 얼마나 직접 쓰느냐**다.
- Tauri가 약한 곳은 macOS 로그인 항목 API(위 표, 플러그인이 LaunchAgent/AppleScript)와 Resources 서명이다. 네이티브가 약한 곳은 Swift 코드 유지와 Windows 재작성이다.
- 엔진을 앱의 자식 프로세스로 돌리면 앱 종료 = 엔진 종료다. 설계 M4 A1의 "앱 창 종료 ≠ 엔진 종료"는 창만 닫는 것이고, "앱 종료 ≠ 엔진 종료"까지 원하면 엔진을 launchd 에이전트(지금 `deploy/launchd.plist.in`의 `KeepAlive`)로 분리해야 한다. 이때 에이전트 실행 파일이 서명되지 않으면 문서상 `AssociatedBundleIdentifiers`가 앱과 Team ID가 일치해야 로그인 항목 패널에서 앱 이름으로 묶인다(Apple 문서). 파이썬은 Team ID가 없으므로 **Developer ID로 서명한 작은 런처**가 에이전트의 `Program`이 되고 파이썬을 자식으로 띄우는 구조가 필요하다 [추정, 9절 미결 1·3].

## 2. Python 엔진 배포 방식

### 2.1 이 엔진의 실제 크기·구성 [실측]

`pyproject.toml`의 의존성(`mlx-audio==0.6.4`, `mlx-whisper==0.4.3`, soundfile, numpy, soynlp, PyYAML, starlette, uvicorn, jinja2)을 Python 3.12.9에 설치한 결과.

| 항목 | 값 |
|---|---|
| venv 전체 | 1.3GB |
| 상위 폴더 | torch 570MB, mlx 236MB(`mlx.metallib` 하나가 214MB), llvmlite 128MB, scipy 72MB, transformers 55MB, sklearn 32MB, numpy 22MB |
| Mach-O 파일 | `.so` 223개 + `.dylib` 16개(+python 실행 파일·libpython) → 서명 대상 약 241개 |
| 압축 크기 | `lib/` gzip -3 기준 369MB (wheel 크기가 아니라 설치 결과를 압축한 값) |
| 파이썬 런타임(python-build-standalone) | 60MB, 기본 서명은 ad-hoc·linker-signed |
| `torch`를 들어낸 site-packages | 701MB. `import mlx_whisper, mlx_whisper.audio, mlx_whisper.load_models, mlx_whisper.decoding`, `mlx_audio.stt`, `mlx_audio.vad` import 성공 (**import만 확인, 모델 전사는 안 함**) |
| `torch`가 들어오는 이유 | `mlx-whisper`의 의존성(`uv pip tree`). 코드에서는 `mlx_whisper/torch_whisper.py`가 import(모델 변환용 파일로 보이나 [추정]) |
| `numba` | `mlx_whisper/timing.py`가 `@numba.jit`을 모듈 최상단에서 import → `mlx_whisper`를 import하면 numba가 필수 |
| `uv` 바이너리 | 32MB (Homebrew 0.13.1, ad-hoc linker-signed) |

QuietClerk가 `mlx_whisper`를 쓰는 위치: `quietclerk/backends/mlx.py`(언어 감지 `mlx_whisper.audio`·`load_models`·`decoding`, 전사 `mlx_whisper.transcribe`).

### 2.2 하드닝 런타임·엔타이틀먼트 실측 [실측, 가정으로 확인]

방법: 위 파이썬과 site-packages를 `/tmp`에 복사해 서명 조합을 바꿔 가며 같은 세 시험을 돌림. 시험은 (1) MLX GPU 행렬곱 + `mx.compile`, (2) `@numba.njit` 함수 실행, (3) `import mlx_whisper, mlx_audio, soundfile, scipy, torch`.

| 서명 조합 | 결과 |
|---|---|
| 서명 없음(기본) 파이썬 | (1)(2)(3) 모두 통과 |
| ad-hoc + `--options runtime`, 엔타이틀먼트 없음 | **실행 자체가 안 됨**: `libpython3.12.dylib`를 `different Team IDs`로 거부(라이브러리 검증) |
| ad-hoc + runtime + `disable-library-validation` | (1)(2)(3) 모두 통과. 단 ad-hoc 프로세스는 JIT 제한이 실제로 걸리지 않음을 `MAP_JIT` 시험으로 확인(이 행은 JIT 판단 근거가 못 됨) |
| **Team ID 서명(Apple Development) + runtime, 파이썬·libpython·site-packages 안 `.so/.dylib` 241개 전부 같은 신원으로 재서명, 엔타이틀먼트 없음** | (1) 통과(**MLX는 JIT 예외 불필요**) · (2) **SIGKILL 137** · (3) `import mlx_whisper` 137로 죽음(`import numba` 단독도 137) · `MAP_JIT` 직접 시험은 errno 22로 차단(제한이 실제로 걸리고 있음을 확인) |
| 위 + `allow-jit`만 | (2)(3) 여전히 137 |
| 위 + `allow-unsigned-executable-memory`만 | (1)(2)(3) 모두 통과 |
| 하드닝된 Team ID 서명 파이썬이 **하드닝 안 된 별도 파이썬**을 `subprocess`로 실행 | 자식에서 (1)(2)(3) 모두 통과 |

해석
- 전 Mach-O를 같은 Team ID로 재서명하면 `disable-library-validation` 없이도 로드된다. 재서명을 빼먹은 서드파티 `.so` 하나가 앱을 못 뜨게 만든다(위 2행이 그 증상).
- **numba(llvmlite) 때문에 하드닝 런타임에서 `allow-unsigned-executable-memory`가 사실상 필수**다. Apple 문서는 이 계열 예외를 "Certain Python frameworks" 등으로 설명한다(`allow-jit` 문서). 서드파티 사례: Buzz(PyInstaller)는 `allow-jit`·`allow-unsigned-executable-memory`·`disable-library-validation`을 모두 넣었고, Speedwave는 Node에 JIT·unsigned-memory를 준다.
- `disable-library-validation`은 Apple 문서상 "Gatekeeper가 추가 검사를 수행"하는 예외다(아래 방식 (b)는 이 예외가 필요 없음).
- 이 결과가 모델 전사에서도 같은지는 **확인 못 함**(실제 모델·입력 미실행).

### 2.3 방식별 비교

| 방식 | MLX·mlx-audio·mlx-whisper 동작 | 공증 요구에 대한 영향 | 앱 크기·업데이트 | 사용자 경험 | 위험 | 난이도 |
|---|---|---|---|---|---|---|
| **(a) 앱에 python-build-standalone+의존성을 담아 서명** | 위 실측대로 동작(하드닝+재서명+`allow-unsigned-executable-memory`). Tractus가 이 방식으로 MLX 파이썬 코어를 출하(코드·DMG 166MB) | 공증 규칙: 모든 Mach-O가 Developer ID 서명·하드닝·보안 타임스탬프(Apple). 약 241개를 앱 안쪽부터 서명하는 스크립트 필요(Tauri 번들러는 Resources를 서명 안 함). Apple Development 신원으로 241개를 서명하는 데 3초(타임스탬프 없이)였고, Developer ID·타임스탬프 서버 호출·공증 시간은 **확인 못 함** | 설치 결과 1.3GB(gzip 369MB, torch 제외 시 더 작음 [추정]). Tauri updater/Sparkle 모두 **앱 전체**를 받음(Tractus 문서: 업데이트마다 앱 전체 약 240MB라고 적음, 릴리스 `Tractus.app.tar.gz`는 143MB [gh api]). Sparkle은 델타 업데이트를 지원하나 파이썬 트리에서 효과는 **확인 못 함** | 첫 실행 때 네트워크 불필요(모델 제외). 설치 즉시 일관된 환경 | 번들은 서명으로 봉인되어 바이트코드 쓰기 불가(Tractus는 `PYTHONDONTWRITEBYTECODE=1`·사전 컴파일). 번들 안 wheel의 macOS 최저 버전이 앱 약속보다 높으면 낮은 OS에서 dlopen 실패(Tractus가 `macosx_14_0` wheel을 URL·해시로 고정하고 14.4 초과 Mach-O를 빌드에서 막음). 파이썬·의존성 보안 패치마다 앱 재배포 | **높음** |
| **(b) 앱에 `uv`만 담고 첫 실행 때 venv 생성** (추천) | 지금 `deploy/install.sh`가 쓰는 방식과 같고 동작 확인됨(이 Mac의 venv 및 실측). 파이썬은 번들 밖·하드닝 아님 → 엔타이틀먼트 예외 불필요(하드닝 부모에서 자식 실행도 통과) | 앱 번들 안 Mach-O는 Rust 셸+`uv`뿐(`uv`는 `externalBin`이라 번들러가 서명). 공증 부담이 작고 예외 엔타이틀먼트가 없음 | 앱 수십 MB. 엔진은 lock이 바뀔 때만 다운로드. 모델은 어차피 별도 | 첫 실행에 큰 다운로드(엔진 + 모델 5.2GB)와 네트워크 의존. 진행 표시·재개·디스크 부족 점검을 앱이 해줘야 함 | ① 내려받은 실행 코드는 앱 서명·공증 범위 밖 ② PyPI·wheel 고정 필요(Tractus가 `--only-binary --require-hashes` 사용) ③ macOS 버전별 wheel 선택 문제(Tractus: macOS 26 호스트는 `macosx_26_0` mlx wheel을 고르는데 minos 26.2라 14.4~15에서 안 열림 → lock에서 최저 macOS wheel로 고정) ④ Mac App Store 불가(2.4.5(iv)) ⑤ Apple이 정책을 바꾸면 영향 [추정] | **중간** |
| **(c) PyInstaller / Briefcase** | PyInstaller+MLX는 **메타 라이브러리·dylib·metallib 누락 위험**: 공개 이슈에서 PyInstaller 번들의 `mlx/core.so`가 `libmlx.dylib`의 심볼을 못 찾는 오류가 있었으나 원인은 conda 환경 혼선이라 닫힘(mlx-vlm #201). **MLX를 PyInstaller로 성공 배포한 사례는 이번 8개 저장소에서 확인 못 함**(Buzz는 PyInstaller+서명·공증이지만 faster-whisper/torch 기반, MLX 아님). Briefcase는 이번에 조사 안 함 | PyInstaller 번들은 Buzz 사례처럼 엔타이틀먼트 3종을 넣고 모든 `.so/.dylib`를 반복문으로 서명 | Buzz 최신 릴리스 mac DMG 469MB(torch 포함) | (a)와 비슷 | 숨은 import·데이터 파일 누락(spec 유지 부담), `mlx.metallib` 같은 비파이썬 자산 위치 문제, 업데이트 시 전체 교체 | **높음**(MLX 사례 없음) |

출처: [MLX 설치 문서(macOS ≥14, 네이티브 arm 파이썬 필요, 0.32.4)](https://ml-explore.github.io/mlx/build/html/install.html), [python-build-standalone](https://gregoryszorc.com/docs/python-build-standalone/main/), [Apple 공증 문서](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution), [Apple 공증 문제 해결](https://developer.apple.com/documentation/security/resolving-common-notarization-issues), [Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime), [allow-jit](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.allow-jit), [disable-library-validation](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.disable-library-validation), [mlx-vlm #201](https://github.com/Blaizzy/mlx-vlm/issues/201), Tractus `scripts/build_app_bundle.sh`·`docs/setup.md`(저장소 sjoon21/Tractus, 커밋 0e39e5b), Buzz `Makefile`·`entitlements.plist`(chidiwilliams/buzz, 0556d17).

### 2.4 내려받은 실행 코드와 Gatekeeper·quarantine

- `com.apple.quarantine`은 **앱이 `LSFileQuarantineEnabled`를 켜거나 시스템 예외 목록에 있을 때만** 새 파일에 붙는다. 샌드박스가 아닌 일반 앱이 만든 파일에는 기본적으로 붙지 않고, `curl`로 받은 파일에도 안 붙는다(Eclectic Light Co., macOS 26 기준). Safari 같은 브라우저는 붙인다.
- [실측] 이 Mac에서 `uv`가 만든 venv와 파이썬 런타임 파일에는 `com.apple.quarantine`이 없다(검사한 `mlx` 폴더에서 0개, 파이썬 쪽은 `com.apple.provenance`만 있음). `uv`와 앱이 받는 파일은 Gatekeeper의 "인터넷에서 받은 파일" 첫 실행 검사 대상이 아니다.
- 따라서 (b)의 파이썬·wheel은 첫 실행 때 경고창 없이 돈다. 반대로 사용자가 **브라우저로 받은 DMG·앱**에는 quarantine이 붙어 서명·공증 여부가 그대로 사용자 경험이 된다.
- 하드닝 부모 → 비하드닝 자식 실행은 [실측]으로 통과(위 표 마지막 행). 단 이것이 앞으로의 macOS에서도 유지될지는 **확인 못 함**.

## 3. 자동 업데이트

| 항목 | Tauri updater | Sparkle 2 | Homebrew cask |
|---|---|---|---|
| 서명 | 업데이트 아티팩트에 **필수·끌 수 없는** 서명. `tauri signer generate`로 키 생성, 공개키는 `tauri.conf.json`(경로 불가), 개인키는 `TAURI_SIGNING_PRIVATE_KEY`(환경변수, `.env` 불가). **개인키를 잃으면 이미 설치된 사용자에게 업데이트 불가** | EdDSA(ed25519) 서명: `generate_keys`가 로그인 키체인에 개인키 저장, 공개키는 `SUPublicEDKey`. Developer ID 서명이 함께 있으면 키 회전 가능(둘 중 하나만 교체). 피드 서명(`SURequireSignedFeed`, 2.9부터) 선택 | `sha256`(바이트 일치만 증명, 만든 주체는 증명 안 함). Homebrew는 cask 다운로드에 quarantine을 붙여 Gatekeeper가 검사하게 함 |
| 배포 위치 | `latest.json`(정적 JSON, GitHub Releases `releases/latest/download/latest.json`) 또는 동적 서버. TLS 강제. **저장소가 공개여야 인증 없이 받음**(현재 private, 위 결론 7) | appcast(RSS) + 아카이브(dmg/zip/tar.xz/aar/pkg). 정적 호스팅이면 됨. `generate_appcast`가 서명·델타 생성 | `homebrew/cask`(공식)는 Gatekeeper 통과 필수. 서명·공증 안 된 cask에 "2026-09-01에 비활성화" deprecation 메시지(2025-10 토론 #6482, 실제 시행 여부는 확인 못 함). 자체 tap은 기본 검사 없음이나 "제3자 tap은 Homebrew가 지원하지 않음" |
| 갱신 단위 | macOS `.app.tar.gz`(앱 전체 교체) | 앱 전체, 선택적 **바이너리 델타**(`.delta`) | 새 버전 cask가 새 DMG를 가리킴(`brew upgrade`). 앱 자체 갱신(`auto_updates`)과 공존 가능 |
| UI | 직접 만들어야 함(Tractus는 설정 > 업데이트 + 시작 알림 구현). 문서의 `check()`·`downloadAndInstall()`·`relaunch()` | 표준 업데이트 창 제공(`SPUStandardUpdaterController`), 2번째 실행부터 자동 확인(기본 24시간 간격) | 터미널 필요 → 비개발자 경로 아님 |
| 단점 | 앱 전체 교체라 번들(a)이면 매번 큼. **업데이트 후 ad-hoc 서명 해시가 바뀌면 TCC 권한이 다시 나올 수 있다는 Tractus 문서 추정**(직접 확인은 못 했다고 적음). Developer ID 서명이면 신원이 유지됨 [추정] | Tauri 앱에 붙이는 건 **커뮤니티 플러그인**(`ahonn/tauri-plugin-sparkle-updater`, 2025-12 생성, stars 30, 마지막 push 2026-10-13)이 있으나 이번엔 동작 미확인 | 공식 cask 신청 조건: 신규 패키지는 공개 관심 증명(30 fork/30 watcher/75 star, 본인 제출은 90/90/225), 저장소 생성 30일 이상. 앱 서명·공증 필수 |

출처: [Tauri updater](https://v2.tauri.app/plugin/updater/), [Sparkle 문서](https://sparkle-project.org/documentation/), [Sparkle 샌드박스](https://sparkle-project.org/documentation/sandboxing/), [Homebrew Acceptable Casks](https://docs.brew.sh/Acceptable-Casks), [Homebrew 보안·공급망](https://github.com/Homebrew/brew/blob/main/docs/Homebrew-Security-and-Supply-Chain.md), [Package Acceptance Policy](https://raw.githubusercontent.com/Homebrew/brew/main/docs/Package-Acceptance-Policy.md), [Homebrew 토론 #6482](https://github.com/orgs/Homebrew/discussions/6482), [tauri-plugin-sparkle-updater](https://github.com/ahonn/tauri-plugin-sparkle-updater).

### 3.1 업데이트 때 엔진(venv·모델)을 어떻게 바꾸나 (방식 (b) 기준 설계안)

> 아래는 조사 결과를 모은 **설계 제안**이다. 실행·시험하지 않았다(검증 수준 없음).

- **디렉터리 분리**: 앱(`/Applications/QuietClerk.app`, 서명으로 봉인)과 데이터(`~/Library/Application Support/QuietClerk/`: `engine/<lock해시>/`, `models/`, DB, 로그)를 분리. Tractus도 노트·모델·설정을 앱 밖에 두고 "어떤 방법으로 업데이트해도 데이터는 그대로"라고 명시한다.
- **엔진 = 앱 버전에 묶인 lock**: 앱 안에 `uv.lock`(해시 포함)과 `quietclerk` wheel 또는 소스 트리를 넣고, 시작 때 `engine/CURRENT`가 가리키는 lock 해시와 비교한다. 다르면 새 `engine/<해시>/`에 `uv sync --frozen`(Tractus는 `--only-binary --require-hashes`)을 만들고 **성공했을 때만 심볼릭 링크를 교체**한다. 실패하면 이전 엔진으로 계속 돈다.
- **롤백**: 이전 1개 버전의 엔진 폴더를 보존. DB 마이그레이션이 앞으로만 가면 엔진 롤백이 DB 스키마보다 낮아질 수 없으므로 앱 롤백 정책과 같이 정해야 한다(설계 5.3절 DB 이행과 연결, 미결 6).
- **모델은 앱 업데이트로 건드리지 않는다**. 모델 레지스트리(이름·크기·해시)를 앱 버전이 갖고, 필요한 모델이 바뀌면 모델 화면에서 받게 한다. Tractus의 구현이 참고: 모델별 크기·필수/선택 구분, 프리셋(표준 약 4.6GB, 저사양 약 1.2GB, 전부 약 5.7GB), 쓰지 않는 예전 모델 `prune`.
- **업데이트 중 상주 서비스**: 엔진(launchd 에이전트)을 멈추고 → 앱 교체 → 새 엔진 동기화 → 재시작. Tractus는 녹음·변환 중이면 설치를 잠근다.

## 4. 비슷한 오픈소스 Mac 앱이 실제로 하는 것

저장소를 `git clone --depth 1`로 받아 설정·워크플로·README를 직접 읽음. 릴리스 크기는 `gh api`의 최신 릴리스 에셋(2026-11-11).

| 저장소(확인 커밋 날짜) | 셸 | 파이썬 포함 | 서명·공증 | 업데이트 | 모델 내려받기 UX |
|---|---|---|---|---|---|
| **sjoon21/Tractus** (2026-11-10, Apache-2.0, stars 5) — Tauri 2 + 파이썬 코어 + MLX + Swift 녹음 헬퍼 | Tauri 2(`titleBarStyle` 오버레이, 메뉴 막대 아이콘+팝오버, 창 닫아도 앱 유지) | **예, (a)**: `uv`의 python-build-standalone를 `Contents/Resources/runtime`에 복사, `uv pip install --target`으로 wheel(해시 고정·sdist 거부), 안 쓰는 하위 패키지·tests·`*.pyi` 삭제, 바이트코드 사전 컴파일, wrapper가 `python -I -B`로 실행. 코어·macOS 14.4 이하 Mach-O 점검 | **ad-hoc(`-`)만, 하드닝 안 켬, 공증 안 함**. 코드 주석: 하드닝을 켜면 ad-hoc 라이브러리를 못 불러옴. 사용자에게 "그래도 열기"/`xattr -dr com.apple.quarantine` 안내. 아직 깨끗한 Mac·다운로드 후 Gatekeeper·macOS 14~15는 **직접 확인 못 했다고 문서가 명시** | Tauri updater: `releases/latest/download/latest.json`, `requireSignedVersion: true`, 앱 시작 약 10초 후 확인, 사용자가 누를 때만 설치, 앱 전체 교체(릴리스 `Tractus.app.tar.gz` 143MB, DMG 166MB) | 앱 안 "모델" 화면: 모델별 크기(1.2MB~2.5GB)·필수/선택, 프리셋, `prune`. 모델 제외 번들(수 GB 별도), ffmpeg는 번들 안 함(`brew install ffmpeg` 안내) |
| **silverstein/minutes** (2026-11-10) — Rust+Tauri | Tauri(메뉴 막대 녹음·받아쓰기), CLI 동반 | 아니오(Rust, sherpa-onnx 플러그인 dylib) | **Developer ID 서명+공증**: `cargo tauri build` 뒤 중첩 코드를 **안쪽부터 `codesign --options runtime --timestamp`** 로 다시 서명하고 `.app` 전체 공증(워크플로) | Tauri updater `latest.json`(minisign) + **Homebrew cask `silverstein/tap/minutes`**(자체 tap) | `minutes setup`(CLI)로 Whisper·Parakeet 다운로드, 설치 문서가 모델 포함 여부를 정리. DMG 62MB |
| **Zackriya-Solutions/meetily** (2026-11-02) — Tauri 2 + whisper.cpp/llama sidecar | Tauri 2(+트레이 권한), Windows·macOS 릴리스 | 앱은 아니오(Rust). 저장소에 FastAPI 백엔드가 있으나 설치 경로는 Docker 문서 | 워크플로에 **Developer ID 인증서 가져오기·서명·공증 환경변수**가 있으나 `tauri.conf.json`의 `signingIdentity`는 `-` → CI 입력(`sign-binaries: true`)이 우선 [코드; 실제 릴리스 DMG 서명 상태는 `codesign` 미확인] | Tauri updater(`latest.json`, `createUpdaterArtifacts`), 릴리스 DMG 48MB | 앱 안 모델 관리(`BuiltInModelManager.tsx`, `ModelDownloadProgress.tsx`) |
| **fastrepl/anarlog**(Hyprnote) (2026-11-05) — Tauri 2, Rust+Swift MLX | Tauri 2, 최소 macOS 15 | 아니오. Swift MLX의 `mlx-swift_Cmlx.bundle/default.metallib`을 리소스로 복사 | **서명+공증 후 DMG까지 따로 공증·staple**(`macos_notarize_dmg` 액션, Tauri는 DMG 자체를 공증하지 않는다는 주석). 하드닝 엔타이틀먼트: `device.audio-input`, `allow-jit`, `allow-unsigned-executable-memory` 등 | Tauri updater(`desktop.anarlog.so/update/{target}-{arch}/{current_version}`, 동적 서버), DMG 211MB | 확인 못 함(소스에 로컬 모델 선택 UI 파일은 있음) |
| **thewh1teagle/vibe** (2026-10-30) — Tauri 2, whisper.cpp 사이드카 | Tauri 2(`externalBin: vibe-server`) | 아니오 | **서명·공증 경로 있음**(워크플로가 릴리스 본문에 "Signed and notarized on macOS and Windows" 문구를 넣고 `APPLE_*` 환경변수 사용, 릴리스 DMG 자체는 `codesign` 미확인). 엔타이틀먼트 주석이 정직: `disable-library-validation` 일부러 안 넣음, Metal 컴파일 때문에 `allow-jit`는 "추측(hedge)"으로 넣음 | Tauri updater(GitHub Pages `stable.json`), DMG 38MB | `setup` 화면에 모델 내려받기 진행률 표시(소스 확인) |
| **OpenWhispr/openwhispr** (2026-11-11) — Electron 43 | Electron(+electron-builder) | 아니오(whisper.cpp·sherpa-onnx·llama-server 네이티브 바이너리 `extraResources`) | **Developer ID + `notarize: true`** , 하드닝 켬, `electron-updater` | `electron-updater`(`latest-mac.yml`), 커뮤니티 Homebrew cask, DMG 343MB | 온보딩에서 필수 모델 다운로드 단계(`RequiredModelDownloadStep`) |
| **chidiwilliams/buzz** (2026-11-09) — **PyInstaller+PyQt6** | PyQt6 | **예, (c)**: `Buzz.spec` + PyInstaller, torch 포함(Apple Silicon만) | Makefile에 **서명(`--options runtime`)→ zip 공증 → staple → `create-dmg --notarize`** 절차가 있다. 그런데 README는 "App is not signed… More info → Run anyway"라 적는다(서로 충돌, 최신 릴리스의 서명 상태 **확인 못 함**). 엔타이틀먼트: `allow-jit`, `allow-unsigned-executable-memory`, `disable-library-validation`, `audio-input` | 앱 자체 `update_checker.py`가 `version_info.json`을 확인해 `update_available` 신호를 냄(파일 일부만 읽어 자동 설치 여부는 확인 못 함, 알림 방식으로 보임 [추정]), Homebrew cask는 `brew bump-cask-pr`로 갱신 | 앱 안 모델 로더(`model_loader.py`). 최신 릴리스 mac DMG 469MB(arm64) |
| **RecapAI/Recap** (2026-02-07, MIT) — 순수 Swift | 네이티브 SwiftUI | 아니오(WhisperKit·Ollama) | 릴리스 워크플로에 인증서·`CODE_SIGN_IDENTITY` 서명은 있으나, README는 "지금은 소스 컴파일만, 사전 빌드 릴리스는 나중"이라 적음. GitHub 릴리스 2개 | 확인 못 함(저장소 전체에서 'sparkle' 문자열 grep 결과 없음) | HF 토큰으로 Whisper 모델 받음(README) |

종합(이 8개에서 읽은 것만)
- Tauri가 8개 중 5개(Tractus, Minutes, Meetily, Anarlog, Vibe)다. 이 중 4개는 Developer ID 서명·공증 경로가 있다(Tractus만 ad-hoc).
- **파이썬을 앱에 담은 곳은 Tractus(a), Buzz(c) 둘뿐**이고, MLX+파이썬 조합은 Tractus가 유일하다. (b) 방식(첫 실행 때 환경 생성)을 쓰는 앱은 **이번 8개에서 확인 못 함**.
- 업데이트는 Tauri 앱 전부 Tauri updater + `latest.json`(공개 GitHub Releases·Pages·자체 서버). Sparkle을 쓰는 곳은 **이번 8개에서 확인 못 함**. Electron은 `electron-updater`.
- 모델은 어느 곳도 앱에 넣지 않고 앱 안 화면에서 받는다(Tractus·Meetily·Vibe·OpenWhispr 확인).

## 5. Apple 계정·서명 없는 배포·Mac App Store

### 5.1 Apple Developer Program

| 항목 | 내용 | 출처 |
|---|---|---|
| 비용 | **99 USD/멤버십 연도**(지역에 따라 현지 통화) | [Apple enroll](https://developer.apple.com/programs/enroll/) |
| 개인 | 2단계 인증이 켜진 Apple Account, 거주 지역 성인, **법적 이름**(별명·회사명 쓰면 승인 지연). 법적 이름이 앱의 판매자 이름으로 표시됨. 주소는 사서함 불가 | 같은 쪽 |
| 조직 | 법적 구속력을 가진 사람이 Account Holder, **법인격(DBA·상호 불가), D-U-N-S 번호, 조직 도메인 이메일, 공개 웹사이트** 필요. 번호 발급·검증에 걸리는 시간은 문서에 없음 → **확인 못 함** | 같은 쪽 |
| 면제 | 비영리·교육·정부는 수수료 면제 신청 가능 | 같은 쪽 |
| 공증 | 무료 등록으로는 안 됨: Tauri 문서는 무료 플랜을 "테스트·개발 전용"이라 하고, Electron 문서는 공증에 프로그램 가입(연회비)을 요구. Apple 비교표 페이지의 체크 표시는 텍스트로 안 읽혀서 **Apple 원문으로는 확인 못 함** | [Tauri](https://v2.tauri.app/distribute/sign/macos/), [Electron](https://raw.githubusercontent.com/electron/electron/main/docs/tutorial/code-signing.md) |
| 인증서 | 직접 배포는 **Developer ID Application**(앱·dylib·바이너리·DMG), 설치 패키지는 Developer ID Installer. Apple Distribution·Apple Development·ad-hoc·자체 서명은 공증 거부 | [Apple 문제 해결](https://developer.apple.com/documentation/security/resolving-common-notarization-issues) |
| 유효 기간 | Developer ID 인증서 5년(Speedwave ADR가 Apple 지원 페이지를 인용, **Apple 원문은 이번에 안 읽음**) | ADR-037 |
| CI | 인증서 `.p12`를 base64로 비밀 저장 + 공증은 App Store Connect API 키(Developer 접근 권한) 또는 Apple ID+앱 전용 암호+Team ID | [Tauri 서명](https://v2.tauri.app/distribute/sign/macos/) |
| 공증 소요 | Apple 문서: "보통 한 시간 미만" | [Apple 공증](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) |

**개인 vs 조직**: 개인으로 가입하면 판매자 이름이 법적 이름으로 공개된다. 조직은 D-U-N-S·웹사이트 요건이 있어 시간이 더 걸릴 수 있다(걸리는 시간은 확인 못 함). 어느 쪽이든 앱 이름·번들 ID는 이후 바꾸기 어렵다(TCC·로그인 항목이 신원에 묶임 [추정]). 결정은 사용자 몫(미결 5).

### 5.2 서명 없이 배포할 때 사용자 경험 (Apple 문서 기준)

- Apple 지원 문서가 나열하는 경고는 세 가지다: 인터넷에서 받은 앱을 처음 열 때의 "열겠습니까" 확인, "Apple이 악성 소프트웨어를 확인할 수 없음"(Apple이 검사할 수 없는 앱), "개발자를 확인할 수 없음"(개발자 신원이 없고 Catalina 이후 공증도 안 된 앱). 서명만 있고 공증이 없는 경우와의 대응은 문서가 구분해 적지 않아 **확인 못 함**.
- 해제: 앱을 한 번 열어 본 뒤 **시스템 설정 > 개인정보 보호 및 보안 > "그래도 열기"** → 경고가 다시 뜨고 "열기". 이후 예외로 저장됨. 이 설정은 관리 Mac(MDM)에서는 막힐 수 있음. (Apple 지원 문서, 2026-05-27 게시)
- 앱이 수정·손상으로 판단되면 "손상됨" 메시지, 알려진 악성이면 휴지통 이동.
- Apple Silicon은 모든 코드가 최소 ad-hoc 서명을 요구한다(Tauri 문서). 서명 안 한 앱을 브라우저로 받으면 "손상되어 열 수 없음"이 나올 수 있다(Tauri 문서, Tractus 안내서가 `xattr -dr com.apple.quarantine` 해법을 적음).
- 실사례: Tractus·Buzz README가 같은 경고와 해제 방법을 사용자에게 안내한다.
- 비개발자 대상 설계 2.1의 통과 기준("도움 없이 설치")과 충돌한다. **개발자 프리뷰까지는 ad-hoc도 가능하나 일반 사용자 출시(M4)는 서명·공증이 필요**하다.

### 5.3 Mac App Store 적합성: 맞지 않음

| 요구(App Review Guidelines 2.4.5·2.5.2) | QuietClerk 구조 |
|---|---|
| (i) 적절히 샌드박스. App Sandbox는 MAS 필수(Apple) | 샌드박스는 컨테이너·사용자 선택 파일·명시한 엔타이틀먼트로만 접근. Syncthing 폴더와 Obsidian vault는 사용자 선택(보안 범위 북마크)이 필요 |
| (ii) 자체 완결 단일 번들, 공유 위치에 코드·리소스 설치 불가 | 홈 디렉터리 venv·launchd plist·모델 폴더와 충돌 |
| (iii) 동의 없는 로그인 시 자동 실행·사용자가 종료한 뒤 계속 도는 프로세스 금지 | 상주 엔진(KeepAlive launchd)과 충돌. 동의를 받는 SMAppService라면 가능성은 있으나 "앱 종료 후 계속 도는 서비스"는 별도 동의 필요 |
| (iv) 심사에서 본 것과 다른 기능을 더하는 코드·리소스를 내려받아 설치 금지, 2.5.2 코드 다운로드·실행 금지 | 첫 실행 때 파이썬 환경·모델(모델은 데이터라 다를 수 있으나 판단은 심사자 몫 [추정]) 내려받기와 외부 CLI 실행 |
| (vii) 업데이트는 MAS로만 | Tauri updater·Sparkle 불가 |
| 샌드박스에서 자식으로 띄운 도구 | Apple 문서: 샌드박스 앱이 실행하는 헬퍼는 같은 팀 서명 + `app-sandbox`+`inherit` 엔타이틀먼트만 허용하는 구조(다른 엔타이틀먼트를 넣으면 크래시 가능). 사용자가 따로 설치한 Codex·Claude Code CLI를 이 샌드박스 안에서 어떻게 실행·인증(`~/.codex` 읽기)하는지는 **확인 못 함**, 막힐 가능성이 크다 [추정] |

출처: [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)(2.4.5, 2.5.2), [App Sandbox](https://developer.apple.com/documentation/security/app-sandbox), [샌드박스 구성](https://developer.apple.com/documentation/xcode/configuring-the-macos-app-sandbox), [샌드박스 앱에 CLI 도구 넣기](https://developer.apple.com/documentation/xcode/embedding-a-helper-tool-in-a-sandboxed-app).

### 5.4 권한: 이 제품이 실제로 요구하는 것

| 권한 | 필요 여부 | 근거·방법 |
|---|---|---|
| 마이크 | **현재 흐름은 불필요**(폰 녹음 → Syncthing). Mac 직접 녹음을 나중에 넣을 때만 | 하드닝 시 `com.apple.security.device.audio-input` + `NSMicrophoneUsageDescription`(Tractus·Vibe·Meetily·Anarlog·Buzz가 동일 구성) |
| 시스템 오디오 | 불필요 | Core Audio process tap은 엔타이틀먼트 없이 `NSAudioCaptureUsageDescription`만(Tractus 주석). ScreenCaptureKit 방식은 화면 녹화 권한(Meetily plist) |
| 전체 디스크 접근(FDA) | **요구하지 않는 설계** | 보호 폴더(Documents·Desktop·Downloads, iCloud)에 접근할 때는 "파일 및 폴더" 권한이면 되고, FDA가 있으면 그것이 우선한다(Eclectic Light Co., macOS 26.4 로그). 사용자가 **열기 패널로 고른 폴더는 의도 기반 접근이라 이 규칙 대상이 아니다**(같은 글). 기본 폴더를 홈 아래 비보호 위치로 정하면 프롬프트 자체가 없다 |
| 알림 | 선택 | Tauri notification 플러그인 / `UserNotifications` |
| 로그인 항목 승인 | 필요 | SMAppService는 "사용자 승인 후 시작", `requiresApproval`이면 시스템 설정 안내(Apple). Tauri autostart의 LaunchAgent도 시스템 설정 > 로그인 항목에 나타남 [추정, 표시 이름은 서명 신원에 따라 달라짐: Apple 문서는 앱에 못 묶이면 서명 인증서의 조직명이나 실행 파일명을 표시한다고 적음] |

**launchd 에이전트의 TCC**: 한 저장소 이슈(rjwalters/loom #3980)는 "launchd 작업은 스스로가 responsible process여서 보호 위치를 건드리면 새로 프롬프트가 뜬다. 서명 안 된 바이너리는 재빌드마다 권한이 날아간다"고 적었다. Speedwave ADR는 "리소스 엔타이틀먼트는 responsible process인 앱에서 확인되고, 앱이 띄운 헬퍼의 키는 보지 않는다"고 정정했다. **둘 다 2차 출처**이고 우리 구조(launchd 에이전트 → 서명 런처 → 파이썬 자식)에서의 실제 동작은 **확인 못 함**(미결 3).

## 6. 방식별 종합표 (난이도·사용자 경험·위험·출처)

점수는 이 문서의 근거만으로 매긴 상대 평가(낮음/중간/높음)이며, 정량 지표가 아니다.

| 조합 | 구현 난이도 | 설치·사용자 경험 | 주요 위험 | 핵심 출처 |
|---|---|---|---|---|
| **A. Tauri + (b) 첫 실행 venv + Developer ID** (추천) | 중간. 셸 얇음, 서명 대상 적음(`uv`+셸), 엔진 동기화·진행 UI 직접 구현. SMAppService 연결은 시험 필요 | DMG 드래그 → 첫 실행에 엔진·모델 내려받기(진행 표시). 이후 업데이트는 앱이 알림, 엔진은 필요할 때만 | 첫 실행 네트워크 실패·재개, PyPI/wheel 변동(해시 고정으로 완화), 앱 서명 범위 밖 코드, MAS 불가 | 2.2절 [실측], 2.4절, Tauri 문서, Tractus 스크립트 |
| **B. Tauri + (a) 번들 파이썬 + Developer ID** | 높음. 241개 Mach-O 서명 스크립트·`allow-unsigned-executable-memory`·wheel 최저 macOS 고정·사전 컴파일 | 오프라인 설치 후 즉시 동작. 설치 용량·다운로드 큼, 업데이트도 큼 | 하드닝 예외가 앱 전체에 적용, 공증 실패 시 원인 추적 어려움(미실행), 보안 패치마다 앱 재배포 | Tractus(ad-hoc 사례), Speedwave ADR, 2.2절 |
| **C. 네이티브 SwiftUI + Sparkle + (b)** (대안) | 중간~높음. Swift 코드 신규, SMAppService·Sparkle은 표준 경로로 쉬움 | Sparkle 표준 업데이트 창·로그인 항목 승인 화면이 네이티브 | Windows 셸 재작성, Swift 유지 인력, 이번 8개 중 이 조합 사례 없음(Recap은 릴리스 없음) | Apple·Sparkle 문서 |
| **D. Electron + (b)** | 중간. 셸 쉬움, 앱 큼 | 용량·메모리 큼. 업데이트·로그인 항목 지원 좋음(`electron-updater`, SMAppService 유형) | 용량, 파이썬 엔진 사례 없음, 보안 면적 | OpenWhispr, Electron 문서 |
| **E. 서명 없이(ad-hoc) 배포** | 낮음 | "확인할 수 없음" 경고, 해제 절차 필요, 일부 환경 막힘, Homebrew 공식 cask 불가 | 비개발자 이탈, 업데이트 때마다 권한 재요청 가능성(Tractus 추정) | Apple 지원 문서, Homebrew 문서 |
| **F. Mac App Store** | 매우 높음(구조 변경) | 최고(심사 통과 시) | 외부 CLI·launchd·내려받기와 충돌, 샌드박스 | App Review Guidelines 2.4.5 |

## 7. QuietClerk에 맞는 조합

### 추천: Tauri v2 셸 + (b) 첫 실행 venv + Developer ID 서명·공증 + 앱은 Tauri updater, 엔진은 lock 해시로 동기화

근거
1. **실측으로 하드닝 비용이 드러났다**: 이 엔진은 `mlx-whisper → numba`라서 번들(a)이면 앱 전체에 `allow-unsigned-executable-memory`가 영구히 들어간다(2.2절). (b)는 파이썬이 번들 밖·비하드닝이라 앱 서명의 엔타이틀먼트는 마이크(나중 기능)·네트워크 정도로 최소화된다.
2. **지금 동작하는 설치 경로와 거리가 가장 짧다**: `deploy/install.sh`(uv venv)·`quietclerk serve`·로컬 웹 화면을 그대로 두고 셸만 얹는다. 설계 2.2절의 방향과도 일치한다.
3. **서명 범위가 작다**: Tauri 번들러가 서명하는 것은 셸과 `externalBin`(`uv`)뿐이고, Resources 안 Mach-O 미서명 문제를 피한다.
4. **업데이트가 작고 독립적이다**: 앱은 수십 MB, 엔진은 lock이 바뀔 때만. 번들은 앱 업데이트마다 엔진 전체(torch 제외해도 700MB 급)를 다시 준다.
5. **확장성**: 셸이 Tauri라 Windows 셸을 이후에 같은 코드베이스로 확장할 수 있다. 엔진 쪽 Windows 지원(M5 N1·N2)은 별개(MLX는 Apple Silicon 전용).

이 조합이 **전제하는 것**(시험 전에는 가정)
- Developer ID 인증서 취득과 공증 통과(미실행).
- 엔진 상주를 SMAppService 에이전트로 만들기: Tauri에 이 API가 없어 작은 네이티브 연결(Swift 헬퍼 또는 Rust objc 호출)이 필요, 그리고 에이전트 `Program`은 서명된 런처여야 함(미결 1·3).
- 첫 실행 다운로드의 재개·검증·디스크 점검 UX.
- 저장소 공개(GitHub Releases `latest.json` 접근).

**(b)가 실패할 때의 후퇴선**: 첫 실행 네트워크 문제가 일반 사용자 시험(M4 T5)에서 반복되면 (a)로 전환하되, 그때 `allow-unsigned-executable-memory`를 승인하거나 `mlx-whisper`를 `numba` 없이 쓰는 경로(예: `mlx_audio` STT 경로로 일원화)를 먼저 검토한다 [추정].

### 대안: 네이티브 SwiftUI 메뉴 막대(MenuBarExtra + WKWebView) + SMAppService + Sparkle, 엔진은 같은 (b)

채택 조건: ① Windows 셸을 당분간(1~2년) 만들지 않기로 확정, ② Tauri에서 SMAppService 연결이 시험에서 번거롭다고 판명, ③ Swift를 유지할 인력이 있음. 장점: 로그인 항목·업데이트 UI·권한 프롬프트가 모두 시스템 표준이고 Sparkle 델타·피드 서명이 공식 지원된다. 단점: Windows 재작성, 사례 부족(이번 8개에서 같은 조합의 출하 사례 없음).

**채택하지 않을 것**: Electron(용량·파이썬 엔진 사례 부재), Mac App Store(5.3절), 서명 없는 배포(5.2절)를 일반 사용자 출시에 쓰는 것.

## 8. 패키징 경로로 들어오는 입력의 처리 방침과 악의·비정상 입력 시험 (제안)

> 제품 게이트가 요구한 "입력 유형별 처리 방침 + 비정상·악의 입력 시험"을 패키징 범위에 맞춰 정리한 **제안**이다. 아직 어떤 것도 실행하지 않았다(검증 수준: 없음).

| 입력 | 방침 | 시험 (비정상·악의 포함) |
|---|---|---|
| 업데이트 피드(`latest.json`/appcast) | HTTPS만, 서명된 아티팩트만 설치. 버전 비교는 앱이 직접(서버의 하향 지시 무시, 롤백은 별도 경로). 피드 전체 검증 후 버전 확인(Tauri는 파일 전체를 먼저 검증) | 서명 불일치 아티팩트, 낮은 버전 피드, 잘린 JSON, 서버가 다른 URL로 리다이렉트, TLS 해제 시 거부 |
| 업데이트 아카이브(`.app.tar.gz`) | 서명 검증을 통과한 것만 설치(Tauri 문서: 설치 전에 공개키로 아티팩트 검증, 끌 수 없음). 설치 중 녹음·변환 중이면 잠금 | 서명키가 다른 아티팩트, 0바이트·부분 다운로드 후 재시도, 디스크 부족 |
| 엔진 lock·wheel | `uv.lock` 해시 일치만 설치(`--require-hashes`, `--only-binary`). 앱이 가진 lock 외 패키지 설치 금지. 설치 실패 시 이전 엔진 유지 | 해시가 다른 wheel, PyPI에 같은 버전 재업로드, 네트워크 중단, macOS 최저 버전보다 새로운 wheel(minos 점검) |
| 모델 파일 | 레지스트리의 크기·해시와 일치할 때만 사용. 부분 파일은 `.part`로 두고 완료 후 원자적 이름 변경 | 잘린 모델, 해시 불일치, 디스크 가득, HF 다운로드 정지(`HF_HUB_DISABLE_XET=1` 문제), 모델 폴더가 읽기 전용 |
| 사용자가 고른 폴더 경로(inbox·vault) | 열기 패널로 받은 경로만. 홈 밖·시스템 폴더·심볼릭 링크 탈출·동기화 충돌 경로는 경고. inbox는 읽기만(설계 6절 방침과 동일) | 존재하지 않는 경로, 권한 거부(TCC 거부 후 상태), 네트워크 볼륨, 경로 안의 특수 문자·NFD 한글 |
| 로컬 화면 주소(`127.0.0.1:포트`) | 셸은 고정 오리진만 로드, 외부 URL 이동 차단, 원격 URL에 Tauri 권한(capability) 미부여, 일회 토큰 로그인 | 포트 충돌(다른 프로세스가 점유), 토큰 재사용·만료, 다른 오리진 이동 시도, 앱 종료 후 엔진만 생존할 때 화면 재연결 |
| 외부 CLI 경로(Codex·Claude 등) | 앱이 찾는 PATH를 고정하고(현재 plist의 PATH 고정과 동일), 못 찾으면 안내. 앱 번들 PATH ≠ 사용자 셸 PATH임을 반영 | 로그인 셸에서만 보이는 PATH, 인증 만료, CLI가 TCC 프롬프트를 일으키는 경우 |

## 9. 미결 항목 (담당·확인 시점은 제안이며 Main 확인 필요)

| # | 미결 | 왜 중요한가 | 제안 담당 | 제안 확인 시점 |
|---|---|---|---|---|
| 1 | Tauri 앱에서 SMAppService 에이전트(번들 안 plist, `BundleProgram`=서명된 런처) 등록이 되는지 | 엔진 상주·로그인 항목 UX를 좌우 | A1 구현 담당 | A1 착수 첫 스파이크(Developer ID 확보 전에도 Apple Development로 가능) |
| 2 | Developer ID 서명·공증으로 셸+`uv`(방식 b) 및 번들(a) 후퇴선이 실제로 통과하는지 | 이 문서는 공증을 실행하지 못함 | 사용자(계정 발급) → A2 담당 | 계정 승인 직후, 번들 첫 빌드 전 |
| 3 | launchd 에이전트가 띄운 파이썬 자식의 TCC 주체와, 열기 패널로 고른 폴더가 자식에게도 통하는지 | 폴더 권한 프롬프트·FDA 요구 여부 | A1 구현 담당 | #1과 같은 스파이크 |
| 4 | 깨끗한 macOS 14.x·15.x 계정에서 (b) 첫 실행(엔진·모델 다운로드) | MLX 최저 macOS 14.0, wheel `minos` 문제(Tractus 사례) | T5 시험 담당 | M4 T5 전 |
| 5 | 개인 vs 조직 Apple 계정 | 판매자 이름 노출, 요건·소요 시간 | 사용자 | 계정 신청 전 |
| 6 | 모델 전사까지 포함한 하드닝 시험, torch 제거 시 전사 품질·동작, 엔진 롤백과 DB 스키마 정책 | 이번 [실측]은 합성 입력이고 모델 미실행 | 엔진 담당 | (b)의 후퇴선을 검토하기 전, 또는 M2 |
| 7 | 저장소 공개 시점(현재 private) | updater 엔드포인트·Homebrew 신청 | 사용자 | 첫 릴리스 전 |

## 부록 A. 출처 목록(확인일 2026-11-11)

- Tauri: [sidecar](https://v2.tauri.app/develop/sidecar/) · [updater](https://v2.tauri.app/plugin/updater/) · [autostart](https://v2.tauri.app/plugin/autostart/) · [system tray](https://v2.tauri.app/learn/system-tray/) · [distribute](https://v2.tauri.app/distribute/) · [macOS 서명](https://v2.tauri.app/distribute/sign/macos/) · [Windows 서명](https://v2.tauri.app/distribute/sign/windows/) · [capabilities](https://v2.tauri.app/security/capabilities/) · [bundler 소스](https://raw.githubusercontent.com/tauri-apps/tauri/dev/crates/tauri-bundler/src/bundle/macos/app.rs) · [autostart 소스](https://raw.githubusercontent.com/tauri-apps/plugins-workspace/v2/plugins/autostart/src/lib.rs) · [#11992](https://github.com/tauri-apps/tauri/issues/11992)
- Apple: [SMAppService](https://developer.apple.com/documentation/servicemanagement/smappservice) · [Status](https://developer.apple.com/documentation/servicemanagement/smappservice/status-swift.enum) · [헬퍼 갱신](https://developer.apple.com/documentation/servicemanagement/updating-helper-executables-from-earlier-versions-of-macos) · [공증](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) · [공증 문제 해결](https://developer.apple.com/documentation/security/resolving-common-notarization-issues) · [Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime) · [allow-jit](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.allow-jit) · [disable-library-validation](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.disable-library-validation) · [App Sandbox](https://developer.apple.com/documentation/security/app-sandbox) · [샌드박스 구성](https://developer.apple.com/documentation/xcode/configuring-the-macos-app-sandbox) · [샌드박스 CLI 도구](https://developer.apple.com/documentation/xcode/embedding-a-helper-tool-in-a-sandboxed-app) · [MenuBarExtra](https://developer.apple.com/documentation/swiftui/menubarextra) · [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) · [프로그램 가입](https://developer.apple.com/programs/enroll/) · [계정 개요](https://developer.apple.com/help/account/basics/about-your-developer-account) · [앱 안전하게 열기](https://support.apple.com/en-us/102445) · [파일 및 폴더 권한](https://support.apple.com/guide/mac-help/control-access-to-files-and-folders-on-mac-mchld5a35146/mac)
- Sparkle: [문서](https://sparkle-project.org/documentation/) · [샌드박스](https://sparkle-project.org/documentation/sandboxing/) · Tauri 플러그인(커뮤니티) [ahonn/tauri-plugin-sparkle-updater](https://github.com/ahonn/tauri-plugin-sparkle-updater)
- Homebrew: [Acceptable Casks](https://docs.brew.sh/Acceptable-Casks) · [보안·공급망](https://github.com/Homebrew/brew/blob/main/docs/Homebrew-Security-and-Supply-Chain.md) · [Package Acceptance Policy](https://raw.githubusercontent.com/Homebrew/brew/main/docs/Package-Acceptance-Policy.md) · [토론 #6482](https://github.com/orgs/Homebrew/discussions/6482)
- Electron: [app API](https://www.electronjs.org/docs/latest/api/app) · [autoUpdater](https://raw.githubusercontent.com/electron/electron/main/docs/api/auto-updater.md) · [code signing](https://raw.githubusercontent.com/electron/electron/main/docs/tutorial/code-signing.md)
- MLX·파이썬: [MLX 설치](https://ml-explore.github.io/mlx/build/html/install.html) · [python-build-standalone](https://gregoryszorc.com/docs/python-build-standalone/main/) · [mlx-vlm #201](https://github.com/Blaizzy/mlx-vlm/issues/201)
- 2차 출처: [Eclectic Light: quarantine](https://eclecticlight.co/2025/12/08/who-decides-to-quarantine-files) · [Eclectic Light: Files & Folders vs FDA](https://eclecticlight.co/2026/04/08/privacy-files-folders-or-full-disk-access) · [rjwalters/loom #3980](https://github.com/rjwalters/loom/issues/3980) · [Speedwave ADR-037](https://github.com/speednet-software/speedwave/blob/dev/docs/adr/ADR-037-code-signing-and-bundled-binary-signing.md)
- 읽은 저장소(전부 `git clone --depth 1`, 기준 커밋 날짜 2026-11-11 확인): [sjoon21/Tractus](https://github.com/sjoon21/Tractus)(2026-11-10) · [silverstein/minutes](https://github.com/silverstein/minutes)(2026-11-10) · [Zackriya-Solutions/meetily](https://github.com/Zackriya-Solutions/meetily)(2026-11-02) · [fastrepl/anarlog](https://github.com/fastrepl/anarlog)(2026-11-05) · [thewh1teagle/vibe](https://github.com/thewh1teagle/vibe)(2026-10-30) · [OpenWhispr/openwhispr](https://github.com/OpenWhispr/openwhispr)(2026-11-11) · [chidiwilliams/buzz](https://github.com/chidiwilliams/buzz)(2026-11-09) · [RecapAI/Recap](https://github.com/RecapAI/Recap)(2026-02-07)
- 이 저장소: `docs/product-design-v2.md`(2.2·4·M4절), `pyproject.toml`, `deploy/launchd.plist.in`, `quietclerk/backends/mlx.py`, `quietclerk/providers/cli.py`

## 부록 B. 재현 방법(이 Mac, 임시 파일은 조사 후 삭제)

- 크기: `uv venv /tmp/qcvenv --python 3.12` 후 `uv pip install --python /tmp/qcvenv/bin/python mlx-audio==0.6.4 mlx-whisper==0.4.3 soundfile numpy soynlp PyYAML starlette uvicorn jinja2` → `du -sh`, `find … -name '*.so' -o -name '*.dylib'`, `tar -cf - lib | gzip -3 | wc -c`.
- 하드닝: 파이썬 베이스(`~/.local/share/uv/python/cpython-3.12.9-macos-aarch64-none`)와 site-packages를 `/tmp`로 복사 → `codesign --force --sign <Apple Development> --options runtime [--entitlements <plist>]`를 `.so`·`.dylib` 전부와 `bin/python3.12`에 적용 → `PYTHONPATH=<복사본> <복사본 python> t_*.py`(시험: `mlx.core` GPU 행렬곱·`mx.compile`, `numba.njit`, `import mlx_whisper …`, `ctypes mmap MAP_JIT`). 종료 코드 137은 `import numba`에서 확인.
- quarantine: `xattr -lr`로 venv 파일의 `com.apple.quarantine` 개수 확인(0).
