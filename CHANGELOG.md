# Changelog / 변경 기록

## 0.0.11

### 한국어

- 화면이 빨라졌습니다. 화면·API를 맡는 엔진은 macOS 반응형 우선순위로 돌고, 받아쓰기·요약은 지금처럼 백그라운드에서 돕니다. 화면 파일은 시작할 때 메모리에 올려 두고 바뀐 것만 다시 받으며, 필요한 파일을 한 번에 받습니다. 업데이트할 때 이 설정도 바뀌고, 실패하면 이전 서비스 설정으로 되돌립니다.
- 화면을 다듬었습니다. 한국어/English 전환은 같은 너비 두 칸, 목록은 파일 이름 대신 회의 제목, 사이드바 엔진 상자는 포트 대신 상태를 보입니다. 설정 키·API 이름·대화록 줄 번호 같은 개발자용 글자를 화면에서 내렸고, 아직 쓸 수 없는 필터·탭을 숨겼습니다. 버튼·입력·칩 높이와 엔진 카드 배치를 맞췄습니다.

### English

- Faster screens. The engine's screen and API process runs at macOS interactive priority while transcription and summaries stay in the background. Static files are loaded into memory at start, revalidated instead of re-sent, and fetched in one go. Updates apply this setting and roll back to the previous service definition on failure.
- Polished screens: equal-width language switch, meeting titles instead of file names in lists, engine status instead of a port in the sidebar, developer text (setting keys, API names, transcript line IDs) moved out of view, unavailable filters and tabs hidden, consistent control heights and engine cards.

## 0.0.10

### 한국어

- 이전 형식 노트의 게시 차단·노트 충돌은 자동 재시도하지 않고 사용자 조치를 기다립니다. 홈·작업·회의록에서 이유와 해결 방법을 안내합니다.
- 실패한 실행에 완료된 단계도 메타·해시·입력·모델 리비전·설정이 맞으면 재사용합니다. 이행된 작업의 새 산출물까지 재사용하지 못하던 문제와 자동 재시도 때 앞 단계를 다시 계산하던 문제를 고쳤습니다.
- ‘새 형식으로 바꾸기’에서 미리보고 동의하면 최신 실행 결과로 LLM 호출 없이 교체합니다. 교체 직전 볼트 밖에 다시 백업하고 사용자 속성·기존 본문 전체를 안전하게 보존합니다. 새 파일명·데일리 링크·검색을 갱신하고 중단 시 게시 저널로 복구합니다.

### English

- Old-format note publication blocks and note conflicts now wait for your action without automatic retries. Home, Jobs and Minutes explain why and what to do next.
- Completed stages from failed runs are reused when verified metadata, hashes, inputs, model revisions and settings match. Fixed migrated jobs rejecting their new artifacts and automatic retries repeating completed work.
- Preview and consent to ‘Convert to new format’ to publish the latest verified result with no LLM call. An extra outside-vault backup, your properties and the whole old body are preserved safely. Filenames, daily links and search are updated, with journaled crash recovery.

## 0.0.9

### 한국어

- 회의록·내보내기 파일 이름을 `날짜_시각_제목`으로 바꿔 같은 날 녹음도 파일명 내림차순으로 찾을 수 있습니다. 메모는 시각 뒤에 `메모_`가 붙습니다.
- 기존 엔진 형식 이름은 다음 게시(완료한 작업의 이어 하기 포함) 때 제목 부분을 보존하며 바뀝니다. 직접 정한 이름과 충돌 파일은 건드리지 않고, 게시 저널로 중단 후 복구하며 켜 둔 데일리 노트 링크도 갱신합니다.
- Obsidian Bases의 최근/검토 대기 보기 모두 녹음 시각을 분까지 표시하고 최신순으로 정렬합니다. 알려진 옛 엔진 보기와 내용이 같으면 YAML 표기만 달라도 갱신하며, 내용을 고친 보기는 보존합니다.

### English

- Meeting-note and export filenames now use `date_time_title`, so filename sorting also orders recordings within a day. Memos keep `메모_` after the time.
- Old engine filenames change on the next publication, including Resume for completed jobs, keeping the existing title slug. Custom names and collisions are left alone; the publication journal recovers interrupted moves and enabled daily-note links are updated.
- Both Obsidian Bases views show recording time to the minute and sort newest first. Known old engine views are upgraded even after YAML reserialization; views with changed content are preserved.

## 0.0.8

### 한국어

- 맥서기를 새로 그렸습니다. 고양이 귀를 단 은색 도트 Mac mini입니다. 화면 캐릭터, 앱 아이콘, 메뉴 막대 아이콘, README 배너가 모두 같은 그림입니다.
- 화면의 맥서기가 가끔 눈을 깜빡이고, 녹음을 처리하는 동안은 눈을 굴리며 전원 표시등이 깜빡입니다. 오류일 때는 눈을 감고 땀을 흘립니다. macOS에서 "동작 줄이기"를 켜면 움직이지 않습니다.

### English

- Redrew the mascot 맥서기: a silver pixel Mac mini with cat ears. The screens, app icon, menu bar icon and README banners now share one drawing.
- On screen it blinks now and then, glances around with a pulsing power light while a recording is processed, and shuts its eyes with a sweat drop on errors. It stays still when macOS Reduce Motion is on.

## 0.0.7

### 한국어

- 메뉴 막대 아이콘을 바꿨습니다. 고양이 귀를 단 Mac mini 모양이고, 입은 USB-C 단자, 오른쪽 아래 점은 전원 표시등입니다. 선 대신 꽉 찬 모양이라 작은 크기에서도 잘 보입니다.

### English

- New menu bar icon: a Mac mini with cat ears, a USB-C port for a mouth and the power light at the lower right. A solid shape instead of thin outlines, so it stays legible at menu bar size.

## 0.0.6

### 한국어

- 앱 업데이트 직후 창에 "Run quietclerk open to sign in."만 뜨던 문제를 고쳤습니다. 메뉴 막대 상태를 읽을 때 한 번만 쓸 수 있는 로그인 토큰을 써 버려, 동시에 열리던 창이 로그인하지 못했습니다. 이제 메뉴 상태는 토큰 없이 서비스 등록 상태와 설치된 엔진 버전으로 표시합니다.
- 다시 여는 방법 안내에 메뉴 막대 아이콘의 ‘QuietClerk 열기’를 함께 적었습니다(이전에는 터미널 명령만 안내).

### English

- Fixed the window showing only "Run quietclerk open to sign in." right after an app update. Reading the menu bar status spent the single-use sign-in token, so a window opening at the same time could not sign in. The menu now shows the service registration and the installed engine version without a token.
- Reopen hints now mention Open QuietClerk in the menu bar icon, not only the Terminal command.

## 0.0.5

### 한국어

- 설정에서 엔진 버전·앱/CLI 설치 방식과 기록된 마지막 업데이트 시각을 확인합니다. 메뉴 막대에는 엔진 버전·상태와 별도의 앱 버전을 표시합니다.
- launchd의 제한된 PATH 밖에 설치된 omp·Codex·Claude도 알려진 사용자 bin 위치에서 찾습니다. 기존 PATH 우선순위와 버전·도구 차단 검증은 유지하며, 기존 서비스 plist는 변경하지 않습니다.

### English

- Settings shows the engine version, app/CLI installation method and last recorded successful update time. The menu bar shows engine version/status and the separate app version.
- Find omp, Codex and Claude in known per-user bin directories when launchd's limited PATH misses them. Preserve PATH precedence and version/tool-block checks without changing existing service plists.

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
