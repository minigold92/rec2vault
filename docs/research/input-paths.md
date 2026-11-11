# QuietClerk 입력 경로 조사 (사실 조사)

작성 2026-11-11 (모든 URL 확인일 2026-11-11). 읽기 전용 조사: 코드·문서 수정 없음, 사용자 개인 파일 내용은 열지 않음(경로 존재·권한만). 질문 5개(아이폰 음성 메모 / 클라우드 폴더 / 안드로이드→Mac 전송 / Mac 직접 녹음 / 파일 직접 넣기)에 답한다.

## 설계에 바로 쓰는 결론

1. **엔진의 입력은 "감시 폴더 + 파일 하나씩 검증" 한 가지로 통일**하고, 모든 경로(Syncthing·클라우드 폴더·끌어놓기·Mac 녹음 결과)를 그 앞단 어댑터로 둔다. 어떤 경로도 검증 계약(크기 한도 → 격리 → probe → 해시 → 확정)을 건너뛰지 못하게 한다.
2. **클라우드 폴더는 "내려받기 안 된 파일"을 정상 상태로 다룬다.** `stat`의 `SF_DATALESS`로 판별하고, 파일을 읽으면 내려받아지며(느리거나 시간 초과 가능), 폴더 목록 읽기만으로도 내려받기가 일어날 수 있다(Apple TN3150). `brctl download`는 이 MacBook(macOS 27.0.1)에 없다(직접 확인) → CLI에 기대지 않는다.
3. **아이폰 음성 메모 자동 읽기는 Full Disk Access가 필수**이고 내부 DB(`CloudRecordings.db`)는 비공개 스키마다. 첫 배포에서 빼고, "Voice Memos에서 감시 폴더로 끌어놓기"(Apple 문서에 있는 방법)를 안내한다.
4. **"녹음 끝 → 자동 전송"을 앱 설치 없이 해 주는 안드로이드 기본 기능은 확인 못 함(U8).** 가장 가까운 것은 서드파티 폴더 감시 앱(Syncthing-Fork, FolderSync)이다. LocalSend·KDE Connect·Quick Share는 모두 건별 수동 전송이다.
5. **Mac 직접 녹음은 가능하고 권한 비용이 다르다.** Core Audio 탭(macOS 14.2+, "시스템 오디오만" 권한) + 마이크 vs ScreenCaptureKit(화면·시스템 오디오 권한, Sequoia에서 월 단위 재확인 보도). 조사한 4개 오픈소스(Recap·OpenWhispr·anarlog·meetily) 모두 Core Audio 탭 코드를 갖고 있다(meetily는 ScreenCaptureKit도 선택 가능, 코드 확인). 두 번째 출시로 미루되, 입력 어댑터와 동의 안내 자리를 지금 설계에 넣는다.
6. **녹음 사실 고지는 제품 기능으로 둔다.** 대법원은 대화 당사자 본인의 녹음을 통신비밀보호법 제3조 위반으로 보지 않았다(2006도4981, 2013도16404 등). 제3자 몰래 녹음은 다르다. 앞서가는 제품(Granola·anarlog)은 채팅 자동 고지·재확인 문구를 둔다. 법률 판단은 단정하지 않고 검토 대상으로 남긴다(U9).
7. **첫 배포: 감시 폴더(+클라우드 폴더 인지) · 끌어놓기/열기 · Syncthing 안내.** 나중: 음성 메모 자동 읽기, Mac 직접 녹음, FolderSync 안내. 빼기: KDE Connect, LocalSend 자동화, Quick Share, 공유 메뉴 확장, 통화 녹음 앱 연동.
8. **검증 수준: 이 조사는 "문서·코드를 읽고 이 MacBook에서 명령 몇 개를 실행"한 수준이고, 실제 입력(실제 음성 메모·실제 폰·실제 클라우드 계정)으로 확인한 항목은 0건이다.** 아래 §7 테스트가 그 공백을 채운다.
9. **미결 14건은 모두 §8에 담당·확인 시각 또는 닫는 결정이 붙어 있다.** 기존 `contract.md:43`(삼성 앱 녹음 중 파일 쓰기)은 확인 예정 시각 2026-11-10 18:00 KST가 지났고 결과 기록을 못 찾았다. 새 시각 제안은 §8 U1.

---

## 0. 표기와 검증 수준

| 표기 | 뜻 |
|---|---|
| **실행** | 이 MacBook에서 명령을 직접 실행해 출력을 봄. 실제 입력은 아님 |
| **문서·코드** | 공식 문서·저장소 코드·README를 읽음. 동작은 재현하지 않음(= "가정으로 확인"에 해당) |
| **2차** | 블로그·커뮤니티·뉴스. 근거로 쓰되 약하다고 표시 |
| **실제 입력** | 실제 음성 파일·폰·계정으로 끝까지 확인 → **이 조사에서는 0건** |
| `U#` | §8 미결 목록의 번호. 본문에서 "확인 못 함"·추정으로 표시한 항목은 전부 `U#`와 연결 |

**환경(실행)**: macOS 27.0.1 (빌드 26A434), Apple Silicon. `sw_vers`.

**samples/ 점검(실행, 내용은 열지 않음)**: 저장소 `samples/`는 있다(`.gitignore`로 제외). 바로 아래 파일 0개, `samples/audio` 4개(전부 m4a), `samples/clova` 4개, `samples/probe` 21개. 제품 게이트가 "samples/ 없음"이라 한 점검이 어떤 경로를 봤는지는 모르지만, 저장소 루트의 `samples/`는 존재한다. 이 조사는 `samples/`를 사용하지 않았다. 실제 입력 시험은 §7에서 공개 가능한 합성 표본을 새로 만들도록 제안한다.

---

## 1. 경로별 비교표

"단계 수"는 사용자가 하는 별개 조작을 **문서 절차에서 조사자가 센 값**이다(앱 설치·로그인 포함, 사람이 따라 해 본 값 아님 → 문서·코드 수준). "건당"은 녹음마다 반복.

| # | 경로 | 자동성 | 단계 수 | 필요 권한 | 완료 판정 | 위험 | 출처 |
|---|---|---|---|---|---|---|---|
| A | 아이폰 음성 메모 → iCloud → Mac `Voice Memos`가 받은 파일을 우리 앱이 직접 읽기 | 완전 자동(새 녹음 감지) | 약 5–6: iCloud의 음성 메모 켜기 1, 앱 설치 1, 설정→개인정보→전체 디스크 접근에 앱 추가 3–4(+앱 재시작) | **Full Disk Access**. 이 MacBook의 권한 없는 프로세스는 컨테이너 접근이 `Operation not permitted`(실행) | DB 행 + 파일 + 크기 안정 + 길이 확인(제안, 오픈소스는 판정하지 않음) U2 | 비공개 DB 스키마, FDA를 launchd 엔진·앱 번들 중 어디에 줄지, 서명이 바뀌면 FDA 재부여 필요 가능, 아이클라우드에만 있는 녹음은 못 읽음 | §2.1 |
| B | Voice Memos → Finder 감시 폴더로 끌어놓기(Mac) | 수동(건당 2: 선택, 끌기) | 설정 0 | 없음(감시 폴더가 보호 폴더 밖이면) | 일반 검증 계약 | 사용자가 잊으면 끝 | Apple 음성 메모 도움말 |
| C | iCloud Drive 폴더 감시(폰에서 "파일에 저장"하거나 녹음 앱이 거기 저장) | 폴더 도착은 자동, 폰 쪽 저장은 건당 수동(아이폰 절차는 Apple 문서로 확인 못 함 U14) | 약 2–3 | Files & Folders 접근 팝업 가능(Desktop·Documents·Downloads 등) | 내려받기 완료(`SF_DATALESS` 없음) + 안정 + probe | 최적화 저장 공간이 켜지면 파일이 다시 비워질 수 있음 | §2.2 |
| D | Google Drive for desktop(스트리밍/미러) | 폰 쪽은 업로드 앱 필요 | Mac 약 3–4 + 폰 §3 | Files & Folders(미러 폴더), File Provider 활성화 | 스트리밍은 내려받기 필요, **미러는 항상 로컬 보관** | 스트리밍에서 폴더 밖으로 끌면 클라우드 파일이 휴지통으로 | §2.2 |
| E | Dropbox(File Provider/기존) | 〃 | 〃 | macOS 12.5+ (File Provider 판) | 온라인 전용이면 내려받기 필요 | 기존 판의 온라인 전용은 타 앱 호환 문제가 있었음(Dropbox 설명) | §2.2 |
| F | OneDrive(Files On-Demand) | 〃 | 〃 | 동기화 동의 1회, 동기화 폴더 `~/Library/CloudStorage`(이동 불가) | 핀("항상 이 기기에 유지") 아니면 내려받기 필요 | 공간 부족 시 OS가 파일을 언제든 비움 | §2.2 |
| G | **Syncthing-Fork**(안드로이드) → Mac Syncthing | 완전 자동 | 약 8–10(설계 문서 §1: "대부분 여기서 포기") | 폰: 배터리 최적화 제외·저장소 접근, Mac: 없음 | `.syncthing.*.tmp` 제외 + 크기·시각 60초 안정 + probe(`contract.md:16`) + **moov 확인** | 폰 배터리, 포크 유지보수 연속성, 받는 폴더에서 이동·삭제하면 폰 원본이 지워짐 | §3, surfnterd |
| H | FolderSync(안드로이드) → 클라우드/SFTP/SMB | 완전 자동("즉시 동기화"는 일정과 함께) | 약 8–10 | 폰 저장소 접근, Mac은 SFTP면 원격 로그인 켜야 함 | "임시 파일 후 이름 변경" 옵션이 켜져 있어야 완료 신호가 생김 | 가격·라이선스 조사 안 함(U7), Mac 서버 설정이 초심자에게 어려움 | FolderSync 문서 |
| I | LocalSend | **건당 수동**(안드로이드에서 공유→기기 선택→Mac에서 수락). 즐겨찾기 장치 자동 수락 설정 있음 | 설치 양쪽 2 + 건당 3 | Mac: 로컬 네트워크 접근, 방화벽 53317 | 받은 파일은 저장 폴더에 도착(완료 신호 문서 미확인 U7) | 같은 Wi-Fi 필요, 공유기 AP 격리 | LocalSend README·changelog |
| J | KDE Connect | 건당 수동(공유) | 설치 양쪽 2 + 페어링 + 건당 | 로컬 네트워크 | 일반 검증 계약(전송 도구의 완료 신호는 조사 안 함) | **Mac 지원 문서가 서로 모순**(§3) → 닫음(U6) | KDE |
| K | Quick Share → AirDrop(Mac) | 건당 수동 | 건당 3–4(수신자가 "모든 사람 10분" + 수락) | AirDrop | Downloads 등에 도착, 완료 신호는 문서에 없음(U7) | 지원 기기 한정, 폴더 위치 사용자 설정 | Google·Apple 문서 |
| L | 구글 레코더(Pixel) "다른 앱에서 접근" 공개 사본 + G/H | 폰 쪽 자동 | G와 같음 + 레코더 설정 1 | — | G와 같음 | Pixel 한정, 앱에서 지워도 사본은 남아 중복 | Pixel 도움말 |
| M | **Mac 직접 녹음: Core Audio 탭 + AVAudioEngine 마이크** | 회의 시작 알림 → 사용자 승인(마이크 감지는 알림, 일정 시각 자동 시작은 옵션 — anarlog 문서) | 앱 설치 1 + 허용 팝업 2–3 | 마이크, **시스템 오디오 녹음**(`NSAudioCaptureUsageDescription`), 회의 감지에 접근성/캘린더(선택) | 우리가 파일을 만들므로 정지 시 확정(충돌 방지 컨테이너 필요, 2차 근거) | macOS 14.2/14.4 이상, 무음 버퍼 버그 보고, Teams 개별 앱 탭 무음 보고, 법적 고지 | §4 |
| N | Mac 직접 녹음: ScreenCaptureKit(`capturesAudio` 13.0+, `captureMicrophone` 15.0+) | 〃 | 〃 + 권한 월간 재확인 | **화면 및 시스템 오디오 녹음**(더 넓음) | 〃 | Sequoia 월 단위 재확인 보도, 영상 파이프라인 오버헤드(2차), 마이크 코덱 혼재 버그 보고(2차) | §4 |
| O | 앱 창·메뉴 막대·Dock 아이콘에 끌어놓기 | 수동(건당 1) | 0 | 없음 | 경로가 오므로 즉시 복사 후 검증 | 경로 위의 파일이 내려받기 전일 수 있음, 폴더·별칭·심볼릭 링크 드롭 | Tauri API |
| P | Finder 빠른 동작/서비스("QuietClerk로 처리") | 수동(건당 2) | Automator/단축어 한 번 설치 | 없음 | O와 같음 | 앱 번들 안에 넣으려면 Automator 워크플로 배포 필요 | Apple |
| Q | 공유 메뉴 확장(Mac) | 수동(건당 2) | 확장 켜기 1 | 확장 승인 | O와 같음 | **별도 Xcode 확장 타깃이 필요**, Tauri에서 쉽게 되는지 확인 못 함 → 닫음(U11) | Apple 확장 가이드 |

---

## 2. 클라우드·로컬 입력 근거

### 2.1 아이폰 음성 메모 → iCloud → Mac

**위치·형식(문서·코드)**
- 경로: `~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/`, 메타데이터 DB `CloudRecordings.db`(같은 폴더). xyb/voicememowhisper `docs/technical_details.md`(저장소 최신 커밋 2026-11-01), harryf/voice-memos README.
- 오디오는 `.m4a`. 파일 이름 예: `20260510 201833-B98E5D08.m4a`, 인코더 문자열 `com.apple.VoiceMemos (iPhone Version 26.4.2 …)`(harryf, 2026년 예시).
- macOS 15+/iOS 18+는 Apple Intelligence 전사문을 m4a 안 `tsrp` 원자에 단어별 시각과 함께 기록(harryf). 한국어 지원 여부는 확인 못 함 → 쓰지 않고 자체 전사(닫음 U10).
- macOS 15.1 이하는 아이폰의 레이어 녹음이 Mac에 안 보인다(Apple Voice Memos 도움말).
- Mac의 동기화 켜기: 시스템 설정 → 이름 → iCloud → "iCloud에 저장됨 모두 보기" → 음성 메모(Apple 도움말).

**제목·날짜(DB, xyb)**: 테이블 `ZCLOUDRECORDING`. `ZUNIQUEID`(녹음 GUID, 파일과 대응), `ZDATE`(2001-01-01 기준 초), `ZDURATION`/`ZLOCALDURATION`, `ZENCRYPTEDTITLE`(이름과 달리 새 시스템에서는 평문 제목), `ZCUSTOMLABEL`(사용자가 정한 이름), `ZPATH`(파일 이름), `ZEVICTIONDATE`(null 아님 = 최근 삭제됨). 옛 시스템은 `Recents.sqlite`의 `ZVOICE`. harryf는 `PRAGMA table_info`로 컬럼을 확인해 macOS 버전 차이를 흡수한다. Apple은 스키마를 문서화하지 않는다(polarity-dev README: "다음 macOS에서 깨질 수 있음").

**권한(문서·코드 + 실행)**: 읽으려면 Full Disk Access가 필요하다는 README 3건(harryf, xyb, polarity-dev)이 일치한다. **실행**: 이 MacBook에서 같은 컨테이너와 다른 앱 컨테이너(`group.com.apple.notes`)를 FDA 없는 프로세스로 열어 보면 둘 다 `Operation not permitted`. 컨테이너 디렉터리는 존재(`group.com.apple.VoiceMemos.shared`, `drwx------`), 하지만 이 프로세스로는 `Recordings/`가 있는지 알 수 없다(하위 경로 조회는 ENOENT로 보이나 TCC 때문에 믿을 수 없음) → **macOS 27에서의 경로·스키마는 확인 못 함 (U3)**. `~/Library/Containers/com.apple.VoiceMemos`는 있음(앱 실행 흔적, 실행).

**FDA 부여 방식의 선례**: polarity-dev는 FDA를 터미널이 아니라 서명된 **브로커 앱**에만 주고 CLI가 LaunchServices로 호출한다(README). 같은 README는 임시 서명 앱을 다시 빌드하면 FDA 항목을 지우고 다시 추가해야 할 수 있다고 쓴다 → 우리 구조(launchd 상주 엔진 + 앱 껍데기)에서 FDA를 어느 실행 파일에 붙일지와 업데이트 후 유지 여부는 시험 대상(U13).

**동기화 완료 판정**: 조사한 7개 저장소 중 판정 로직이 있는 곳은 없다. apple-voice-memo-mcp는 계획서에 "아직 동기화 안 된 메모를 다룰지"를 열린 질문으로 남겼고, polarity-dev는 "아이클라우드에만 있는 녹음은 Voice Memos가 받기 전에는 내보낼 수 없다"고만 쓴다. Reddit(2차)은 Mac이 모든 녹음을 로컬에 보관하고 사진 앱 같은 "저장 공간 최적화"가 없다고 사용자들이 말한다. → 제안(미검증, U2): DB 행 존재 + `ZEVICTIONDATE` null + `Recordings/<ZPATH>` 파일 존재 + 크기 10초 안정 + `ffprobe` 길이가 `ZDURATION` 근처 + moov 존재.

**다른 오픈소스 사례(코드·README, 클론 확인일)**: harryf/voice-memos(Swift, MIT), xyb/voicememowhisper(Python+WhisperKit, 2026-11-01), polarity-dev/macos-voice-memos-export(Swift, MIT), bulletinmybeard/voice-memo-export(Python, PyPI), jwulff/apple-voice-memo-mcp(2026-10-19), appstart-one/ciderpress(2026-07-28), iLEAPP(포렌식 `voiceRecordings.py`). 모두 같은 경로·DB를 읽는다 = **경로 자체는 여러 독립 구현이 공유하지만 Apple 공식 계약은 아니다.**

**이 MacBook에서 확인한 것(실행, 내용 열람 없음)**: Voice Memos 앱은 `/System/Applications/VoiceMemos.app`(버전 4.0). `~/Library/Mobile Documents`의 확장 속성에 `com.apple.file-provider-domain-id: com.apple.CloudDocs.iCloudDriveFileProvider/…` → iCloud Drive가 File Provider로 동작. `~/Library/CloudStorage`는 비어 있음 = 이 Mac에는 Google Drive·Dropbox·OneDrive File Provider 도메인이 없다(그래서 §2.2는 문서·코드 수준).

### 2.2 클라우드 폴더(File Provider, dataless)

**판별(문서)**: Apple TN3150(2023-05-09). 내용이 없는 파일 = dataless. `stat`/`getattrlist`의 `st_flags`에 `SF_DATALESS`가 있는지로 판별. 단 `stat`은 경로 중간의 dataless **폴더**를 내려받게 한다. SDK 헤더에 `#define SF_DATALESS 0x40000000`(실행).

**내려받기 요청(문서)**
- 파일을 읽으면 시스템이 내려받는다(materialization). 파일이 크거나 네트워크가 나쁘면 오래 걸리고 `ETIMEDOUT`이 날 수 있다. 목록 읽기(`contentsOfDirectory`)도 dataless 폴더에서 내려받기를 유발한 트레이스가 TN3150에 있다.
- 스레드/프로세스 단위로 끄기: `setiopolicy_np(IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES, …, IOPOL_MATERIALIZE_DATALESS_FILES_OFF)` → 접근 시 `EDEADLK` 처리 필요. "목록만 보고 내려받지는 않기"에 쓸 수 있다.
- iCloud 항목: `FileManager.startDownloadingUbiquitousItem(at:)`(macOS 10.7+), 상태는 `NSMetadataUbiquitousItemDownloadingStatusKey`(Apple 문서). **타사 File Provider(Drive·Dropbox·OneDrive)에 같은 API가 통하는지는 확인 못 함 (U7)**.
- `brctl download`/`evict`: **이 MacBook(macOS 27.0.1)의 `brctl`에는 없다**(명령: diagnose, log, dump, status, accounts, quota, monitor, 실행). `fileproviderctl`에도 download 계열 명령은 없다(dump, diagnose, evaluate, check/repair, obfuscate, 실행). CLI에 기대지 않는다.
- 고정(내려받은 채 유지): iCloud는 Sequoia에서 Finder로 항목 고정이 가능하고 `com.apple.fileprovider.pinned` 확장 속성이 붙지만 Apple은 이 속성을 문서화하지 않았다(Eclectic Light 2024-09-30, 2차). OneDrive "항상 이 기기에 유지", Google Drive "미러 파일", Dropbox "오프라인 사용 가능"은 각 사 문서에 있다.

**iCloud Drive**: Sonoma(14)부터 File Provider로 통합. 예전 숨김 `.icloud` 스텁 파일 대신 dataless 파일을 쓴다. "Mac 저장 공간 최적화"를 끄면 replicated(항상 내려받음), 켜면 nonreplicated(비울 수 있음)로 바뀐다(Eclectic Light 2023-11-21·2024-09-30, 2차, 로그 분석 기반). → 앱 최소 macOS를 14 이상으로 두면 `.icloud` 스텁을 다룰 필요가 없다.

**Google Drive for desktop**: macOS 12.1+에서 "스트리밍"은 File Provider를 쓰고 파일은 `~/Library/CloudStorage`, 위치는 바꿀 수 없다. 스트리밍은 파일이 "주로 클라우드에 있고 열 때 내려받음", **미러링은 "항상 로컬과 클라우드 양쪽에 있고 오프라인 사용 가능"**. File Provider 모드에서는 Finder 끌어놓기가 **이동**이라 폴더 밖으로 끌면 클라우드 파일이 휴지통으로 간다(Option 키로 복사). 동기화가 멈춘 동안은 내려받을 수 없다. 앱이 꺼져 있어도 이미 내려받은 파일은 접근 가능. → 감시 폴더로 **미러** 폴더를 권장하는 것이 안전(우리가 비움 걱정 없음).

**Dropbox**: File Provider 판은 macOS 12.5+ 필요, 목적은 "타사 앱에서 온라인 전용 파일을 여는 문제 해결"(Dropbox 도움말 2025-11-13 갱신)이라고 적혀 있다(해석: 이전 판은 타 앱에서 여는 데 문제가 있었다고 읽힌다). 이전은 필수가 아니고, 이전하지 않아도 Finder에서 온라인 전용 파일을 직접 열 수 있다. 폴더는 `~/Library/CloudStorage`로 이동(검색 결과 발췌, 원문 미열람).

**OneDrive**: macOS 12.1+에서 File Provider 기반 Files On-Demand. 동기화 루트는 `~/Library/CloudStorage/OneDrive-Personal`로 고정되고 사용자가 이동할 수 없다. 첫 실행에 동의 필요. "항상 이 기기에 유지"(핀)가 아니면 공간 부족 시 OS가 언제든 비운다. `ls -alR`로 폴더 트리만 미리 만들고 내용은 내려받지 않을 수 있다(OneDrive 아키텍트 블로그).

**"쓰는 중 파일" 판정**: 공급자 중립 API는 확인 못 함. 클라우드에서 도착한 파일은 "자리 표시 → 내려받기 → 완료"를 거친다고 볼 수 있지만, 폰 앱이 올리는 도중 Mac에서 부분 파일이 보이는지는 공급자별로 확인 못 함 (U7). 일반 검증 계약(크기·시각 안정 + moov + probe)을 그대로 적용한다. 아래 §3의 moov 근거 참조.

**폰 녹음 앱 → 클라우드 자동 업로드**
- **삼성 음성 녹음**: 삼성 클라우드 동기화 지원 항목(캘린더·연락처·블루투스·리마인더·삼성 브라우저·Samsung Notes·Samsung Health·Samsung Pass·Wi-Fi·갤럭시 아바타)에 **음성 녹음이 없다**(samsungcloud.com 동기화된 앱 페이지, 기기·통신사별 상이 가능). "백업" 항목에 있는지는 확인 못 함 → 약속하지 않는다(U8). 저장 위치(삼성전자서비스, 2026-09-30): Android 13·14 `내장 저장공간/Recordings/Voice Recorder`, Android 12 `내장 메모리/Recordings/Voice Recorder`, **Android 11 `Music/Voice Recorder`**, 통화 녹음은 `Recordings/Call`. 이 페이지는 Android 9–14만 다룬다 → 15 이상은 확인 못 함 (U8).
- **구글 레코더(Pixel)**: "백업 및 동기화"는 **구글 계정**(recorder.google.com)에 저장하며 Drive 폴더가 아니다. 별도로 "다른 앱에서 녹음 접근"(Android 12+, Pixel, 기본 켜짐)이 공개 **사본**을 만들어 파일 관리·동기화 앱이 읽게 한다. 앱에서 삭제해도 사본은 남고, 사본을 고치거나 지워도 원본에 영향 없음(Pixel 도움말).
- **에이닷(SKT)**: 통화 녹음 기능은 무제한이지만 2024-10 기사(이데일리)에 따르면 앱 안의 **외부 공유 기능이 사라져** 파일 관리 앱·클라우드를 직접 써야 하고, 예전의 클라우드 자동 업로드도 없다. 저장 경로 `Recordings/TPhoneCallRecords`(OS 12+)는 이 기사에 있다. 2024년 기사라 현재 동작은 확인 못 함 (U8).
- **클로바노트·다글로** 등은 조사하지 않았다 (U8, 닫음).
- 안드로이드 공식 Drive 앱의 임의 폴더 자동 업로드 설정은 공식 문서에서 못 찾았다. 2차 글들은 서드파티 앱을 쓰라고 한다 (U8).

---

## 3. 안드로이드 → Mac 전송 비교

| 항목 | Syncthing-Fork | FolderSync | LocalSend | KDE Connect | Quick Share |
|---|---|---|---|---|---|
| 폴더 감시 자동 전송 | **예** | **예**("즉시 동기화": 폴더 변경 감지, 일정 설정 필요) | 아니오(건당 공유) | 아니오(건당 공유) | 아니오 |
| Mac 쪽 | Syncthing 앱 | 클라우드·SFTP·SMB·WebDAV 등 대상 필요 | 앱(App Store·Homebrew·DMG, macOS 12+) | 안정판 dmg·`brew install --cask kde-connect`(KDE 다운로드 페이지) | **공식 Mac 앱 없음**(Windows 앱만). Mac은 AirDrop 호환 기기 또는 QR→브라우저 |
| 백그라운드 | 포그라운드 서비스 + 배터리 최적화 제외 필수(앱 위키), 배터리 소모 이슈 존재(#233 종결, 포럼) | 일정/즉시 동기화 | 수신 시 앱이 떠 있어야 하는지 확인 못 함(U7), 안드로이드 백그라운드 전송은 변경 이력 발췌에만 보임 | 앱 연결 필요 | 화면 켜짐·수락 필요 |
| 설정 난이도 | 높음(우리 §1 실측: 대부분 포기) | 높음(폴더쌍·계정·일정) | 낮음 | 중(페어링) | 낮음, 건당 수동 |
| 다른 위험 | 포크 연속성 | 서드파티 앱 | 같은 네트워크, 공유기 AP 격리, `Local Network` 권한 토글 | **Mac 지원 문서가 모순** | Google 서버 경유 24시간 보관, 10GB/24시간 한도 |

**근거 메모**
- **Syncthing-Fork 상태**: 원래 Syncthing-Android는 폐기, 이를 이은 Catfriend1 저장소가 2025-11-13에 404가 됐고(같은 포럼 스레드에서 한 사용자가 2025년에 저장소 초기화가 3번 있었다고 언급) researchxxl/syncthing-android가 이어받았다. 별 3294개, MPL-2.0, v2.1.6.0(2026-10-06: `requestRawExternalStorageAccess` 추가, target SDK Android 17), 릴리스 목록 최신 v2.1.7.0. 포크의 포크이고 v2.1.6.0 릴리스 기여자 표기가 1명이라 유지보수 연속성이 위험 요소다. 우리가 겪은 v2.1.3의 ✓ 회색 버그는 설계 문서 §1에 이미 있다.
- **moov 문제**: 안드로이드 녹음 앱은 녹음 **중**에는 `mdat`만 쓰고 `moov`는 정지할 때 쓴다 → Syncthing이 중간 스냅샷을 보내면 "크기가 잠깐 멈춘 채 재생 불가 파일"이 도착한다. 받는 쪽이 파일을 옮기거나 지우면 삭제가 폰에 전파돼 녹음이 사라진다(surfnterd/syncthing-partial-recordings README, 작성자 1인 경험 + "여러 폰의 기본 녹음기가 같다"는 주장 → **2차**). 이것은 `contract.md:43`의 "[추정] 삼성 앱은 최종 m4a를 한 번에 쓴다"와 **반대 방향의 증거**다(삼성 앱에 대해 직접 확인된 것은 아님, U1). 결론: "크기 안정"만으로는 부족하고 moov 존재 + probe 성공이 완료 판정에 들어가야 한다.
- **FolderSync**: "임시 파일 후 이름 변경" 옵션, "삭제 동기화"는 기본 꺼짐, "원본 이동" 옵션은 기본 꺼짐(문서). Mac이 SFTP 대상이면 원격 로그인(SSH)이 필요 [추정, 문서 미확인 U7]. 가격·라이선스는 확인 못 함.
- **LocalSend**: 라이선스 Apache-2.0, 별 약 9.8만, 포트 53317, 자동 업데이트 없음(스토어·패키지 관리자 권장), "즐겨찾기 장치 자동 수락"(changelog), Quick Save(끔/즐겨찾기/전체) 설정이 있다는 주변 도구 설명(2차). CLI `localsend-cli send`는 **보내기**만 문서화돼 있다. 안드로이드가 보낼 때는 공유 시트에서 대상을 고르는 건당 조작이 남는다.
- **KDE Connect 모순**: kdeconnect.kde.org 다운로드 페이지는 "macOS 안정판 사용 가능(26.08.2, arm64 dmg, Homebrew cask)"이라 하고, `kdeconnect-kde` README는 "Linux 외 플랫폼은 공식 지원이 아니며 macOS는 충분히 시험되지 않았다"고 한다. 다운로드 페이지가 더 최근일 가능성이 있지만 확인 못 함. 어느 쪽이든 폴더 감시 자동 전송은 없어 **빼기로 닫는다 (U6)**.
- **Quick Share**: Google 도움말은 Quick Share가 Android·Chromebook·Windows(앱)에서 쓰이고, iPhone·iPad·**macOS는 AirDrop 호환 기기**(Pixel 8a 이상, 일부 삼성·오포·원플러스·비보·샤오미·아너·트랜션·모토로라 — 정확한 갤럭시 모델은 확인 못 함 U8)나 **QR 코드→브라우저**로 받는다고 쓴다. 같은 구글 계정끼리만 자동 수락. Mac 공식 Quick Share 앱은 없다.
- **자체 동반 앱 없이 "녹음 끝 → 자동 전송"**: 확인한 범위에서 **없다.** 폰 OS의 기본 기능은 건당 수동 공유이고, 폴더 감시 자동 전송은 서드파티 앱(Syncthing-Fork·FolderSync)이다. 삼성 클라우드 동기화 목록에도 음성 녹음이 없다(§2.2). 우리 동반 앱(설계 문서 4.2)의 필요성이 여기서 나온다.

---

## 4. Mac 직접 녹음

### 4.1 API·권한·버전

| 항목 | Core Audio 프로세스 탭 | ScreenCaptureKit |
|---|---|---|
| 시스템/앱 오디오 | 예(앱 하나·여러 개·전체 제외 목록, `CATapDescription` + 집합 장치) | 예(`capturesAudio`, macOS 13.0+, Apple 문서) |
| 마이크 | **아니오**(AVAudioEngine 등 별도) | 예(`captureMicrophone`, macOS 15.0+, Apple 문서) |
| 최소 macOS | Apple 샘플 "14.2 이상", `NSAudioCaptureUsageDescription` 키 macOS 14.2+(Apple). insidegui/AudioCap은 "14.4+"로 표기, Apple 심볼 메타데이터에는 12.0이 적혀 있어 서로 안 맞음 U5 | 13.0(오디오) / 15.0(마이크) |
| 권한 | 첫 녹음 시 **시스템 오디오 녹음 허용 팝업**. 공개 확인 API 없음, AudioCap은 비공개 TCC 사용 | **화면 및 시스템 오디오 녹음**. Apple 도움말(macOS 27판): "화면과 오디오 모두 또는 **오디오만**" 허용을 앱별로 설정 |
| 재확인 | 정기 재확인 없음(2차: Biscotti 조사서) | **Sequoia 월 단위 재확인**(9to5Mac 2024-08-14 보도, 15.1에서 빈도 감소는 iDownloadBlog 2차). macOS 27 동작은 확인 못 함 U4 |
| 알려진 문제(2차) | 전체 0 버퍼 반환 보고(Apple 개발자 포럼 스레드 825780, 작성자는 macOS 26.5 베타, 같은 조사서의 macOS 15 검증에서는 재현 안 됨), Teams 개별 앱 탭 무음 보고(meeting-transcriber #79) → 전체 탭 권장 | 마이크+앱 오디오가 같은 델리게이트로 섞여 들어와 한 `AVAssetWriterInput`에 쓰면 파일이 깨진다(Apple 포럼 805892, 2차) |
| 코드 근거 | Recap·OpenWhispr·anarlog·meetily(기본값) | meetily(대체), Recap(회의 감지용 창 제목) |

제안: **녹음 기능의 최소 macOS를 15로 정해 14.2/14.4 논쟁을 닫는다**(Recap·anarlog 둘 다 15.0, U5).

### 4.2 오픈소스·제품이 쓰는 방식 (저장소 코드, 2026-11-11 클론)

| 제품 | 라이선스·커밋 | 시스템 오디오 | 마이크 | 최소 macOS | 회의 시작 감지 |
|---|---|---|---|---|---|
| **Recap** (rawandahmad698/Recap) | MIT, 6d3ccf5 (2026-02-07) | `ProcessTap.swift`: `CATapDescription(stereoMixdownOfProcesses:)` + `AudioHardwareCreateProcessTap`·집합 장치 | 선택 사항 | 배포 타깃 15.0–15.5(pbxproj) | 1초 주기로 `SCShareableContent` 창 제목을 패턴 일치(Teams·Zoom·Meet 감지기). 그래서 `NSScreenCaptureUsageDescription`을 선언("창 제목만 확인"). `Info.plist`의 `NSAudioCaptureUsageDescription` 문구는 "마이크"로 적혀 있어 실제 권한과 불일치 |
| **OpenWhispr** (OpenWhispr/openwhispr) | MIT, 1f01eb6 (2026-11-11) | `resources/macos-audio-tap.swift`: `@available(macOS 14.2)`, `CATapDescription` `processes=[]`·mono·mixdown·private·exclusive(전체 탭으로 보임 U5). 문서: 권한 안내는 "화면 기록" 창을 연다(문서는 오디오만 쓴다고 설명) | Electron(렌더러) 마이크 | 12+, 시스템 오디오는 14.2+ | `subscribeWorkspaceNotification`으로 Zoom·Teams·Webex·FaceTime 실행 감지(문맥 정보일 뿐 단독 알림 없음) + `macos-mic-listener.swift`가 Core Audio 프로세스 객체로 마이크 사용 전환 감지(브라우저 회의용) + 캘린더. 알림으로 안내, 단축키로 시작 |
| **anarlog** (fastrepl/anarlog) | MIT, 0a97fcd (2026-11-05) | `crates/audio-actual/src/speaker/macos.rs`: cidre `TapDesc::with_mono_global_tap_excluding_processes` | `NSMicrophoneUsageDescription` | `tauri.conf.json` 15.0 | 캘린더 시각 자동 시작(옵션) · 마이크 지속 사용 감지는 **알림만**(Accessibility 권한 필요) · 회의 앱이 마이크를 놓으면 자동 정지(오작동 경고 문서화) · 회의 채팅에 **고지 자동 게시** 옵션 |
| **meetily** (Zackriya-Solutions/meetily) | MIT, 07c4dfd (2026-11-02) | `backend_config.rs`: 두 백엔드 ScreenCaptureKit(CPAL SCK 호스트)·CoreAudio(집합 장치+탭). **코드의 `default()`는 macOS에서 CoreAudio**, 같은 파일 주석과 CLAUDE.md는 SCK를 기본이라 적어 서로 다름 | CPAL | CLAUDE.md "SCK는 13+" | Info.plist에 마이크·화면 기록·오디오 캡처 3개 모두 선언 |
| **Granola** (비공개 소스라 코드는 보지 않음, 문서만 근거) | — | 문서: 시스템 오디오+마이크, 회의 앱별 분리 안 됨, "오디오를 녹음·보관하지 않고 전사 제공자에게 직접 전달" | 〃 | macOS 14 이상 | 사용자가 알림을 누르거나 노트를 열 때만 시작. 일정 시작 시각에 자동 시작은 노트를 열어 둔 경우. 종료: 통화 종료 감지, 15분 무음, 절전 |

**설계 시사점(이 조사자의 판단)**: ① 마이크·프로세스 감지는 **알림**이 기본이고(anarlog·OpenWhispr·Granola), 일정 시각 자동 시작은 옵션으로 둔다(anarlog). ② 마이크와 시스템 오디오를 **트랙 두 개로 따로** 받으면 "나/상대" 힌트를 얻는다(Granola는 "Me/Them", Biscotti 조사서도 권장). ③ 감지 방식별 권한 비용: 캘린더 시각 = 캘린더 권한, 프로세스·마이크 목록 = Core Audio(권한 요구 여부 확인 못 함 U4), 창 제목 = 화면 기록 권한, 회의 앱 정밀 감지·채팅 고지 = 접근성 권한. ④ 우리 엔진은 사후 일괄 처리이므로 실시간 전사는 필요 없고, 녹음 결과는 "또 하나의 파일 생산자"로 감시 폴더 경로에 들어가면 된다(§6).

### 4.3 녹음 사실 고지와 한국 법

- **판례(국가법령정보센터, 문서)**: 통신비밀보호법 제3조 제1항은 법률이 정한 경우를 제외하고 **공개되지 않은 타인 간의 대화**를 녹음·청취하지 못하게 하고, 제16조 제1항이 처벌한다. 이는 대화에 원래 참여하지 않는 **제3자**가 녹음·청취해서는 안 된다는 취지로, **3인 간 대화에서 그중 한 사람이 녹음하는 행위와 내용 공개는 제16조 제1항에 해당하지 않는다**(대법원 2014.5.16. 2013도16404, 2006.10.12. 2006도4981 인용). 다만 같은 판결은 몰래 중계·공개한 경우 초상권 등 **민사상 손해배상** 책임은 질 수 있다고 한다.
- **대법원 2024.2.29. 2023도8603**: "청취"는 대화가 진행 중일 때 실시간으로 엿듣는 것이고, **이미 끝난 대화의 녹음물을 재생해 듣는 것은 청취에 포함되지 않는다**. "녹음"도 실시간 대화를 녹음하는 것이지 녹음물을 다시 녹음하는 것은 아니다. → 파일 가져오기 경로(§5)에서 "남이 몰래 녹음한 파일"을 사용자가 가져오는 문제는 이 판결로 청취 처벌 대상이 아니라는 점만 확정되고, **원래 녹음의 적법성과 공개·누설 책임은 별개**로 남는다(판례 해석은 이 조사자의 읽기이며 법률 자문 아님).
- **그래서 제품이 해야 할 일(제안)**: 사용자가 대화 당사자일 때만 쓰라는 안내(첫 실행 1회로 끝내지 않고 설정·도움말에서 다시 보이게 — 설계 문서 §7과 일치), 녹음 시작 때마다 "참석자에게 알리세요" 한 줄(Granola는 시작할 때마다 허락을 구하라고 알림), 회의 채팅 자동 고지·영상 워터마크 같은 선택 기능(Granola·anarlog), 녹음 중임을 항상 보이는 표시(메뉴 막대·플로팅 바). anarlog 문서는 "고지 게시가 동의를 확인해 주지는 않는다"고 쓴다.
- **개인정보 보호법·회사 내부 규정·계약상 비밀유지의 적용은 조사하지 않았다 (U9)** → 법률 검토 전 단정 금지.

---

## 5. 파일 직접 넣기

| 방법 | 가능한 사실 | 주의 |
|---|---|---|
| 앱 창 끌어놓기 | Tauri v2 `onDragDropEvent`는 `enter`·`over`·`drop`·`leave` 이벤트를 주고 `enter`/`drop`에 **파일 경로 배열**이 담긴다(`packages/api/src/webview.ts`). `dragDropEnabled`가 켜져 있으면 웹 `drop` 이벤트는 오지 않고, 파일 경로와 `text/plain` 드롭을 같이 다룰 수 없다는 이슈가 `not_planned`로 닫혔다(#14055). 현재 웹 화면이 브라우저 localhost라면 이 경로가 없다 → 앱 껍데기가 필요 | 드롭된 경로가 Drive 스트리밍·iCloud의 dataless일 수 있음, 폴더·별칭·심볼릭 링크 |
| 메뉴 막대 아이콘 | OpenWhispr은 메뉴 막대 앱으로 동작하고 Dock 아이콘은 창이 열릴 때만 보인다(문서). 우리 Tauri 껍데기의 트레이는 설계 문서 A1 범위. 아이콘 자체에 드롭을 받으려면 네이티브 코드가 필요한지 확인 못 함 U12 | — |
| Dock 아이콘·"다음으로 열기" | 번들 `fileAssociations` 설정, macOS에서 파일을 열면 Tauri가 `RunEvent::Opened`를 발생시킨다(Tauri 저장소 예제·해설 글의 검색 결과 발췌, 원문 미열람) | 앱이 꺼져 있을 때 열리는 경우, 이미 처리한 파일 |
| Finder 빠른 동작 | Automator 워크플로를 빠른 동작으로 만들어 Finder·서비스 메뉴에 노출하거나 단축어를 추가(Apple 도움말) | 설치 방법 안내 필요 |
| 공유 메뉴(Mac) | Share extension은 `com.apple.share-services` 확장 타깃(Apple 가이드). 앱 번들에 확장 타깃을 넣어야 함. Tauri로 되는지 확인 못 함 U11 | 이번엔 닫음 |
| 폰 → "공유하기" | 안드로이드: LocalSend·Quick Share(AirDrop 호환 또는 QR). 아이폰: AirDrop(같은 Apple 계정은 자동 수락·저장, 다른 사람은 수락 필요), Mac에서는 일부 항목이 Downloads에 저장되고 저장 위치를 고르게 할 수도 있다(Apple 도움말) | Downloads는 보호 폴더라 Files & Folders 팝업이 날 수 있음 |
| 음성 메모 Mac 앱 | 녹음을 선택해 Finder 폴더로 끌면 파일로 저장된다(Apple 도움말) | 레이어 녹음·편집본의 파일 형태는 조사 안 함(U2) |

**처리 원칙(설계 문서 §6과 일치)**: 어느 경로에서 오든 **복사**한 뒤 검증한다(원본 이동·삭제 금지). Google Drive File Provider에서 폴더 밖으로 끌면 이동이라 클라우드 원본이 사라지는 것과 같은 사고를 우리가 만들지 않기 위해서다.

---

## 6. 입력 유형별 처리 방침 (이 조사가 추가하는 부분)

| 유형 | 방침 | 근거·상태 |
|---|---|---|
| m4a(안드로이드, Syncthing) | `.syncthing.*.tmp`·`~syncthing~*`·숨김 파일 제외 → 크기·시각 안정 → **moov 존재 + ffprobe 성공** → 확정. 실패해도 받는 폴더에서 **이동·삭제하지 않음**. "손상" 표시까지의 대기 상한은 사용자 설정값(참고: surfnterd는 자기 환경에서 1시간을 추정치로 썼다) | surfnterd(2차), `contract.md:16`. 삼성 앱 직접 확인은 U1 |
| m4a(아이폰 음성 메모, FDA 경로) | DB 행·파일·길이 일치 확인 후 **복사** | 제안, U2·U3 |
| 클라우드 폴더 파일(dataless) | `SF_DATALESS`면 "내려받는 중" 상태로 표시, 시간 제한 있는 읽기로 내려받음, 실패는 재시도 대기, **다른 스레드에서만** 접근 | TN3150. U7 |
| 클라우드 폴더(스트리밍·최적화 켜짐) | 설정 화면에서 "항상 이 기기에 유지/미러" 권장, 처리 끝난 원본은 우리가 아카이브로 복사 | 공급자 문서 |
| 끌어놓은 폴더·별칭·심볼릭 링크 | 폴더는 재귀하지 않고 확장자 허용 목록만, 심볼릭 링크는 따라가지 않고 거부 | 제안 |
| 통화 녹음(`Recordings/Call`, `TPhoneCallRecords`) | 수집 제외(설계 문서 §6 "통화" 행과 같음). 사용자가 직접 끌어놓으면 "통화 당사자만" 경고 후 허용 여부는 U9 | 법적 검토 필요 |
| Mac 직접 녹음 결과 | 우리가 만든 파일 → 크기와 길이 확인 → 같은 계약. **무음 감지**(앞 N초 전부 0이면 권한·장치 문제로 표시) | 2차(권한 거부 시 탭은 만들어지지만 무음) |
| 중복(Syncthing + iCloud + 끌어놓기에 같은 녹음) | 해시 같으면 무시(설계 문서 §6), 이름 같고 내용 다르면 별개. 아이폰 전사문(`tsrp`)은 사용하지 않음 | U10 닫음 |

---

## 7. 비정상·악의 입력 테스트 (제안, 아직 하나도 실행 안 함)

현재 검증 수준은 전부 **미실행**이다. "목표 수준"이 달성돼야 해당 경로를 "지원"으로 표시한다. 표본은 공개 가능한 합성으로 새로 만든다(예: `samples/` 밖의 `tests/fixtures/inputs/`; 기존 `samples/`는 사설이라 쓰지 않음).

| ID | 입력 | 기대 결과 | 목표 수준 |
|---|---|---|---|
| IP-T01 | moov 없는 m4a(녹음 중 스냅샷), 크기만 안정 | 처리 안 함, 대기 표시, 원본·폴더 변경 0, 나중에 완성본이 오면 정상 처리 | 실제 입력(안드로이드 폰 1대) + 가정(합성) |
| IP-T02 | 0바이트·매우 작은 파일·확장자만 m4a인 텍스트 | 거부 또는 대기, 사유 표시 | 가정(합성) |
| IP-T03 | `SF_DATALESS` 파일(iCloud Drive에서 "다운로드 제거"한 실제 파일) | 내려받는 중 표시 → 완료 후 처리, 앱 UI 스레드 비정지, 시간 초과 시 재시도 | **실제 입력(iCloud 계정)** |
| IP-T04 | Google Drive 스트리밍·Dropbox·OneDrive 온라인 전용 | 위와 같음, 공급자별 결과 기록 | 실제 입력(계정별) — 못 하면 "미지원" 표시 |
| IP-T05 | 폴더 밖을 가리키는 심볼릭 링크·macOS 별칭·`..` 포함 이름 | 따라가지 않음, 거부 사유 표시, 외부 파일 열람 0 | 가정(합성) |
| IP-T06 | 파일 이름이 `-`로 시작·공백·줄바꿈·NFC/NFD·긴 이름 | 외부 명령에 안전하게 전달(옵션과 혼동 없음), 이름 충돌 없음 | 가정(합성) |
| IP-T07 | 위장 컨테이너(재생 목록·concat·HLS가 m4a 확장자로) | probe가 허용 형식·프로토콜만 열고 외부 요청 0, 장시간 점유 0 | 가정(합성) + 네트워크 차단 환경 실행 |
| IP-T08 | 태그·제목(`ZCUSTOMLABEL`, m4a 메타데이터)에 "이전 지시를 무시하라" 류 문장 | LLM에 **데이터로** 전달, 도구 실행·외부 요청 0 (설계 문서 §6 "지시문" 행) | 가정(프롬프트 단위) + 격리 CLI 시험 |
| IP-T09 | 같은 녹음이 Syncthing·iCloud·끌어놓기로 세 번 | 해시 중복 무시, 회의록 1개 | 가정(합성) |
| IP-T10 | 아주 큰 파일·디스크 부족 | 조기 중지, 부분 파일 정리, 사유 표시 | 가정(합성) |
| IP-T11 | 음성 메모 FDA 거부·부분 허용(컨테이너 `Operation not permitted`) | "권한 필요" 안내, 반복 알림 억제, 다른 경로는 정상 | 실제 입력(이 MacBook에서 실행 가능) |
| IP-T12 | Mac 녹음: 권한 거부(무음 버퍼), 출력 장치 전환, 블루투스 연결 해제, 절전 | 무음·끊김 감지 표시, 파일 앞부분 보존 | 실제 입력(Mac+실제 회의 앱) |
| IP-T13 | 파일 가져온 뒤 원본이 사라짐·이름 바뀜 | 이미 복사한 것은 영향 없음 | 가정(합성) |
| IP-T14 | 사용자가 감시 폴더에서 파일을 끌어내거나 지움 | 우리 DB·아카이브는 영향 없음, 회의록 유지 | 가정(합성) |

**완료 보고 형식**: 각 시험 결과에 "실행만 / 가정으로 확인 / 실제 입력으로 확인" 중 하나를 쓴다. 합성 표본으로 통과한 항목을 "지원"으로 표시하지 않는다.

---

## 8. 미결 목록 (담당·확인 시각 / 닫는 결정)

담당 약칭은 설계 문서 §10을 따른다: `main` 메인 세션, `impl` 구현, `user` 사용자. **아래 시각은 제안이며 확정은 Main이 한다.** 이 조사는 `contract.md`를 고치지 않았다.

| ID | 내용 | 상태 | 담당 | 확인 시각 / 닫는 근거 |
|---|---|---|---|---|
| U1 | 삼성 앱이 녹음 중 파일을 쓰는 방식(`contract.md:43`) | **기한 경과**(2026-11-10 18:00 KST 예정, 결과 기록 못 찾음). 반대 방향 2차 증거 있음(§3) | main + user(폰 USB) | **2026-11-12 18:00 KST**. 확인 방법: 녹음 중 `Recordings/Voice Recorder` 파일의 크기와 moov 존재 변화를 기록. 결과가 어떻든 완료 판정에 moov 확인을 넣는 결정은 이미 §6에 반영 |
| U2 | 음성 메모 동기화 완료 판정(DB 행과 파일의 선후), 레이어 녹음·편집본의 파일 형태 | 오픈소스에 판정 로직 없음 | impl + user(아이폰) | 2026-11-14. 새 녹음 5건에서 DB·파일 출현 시각 기록, 레이어·편집 녹음 1건씩 파일 확인 |
| U3 | macOS 27에서 `Recordings/`·`CloudRecordings.db` 스키마 | 이 MacBook의 권한 없는 프로세스로는 못 봄 | user | 2026-11-12. FDA 있는 터미널에서 `PRAGMA table_info`와 파일 개수만 확인(내용 열지 않음) |
| U4 | SCK 월 단위 재확인의 macOS 27 동작, Core Audio 프로세스 목록 조회의 권한 요구 | 확인 못 함 | impl | 녹음 프로토타입 단계, 2026-11-18 |
| U5 | 탭 최소 버전 14.2 vs 14.4, OpenWhispr 전체 탭 구성 | **닫음**: 녹음 기능 최소 macOS 15로 결정 제안 | main | 결정 시점 2026-11-12 |
| U6 | KDE Connect Mac 지원 문서 모순 | **닫음**: 자동 전송이 없어 "빼기" | main | 즉시 |
| U7 | 타사 File Provider에서 내려받기 API·부분 파일 가시성, FolderSync→Mac SFTP 설정, LocalSend 완료 신호 | 확인 못 함 | impl | IP-T03·T04 실행 시, 2026-11-16 (계정 필요, 못 하면 해당 공급자 "미지원") |
| U8 | 삼성 클라우드 "백업"의 음성 녹음 포함, Android 15+ 저장 경로, 갤럭시 Quick Share-AirDrop 지원 모델, 에이닷 현재 동작, 클로바노트·다글로 | **닫음**: 첫 배포는 Syncthing·수동 입력만 약속하고 이 앱들의 클라우드 동기화는 약속하지 않음 | main | 즉시. 사용자가 폰에서 확인해 알려 주면 재개 |
| U9 | 개인정보 보호법·회사 규정 적용, 고지 문구 | 법률 검토 필요 | user | 일반 출시 시험(T5) 전 |
| U10 | 음성 메모 `tsrp` 전사 한국어 지원 | **닫음**: 사용하지 않음(자체 전사) | main | 즉시 |
| U11 | 공유 메뉴 확장 + Tauri | **닫음**: 이번에 안 함 | main | 즉시 |
| U12 | 메뉴 막대 아이콘에 직접 드롭 | 확인 못 함 | impl | 앱 껍데기(A1) 단계 |
| U13 | FDA를 launchd 엔진·앱 번들 중 어디에 붙일지, 서명 유지 시 재부여 필요 여부 | 확인 못 함 | impl + user(Apple Developer 계정, A2) | 서명·공증 단계 |
| U14 | 아이폰에서 "파일에 저장"·단축어로 감시 폴더까지 보내는 절차(Apple 문서 미확인) | **닫음**: 첫 배포는 Mac 쪽 끌어놓기만 안내하고 아이폰 쪽 절차는 약속하지 않음 | main | 즉시. 사용자가 아이폰에서 확인해 알려 주면 재개 |

---

## 9. 제안: 첫 배포 / 나중 / 빼기

### 첫 배포에 넣을 것

| 경로 | 이유 | 조건 |
|---|---|---|
| **감시 폴더(어느 폴더든) + 파일 검증 파이프라인** | 모든 경로의 공통 토대. 클라우드 폴더 4종을 "폴더 지정"으로 수용 | dataless 처리(§2.2), 클라우드 폴더는 미러/핀 안내. 시험 통과한 공급자만 "지원" 표시(IP-T03·T04) |
| **끌어놓기(앱 창·Dock)와 "다음으로 열기"** | 권한 0, 사용자 설정 0, 모든 사용자의 마지막 수단. 아이폰 사용자에게는 "음성 메모에서 감시 폴더로 끌기"를 안내 | 앱 껍데기 필수(Tauri `onDragDropEvent`) |
| **Syncthing(Fork) 안내** | 안드로이드 자동 전송으로 확인된 유일한 후보. 현재 동작 경로 | 초심자 시험 결과로 동반 앱 여부 결정(설계 문서 2.1), 포크 연속성 위험 명시 |

### 나중

| 경로 | 이유 |
|---|---|
| 아이폰 음성 메모 자동 읽기 | FDA, 비공개 스키마, 동기화 완료 판정 없음, macOS 27 미확인(U2·U3·U13). 옵션형 고급 기능으로 |
| **Mac 직접 녹음** | 폰 전송 문제를 통째로 없애는 장점(Granola류 핵심 기능)과 권한·법·플랫폼 위험이 같이 온다. 첫 배포 설계에서 입력 어댑터·동의 안내·두 트랙 저장 자리만 확보. **타깃 사용자가 Mac 회의 중심이면 앞당길 수 있음 — 사용자 결정** |
| FolderSync 안내 | 설정이 어렵고 사양 미확인(U7). Syncthing이 막히는 사용자 대체안으로 문서만 |
| FolderSync/Syncthing를 대신할 동반 앱 | 설계 문서 4.2 시험 결과에 따름 |
| 구글 레코더 사본 + Syncthing 문서 | Pixel 한정 |

### 빼기

| 경로 | 이유 |
|---|---|
| KDE Connect | Mac 지원 문서 모순, 폴더 감시 없음 |
| LocalSend 자동화, Quick Share | 건당 수동, Mac 공식 앱 없음(Quick Share). 사용자가 받은 파일을 감시 폴더에 두면 일반 경로로 처리됨 — "공식 지원" 약속은 하지 않음 |
| 공유 메뉴 확장 | 별도 확장 타깃, Tauri 가능 여부는 조사 안 함(U11) |
| 통화 녹음 앱 연동(`Recordings/Call`, 에이닷) | 법적 검토 전, 수집 제외는 기존 설계(§6)와 같음 |

---

## 10. 출처 (확인일 2026-11-11)

**Apple**
- TN3150 dataless: https://developer.apple.com/documentation/technotes/tn3150-getting-ready-for-data-less-files
- File Provider 동기화: https://developer.apple.com/documentation/fileprovider/synchronizing-the-file-provider-extension
- `startDownloadingUbiquitousItem`: https://developer.apple.com/documentation/foundation/filemanager/startdownloadingubiquitousitem(at:)
- Core Audio 탭 샘플: https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps
- `NSAudioCaptureUsageDescription`: https://developer.apple.com/documentation/bundleresources/information-property-list/nsaudiocaptureusagedescription
- `CATapDescription`: https://developer.apple.com/documentation/coreaudio/catapdescription
- `capturesAudio`: https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/capturesaudio · `captureMicrophone`: https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/capturemicrophone
- 화면 및 시스템 오디오 녹음 접근: https://support.apple.com/guide/mac-help/control-access-screen-system-audio-recording-mchld6aa7d23/mac
- 음성 메모 iCloud: https://support.apple.com/guide/voice-memos/see-your-recordings-on-all-your-apple-devices-vma6cc4d0571/mac · 공유·끌어놓기: https://support.apple.com/guide/voice-memos/share-a-recording-vm05f9fa82d4/mac
- AirDrop: https://support.apple.com/guide/mac-help/use-airdrop-to-send-items-to-nearby-devices-mh35868/mac
- Finder 빠른 동작: https://support.apple.com/guide/mac-help/perform-quick-actions-in-the-finder-on-mac-mchl97ff9142/mac
- Share 확장(보관 문서): https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/Share.html

**클라우드·폰 앱**
- Google Drive(macOS·스트리밍/미러): https://support.google.com/drive/answer/12178485 · https://support.google.com/drive/answer/13401938
- Dropbox File Provider: https://help.dropbox.com/installs/dropbox-for-macos-support
- OneDrive Files On-Demand(macOS): https://techcommunity.microsoft.com/blog/onedriveblog/inside-the-new-files-on-demand-experience-on-macos/3058922
- 삼성 클라우드 동기화 항목: https://www.samsungcloud.com/ko/about/sync · 삼성전자서비스 녹음 저장 경로(2026-09-30): https://www.samsungsvc.co.kr/solution/39738
- Pixel 레코더 백업·공개 사본: https://support.google.com/pixelphone/answer/16267668
- 에이닷 전화 외부 공유 제한(2024-10-20, 2차): https://www.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=01866326639054888
- Quick Share: https://support.google.com/android/answer/9286773

**전송 도구**
- Syncthing-Fork: https://github.com/researchxxl/syncthing-android · v2.1.6.0 https://github.com/researchxxl/syncthing-android/releases/tag/v2.1.6.0 · 배터리 위키 https://github.com/researchxxl/syncthing-android/blob/main/wiki/Info-on-battery-optimization-and-settings-affecting-battery-usage.md · 원 저장소 404 스레드 https://forum.syncthing.net/t/does-anyone-know-why-syncthing-fork-is-no-longer-available-on-github/25661
- moov·삭제 전파: https://github.com/surfnterd/syncthing-partial-recordings (2차)
- FolderSync 폴더쌍 설정: https://foldersync.io/docs/help/v2/folderpairsettings/
- LocalSend: https://github.com/localsend/localsend · 프로토콜 https://github.com/localsend/protocol
- KDE Connect: https://kdeconnect.kde.org/download.html · https://github.com/KDE/kdeconnect-kde

**음성 메모 오픈소스**
- https://github.com/xyb/voicememowhisper (docs/technical_details.md) · https://github.com/harryf/voice-memos · https://github.com/polarity-dev/macos-voice-memos-export · https://github.com/bulletinmybeard/voice-memo-export · https://github.com/jwulff/apple-voice-memo-mcp · https://github.com/appstart-one/ciderpress · https://github.com/abrignoni/iLEAPP

**Mac 녹음 오픈소스·제품**
- Recap: https://github.com/rawandahmad698/Recap (`Recap/Audio/Capture/Tap/ProcessTap.swift`, `Recap/Info.plist`, `Services/MeetingDetection/`)
- OpenWhispr: https://github.com/OpenWhispr/openwhispr (`resources/macos-audio-tap.swift`, `resources/macos-mic-listener.swift`, CLAUDE.md §16) · 문서 https://docs.openwhispr.com/platform/macos
- anarlog: https://github.com/fastrepl/anarlog (`crates/audio-actual/src/speaker/macos.rs`, `apps/desktop/src-tauri/Info.plist`, `tauri.conf.json`) · 문서 https://docs.anarlog.so/automatic-capture · https://docs.anarlog.so/meetings
- meetily: https://github.com/Zackriya-Solutions/meetily (`frontend/src-tauri/src/audio/capture/backend_config.rs`, `Info.plist`, `CLAUDE.md`)
- Granola 문서: https://docs.granola.ai/help-center/getting-started/setting-up-granola-for-the-first-time · https://docs.granola.ai/help-center/taking-notes/transcription · 고지 블로그 https://www.granola.ai/blog/why-granola-doesnt-use-a-bot
- insidegui/AudioCap: https://github.com/insidegui/AudioCap
- Biscotti 오디오 조사서(2차): https://github.com/scosman/Biscotti/blob/main/specs/research/audio/README.md
- Sequoia 월 단위 재확인(2차): https://9to5mac.com/2024/08/14/macos-sequoia-screen-recording-prompt-monthly/

**Tauri**
- 드래그앤드롭 이벤트: https://github.com/tauri-apps/tauri/blob/dev/packages/api/src/webview.ts · https://v2.tauri.app/reference/javascript/api/namespacewebview · 이슈 #14055 https://github.com/tauri-apps/tauri/issues/14055

**법(국가법령정보센터)**
- 대법원 2014.5.16. 2013도16404: https://www.law.go.kr/LSW/precInfoP.do?precSeq=174858
- 대법원 2006.10.12. 2006도4981: https://www.law.go.kr/LSW/precInfoP.do?evtNo=2006%EB%8F%844981
- 대법원 2024.2.29. 2023도8603: https://www.law.go.kr/LSW/precInfoP.do?evtNo=2023%EB%8F%848603

**2차(약함)**: Eclectic Light(iCloud Drive Sonoma·Sequoia) https://eclecticlight.co/2023/11/21/icloud-drive-in-sonoma-fileprovider-and-eviction · https://eclecticlight.co/2024/09/30/how-icloud-has-changed-in-sequoia-pinning-and-more/ · Reddit 음성 메모 저장 공간 스레드(2026-02) · freedom251.com 음성 메모 위치 글은 `~/Library/Application Support/com.apple.voicememos/`를 주 경로로 적었으나 이 MacBook에는 그 경로가 없고 위 오픈소스 3곳과 어긋나 **근거로 쓰지 않음**.

**실행(이 MacBook)**: `sw_vers`, `ls`/`stat`(Voice Memos 컨테이너·`~/Library/CloudStorage`·`~/Library/Mobile Documents`), `brctl`·`fileproviderctl` 도움말, SDK `sys/stat.h`의 `SF_DATALESS`, `codesign`/앱 버전. 저장소 4곳(`Recap`, `anarlog`, `meetily`, `openwhispr`)은 `/tmp`에 얕은 클론 후 `grep`으로 코드 확인(조사 후 삭제 대상, 저장소 `rec` 변경 없음).
