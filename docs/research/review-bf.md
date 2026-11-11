# QuietClerk M1 B–F1 계약 리뷰

## 판정·범위·검증 수준

- overall_correctness: **incorrect**. explanation: 새 게시 경로의 제외·복구 처리와 API 삭제/재처리 경합이 안전 계약을 깨며, serve와 tick의 잠금도 서로 배타적이지 않다. 일반 볼트 이행, bootstrap 갱신, 제공자 복구 및 동시 호출에도 수정할 결함이 있다. confidence: **0.97**.
- 대상: `c328904..HEAD`, 특히 `0dad8aa`(C), `dd8e586`(D), `17e5d81`(F1), `e14e973`(통합 수정). 기준은 `docs/contracts-v2.md` 1–9·10.3·11절이다.
- **B와 E 구현 자체는 이미 기준 커밋에 들어 있다.** `git diff --name-only c328904..HEAD -- quietclerk/intake.py quietclerk/providers quietclerk/probe.py quietclerk/backfill.py quietclerk/quarantine.py`는 변경 파일을 출력하지 않았다. 해당 코드는 소비자 경계까지 읽었으며, 아래 B/E 관련 지적은 새 F1 호출 경로가 도입한 문제에 한정했다. A 이전 리뷰를 다시 지적하지 않았다.
- **검증 수준: 정적 코드 추적 / 실행 미확인.** 아래 결과 예상은 전부 **[추정][INFERENCE]**이고, 실제 실행으로 재현했다는 뜻이 아니다. 읽기 전용 리뷰의 명령 제한에 따라 git diff/log/show 및 파일·검색 도구만 사용했다. 테스트·빌드·모델·CLI·HTTP 요청·운영 데이터 접근은 하지 않았다. 따라서 이번 리뷰에서 새로 획득한 ‘실행만 / 가정으로 확인 / 실제 입력으로 확인’ 결과는 없다. 기존 인수 문서의 테스트·E2E 결과는 그 문서의 기록일 뿐 이번 리뷰의 실행 증거가 아니다.
- P0: 없음. **P1 4건, P2 7건**, P3: 없음. 각 지적의 주 위치는 이번 diff 안이며 10줄 이내다.

## P1 — G 전에 우선 수정

### F01. 게시 완료 트랜잭션에서도 보류 중인 제외를 처리하라

- 주 위치: `quietclerk/store.py:503-509`; priority: 1; confidence: 0.99.
- **문제·영향 [추정]:** 게시 직전 마지막 checkpoint 이후 `/exclude`가 `exclude_requested=1`을 기록해도 새 `commit_publication()`은 소유권만 검사하고 `_commit_publication()`으로 무조건 done을 확정한다. 결과는 `done + exclude_requested=1`이며 제외 요청이 반영되지 않는다. 재시작 시 renamed 게시를 마무리하는 경로도 같은 함수를 사용해 제외를 무시한다. 기존 `complete()`의 제외 우선 처리를 D의 새 완료 경로가 우회한 회귀다(계약 2.2).
- 근거: `notes/__init__.py:220-229`의 checkpoint→rename→commit, `store.py:200-208`의 running 제외 플래그, `store.py:313-325`의 기존 complete 검사, `store.py:493-500`의 무조건 done 갱신, `store.py:526-534`의 복구 완료 호출. `executor.py:140-141`은 게시 committed이면 기존 complete까지 가지 않고 반환한다.
- 재현 순서: 게시의 마지막 checkpoint 또는 rename 이후를 barrier로 멈춤 → 별도 연결에서 exclude → 게시 계속. 정상 경로와 renamed 복구 경로 모두 검사한다.
- 고침 제안: 게시 최종 확정과 복구에 제외 우선 정책을 넣고, 이미 rename된 경우에는 journal·해시로 기존 노트/새 파일의 안전한 처리를 마친 뒤 제외 상태를 확정한다. 단순히 예외만 던져 미완료 journal을 남기지 않는다.

### F02. 삭제 확인과 재처리 전이를 한 트랜잭션으로 묶어라

- 주 위치: `quietclerk/server/__init__.py:273-280`; priority: 1; confidence: 0.99.
- **문제·영향 [추정]:** `/process`의 tombstone 확인과 실제 `request_process()`는 별개다. 확인 직후 다른 요청이 delete-local을 커밋하면, 앞 요청은 삭제된 작업의 현재 skipped 상태와 아직 남은 유효 archive를 보고 다시 queued로 바꾸고 제외 플래그까지 지운다. 실행자의 삭제 목록 확인이 이미 끝난 시점이면 이 작업을 claim하여 삭제 요청 뒤에도 음성 처리·외부 전송을 계속할 수 있다. 반대로 cleanup이 먼저 완료하면 삭제된 작업을 queued로 남기는 잘못된 상태도 가능하다(계약 9.3).
- 근거: `server/__init__.py:274-290`의 분리된 확인/전이, `store_ops.py:42-58`의 tombstone+제외 기록, `store.py:167-183`의 tombstone 없는 재대기, `store.py:161-164`의 제외 초기화, `store.py:219-226`의 tombstone 없는 claim, `serve.py:116-118`의 cleanup→claim 사이 경계. `store_ops.py:79-82`는 정리 완료 때 상태를 skipped로 재확정하지 않는다.
- 재현 순서: 실행자의 pending 조회를 마침 → A `/process`가 deleted=False까지 진행 → B delete-local 커밋 → A request_process 커밋 → 실행자 claim. 유효 archive와 done 작업으로 구성하면 된다.
- 고침 제안: request_process/promote가 같은 BEGIN IMMEDIATE 안에서 tombstone·pending deletion을 검사하도록 하고, claim도 삭제 대상을 제외한다. API 사전 조회를 최종 권한 판정으로 사용하지 않는다.

### F03. 게시 취소·실패 때 prepared 임시 노트를 회수하라

- 주 위치: `quietclerk/notes/__init__.py:220-229`; priority: 1; confidence: 0.99.
- **문제·영향 [추정]:** prepared 커밋 직후 제외 요청이 도착하면 다음 checkpoint가 작업을 skipped로 닫고 Excluded를 던지지만, 임시 `.md`와 journal은 그대로 남는다. 시작 복구는 running 작업만 보므로 이것을 회수하지 않는다. 이후 include/재처리에서는 `safe_notes()`가 숨김 `.quietclerk-tmp/`도 검색하여 이 미게시 노트를 정상 기존 노트로 선택한다. 첫 게시였다면 숨김 임시 경로에 게시하고 done이 되며, 기존 노트가 있었다면 동일 identity 두 개로 영구 note_conflict가 난다(계약 7.2–7.4). 준비 파일 생성 뒤 다른 일반 예외가 발생하는 경우도 같은 수명 관리 문제를 가진다.
- 근거: `notes/__init__.py:80-95`의 임시 디렉터리 포함 검색, `notes/__init__.py:209-221`의 파일 생성/준비/checkpoint, `executor.py:147-148,171-172`의 Excluded 전파/종료, `store.py:365-373`의 running·active_run 한정 복구. 기존 kill 테스트는 직접 publish를 kill하여 running이 유지되는 경우만 덮는다(`tests/test_notes.py:130-190`).
- 재현 순서: prepare_publication 직후 별도 연결 exclude → checkpoint 종료 → 서비스 재시작 → include → 재게시. 첫 게시와 기존 노트 재게시를 각각 검사한다.
- 고침 제안: 취소·정상 예외 경로에서도 prepared journal을 정리/복구하고, 실행 상태가 이미 닫혔어도 미완료 게시를 회수할 수 있게 한다. `.quietclerk-tmp`는 기존 노트·프로젝트·이행 후보 검색에서 항상 제외한다.

### F04. serve와 tick이 같은 실행 배타 잠금을 사용하게 하라

- 주 위치: `quietclerk/serve.py:78-84`; priority: 1; confidence: 0.99.
- **문제·영향 [추정]:** 새 serve는 지원 폴더의 serve.lock만 잡지만 남아 있는 `python -m quietclerk.tick`은 root/tick.lock만 잡는다. 같은 루트에서 둘을 실행하면 동시에 진입하며, 나중 프로세스의 recover는 아직 살아 있는 다른 boot의 실행을 중단된 것으로 바꾼다. 새 실행이 시작되어 모델/LLM이 중복 실행될 수 있고, 기존 serve 실행자가 다음 owned 쓰기에 도달하면 LostClaim이 밖으로 전파되어 프로세스 전체가 종료된다. launchd 등록 검사로는 수동 tick 또는 이미 시작된 tick을 막지 못한다(계약 1.1·1.4).
- 근거: `serve.py:65,79-84`의 잠금/복구, `tick.py:21-29`의 서로 다른 잠금/복구, `store.py:362-391`의 boot가 다른 running 복구, `executor.py:173-174`의 LostClaim 재전파, `serve.py:93-99`의 fatal 종료.
- 재현 순서: 임시 루트의 serve 실행을 stage barrier에서 멈춘 채 같은 루트 tick을 시작하거나 그 반대 순서를 사용한다. 운영 서비스에서는 실행하지 않는다.
- 고침 제안: 모든 실행 진입점이 사용자 고정 서비스 잠금에 참여하도록 하거나, serve 활성 중 tick을 쓰기 전에 확실히 거부한다. 기존 tick.lock과의 전환도 실행 중 구 프로세스가 없는지 확인하는 하나의 절차로 묶는다.

## P2 — 계약 불일치 및 사용자 동작 실패

### F05. 일반 Markdown을 구형 엔진 노트 이행 충돌로 세지 말라

- 주 위치: `quietclerk/notes/migration.py:110-115`; priority: 2; confidence: 0.99.
- **문제·영향 [추정]:** frontmatter 없는 일반 메모는 parse_note에서 거부되는데, preview가 이를 무조건 blocking entry로 넣는다. 새 `_legacy_notes_present()`는 entries가 하나라도 있으면 구형 노트가 있다고 판단하므로, 엔진 노트가 전혀 없는 기존 Obsidian 볼트도 평범한 `# 개인 메모` 파일 하나 때문에 게시가 막힌다. 명시적 migrate --apply --consent도 같은 blocking conflict로 실패하므로 동의로 해결되지 않는다. 엔진과 무관한 사용자 파일을 고치거나 치워야 하는 상태다(계약 7.5).
- 근거: `notes/__init__.py:50-53`의 frontmatter 필수, `notes/migration.py:110-115,172-173`의 후보·차단 처리, `stages/note.py:21-27,49-52`의 entries 기반 이행 게이트.
- 재현 순서: 새 DB와 볼트에 frontmatter 없는 개인 메모 한 개를 놓고 첫 게시, 이어 migrate apply를 수행한다.
- 고침 제안: 엔진 identity 또는 DB note_path 등으로 엔진 관련성이 확인된 파일만 이행 대상으로 삼는다. 알려진 엔진 파일의 손상은 계속 차단하되 일반 Markdown의 frontmatter 부재는 무시한다.

### F06. 볼트 이행 완료 상태를 출력 볼트별로 저장하라

- 주 위치: `quietclerk/stages/note.py:49-52`; priority: 2; confidence: 0.99.
- **문제·영향 [추정]:** 이행 완료는 DB 전역 `vault_migration=done` 하나인데 F1은 output 설정 변경을 허용한다. 볼트 A가 빈 볼트라 자동 완료되거나 사용자가 A 이행에 동의한 뒤 output을 구형 엔진 노트가 있는 B로 바꾸면, 다음 실행은 B를 검사조차 하지 않고 게시한다. A의 동의/자동 완료가 B에도 적용되어 볼트 이행 전 쓰기 금지 계약을 우회한다. B의 v1 노트는 find_existing의 qc_schema=2 조건에도 잡히지 않아 중복 새 노트 생성으로 이어질 수 있다(계약 3.3·7.5).
- 근거: `store.py:441-457`의 전역 완료 키, `server/settings.py:23-25`의 root/inbox만 변경 금지, `server/__init__.py:298-302`의 즉시 설정 교체, `notes/__init__.py:93-95`의 v2 identity 검색.
- 재현 순서: A에서 첫 게시 → output=B 저장 → B에 DB 작업과 대응하는 v1 노트 존재 → 다음 새 녹음 게시.
- 고침 제안: canonical 출력 볼트 identity별로 완료/동의/manifest를 관리한다. 다음 실행 스냅샷의 output과 완료 기록이 같을 때만 게이트를 통과시킨다.

### F07. bootstrap 토큰 갱신을 장시간 실행자 호출에서 분리하라

- 주 위치: `quietclerk/serve.py:112-118`; priority: 2; confidence: 0.99.
- **문제·영향 [추정]:** 토큰의 주기적 refresh는 executor.run_one 직전에만 호출된다. 한 녹음 처리가 60초를 넘고 새 세션 교환이 없으면 파일 토큰이 만료된 채로 남는다. 그동안 quietclerk open/status는 read_bootstrap에서 거부되며, HTTP exchange 역시 만료 토큰을 거부하고 새 토큰을 발급하지 않는다. 사용자에게 가장 필요한 처리 중 상태 확인/첫 로그인이 작업 전체 종료까지 막힌다(계약 9.1).
- 근거: `server/auth.py:34-40,47-50,57-59,95-96`의 수명/갱신/거부, `cli.py:35-39`의 파일 읽기 선행, `executor.py:104-170`의 전체 파이프라인 동기 실행. lifespan의 refresh(`server/__init__.py:168`)는 시작 때 한 번뿐이다.
- 재현 순서: 가짜 실행자를 barrier에서 60초 이상 보류하거나 주입 clock을 61초 이동 → open/status용 read_bootstrap 및 session 교환 확인. 기존 만료 테스트는 refresh를 직접 호출하므로 이 런타임 연결 문제를 검출하지 못한다.
- 고침 제안: 모델/LLM과 독립된 서비스 타이머에서 안전한 주기로 갱신하고 종료 시 회수한다. 토큰의 60초 만료·일회성은 유지한다.

### F08. 병렬 backlog 요청을 하나의 갱신 단위로 직렬화하라

- 주 위치: `quietclerk/server/__init__.py:322-327`; priority: 2; confidence: 0.98.
- **문제·영향 [추정]:** F1이 기존 backfill.request를 병렬 HTTP worker에서 호출하게 했지만 이 함수는 동시 실행에 안전하지 않다. 서로 다른 두 요청이 같은 include 목록을 읽고 각각 갱신하면 한쪽 선택이 사라지며, 고정 include.txt.part를 공유하므로 다른 요청의 내용을 rename하거나 FileNotFoundError로 503이 날 수도 있다. Syncthing ignore 목록도 GET→POST 전체 교체라 서로의 unignore를 되돌릴 수 있다. 사용자가 선택한 기존 녹음이 동기화되지 않거나 before_cutoff로 빠진다(계약 5.3).
- 근거: `server/__init__.py:352-379`의 키 없는 요청 threadpool 병렬 dispatch, `backfill.py:38-49`의 read-modify-write·고정 임시 경로, `syncthing.py:61-78`의 ignore 전체 교체. Idempotency-Key는 선택 사항이고 서로 다른 요청의 올바른 병합을 보장하는 계약이 아니다.
- 재현 순서: 두 별도 요청이 서로 다른 녹음을 선택하게 하고 included 또는 db/ignores 읽기 직후 barrier로 맞춘다.
- 고침 제안: Syncthing ignore 갱신부터 include 목록 확정까지 같은 루트의 배타 잠금/직렬 큐로 묶고, 잠금 획득 후 최신 목록을 읽는다. 임시 파일명만 고치는 것으로 lost update는 해결되지 않는다.

### F09. 설정·로그인 조치 완료 후 해당 blocked 작업을 다시 대기시켜라

- 주 위치: `quietclerk/server/__init__.py:298-302`; priority: 2; confidence: 0.99.
- **문제·영향 [추정]:** 제공자 미설정/미동의/인증 만료로 막힌 작업이 있어도 PUT settings는 파일 저장과 wake만 하고, providers/{name}/check 성공도 결과만 반환한다. claim은 blocked_reason이 NULL인 retry_wait만 선택하고 자동 해제 구현은 disk_low뿐이므로, 사용자가 동의·설정을 고치거나 로그인 확인에 성공해도 작업은 계속 멈춘다. 매 작업에 별도의 process 요청을 해야 하며, ‘막힌 사유 해소 시 queued’ 전이가 구현되지 않았다(계약 2.2·8.3).
- 근거: `server/__init__.py:335-336`의 check 결과 반환, `server/integrations.py:76-93`의 DB 전이 없는 확인, `store.py:219-226`의 claim 필터, `executor.py:96-97` 및 `store.py:412-416`의 disk_low 전용 해제. 관련 호출 검색에서 다른 auth/no_local_provider/no_verified_provider 해제 경로는 없었다.
- 재현 순서: no_verified_provider로 blocked → 허용 제공자·동의 저장 → wake/claim 관찰; auth로 blocked → check 성공도 따로 검사한다.
- 고침 제안: 설정 변경 및 확인 성공 후 실제 해소된 사유에 해당하는 작업만 store 트랜잭션에서 request_process 규칙으로 재대기시킨다. 아직 인증/로컬 조건이 충족되지 않은 작업까지 무조건 풀지는 않는다.

### F10. type_basis_id 타입 오류를 구조 검증 실패로 전달하라

- 주 위치: `quietclerk/postprocess.py:128-129`; priority: 2; confidence: 0.99.
- **문제·영향 [추정]:** 새 type_basis_id 검증은 타입 확인 없이 set membership을 수행한다. LLM이 나머지는 유효하지만 `type_basis_id`만 배열 또는 객체로 반환하면 ValueError가 아닌 TypeError가 발생한다. provider 라우터가 이 예외를 잡지 않으므로 계약상 같은 제공자 구조 재시도 1회·다음 제공자 대체를 하지 않고 전체 실행 실패로 나간다. 이전 분류기는 이 필드를 검사하지 않았으므로 이 특정 실패는 패치에서 도입되었다(계약 8.3, IN-23).
- 근거: `postprocess.py:113,123-129`의 set 및 새 membership 검사, `providers/__init__.py:178-192` 부근의 validate 호출과 `(ProviderError, ValueError, ToolUseDetected)` 예외 한정 처리, `executor.py:185-186`의 일반 실행 실패. 기존 `tests/test_postprocess.py`는 없는 문자열 ID를 검사하지만 배열/객체는 검사하지 않는다.
- 재현 순서: 테스트의 정상 BASE_REPLY에서 type_basis_id만 빈 배열로 바꾸고, 첫 제공자 다음에 정상 응답 제공자를 둔다. 정상 대체 제공자가 불리지 않고 TypeError로 빠지는지 확인한다.
- 고침 제안: membership 전에 문자열 타입을 검사하고 실패를 ValueError로 통일한다. 배열·객체·숫자·null 입력이 구조 검증 정책으로 전달되는지 검사한다.

### F11. 제공자 시험 호출도 서비스의 단일 호출 실행권을 사용하게 하라

- 주 위치: `quietclerk/server/integrations.py:90-93`; priority: 2; confidence: 0.98.
- **문제·영향 [추정]:** 새 provider check API는 threadpool에서 provider.complete를 직접 호출하므로 실행자가 교정/분류/요약 중이어도 별도 LLM CLI 또는 Ollama 요청을 동시에 시작한다. 여러 check 요청끼리도 병렬 실행된다. 서비스가 약속한 ‘LLM CLI 최대 1개 / Ollama 요청 최대 1개’가 실제 호출 진입점 전체에서 보장되지 않는다. 특히 로컬 Ollama 시험 호출이 실제 작업과 동시에 generate를 수행하여 단일 로컬 추론 운영 조건을 깨뜨린다(계약 1.1).
- 근거: `server/__init__.py:335-336,378-379`의 direct threadpool dispatch, `server/integrations.py:91`의 직접 호출, `providers/__init__.py`의 실행자 complete 경로에는 이 API와 공유하는 잠금/큐가 없다.
- 재현 순서: 실행자의 fake provider.complete를 barrier에서 보류 → provider/check 요청 → 두 번째 complete 진입 수를 기록. check 요청 두 개만으로도 같은 경계를 확인할 수 있다.
- 고침 제안: 시험 호출과 정상 처리 모두 같은 서비스 호출 큐/실행권을 통과시키거나, 실행권이 사용 중이면 시험 호출을 명시적으로 대기/거부한다. HTTP idempotency는 실행자와의 배타 수단이 아니다.

## 묶음 사이 계약 추적 결과

아래는 **소스 연결을 확인했다는 뜻이며 실행 검증/무결성 보증이 아니다.**

- B→C: 격리 copy의 hash/경로 → probe → archive/job 등록 → convert → WAV 입력으로 이어진다. 확장자·바로 아래 일반 파일·NOFOLLOW·크기 상한·finite duration·AAC·자기 포함 dref 거부·실제 PCM 길이 검사가 연결되어 있다. 이번 범위에서 B 단독 코드 변경은 없으며, 새 병렬 호출 문제는 F08처럼 F1 경계에 기재했다.
- C→D: detector의 `{status, top, shares, windows}`를 `context_language()`가 읽고, text 단계와 모델 params가 같은 함수를 사용한다. `e14e973`의 language.json 키 불일치 수정은 현재 호출 경로에 연결되어 있다. worker의 result.models는 stage params의 고정 revision과 비교되고, Unsupported/NoSpeech/not_run은 명시적 분기로 처리된다. diarize 라벨은 transcript.turns에서 S1…로 매핑된다.
- D→E: correct/summarize는 transcript, classify는 transcript+source_name+project_list를 명시하고 provider.complete가 필드 전체 동의를 확인한다. 현재 범위에서 새로 도입된 동의 없는 필드 전송 경로는 확정하지 못했다. 이것은 실제 CLI/Ollama 무전송 시험 결과가 아니다.
- E→D: `provenance_rows()`가 reused_from의 원 실행/단계를 조회하고, note가 `external_text_to()`로 실패한 외부 전송도 포함한다. e14e973의 캐시 재사용 표시 수정과 모델 ID JSON→목록 정규화 소비자를 확인했다. 삭제/재처리 경합은 F02와 별개로 이 감사 표시만으로 방어되지 않는다.
- D→store→F1: prepared/renamed/committed는 정상 publish, 시작 recover, executor 조기 반환까지 추적했다. F01/F03은 이 새 경로가 기존 완료·제외·복구의 전제를 벗어나는 지점이다.
- 서버 보안: strict Host와 단일 Origin 검사, 세션/CSRF, 일회용 토큰·만료, no-store/CSP, bootstrap fragment 제거, SQL parameter job 조회, DB archive 경로 제한·NOFOLLOW·Range 거부 경로를 읽었다. 일반 웹 요청으로 즉시 가능한 새 Host/Origin/경로 우회는 확정하지 못했다. 오디오의 파일시스템 경쟁·실제 브라우저 요청·Syncthing·실제 제공자 검증까지 완료했다는 뜻은 아니다.
- F1 schema에 명시적으로 제외된 노트/모델 API 및 앱 화면 자체의 부재는 이번 F1 결함으로 세지 않았다. 이 리뷰는 G 전에 F2까지 구현했다는 주장을 하지 않는다.

## 메인이 수행할 최소 회귀 검증

1. `tests/test_notes.py`: prepared 전/후, rename 전/후, 최종 커밋 전/후의 제외·예외와 재시작을 barrier로 재현. 임시 노트 검색 금지, 기존 노트/사용자 바이트 보존, current_run_id 불변 조건을 확인.
2. `tests/test_store_ops.py` + `tests/test_server.py`: process/include/promote 대 delete-local 경합, 삭제 직후 claim 금지, 삭제 후 외부 호출 0, serve/tick 동시 진입 거부.
3. `tests/test_note_migration.py`: 일반 Markdown만 있는 볼트, 손상된 실제 엔진 노트, A→B output 변경 시 별도 동의 게이트.
4. `tests/test_server.py` + `tests/test_server_integrations.py`: 실행자를 보류한 상태의 토큰 60초 경계, auth/consent 해결 후 재대기, 병렬 backlog 선택 합집합 유지, provider check의 단일 실행권.
5. `tests/test_postprocess.py` + `tests/test_providers.py`: type_basis_id의 배열/객체를 ValueError 정책으로 보내고 정상 대체 제공자까지 도달하는지 확인.
6. 수정 후 실제 모델/실제 제공자와 serve를 연결한 합성 E2E 및 공개 가능한 실제 입력 E2E를 별도 기록한다. 단순 fake registry의 done 결과를 실제 D 게시·모델·제공자 통합 증거로 대신하지 않는다. 현재 serve 합성 E2E(`tests/test_server.py:442-488`)는 직접 노트를 쓰는 fake stage라 F01/F03을 검증하지 않는다.

## 제품 게이트

- 파일 목록상 `samples/`와 `samples/audio/`의 m4a 4개는 존재한다. 내용을 열거나 외부로 보내지 않았다. ‘실제 입력 표본 경로 없음’ 알림과 현 파일 목록은 다르며, 존재 확인이 실녹음 인수 완료를 뜻하지 않는다.
- 읽은 samples 루트에는 출처·권리·해시·기대 결과를 연결한 매니페스트가 없다. 실제 입력 검증에는 이 연결이 먼저 필요하다. 기존 테스트/인수 문서에는 입력 유형별 합성 처리 정책이 있지만, 위 경쟁 조건·일반 사용자 노트·비정상 분류 필드는 추가가 필요하다.
- 계약 12절의 삼성 녹음 중 파일 쓰기 확인에는 이미 담당 `main + user`, 확인 예정 `2026-11-10 18:00 KST`가 있다. 이 리뷰는 그 확인을 실행하거나 닫지 않았다. 읽기 전용 범위에서 계약/인수 문서를 수정하지 않았다.

## 다음 묶음(G 설치·Mac mini 업그레이드) 전 반드시 고칠 것

1. **F01–F04를 먼저 고친다.** 게시의 제외/복구 journal을 닫고, 삭제된 작업의 재대기·claim을 원자적으로 막으며, serve/tick 실행권을 통합한다. 이 상태로 운영 DB·볼트 이행을 시작하지 않는다.
2. **F05–F06을 고친 뒤 일반 메모가 섞인 실제 형태의 볼트 사본으로 이행을 검증한다.** 기존 노트를 치우는 우회나 다른 볼트의 동의를 재사용하는 방식은 허용하지 않는다.
3. **F07–F11의 런타임 연결을 마무리한다.** 장시간 작업 중 로그인, 설정/인증 해결 후 복구, 병렬 backfill, 비정상 LLM 응답, 단일 제공자 호출 조건을 각각 회귀 시험으로 고정한다.
4. 메인이 위 범위의 검증을 실행하고 인수 기록에 **실행만 / 가정으로 확인 / 실제 입력으로 확인**을 분리해 남긴다. 그 다음에만 계약 10.2의 Mac mini DB·설정·노트 **사본** 업그레이드 리허설을 수행한다. 이번 리뷰는 운영 업그레이드 허가나 실행 완료 보고가 아니다.
