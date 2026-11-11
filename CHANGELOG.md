# Changelog / 변경 기록

## 0.0.4

### 한국어

- 이미 있는 모델 때문에 설치에 여유 8GB를 요구하지 않습니다. 고정 revision에서 없는 파일만 계산해 다운로드 크기 + 작업 여유 2GB를 확인하고, 이미 있는 모델은 설치 단계에 표시합니다. 메타데이터 조회 실패 시 전체 크기로 보수적으로 점검하고 로그에 남깁니다.
- 새로 설치할 때 화면·회의록 기본 언어를 Mac의 언어 설정에서 정합니다. 0.0.3은 앱이 설치한 엔진이 한국어 Mac에서도 영어로 설정됐습니다(이미 설치했다면 설정 화면에서 바꾸세요).
- 설치 기록의 한국어가 그대로 읽히고, 새로 설치할 때는 예전 버전 이행 문구를 보이지 않습니다.

### English

- Cached models no longer trigger a blanket 8 GB installation requirement. Check only missing files at pinned revisions plus 2 GB working space, and show models already present. If metadata is unavailable, conservatively check the full size and log the fallback.
- New installs take the screen and note language from the Mac's language order. In 0.0.3 an app-installed engine was set to English even on a Korean Mac (change it in Settings if you already installed).
- The installation log shows Korean as text, and fresh installs no longer print upgrade-only lines.

## 0.0.3

### 한국어

- 앱이 첫 실행 때 엔진·모델을 설치하고 로그인 서비스를 등록합니다. 터미널·Homebrew 없이 진행·경과 시간과 실패 후 다시 시도를 제공하며, 앱을 종료해도 엔진은 계속 실행됩니다.
- 앱에 버전·해시를 고정한 uv·엔진 wheel·의존성 목록과 LGPL 전용 최소 FFmpeg/ffprobe를 포함합니다. CLI 설치는 그대로 사용하고 앱 소유 엔진만 번들에 맞춰 롤백 있는 업데이트를 합니다.

### English

- The app installs the engine and models on first open and registers its login service, without Terminal or Homebrew. See stages and elapsed time, retry failures, and keep the engine running after quitting the app.
- Bundled hash-pinned uv, engine wheel/dependencies and minimal LGPL-only FFmpeg/ffprobe. Existing CLI installations stay untouched; app-owned engines follow the bundle through the rollback updater.

## 0.0.2

### 한국어

- 앱 자동 업데이트(0.0.1 → 0.0.2)를 실제로 확인하기 위한 릴리스입니다. 기능 변화는 없습니다.

### English

- Release to verify the in-app update from 0.0.1 to 0.0.2 end to end. No functional changes.

## 0.0.1

### 한국어

- 녹음 폴더를 감시해 Apple Silicon Mac에서 로컬 전사·화자 분리를 하고, 선택한 텍스트 엔진으로 교정·요약해 Obsidian 또는 Markdown 회의록으로 남깁니다.
- 로컬 웹 화면에서 처리 상태·회의록·설정을 보고, 회의록 검색과 읽기 전용 CLI를 사용할 수 있습니다.
- Mac 메뉴 막대 앱을 추가했습니다. 실행 중인 엔진 화면을 열고, 엔진이 없으면 설치 안내를 표시합니다. 엔진 설치·시작은 아직 앱에서 하지 않습니다.
- 앱 업데이트 확인·서명 검증·설치 후 재시작을 제공합니다. 자동 확인 실패는 조용히 기록하고, 메뉴에서 직접 확인할 때만 실패 안내를 표시합니다. 초기 0.0.x 앱은 ad-hoc 서명으로 배포하며 Apple 공증은 없습니다.

### English

- Watch recording folders, transcribe and separate speakers locally on an Apple Silicon Mac, then correct and summarize with your chosen text engine into Obsidian or Markdown meeting notes.
- View processing status, notes and settings in the local web interface, with note search and a read-only CLI.
- Added a Mac menu bar app that opens the running engine or shows installation instructions. The app does not yet install or start the engine.
- Check for app updates, verify their signature, install and restart. Automatic check failures are logged silently; failure messages appear only when you check from the menu. Initial 0.0.x apps use ad-hoc signing without Apple notarization.
