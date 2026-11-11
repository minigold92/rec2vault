# Changelog / 변경 기록

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
