# M1-A 41f0c34 읽기 전용 리뷰

- 기준: `docs/contracts-v2.md` 1.3–1.5, 2.2, 3.2, 4절. 지적 줄 번호는 **41f0c34 기준**이다.
- 판정(overall_correctness): **incorrect**. 설명(explanation): claim 원자성·소유권 검사와 기본 캐시/프로세스 종료 구조는 갖췄지만, 제외와 실패의 경합, 이행 데이터의 식별·승격, 캐시 revision, 기본 cutoff에 수정할 결함이 있다. 신뢰도(confidence): **0.96**.
- 검증 수준: **정적 코드 추적, 실행 미확인**. 아래 재현 결과는 모두 `[INFERENCE]`이며 실제 실행 결과가 아니다. 테스트·빌드·실녹음 처리를 실행하지 않았고 저장소 파일을 수정하지 않았다. 배포·SSH·운영 데이터 접근도 하지 않았다.
- 기존 `docs/acceptance-v2.md`의 “98 통과 / 가정”은 문서에 기록된 결과이며 이번 리뷰가 실행하거나 확인한 결과로 인용하지 않는다.

## 발견 사항

### 1. [P1] 기본 cutoff를 프로세스 시작이 아닌 설치 시각에 고정하라

`quietclerk/config.py:15` → **문제:** `_INITIAL_SINCE`가 매 Python 프로세스 시작 시각으로 다시 계산되어, `since`를 생략한 정상 설정에서 설치 후 녹음까지 `before_cutoff`로 제외된다(3.3절). **재현 시나리오:** `QC_SINCE`와 TOML의 `since` 없이 첫 tick을 실행한 뒤 녹음하고, 그 녹음 시작 시각보다 늦은 분에 다음 tick을 시작한다. `tick.main → config.load → intake.scan`은 새 시작 시각을 cutoff로 사용하고 `when < since`에서 작업을 skipped로 등록하며 아카이브를 만들지 않는다. 매분 재시작되는 tick과 60초 안정 대기 조건에서는 정상 신규 파일도 이 경로에 들어간다. **고침 제안:** 설치/최초 초기화 시각을 영속 저장하고 이후 load는 같은 값을 읽도록 하며, 누락된 설정을 매번 현재 시각으로 대체하지 않는다. `tests/conftest.py`가 항상 `QC_SINCE=1970-01-01 00:00`을 넣고 E2E도 이를 주입하므로 현재 테스트는 이 경로를 검출하지 못한다. 신뢰도 0.99.

### 2. [P2] 실패를 확정할 때도 보류 중인 제외 요청을 처리하라

`quietclerk/store.py:326-335` → **문제:** `fail()`은 `exclude_requested`를 확인하지 않은 채 running을 retry_wait/failed로 바꾸고 active run을 해제한다. 실행 중 제외 요청과 단계 오류/timeout이 겹치면 `retry_wait + exclude_requested=1`이 남아 `claim()`의 필터에 영구히 걸리며, 사용자에게 약속한 `skipped(user_excluded)`로 끝나지 않는다(2.2절). **재현 시나리오:** claim → convert 실행 중 다른 연결에서 `exclude()` → convert가 timeout/일반 오류 → `Executor.execute`의 실패 경로가 `store.fail()` 호출. 정상 다음 단계의 checkpoint에는 도달하지 않고 attempts까지 증가한다. 그 뒤 `recover()`도 running 작업만 찾으므로 이 상태를 정리하지 않는다. **고침 제안:** `complete()`와 마찬가지로 `fail()`의 소유권 확인 직후 같은 트랜잭션 안에서 제외 요청을 우선 처리하고 `_skip_excluded()`로 닫는다. 성공·중단 시 제외 테스트는 있으나 실패/timeout과의 경합 테스트는 없다. 신뢰도 0.99.

### 3. [P2] skipped 작업을 경로 문자열만 보고 재대기시키지 말라

`quietclerk/store.py:173-176` → **문제:** `request_process()`는 skipped 작업의 `archive_path`가 비어 있지 않으면 검증 없이 queued로 바꾼다. 그러나 v1은 정책상 skipped 작업에도 실제로 만들지 않은 archive 경로를 기록했고, 새 이행 도구도 그 문자열을 그대로 보존한다. 따라서 재검증·아카이브 확정이 필요한 작업이 승격 관문을 우회한다(3.2·5.5절). **재현 시나리오:** `test_migrate_v1.fixture`와 같은 `skipped(before_cutoff/too_short)` + `/virtual/archive/.../source.m4a` 행을 이행한 뒤 `request_process()`를 호출한다. 원본이 없어도 queued가 되고 다음 convert에서 실패하여 재시도 예산을 소진한다. 계약상 원본이 없으면 skipped를 유지해야 한다. **고침 제안:** skipped의 처리 요청은 검증 완료 경로인 `promote()`로만 전이하게 하고, 과거 경로 문자열을 검증 증거로 사용하지 않는다. 현재 `test_allowed_process_transitions_reset_counters`는 가짜 non-null archive를 넣은 skipped의 직접 처리 요청을 성공으로 기대하고, promotion 테스트는 archive=NULL만 검사해 이 우회를 놓친다. 신뢰도 0.99.

### 4. [P2] v1 files의 절대 경로를 v2 상대 경로로 이행하라

`quietclerk/migrate_v1.py:81-86` → **문제:** `files_v2.path`에 구 `row['path']`를 그대로 저장하지만, 구 intake는 `str(p)`로 절대 경로를 저장했고 새 intake는 `p.relative_to(inbox)`를 키로 사용한다. 이행된 files 행을 새 스캐너가 찾지 못하여 같은 실제 파일에 서로 다른 두 행을 만들고 안정 대기·등록 상태를 새로 시작한다(3.1·3.2절). **재현 시나리오:** 구 DB에 절대 경로 `/tmp/fixture/inbox/a.m4a`, `handled=1`을 넣고 이행한 뒤 동일 inbox를 스캔한다. `store.observe('a.m4a', ...)`가 기존 절대 경로 행을 갱신하지 않고 새 waiting 행을 삽입하고, 이후 같은 해시를 duplicate로 따로 기록한다. **고침 제안:** 확인된 기존 inbox 기준 상대 경로로 변환하고 경로 밖/충돌은 명시적으로 중단한다. 실제 구 intake가 만든 절대 경로 fixture로 이행 후 scan까지 연결해 files 행 하나와 상태 연속성을 검사한다. 현재 migration fixture는 애초에 상대 파일명만 저장하여 이 소비자 경계 불일치를 가린다. 신뢰도 0.99.

### 5. [P2] 파일명만으로 v1 파일의 해시와 거부 사유를 확정하지 말라

`quietclerk/migrate_v1.py:79-86` → **문제:** `next(... source_name == basename ...)`가 같은 이름의 첫 작업을 현재 files 행에 연결한다. v1은 내용 해시별 작업을 보존하므로 같은 이름으로 내용을 바꾸어 두 번 처리하면 jobs에는 여러 해시가 있고 files에는 마지막 관측 하나만 있다. 이를 첫 작업의 sha256/reject_reason으로 확정하면 파일 식별과 거부 상태를 잘못 이행한다(3.2절의 모르는 SHA는 NULL). **재현 시나리오:** 같은 `a.m4a`의 첫 내용 H1은 decode 거부, 나중 내용 H2는 정상 처리한 구 DB를 만든다. 이행은 첫 H1 작업을 고르고 마지막 정상 files 행을 `rejected(decode), sha256=H1`로 저장한다. 아직 처리하지 않은 변경 파일(`handled=0`)도 옛 이름만 같으면 옛 해시를 붙인다. **고침 제안:** 이름은 후보 검색에만 쓰고 내용 대응이 입증되지 않으면 sha256을 NULL로 유지하며, 임의 후보의 거부 사유도 복사하지 않는다. 같은 이름·다른 해시 및 handled=0 fixture를 추가한다. 현재 fixture는 모든 source_name이 달라 이 경우를 검사하지 않는다. 신뢰도 0.99.

### 6. [P2] 실제 모델 revision을 캐시 키에 포함하라

`quietclerk/executor.py:234-243` → **문제:** 기본 registry가 모든 모델의 revision을 항상 `None`으로 기록하므로, 동일 모델 ID의 실제 가중치 revision이 바뀌어도 diarize/transcribe/second_pass의 params는 같다. `artifacts.find → reusable`은 그 params와 출력 해시만 비교하므로 이전 모델 결과를 그대로 재사용한다(4.3절의 모델 ID@revision 조건). **재현 시나리오:** 모델 ID M의 revision R1으로 결과를 만든 뒤 같은 ID M의 R2를 내려받고 auto/resume을 요청한다. 현재 `models.prefetch()`는 `snapshot_download(repo)`로 revision을 고정하지 않으며, registry의 revision은 둘 다 None이어서 이전 메타가 적중한다. **고침 제안:** 실행에 사용하는 로컬 모델 snapshot의 불변 revision을 해결해 params에 넣고 워커가 동일 snapshot을 사용하도록 연결한다. 현재 캐시 무효화 테스트는 fake registry의 임의 `version` 숫자를 바꾸는 방식이라 비교 엔진은 검사하지만 실제 registry의 누락된 revision은 검출하지 못한다. 신뢰도 0.97.

## 우선순위별 확인 결과와 테스트의 실효성

### 동시성·트랜잭션·소유권

- `store.claim`은 BEGIN IMMEDIATE 안에서 선택 → 조건부 UPDATE/rowcount → runs 삽입 → active_run_id 갱신을 끝낸다. INSERT/후속 UPDATE 예외 시 transaction의 rollback 경로가 있다.
- `_owned`가 job 상태·active_run_id·claimed_by를 함께 검사하고 단계 시작/주석/종료, 완료/실패 쓰기 전에 같은 쓰기 트랜잭션에서 호출된다. stale owner의 DB 쓰기 차단 구조를 확인했다.
- `test_two_connections_claim_only_one_run`은 실제 별도 SQLite 연결 두 개와 barrier를 사용한다. `test_sigkill_recovery_at_transaction_boundaries`는 실제 자식 프로세스를 kill하고 DB를 다시 열어 rollback/복구를 검사한다. 이 둘은 mock 반환값을 되읽는 테스트가 아니다.
- rowcount!=1 분기를 직접 강제하는 테스트는 없지만 동시 claim 패자의 run=0과 run 삽입 중 kill의 원자성 검사는 있다.
- recover는 attempts를 늘리지 않고 interrupt_count만 증가시키며 세 번째에서 failed로 닫는다. 정상 종료/사용자 재요청의 초기화 경로도 있다. 단, 이름이 `test_blocked_failure_and_success_reset_interrupt_count`인 테스트는 실제로는 complete 성공 경로만 검사한다. blocked/일반 실패에서의 interrupt reset 조합을 그 이름만으로 확인했다고 주장하면 안 된다.
- blocked 상태는 claim의 시간 조건만으로 풀리지 않는다. 직접 테스트가 있다. 제외+실패 조합은 발견 사항 2처럼 빠져 있다.

### v1 이행

- `Connection.backup()`으로 별도 .part DB를 완성한 뒤 rename한다. WAL-only 변경을 만든 상태에서 backup DB를 읽는 테스트는 유효한 검증 설계다.
- *_v2 생성·데이터 변환·DROP·RENAME·schema_version 저장이 같은 트랜잭션 안에 있다. `converted`, `swapped` fault 예외 뒤 v1 dump 동일성 및 재실행 검사가 있다.
- 이행 fault 테스트는 Python 예외/rollback 시험이지 이행 프로세스 SIGKILL 시험은 아니다. 둘을 같은 증거로 부르지 않는다.
- 모르는 테이블·다른 컬럼·상위 버전 거부와 bytes/디렉터리 불변성 테스트가 있다. v2 재실행 no-op도 검사한다.
- `failed_retryable`, `failed_final`, `running`, rejected, 경고 목록, recorded_at, legacy, current_run_id 매핑은 코드와 fixture에 연결되어 있다. 그러나 실제 v1의 절대 경로와 이름 재사용, skipped 가상 archive를 통한 후속 처리 요청은 발견 사항 3–5처럼 통합 검사가 없다.

### 캐시·산출물

- data rename 후 meta rename, 메타 없는 데이터 거부, inputs/params/output_sha256 비교, reused 기록의 sent_fields=[], mode별 금지, legacy 금지를 확인했다.
- 하드링크 재사용 후 새 임시 inode를 rename하여 구 결과를 보존하는 테스트는 실제 inode/내용을 비교한다. 복사 fallback만 os.link 실패를 주입한다. 이 부분은 단순 토톨로지가 아니다.
- 합성 registry 기반 cache 테스트는 일반 비교·전파 엔진의 단위 검증으로는 유효하다. 다만 실제 registry의 모델 revision과 언어 키가 올바르다는 증거는 아니다. 언어 감지/워커 구현은 계약의 C 범위이므로 여기서는 그 미구현 자체를 별도 결함으로 세지 않았다.
- 메타 commit 도중 실제 프로세스 kill/ENOSPC 시험은 현재 목록에 없다. missing_meta 시험을 “쓰기 중단 재현”으로 확대 해석하지 않는다.

### 프로세스 제한 시간·소비자 라우팅

- `procs.run`은 start_new_session=True로 시작하고 TimeoutExpired 시 그룹 SIGTERM → grace → SIGKILL → communicate를 수행한다. 부모가 먼저 종료해도 그룹 존재를 별도로 확인하는 루프다.
- 테스트는 실제 Python 자식/손자, SIGTERM 무시, 부모만 TERM에 종료하는 조합을 사용한다. executor timeout 시험은 합성 StageTimeout을 던지는 별도 단위 시험이다.
- `_model('diarize'/'asr'/'alt')`가 실제 `models.STAGES`의 같은 키로 라우팅되는 것을 확인했다. 일반 CLI 호출은 `_legacy_llm → llm.complete → wrapped engine → procs.run`, timeout은 stage timeout 기록과 fail로 이어진다.
- 신규 Excluded/Blocked/NoSpeech/StageFailure/LostClaim은 executor의 명시적 예외 분기로 전달된다. NoSpeech가 남기는 산출물은 ok=False다. 교정 timeout 원문 유지와 분류/요약 timeout 전파도 소비자까지 추적했다.
- D의 게시 기록 생성/복구 구현, C의 언어 처리, E의 전체 provider 오류 정책은 계약 10.1절상 다음 묶음이다. 아직 없는 기능 자체나 v1 렌더러의 기존 동작을 A가 새로 만든 버그로 보고하지 않았다.

## 검증 수준·제품 게이트

- 이번 리뷰: **정적 읽기만 / 실행 미확인**. “실행만”, “가정으로 확인”, “실제 입력으로 확인” 중 어느 실행 수준도 새로 획득하지 않았다.
- 기존 테스트 소스: 실제 SQLite·파일 시스템·프로세스 시험과 합성 모델/제공자 시험을 구분해 위에 기술했다. 실모델/실제 제공자 E2E 증거는 아니다.
- 도구로 확인한 현재 작업 트리에는 `samples/`와 `samples/audio/`의 m4a 4개가 존재한다. 디렉터리·파일 목록만 보았으며 내용을 읽거나 실행 입력으로 쓰지 않았다. 따라서 “표본 경로 자체 없음”과 “검증 완료” 어느 쪽으로도 단정하지 않는다. 읽은 samples 루트 목록에는 매니페스트가 없으며, 출처·권리·해시·기대 결과 연결은 별도로 필요하다.
- 삼성 녹음 중 파일 쓰기 미결은 계약 12절에 이미 `main + user`, `2026-11-10 18:00 KST`로 담당·확인 시각이 있다. 이번 읽기 전용 리뷰가 그 실험을 닫은 것은 아니다.

## 다음 묶음 착수 전 반드시 고칠 것

1. store의 제외+실패 전이와 skipped 승격 관문을 고쳐 B/API가 잘못된 상태 계약을 이어받지 않게 한다.
2. 이행 fixture를 실제 v1 절대 경로·같은 이름 다른 내용·없는 가상 archive까지 확장하고, 이행 후 scan/request_process 소비자 경로를 연결한다.
3. 기본 since를 설치 시각으로 고정하고, 모델 revision이 실제 cache params와 실행 모델에 일치하게 한다.
4. 메인 검증은 위 6개 재현을 추가한 `test_store.py`, `test_migrate_v1.py`, `test_config.py`, `test_executor.py`와 기존 `test_procs.py`를 대상으로 수행한다. 이번 리뷰는 이를 실행하지 않았다.
