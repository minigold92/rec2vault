# 독립 검토: 커밋 67e5071 (Codex CLI 0.170, read-only, 2026-11-23)
P0는 발견하지 못했습니다. **P1 결함 때문에 현재 방식의 자동 `verified` 부여는 중단을 권고합니다.**

- **P1 — 미끼 시험은 도구 접근 불가능을 증명하지 못합니다.**
  근거: [decoy.py:122](quietclerk/providers/decoy.py:122), [decoy.py:132](quietclerk/providers/decoy.py:132). 가짜 CLI가 파일을 읽고 내용을 숨기거나 Base64로 출력해도 `passed=True`를 재현했습니다. 파일 읽기는 내용·mtime을 바꾸지 않습니다.
  고침: 미끼를 회귀 검사로만 사용하고, 도구 선언·실행 권한의 차단을 확정할 수 없는 버전은 계속 `unverified`로 유지하십시오.

- **P1 — MCP 허용 목록이 서버와 호출 완료를 검증하지 않습니다.**
  근거: [decoy.py:68](quietclerk/providers/decoy.py:68), [decoy.py:98](quietclerk/providers/decoy.py:98). 다른 서버의 `list_mcp_resources`도 빈 결과면 통과하며, `item.started`만 있고 완료되지 않은 호출도 `turn.completed`와 함께 통과합니다.
  고침: 내장 서버 식별자·인자·오류 필드를 엄격히 검사하고, 호출 ID별 시작→완료 상태를 추적하십시오. 식별을 보장하지 못하면 모든 MCP를 거부하십시오.

- **P1 — 시험의 허용 목록이 실제 호출에는 적용되지 않습니다.**
  근거: [cli.py:126](quietclerk/providers/cli.py:126). 운영 파서는 네 종류만 금지합니다. 가상 `file_read` 이벤트를 넣으면 정상 응답으로 수락했습니다. [추정] 새 CLI가 다른 형식으로 도구 사용을 보고하면 탐지를 우회합니다.
  고침: 운영에도 엄격한 이벤트 스키마와 완료 조건을 적용하십시오. 사후 이벤트 검사는 실행 전 권한 차단을 대체할 수 없습니다.

- **P1 — 검증 기록이 시험한 바이너리와 정확한 버전을 식별하지 못합니다.**
  근거: [cli.py:55](quietclerk/providers/cli.py:55), [cli.py:70](quietclerk/providers/cli.py:70), [decoy.py:180](quietclerk/providers/decoy.py:180). 조회·시험·실호출마다 실행 파일을 다시 찾습니다. `0.171.0-beta.1`이 `0.171.0`으로 기록되는 것도 재현했습니다.
  고침: 전체 버전·실행 파일 정체성·차단 설정을 기록에 결합하고 호출 직전 재확인하십시오. [추정] 실제 업데이트 중 A/B 교체 공격은 미실행했습니다.

- **P1 — 실패한 시험도 설정으로 우회할 수 있습니다(기존 경로).**
  근거: [providers/__init__.py:200](quietclerk/providers/__init__.py:200), [providers/__init__.py:242](quietclerk/providers/__init__.py:242). `providers.allow_unverified=["codex"]`이면 실패 기록과 무관하게 호출됩니다. 가짜 제공자로 전송 경로를 재현했습니다.
  고침: 제시된 제품 원칙에 맞춰 Codex의 미확인 예외를 제거하고 계약 8.2·화면도 함께 수정하십시오.

- **P2 — 일시 실패가 해당 버전의 자동 재시험을 영구 차단합니다.**
  근거: [decoy.py:123](quietclerk/providers/decoy.py:123), [decoy.py:214](quietclerk/providers/decoy.py:214). timeout·인증·레이트 리밋 실패도 기록되면 이후 건너뜁니다. timeout 후 다음 자동 시험이 없는 것을 재현했습니다.
  고침: 보안 실패와 실행 불능을 구분하고, 일시 실패는 제한된 백오프로 재시험하되 통과 전까지 차단하십시오.

- **P2 — 자동 해제가 시험 시작 당시의 정책을 재사용합니다.**
  근거: [decoy.py:205](quietclerk/providers/decoy.py:205), [decoy.py:182](quietclerk/providers/decoy.py:182). 시험 도중 동의·순서를 철회하고 로컬 전용으로 바꿔도 작업이 `queued`로 풀리는 것을 재현했습니다. 이후 전송은 새 실행의 정책 검사로 막힙니다.
  고침: 해제 직전에 최신 설정과 제공자 객체를 다시 읽어 동의·순서·로컬 조건을 확인하십시오.

- **P2 — 사용자가 일시정지한 정상 대기도 정체 경보가 됩니다.**
  근거: [stuck.py:56](quietclerk/stuck.py:56), [store.py:229](quietclerk/store.py:229). paused 상태의 13시간 `queued` 작업이 정체로 집계됩니다.
  고침: 일시정지 시간을 정체 계산에서 제외하거나 의도된 대기로 별도 표시하십시오.

- **P2 — 폴링 사이의 실제 진전을 놓쳐 정체 시계가 초기화되지 않습니다.**
  근거: [stuck.py:64](quietclerk/stuck.py:64). 두 관측 사이에 `retry_wait→running→retry_wait`가 발생하면 이전 `since`가 유지됩니다. 새 대기가 한 시간인데 12시간 정체로 집계되는 것을 재현했습니다.
  고침: 상태 전이 트랜잭션에서 전이 시각·세대를 기록하십시오.

- **P2 — 파일 이름이 ops와 로그로 나갑니다(기존 경로).**
  근거: [serve.py:152](quietclerk/serve.py:152), [executor.py:102](quietclerk/executor.py:102). `job_done`·`job_failed`와 시작 로그에 `source_name`이 들어갑니다.
  고침: 작업 ID·고정 오류 코드로 대체하십시오. 새 시험 알림에는 응답 본문 대신 버전·이유 코드만 전달합니다.

확인: 명령 인자는 `Codex.command`를 공유합니다. 수동 API에는 세션·Origin·CSRF 검사가 적용되고, 설정을 통한 검증 기록 직접 쓰기는 거부됩니다.
운영: 자동 시험은 단일 실행자를 120초 동안 점유하며 상태 조회·종료 유예 시간은 별도입니다. 시험 예외는 잡지만, 감시 스레드의 정체 계산 예외는 서비스 종료로 이어집니다([serve.py:111](quietclerk/serve.py:111)).
검증 수준: **가정으로 확인**—메모리 가짜 CLI·SQLite 재현. 실제 Codex·실제 회의 입력·전체 테스트는 미검증이며, 파일 수정은 없습니다.