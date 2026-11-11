# 앱 셸 ↔ 엔진 계약

D0/S1/A1, 앱 0.0.3. 엔진의 처리·저장 규칙은 `contracts-v2.md`를 그대로 따른다. S1 서비스 인터페이스는 6절, 첫 실행 설치·메뉴·앱 소유 엔진 맞추기는 7절이다.

## 1. 식별자·위치·역할

- 제품명: QuietClerk. 앱 식별자: `io.github.minigold92.quietclerk`(변경하지 않는다).
- 대상: Apple Silicon(`aarch64-apple-darwin`), macOS 14.0 이상. 앱은 `/Applications/QuietClerk.app`에 놓는 DMG 방식이다.
- 앱은 메뉴 막대 상주 앱이다(`LSUIElement`, Accessory 활성화 정책). Dock에 중복 아이콘을 두지 않는다. 창을 닫아도 앱은 남고 ‘종료 / Quit’만 앱을 끝낸다. 엔진의 생명주기는 바꾸지 않는다.
- 엔진 접속 파일: `~/Library/Application Support/QuietClerk/bootstrap.json`. 창 열기 전 앱은 서비스 소유권과 인증 상태를 확인한다. 설치·등록은 Python 설치기 소유이며 앱 종료는 서비스를 내리지 않는다(6·7절).
- 현재 엔진 데이터 위치는 엔진 설정·설치 계약을 따른다. 설계의 미래 `engine/<잠금 해시>/` 배치는 아직 구현하지 않았다.

## 2. bootstrap 읽기

근거: `quietclerk/bootstrap_file.py`, `quietclerk/cli.py`의 `open`.

1. 앱 시작과 메뉴의 열기마다 실제 사용자 HOME의 고정 경로를 새로 읽는다. 시험용 경로 환경변수는 없다.
2. `O_NOFOLLOW`로 열어 마지막 경로의 심볼릭 링크를 거부한다. 열린 파일 기술자의 메타데이터를 확인한다(경로 검사 뒤 다시 여는 방식이 아님). 비정규 파일에서 열기가 멈추지 않도록 `O_NONBLOCK`도 사용한다.
3. 소유자가 `getuid()`와 같고, 일반 파일이며, 특수 비트를 포함한 권한이 정확히 `0600`이어야 한다. 부모 디렉터리의 심볼릭 링크는 별도로 거부하지 않는다(엔진과 같음).
4. JSON의 `expires`가 현재 Unix 시각보다 커야 하고, `token`은 문자열, `port`는 1–65535의 정수여야 한다. 빈 문자열 token은 Python reader처럼 읽기는 허용한다(유효한 세션인지 판단하는 쪽은 엔진).
5. 없거나 검사·파싱·인증에 실패하면 묶인 `ui/index.html`에 상태·실패 이유·다시 시도를 표시한다. 미설치이면 크기·백그라운드 실행 동의와 설치 버튼을 보여 준다.

## 3. 창·신뢰 경계

- 여는 주소는 CLI와 같은 `http://127.0.0.1:{port}/#bootstrap={token}`이다. 토큰을 로그나 명령행에 쓰지 않는다.
- 엔진 창은 **http + 127.0.0.1 + 읽은 포트**의 오리진만 탐색할 수 있다. localhost·다른 포트·https·외부 사이트·사용자정보 포함 URL을 거부한다. 새 창도 거부한다.
- 열 때 창을 다시 만들어 토큰과 이동 제한을 함께 새로 적용한다. 엔진이 제공하는 화면·인증 흐름은 변경하지 않는다.
- 번들 안내 창은 묶인 안내 문서 밖으로 이동할 수 없다. 원격 엔진 창과 분리하여 만든다.
- Tauri capability 목록은 비어 있고 원격 권한을 추가하지 않는다. JS 명령은 `installation_status`/`install_engine` 두 개뿐이며, Rust에서도 호출 창의 실제 URL·label을 확인해 번들 페이지 외 출처를 거부한다. 업데이트·대화상자는 Rust에서만 호출한다.
- 메뉴·대화상자는 macOS 선호 언어가 `ko`면 한국어, 나머지는 영어다. 번들 화면도 한국어·영어를 함께 관리하고 선호 언어로 표시한다.

## 4. 업데이트·릴리스

- 엔드포인트: `https://github.com/minigold92/rec2vault/releases/latest/download/latest.json`.
- `tauri-plugin-updater`가 앱 시작 시 한 번, 메뉴 선택 때 확인한다. 동시에 두 확인을 하지 않는다. 새 버전은 시스템 확인 대화상자 뒤 내려받기·서명 검증·설치·재시작한다. 자동 확인의 최신/실패는 조용히 기록하고 수동 확인만 결과를 표시한다. 앱 교체 자체는 엔진을 중지하지 않으며, 재시작 뒤 앱 소유 엔진이 다르면 7절의 작업 대기·rollback update를 수행한다.
- 현재 채널은 latest 하나다. `-`가 있는 태그는 GitHub prerelease로 올리며 latest 자동 조회 대상이 아니다. 설계 v3 8장의 prerelease → 운영 확인 → 같은 빌드 정식 승격 절차와 베타 채널 선택은 이후 과제다.
- 앱 버전은 Cargo·package.json·tauri.conf.json·CHANGELOG에서 맞춘다. 초기 공개는 `0.0.x`, 태그는 `v0.0.x`; prerelease는 `v0.0.x-beta.N`처럼 쓴다. 앱 버전도 해당 prerelease와 맞춰야 한다.
- CI는 태그 버전의 CHANGELOG 한국어·영어 절을 Release 본문으로 쓴다. DMG와 `.app.tar.gz`, `.sig`, `latest.json`을 같은 Release에 올린다.
- macOS 코드 서명은 지금 ad-hoc(`-`), Developer ID·공증은 P1이다. 업데이트 아카이브는 별도 Tauri 공개키(설정 파일)로 검증한다. 개인키·비밀번호는 GitHub secrets `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`만 사용하며 저장소에 넣지 않는다.
- 빌드 CI는 업데이트 아티팩트 생성을 끄므로 업데이트 개인키가 필요 없다. 공개 저장소 전환 전에는 인증 없는 앱 조회가 실패할 수 있다. 실제 배포·업데이트 경로 검수는 Release 게시 뒤 별도 수행한다.

## 5. 유지보수 한도·아직 없는 약속

- Rust 제품 코드 1,500줄 이하(시험 제외), Swift 300줄 이하. S1 선택은 기존 Python launchd 설치기이므로 Swift·네이티브 서비스 헬퍼·앱 엔진 모드는 없다. 엔진 로직을 셸로 옮기지 않는다.
- 순수 함수 시험: 소유자·권한·일반 파일 검사, 만료·형식·포트, 심볼릭 링크 거부, 주소·오리진 경계, 언어 선택, 자동·수동 업데이트 확인 × 새 버전·최신 버전·확인 실패의 여섯 표시 판단. 실사용 디렉터리를 건드리지 않는다.
- 엔진 최소 버전 확인은 아직 없다. bootstrap에 버전 협상을 추가하고 최소 버전을 고정하는 일은 이후 과제다.
- 엔진 첫 설치·모델 내려받기·상태 메뉴는 7절 A1에 구현한다. S1 함수 자체는 설치된 엔진만 등록·해제하며, 미설치 엔진을 암묵적으로 만들지 않는다.

## 6. S1 로그인 서비스 (2026-11-11)

### 6.1 선택·불변식

- **0.0.x ad-hoc은 기존 launchd plist + venv Python 직접 실행(B 변형)**을 쓴다. label은 앱·CLI 모두 `local.quietclerk.serve`, plist는 `~/Library/LaunchAgents/local.quietclerk.serve.plist`. `ProgramArguments[0]`은 설치기가 만든 venv의 `bin/python`이다. 앱 실행 파일·앱 경로·앱 cdhash에 의존하지 않는다.
- `RunAtLoad` + `KeepAlive`, 같은 `quietclerk serve`·설정·데이터·사용자 고정 `serve.lock`을 재사용한다. 창 닫기·앱 종료는 서비스에 아무 명령도 보내지 않는다. 앱 번들 업데이트·이동에도 엔진을 재등록하거나 재시작하지 않는다. 따라서 처리 중 앱 업데이트로 엔진이 끊기는 A의 재등록 문제도 없다.
- 앱 설치용 plist에는 `AssociatedBundleIdentifiers = ["io.github.minigold92.quietclerk"]`를 넣되, **ad-hoc에서는 Team ID가 없어 BTM이 무시하는 것을 실측했다**. QuietClerk 이름으로 표시된다는 약속이나 `SMAppService.requiresApproval` 상태를 제공하지 않는다. System Settings에서 사용자가 끈 백그라운드 항목의 재승인은 사람의 일이다.
- Rust는 plist를 쓰거나 `bootstrap`/`bootout`을 하지 않는다. Python 설치기 하나가 잠금·등록·해제·실패 복구·상태 인증을 소유한다. Rust가 직접 하는 launchctl은 설치 기록이 없을 때의 읽기 전용 `print`뿐이다.

### 6.2 A1이 쓰는 함수·명령·설치 기록

- Rust 공개 함수(`quietclerk_app::login_service`):
  `status(home: &Path)`, `register(home: &Path)`, `unregister(home: &Path)` →
  `Result<ServiceStatus, String>`. 상태는 `{manager: Option<String>, registered: bool, login_enabled: bool}`.
  `manager`는 `"app"`, `"cli"`, 미설치 `None`이다. UI 스레드 밖에서 부른다.
- 앱 첫 설치는 기존 명령에 **`install --app-install`**을 더한다(Python API: `install.run(app_install=True, ...)`). `--settings`, `--support`, `--root`, `--source` 의미·환경 생성·모델 검사·rollback은 기존과 같다. S1 스파이크는 모델을 설치하지 않고 HTTP 의존성만 갖춘 실제 엔진으로 생명주기만 시험했다.
- 이후 Rust는 설치된 Python으로 `-m quietclerk.cli --support <support> login-service status|register|unregister`를 인자 배열로 실행하고 stdout JSON을 읽는다. 토큰은 인자·결과에 없다. stderr 실패 이유를 반환한다. 개발자용 숨은 앱 인자는 없다. `examples/login_service_probe.rs`는 앱에 링크하지 않는 명시적 실측 진입점이다.
- 설치 기록은 `<support>/engine-installation.json`, 소유자=현재 사용자·일반 파일·`0600`·최종 심볼릭 링크 거부다. schema 1의 필수 필드:

  ```json
  {"schema":1,"manager":"app","label":"local.quietclerk.serve",
   "python":"/absolute/root/.venvs/id/bin/python","root":"/absolute/root",
   "settings":"/absolute/root/settings.toml","support":"/absolute/support",
   "plist":"/absolute/home/Library/LaunchAgents/local.quietclerk.serve.plist",
   "plist_sha256":"sha256-of-plist"}
  ```

  경로는 모두 절대 경로다. 앱 번들 경로·버전·헬퍼·엔진 모드 인자는 **없다**. `<support>/service.plist`는 재등록용 원본이다. 설치/엔진 update 트랜잭션이 이 두 파일도 함께 갱신하고 실패 시 정확한 바이트로 되돌린다. 설정·데이터의 별도 원본이 아니다.
- `register`: 소유권 확인 → `upgrade.lock` → 실행 잠금으로 수동 serve와 충돌 거부 → 원본 plist 복원 → bootstrap/start → **신선한 bootstrap으로 인증 `/api/status`** 확인. 실패하면 새 등록을 내리고 이전 plist 존재/내용을 복구한다.
- `unregister`: 같은 유지보수 잠금 → bootout → `serve.lock`·`tick.lock` 회수 확인 → LaunchAgents plist 삭제. 앱 소유 기록·재등록 원본·사용자 데이터는 보존한다. 엔진 update는 로그인 항목이 켜진 상태에서 기존 계약대로 수행한다.

### 6.3 CLI 공존

1. 앱 소유 기록이 없는데 기존 plist 또는 launchd label이 있으면 `"cli"`다. 앱은 register/unregister 요청에서도 **읽기만 하고 그대로 재사용**한다. 기록도 없고 둘 다 없으면 미설치다.
2. 앱 기록이 있어도 실제 plist가 저장 원본과 달라졌거나, plist 없이 다른 등록이 남았으면 CLI/사용자 소유가 우선한다. 조용히 덮어쓰거나 두 번째 label을 만들지 않는다.
3. CLI 설치에는 `--app-install`을 주지 않는다. 기존 서비스 명령·업그레이드·이전 venv 보존·doctor 경로를 바꾸지 않는다. 앱 소유 설치의 engine update만 기록·재등록 원본을 같은 트랜잭션에 포함한다.

### 6.4 후보별 실측

이 Mac의 실제 로그인 세션·실제 launchd·ad-hoc 시험 앱. 화면 클릭·키 입력, 로그아웃·재부팅, 운영 장비 접속은 하지 않았다. A의 Swift 스파이크와 Rust/objc2 스파이크는 제품에서 제거했다.

| 측정 | A: SMAppService.agent | B: 앱 실행 파일 런처 | **선택 B 변형: venv Python 직접** |
|---|---|---|---|
| 등록·승인 | 최초 `status=Enabled(1)`, 승인 조작 없이 성공. 이후 동일 식별자 재설치에서 등록 API 성공인데 spawn 실패도 발생 | 실제 bootstrap 성공, BTM `enabled, allowed` | Rust 함수→Python 설치기→실제 bootstrap·인증 성공. SM 상태 API는 사용 안 함 |
| 이름·BTM | 시스템 로그 advisory: `QuietClerk-S1Probe`. launchd에 parent bundle·BTM UUID·`LWCR.reqs.cdhash` 존재 | BTM `name=QuietClerk-S1Probe`; **Team ID 없음, AssociatedBundleIdentifiers 무시** 오류 로그 | BTM `appURL=(null)`, `legacy agent`, Python 경로. 동일 label의 앞선 A 기록 때문에 이 세션 이름은 `quietclerk-app`으로 남음. 깨끗한 계정의 표시 이름은 미확인 |
| bootstrap·인증·앱 종료 | 실제 bootstrap·인증 성공, 등록 앱 프로세스 종료 뒤 엔진 유지 | 실제 bootstrap·인증 성공, 앱 프로세스 없이 유지 | PID 7638 인증 성공; 시험 앱 시작·종료 후 같은 엔진 PID 유지 |
| SIGKILL·KeepAlive | 81440→84182, 인증 성공 | 85438→85629, 인증 성공 | 7638→7715, 인증 성공 |
| 같은 경로 다른 빌드 | 단순 덮어쓰기 뒤 새 기동 실패. Swift 버전 증가+명시 재등록 1회는 성공했지만 Rust 재등록은 API 성공 뒤 **Launch Constraint Violation / Constraint not matched**로 실패. 안정 경로로 채택 못 함 | 85629→85813, 인증 성공 | 덮어쓴 뒤 같은 엔진 PID 유지; SIGKILL 뒤 7715→7932 인증 성공. 재등록 불필요 |
| 다른 폴더로 이동 | BTM 부모 URL 갱신은 관측. 업데이트 실패와 겹친 엔진 재기동은 실패하여 독립 이동 성공은 미확인 | 원래 절대 앱 경로를 찾아 spawn 실패 | 이동 후 SIGKILL 7932→8132, 인증 성공 |
| CLI 공존 | 폐기 후보의 별도 native 공존 실행은 미확인. 선택 구현의 공통 label 선감지는 아래 실제 확인 | 별도 후보 공존 실행은 미확인 | 실제 CLI PID 8162가 status/register/unregister 모두 동일하게 유지, `"cli"` 반환, 두 번째 서비스 없음 |
| 해제·복구 | native status 0, launchd service 없음 | bootout 뒤 service·plist 없음 | Rust unregister→Python bootout·잠금 회수→service·plist 없음. 재등록 원본/데이터는 정상적으로 보존 후 시험 정리 |

**결정 근거:** B 원안은 앱 이동에 깨지고, A는 ad-hoc 새 cdhash에서 실행 제약이 불안정하다. 앱을 런처로 삼지 않으면 기존 검증된 Python 설치·update·rollback을 그대로 재사용하면서 앱 업데이트·이동을 엔진과 분리할 수 있다. 이름 표시의 한계는 베타의 명시적 제한이다.

- 재현: `scripts/probe_login_service.py --bundle <signed.app> --python <installed-venv/bin/python> --rust-probe <built-example> --replacement <different-Rust-build>`; 실행은 사용자 엔진 경로가 비어 있을 때만 허용한다. 실제 모델·녹음 처리는 이 실측 범위가 아니다.
- 정리: 시험 앱은 `~/Applications`에만 만들고 `lsregister -u` 후 삭제했다. 기본 root는 만들지 않았고, 기본 support·LaunchAgents plist·서비스 등록은 시험 뒤 없게 복구했다. `/Applications/QuietClerk.app`은 건드리지 않았다. BTM의 비활성 이력/label enable override는 macOS DB에 남을 수 있다. 전체 로그인 항목을 지우는 `sfltool resetbtm`은 하지 않는다. 단일 BTM 이력 삭제용 공개 명령은 확인하지 못했으며, 사용자는 시스템 설정 > 일반 > 로그인 항목에서 시험 항목이 보이면 끄고 확인할 수 있다(실행 파일·서비스는 이미 없음).
- **로그인 자동 시작은 launchd RunAtLoad/KeepAlive와 BTM 기록으로만 확인했다.** 실제 재로그인·재부팅은 미확인. A1 설치 후 다음 재부팅 때 앱을 열기 전에 `launchctl print gui/$(id -u)/local.quietclerk.serve`의 `state = running`과 `quietclerk status`를 확인한다.
- **P1 재평가 조건:** Developer ID로 서명한 동일 bundle ID의 두 버전으로 A 등록→인증→앱 종료→kill→번들 교체→자동 재등록→이동→CLI 공존→해제를 다시 실측한다. 처리 중이면 인증 상태의 `current_job`이 없어질 때까지 기다리고, 실패 이유를 UI에 표시·다음 시작 재시도하는 설계를 그때 함께 구현한다. ad-hoc의 `LWCR.cdhash` 결과를 Developer ID 동작으로 일반화하지 않는다. API 근거: [SMAppService](https://developer.apple.com/documentation/servicemanagement/smappservice), [objc2-service-management 설명](https://docs.rs/objc2-service-management/latest/objc2_service_management/struct.SMAppService.html).

## 7. A1 앱 소유 설치·첫 실행 (0.0.3, 0.0.4 수정 예정)

### 불변식·실패 경계

- CLI 소유 엔진은 설치·등록·업데이트하지 않는다. `login_service::status(home)`의 `cli` 판단을 우선하고, 인증된 상태를 확인한 뒤 기존 엔진 화면만 연다.
- 앱 리소스는 빌드된 wheel, macOS arm64/Python 3.12용 `engine-requirements.txt`(모든 버전·SHA-256 고정), manifest, LGPL 전문과 빌드 입력이다. wheel·목록 해시를 실행 전에 확인한다. 준비 스크립트 `scripts/prepare_app.py` 하나를 로컬 Tauri와 두 macOS CI가 같이 쓴다.
- `uv` 0.13.1은 공식 배포 tar SHA-256을 검사하고 `externalBin`에 둔다. Resources 안 Mach-O는 Tauri 서명 대상이 아니므로 사용하지 않는다. FFmpeg 7.1.2도 SHA-256 고정 공식 소스를 필요한 디먹서·디코더·PCM/WAV 출력·리샘플러만 켜 정적 빌드하고 `externalBin`으로 서명한다. GPL/nonfree는 금지한다. 정확한 URL·해시·configure 인자는 `app/build-inputs.json`, LGPL 전문은 Resources의 `COPYING.LGPLv2.1`에 들어간다. CI 캐시 키는 이 입력 전체의 해시다.
- 최초 설치는 Apple Silicon·macOS 14 이상·네트워크를 확인한 뒤 사용자 동의로 시작한다. Python 준비 전 Rust는 엔진 환경 약 2GB + 작업 여유 2GB만 확인하고, 모델 용량 판단은 Python만 한다. Python은 **모델 받기 직전** 고정 commit revision의 Hugging Face 파일 메타데이터와 캐시 조회로 아직 없는 파일 크기를 합산하고, 그 합 + 처리 계약의 작업 여유 2GB를 캐시 파일시스템의 남은 공간과 비교한다. 전부 있으면 모델 필요량은 0이며 2GB 여유만 요구한다. 부족하면 다운로드 전에 ‘필요 X GB, 남은 Y GB’를 한국어·영어로 표시한다. 메타데이터 조회 실패는 캐시를 차감하지 않고 전체 모델 6GB + 여유 2GB로 보수적으로 판단하며 로그에 남긴다.
  모델은 **설치 단계**에서 받는다. ‘없는 모델만 받습니다(최대 약 6GB)’와 모델별 시작·완료·‘이미 있음’, 전체 경과 시간을 표시한다. 메타데이터·캐시 조회·다운로드·로컬 추론은 같은 고정 revision을 사용한다. Hugging Face 캐시를 재사용하며 앱 업데이트는 모델을 다시 받지 않는다.
- 번들 uv가 Python 3.12 부트스트랩 환경을 만든 뒤 번들 wheel의 CLI로 `install --app-install --source <wheel>`을 실행한다. 앱 전용 옵션은 고정 목록·도구 위치를 전달한다. 기존 CLI 기본 동작은 바꾸지 않는다. 서비스·등록·인증·롤백은 Python 설치기 소유다. plist 실행 파일은 venv Python이다.
- 상태 기계: 확인 → 미설치 안내 → 사전 점검 → Python 준비 → 의존성 설치 → 모델 확인 → 서비스 등록·인증 → 엔진 화면. 앱 소유의 버전/목록 해시가 다르면 작업 종료 대기 → 기존 rollback update → 인증 → 화면이다. 서비스 중지/승인 거부·네트워크·디스크·해시 실패는 한 문장 이유와 다시 시도, support의 `app-install.log`로 끝난다. CLI 설치는 이 전이에 들어가지 않는다.
- 동시 설치는 프로세스 수명의 파일 잠금으로 거부한다. 실패·강제 종료의 미완료 트랜잭션은 다음 시도에서 이전 서비스/기록으로 복구하고 다시 설치한다. 완료 표시 전 환경은 엔진으로 사용하지 않는다. support/root 및 경로 조상의 심볼릭 링크는 앱 설치 경로에서 거부한다.
- 앱 도구는 명시적 `QC_UV`/`QC_FFMPEG`/`QC_FFPROBE` 절대 경로로 지정하고 venv에 보존한다. CLI는 기존 PATH 도구를 그대로 쓴다. 앱 번들을 이동하거나 교체해도 서비스 도구 경로는 바뀌지 않는다.
- Tauri IPC는 번들 안내 페이지 출처·현재 안내 창에서만 허용한다. 원격 엔진 화면에는 권한을 주지 않는다. 경로·명령·URL 등 사용자 입력을 받는 IPC는 없다. 상태/시작만 허용하고 설치 소스는 검증한 번들 리소스에 고정한다.
- 첫 설치 성공은 support의 `app-open-setup` 표식으로 다음 앱 창에 전달한다. 앱은 bootstrap fragment에 `next=setup`만 넣고 엔진은 인증 뒤 고정 `/setup/1`로 이동한다(다른 값은 `/home`, 임의 URL/리다이렉트 금지). 실제 마법사 탐색이 시작되면 표식을 지워 이후 일반 열기는 홈을 쓴다. bootstrap 환경의 PyYAML은 전체 잠금 목록에서 기계적으로 뽑은 해시 고정 부분 목록으로 설치하며 manifest에도 해시를 기록한다.

### 입력·상황별 처리 방침

| 입력·상황 | 처리·자동 시험 |
|---|---|
| Intel·macOS 13 이하·엔진 준비 여유 4GB 미만 | Rust는 Python 준비 전에 중단; Python 플랫폼 점검은 네트워크 전에 중단 (`engine_space_does_not_reserve_model_downloads`, `test_platform_fails_before_network`) |
| 모델 전체/일부 캐시·공간 부족·메타데이터 실패 | 네트워크 없는 가짜 허브/캐시 시험으로 0 + 2GB, 누락 크기 합, 다운로드 전 중단·양언어 안내, 전체 6GB 대체 판단 확인 (`tests/test_model_download.py`) |
| 네트워크 단절 | 사전 점검 중단, 설치 중 오류는 로그·다시 시도. 완료 모델 파일은 캐시 재사용 (`test_network_disconnection_is_retryable_before_install`, `test_model_download_restart_reuses_completed_files_and_reports_each_model`) |
| wheel·목록·manifest 손상 | 컴파일된 manifest SHA-256과 각 파일 SHA-256이 모두 맞아야 실행 (`resources_require_compiled_manifest_and_matching_bytes`, `test_damaged_bundle_stops_before_environment_creation`) |
| CLI 설치·사용자 plist 교체 | 읽기·인증만, 앱 옵션을 주어도 소유권 없는 update는 거부 (`test_cli_coexistence_never_preflights_or_installs`, `test_app_packaging_options_cannot_modify_cli_owned_service`) |
| 앱 소유 다른 버전·목록 해시 | pause로 새 claim을 막고 현재 작업 종료 대기 → 기존 update/rollback → 기존 pause 상태 복원 (`test_changed_app_engine_waits_for_job_then_uses_rollback_update`, S1 `test_update_failure_restores_app_metadata_and_service`) |
| 설치 중 강제 종료 | 내구성 journal로 이전 서비스/기록 복구 후 새 환경에서 재시도; 미완성 환경을 열지 않음 (`test_killed_first_install_recovers_private_journal_before_retry`) |
| 앱 두 개의 설치 요청 | support의 프로세스 수명 flock으로 둘째 거부 (`concurrent_installs_and_symlinks_are_rejected`) |
| support/root/`.venvs` 심볼릭 링크 | 링크를 따라 쓰지 않고 중단 (`test_symlinked_root_support_and_environment_are_rejected`, Rust 잠금 시험) |
| 원격 엔진·외부 출처의 IPC | 실제 webview URL과 label의 번들 출처 검사로 거부. 원격 capability 없음 (`installation_ipc_rejects_remote_and_other_windows`) |
| 앱 번들 이동·교체 | Python·uv·FFmpeg/ffprobe는 venv의 절대 경로, 앱 경로에 의존하지 않음. `QC_UV`는 마법사의 도구 확인에도 사용 |
