# QuietClerk 인수 기록 (contracts-v2 11절)

계약 11절의 입력·상황별 기대 결과를 실제 테스트·시험에 연결하고, 실행한 결과를 기록한다. 기존 `acceptance.md`는 v1 파이프라인(운영 중, `e34c5e0`)의 기록이다.

수준: **실제 입력**(실녹음·실제 경로) / **가정**(합성 입력·가짜 모델·가짜 제공자) / **실행만** / **미확인**.

## 묶음별 진행

| 묶음 | 커밋 | 테스트 | 수준 | 비고 |
|---|---|---|---|---|
| 이름 변경 | `e34c5e0` | 18 통과 | 가정 | Mac mini 배포(운영 동결 기준점) |
| A 실행·저장 | `41f0c34` | 전체 98 통과(2026-11-10) | 가정 | 실제 모델·LLM 미검증. 독립 리뷰 결과 수정 6건(`research/review-m1a.md`) → A 수정 진행 중 |
| 단계 분리 | `dff34e4` | 98 통과 | 가정 | `quietclerk/stages/` |
| E 요약 제공자 | `40df8d6` | 전체 131 통과 | 가정 + 실제 CLI(가상 입력) | Codex 0.167.0 실제 호출 1회: 가상 대화록 요약 성공, 강화 플래그, 도구 이벤트 0건. Claude·Ollama 실제 호출 없음(로그인·설치 대기). agy 제거 |
| B 입력 | `bbe3292` | 전체 192 통과 | 가정 | 격리 복사·probe 강화·승격·backfill·공간 부족. IN-12 외부 요청·미끼 열람 0건 |
| A 수정(리뷰 6건 + 공용 변경) | `c328904` | 전체 236 통과 | 가정 | 설치 기본값 영속, 제외 우선, 승격 검증, 이행 경로, disk_low, 언어 연결, 제공자 설정 키 |
| U1 화면 시안 | `61e5711` | 캡처 138장, 겹침·넘침 0 | 실행만 + 데모 오디오 재생 확인 | `docs/ui/`. 계약 밖 항목은 `docs/ui/README.md` 8절 '제안' |
| C 모델 | `0dad8aa` | 전체 280 통과 | 가정 + 실제 모델(합성 입력) | 한국어 합성 157초: ko 몫 1.0, 단계 시간 diarize 10.9초·감지 15.2초·받아쓰기 10.2초·2차 7.6초(M3 Max). 영어 합성 61.1초: en 몫 1.0. 균등 분할 전에는 마지막 1초 조각에서 'Okay' 환각 + 시각 초과로 거부 → 균등 분할·0.5초 보정 후 해결. 모델 ID@커밋은 `tests/fixtures/model-worker-evidence.json` |
| D 텍스트·노트 | (이 커밋) | C 반영 후 전체 307 통과 | 가정 | 사용자 필드·할 일·메모 보존, 게시 prepared→renamed→committed 각 지점 실제 SIGKILL 후 복구, 해시 충돌 시 덮어쓰기 없음, v1 노트 이행 preview/동의/백업/재실행. IN-22·23·24·27 합성 입력. 실제 볼트·실녹음 미검증 |
| F1 serve·API | `17e5d81` | 전체 349 통과 | 가정 | 인증·Host·Origin·CSRF·토큰 재사용·Range 거부, 잠금·실행자 예외 시 종료, 합성 m4a가 serve 아래 queued→done·SSE. 실제 Syncthing·브라우저 미검증 |
| 엔진 통합 E2E(MacBook) | `e14e973` | 아래 | **실제 모델 + 실제 Codex, 가상 회의 음성** | 2026-11-10. `docs/examples/demo-meeting`의 합성 한국어 회의(2.6분, 3명)를 빈 루트의 받는 폴더에 넣고 `python -m quietclerk.tick` 1회 → done, 74초. 노트: 한국어, language_detected ko, 화자 3, pipeline·external_text_to에 codex 표시. 첫 실행에서 결함 5건 발견·수정: 빈 볼트도 이행 요구로 막힘, 루트 바깥 상위 폴더(/tmp) 링크까지 거부, 텍스트 단계가 감지 언어 대신 기본 언어(en) 사용, 캐시 재사용 시 외부 전송 표시가 비어 짐, 모델 ID가 JSON 문자열로 표시. 이어 노트 제목·할 일 체크·메모를 손으로 바꾼 뒤 `resummarize` → 세 가지 모두 보존, 요약만 다시 생성. 실제 녹음·폰·Syncthing·serve 경로는 이 E2E에 포함 안 됨 |
| G 설치·업그레이드 | `a37386d` | 전체 399 통과 | 가정 | 합성 v1 루트·가짜 launchctl. 단계별 실패 주입 시 DB·설정 바이트 복원, 구 서비스 재등록, 잠금·자식 프로세스·루트 충돌 거부, dry-run 무변경. 실제 launchd 등록 미검증 |
| 독립 리뷰 B-F1 반영 | `95e1878` | 전체 453 통과 | 가정(주입·barrier) | F01~F11 모두 고치기 전 재현 테스트 실패 확인 후 수정(`tests/test_review_bf.py` 등). 설치 잠금 교착(F04 수정으로 드러남)도 함께 수정 |
| F2 화면 | `0767009` | 전체 500 통과 | 가정(가상 루트) + **실제 브라우저(headless Chromium)** | 홈·작업·회의록 목록/보기·기존 녹음·설정·노트 옮기기·설정 마법사 1-6. 1280/390 가로 넘침 0, 콘솔 오류 0, 근거 시각 클릭 시 오디오 이동·재생 확인, 세션 없는 화면 경로는 데이터 없이 `/`로. 빠진 API(노트 목록·노트 상세·모델 내려받기 등)는 끈 버튼 + 이유로 표시. Safari·영어 전 화면 미확인 |
| Mac mini 사본 업그레이드 리허설(계약 10.2.7) | `8e4de1c`·`5767a1a`·`53e2bce` | 아래 | **실제 장비·실제 launchd, 운영 DB·설정·노트의 사본** | 2026-11-10 01:09~01:30. 운영 서비스(`local.rec.pipeline`)를 잠시 내리고 `~/qc-rehearsal`에 사본(DB·settings.env·노트 2건, 경로만 사본으로 바꿈)으로 진행 후 운영 서비스 복구(재실행 exit 0). ① 1차 실패 주입: 롤백이 막힘(새 serve가 잠금을 놓기 전에 즉시 잠금 시도) → DB·설정 복원 안 됨 → 수정. ② 2차 실패 주입(서비스 기동·인증 확인 뒤): DB·설정 SHA-256 원본과 같음, 구 서비스 재등록, 새 서비스 제거. ③ 정상 업그레이드: 6.7초, 기존 작업 2건 done 유지, Codex가 launchd 아래에서 로그인 상태로 감지됨. ④ 가상 회의 음성을 받는 폴더에 넣음 → 5분 미만이라 `too_short`로 건너뜀(정책대로) → API로 처리 요청 → M4에서 화자 분리 27초·언어 감지 40초·받아쓰기 41초 → 제공자 동의가 비어 `no_verified_provider`로 대기 → `PUT /api/settings`로 동의 저장 즉시 재대기·처리 → 노트 단계에서 볼트 이행 대기. 발견·수정: 볼트 이행 대기가 재시도 횟수를 써서 결국 최종 실패할 구조 → 막힘 상태로 변경, serve가 실행 잠금을 계속 쥐어 CLI 이행이 불가 → serve 실행자 스레드에서 이행, v1 업그레이드 언어 기본값이 Mac 로케일(en)을 따름 → ko, serve가 로그를 남기지 않음 → 작업별 단계 시간 로그 |
| **Mac mini 운영 업그레이드** | `181c0eb`·`f194906` | 아래 | **실제 장비·운영 데이터** | 2026-11-10 06:15 KST. 사용자 승인 후 `quietclerk upgrade`(14초): 구 서비스 해제, DB 이행(기존 작업 2건 done 유지), 설정 이행(ko 기본값), 새 서비스 기동·인증 확인. 사용자 위임으로 API를 통해 Codex 전송 동의(대화록·파일 이름·프로젝트 목록)와 기존 노트 2건 이행(볼트 밖 백업, 본문 해시 같음, MacBook 볼트까지 동기화 확인). 직전 발견·수정: config import만으로 `~/QuietClerk`가 생겨 업그레이드가 거부됨, 새 서비스가 ops 하트비트를 안 보내 거짓 경보가 날 구조. 터널로 실제 화면 열람 확인(콘솔 오류 0). **남은 확인: 폰의 실제 새 녹음(5분 이상)이 새 서비스로 회의록이 되는 것 — 다음 녹음 때** |
| **실제 녹음 E2E (v2 운영)** | `51ce621` | 아래 | **실제 입력·실제 경로** | 2026-11-10 07:52. 11/5 업무 회의 녹음(18.4분)을 화면용 API `POST /api/backlog/request`로 요청 → Syncthing ignore 해제 → 폰이 약 1분 안에 전송 → serve 등록 07:54:17 → 완료 08:01:58(461초: 화자 분리 28·언어 감지 36·받아쓰기 96·2차 140·교정 95·분류 26·요약 37초). 노트: 한국어, 화자 4, 할 일 6건, 근거 링크 69개, 발화 139줄, 불확실 명칭은 '확인 필요'로 분리. 발견·수정: 노트가 볼트에 써졌으나 다른 기기로 동기화되지 않음(v1의 Syncthing 재스캔이 v2 게시 단계에서 빠짐) + 빈 `.quietclerk-tmp` 폴더가 볼트에 남음 → 수정·배포 후 MacBook 볼트 도착 확인. 남은 확인: 녹음 직후 새 파일(백필이 아닌 경로) |
| **실제 새 녹음 E2E (폰 → 회의록, v2 운영)** | `63e9980` | 아래 | **실제 입력·실제 경로** | 2026-11-10 10:02 시작한 폰 녹음(25.7분)이 저장 후 자동 전송 → serve 등록 10:30 → 완료 10:44 → MacBook 볼트 도착(업무 회의 노트 1개). 처리 중 배포 재시작(10:36)으로 2차 받아쓰기 단계가 끊겼으나 시도 횟수 소모 없이 이어서 완료(앞 단계 재사용). 이후 배포 절차를 "처리 중 작업이 없을 때만 재시작"으로 바꿈 |
| **유사 프로젝트 1·2차 묶음** | `48d8031`·`fbd74bd` | `test_asr_quality.py`, `test_text_quality.py`, `test_overrides.py`, `test_search_export.py`, `test_pipeline_custom.py`, `test_note_screen.py` 외 910개 통과 | **실제 입력**(1차: 실제 회의 4건 비교) / **가상 입력·실제 경로**(2차) | 1차: 실제 회의 4건을 이전·새 코드로 처리. 받아쓰기 글자 오류율 같음(단어장 미사용), 2차 받아쓰기의 실제 반복 환각(B,B,B / ㅋㅋㅋ / 언제 언제) 제거, Whisper 토큰 상한 448이 실제 녹음 2건을 깨뜨려 224로 수정, 요약 사후 검증이 담당·기한을 지우고 말한 숫자를 오경고해 네 차례 고침(남은 숫자 경고는 모델 계산값 68+30=98 같은 실제 불일치). 2차: 가상 회의 2건·9초 메모를 실제 모델·Codex·serve로 처리하고 화면(이름 확정→노트·요약 조사 맞춤, 검색 '응답시간'→'응답 시간' 3곳·#t8 이동, 390px 넘침 0)과 API(병합·되돌리기·줄 고침·Word/SRT·데일리 노트)를 확인. E2E에서 찾아 고친 것: macOS /tmp 링크로 데일리 노트 실패, 볼트가 없으면 서비스가 안 뜨는 문제, 'S2는' 이름 치환, 긴 메모 제목, Word의 날 마크다운. 실제 녹음으로 2차 기능 확인은 업데이트 뒤 사용자 사용으로 남음. |
| 단계식 회의록 비교(A/B) | `15f225f` | 아래 | **실제 입력(실제 녹음 5건, 18~56분), MacBook** | 2026-11-10. 같은 받아쓰기·교정·분류 결과에서 요약만 현행(single)과 단계식(staged)으로 만들어 좌우를 섞은 비교 페이지(`samples/ab/index.html`, 저장소 밖)로 사용자 판정 대기. 단계식 추가 비용: 추출 38~133초 + 핵심 요약 약 9초(Codex Fast). 인용 검증: 5건 모두 버린 항목 0(실제 출력의 인용은 모두 원문에 있었다 → 검증은 지금까지 '안전장치'로만 동작). 실행 중 발견·수정: 56분 녹음이 받아쓰기 단어 시각 0.02초 역행으로 통째 실패(운영에도 있던 결함, 수정·배포), 핵심 요약이 오인식 의심어를 써서 실패(표시로 변경), 첫 출력이 수치·오인식 목록 과다(프롬프트·상한 조정). **사용자 판정(블라인드, 3건): 3건 모두 현행 선택 — '짧은 게 낫다'. 단계식은 채택하지 않고 코드 삭제** |
| **앱 D0: 첫 공개 릴리스와 실제 앱 업데이트** | `bf53b69`·`ca1e8f7` | Rust 7개, clippy, 파이썬 935개, CI(Linux·macOS) 통과 | **실제 경로(사용자 MacBook, 사람이 조작)** | 2026-11-11. GitHub Actions가 빌드한 `v0.0.1` DMG를 사용자가 내려받아 설치 → 첫 실행에서 Gatekeeper 차단(서명 없음, XProtect 판정 악성 아님)에서 "휴지통으로 이동"을 눌러 앱이 지워짐 → 다시 설치, 격리 표시는 메인이 해제(릴리스와 실행 파일 해시 같음 확인) → 앱 시작 시 0.0.2 확인 창 → 사용자가 "확인" → 약 35초 뒤 0.0.2로 교체·재시작(설치본 해시 = 릴리스 해시, 서명 검증 통과). 발견: 같은 식별자의 로컬 개발 빌드가 받은 앱 대신 열림(시험 전 개발 빌드 정리 규칙 추가), 처음 여는 사람에게 서명 없는 앱 차단이 큰 장벽(README 안내 추가, Developer ID 시점은 사용자 판단). "그래도 열기" 경로 자체는 사람이 끝까지 해 보지 않음 |
| **앱 S1: 로그인 서비스 생명주기** | (이 커밋) | `scripts/probe_login_service.py`, Rust 공개 함수 3개 + 실제 Python 설치기 | **실제 사용자 세션·실제 launchd·HTTP 인증** | 2026-11-11. A(SMAppService ad-hoc)·B(앱 런처) 비교 후 B 변형(venv Python 직접) 선택. 등록→인증 PID 7638→시험 앱 종료 후 유지→SIGKILL 7715→서로 다른 Rust 빌드 덮어쓰기 뒤 같은 PID 유지→SIGKILL 7932→앱 이동 뒤 SIGKILL 8132→해제·plist 없음. 기존 CLI PID 8162는 앱 status/register/unregister에서 그대로 유지. 앱 기본 root 생성 안 함, 임시 support·LaunchAgents·시험 앱 삭제·LS 등록 해제. 사용자 설치본·운영 장비 무변경. 후보별 실패·BTM 이름 한계·이력 잔존은 `contracts-app.md` 6절. 실제 재로그인·재부팅·깨끗한 계정·실제 모델 처리는 미확인 |

S1 최종 회귀(2026-11-11): `CONTRIBUTING.md`의 전체 Python 명령 **950 통과**,
기존 Starlette/httpx deprecation 경고 1건. `cargo test` **11 통과**,
`cargo clippy -- -D warnings` 통과. 이 회귀는 가정(합성 데이터·가짜 외부 엔진) 수준이며,
위 실제 launchd 실측과 구분한다.

## A가 덮은 계약 항목

| 계약 | 테스트 |
|---|---|
| 1.3 처리 요청·claim(동시 claim 하나만, 실패 쪽 run 없음) | `test_store.py::test_two_connections_claim_only_one_run`, `test_allowed_process_transitions_reset_counters`, `test_disallowed_requests_and_stale_writes` |
| 1.4 복구(attempts 그대로, 3번째 중단 failed, 트랜잭션 경계 kill) | `test_interruption_three_times_attempts_unchanged`, `test_sigkill_recovery_at_transaction_boundaries`, `test_pending_exclusion_survives_interruption` |
| 1.5 제한 시간·그룹 종료 | `test_procs.py::test_timeout_terminates_child_and_sigterm_resistant_grandchild`, `test_grandchild_killed_even_if_parent_exits_on_term`, `test_contract_timeouts`, `test_executor.py::test_stage_timeout_and_failure_history` |
| 2.2 전이(재시도 예산, blocked는 시간으로 안 풀림, 제외, 승격 조건) | `test_retry_budget_and_blocked_not_time_released`, `test_exclude_from_any_nonrunning_state`, `test_exclusion_finishes_at_next_checkpoint`, `test_late_exclusion_wins_over_success_commit`, `test_promotion_requires_matching_verified_archive`, `test_blocked_failure_and_success_reset_interrupt_count` |
| 3.1 스키마 | `test_schema_and_connection_pragmas` |
| 3.2 v1 이행(WAL 포함 백업, 매핑, 실패 시 원본 유지, 모르는 구조 중단) | `test_migrate_v1.py` 4개 |
| 3.3 설정(우선순위, 타입, 실행 스냅샷, REC_* 별칭 없음) | `test_config.py` 5개 |
| 4 캐시(재사용·무효화·모드 범위·하드링크 불변·메타 검사) | `test_executor.py` 재사용·무효화·모드·하드링크·메타 테스트 |
| 8.2 동의·로컬 전용(기존 Codex 호출 경로) | `test_unconsented_and_local_only_legacy_calls_block_without_attempt`, `test_legacy_external_adapter_records_actual_sent_fields` |
| 통합: 합성 m4a → queued → done(가짜 모델·LLM) | `test_tick_module_synthetic_m4a_end_to_end` |

## 입력·상황별 상태 (11절)

| ID | 상태 | 근거 |
|---|---|---|
| IN-01 정상 한국어 | v1 운영에서 실제 입력 확인(2026-11-09, 실녹음 2건). v2 엔진은 미확인 | `acceptance.md` |
| IN-03~IN-19 | 가정 확인(합성) | `test_intake.py`, `test_intake_security.py`, `test_audio.py`: `test_in03_duration_boundary`, `test_in04_before_cutoff_and_in18_nfc_include`, `test_in05_promote_revalidates_original`, `test_in06_in07_ignored_paths_leave_no_records`, `test_in08_zero_byte_waits_and_late_growth_is_accepted`, `test_in09_stability_restarts_after_growth`, `test_in10_truncated_m4a_is_decode_rejection_without_job`, `test_in11_disguised_format_and_unsupported_codec`, `test_in12_external_references_never_open_network_or_local_bait`, `test_in13_sparse_oversized_file_never_hashed_or_probed`, `test_in14_*`(3), `test_in15_disk_low_stops_copy_or_archive`, `test_in16_duplicate_and_tombstone`, `test_in17_same_name_different_contents_creates_new_job`, `test_in19_synthetic_silence_noise_no_speech_transition` |
| IN-23 잘못된 응답 | 줄 누락만 가정 확인. 중복 ID 검출은 D | `test_postprocess.py` |
| IN-24 없는 근거 ID | **지금 테스트가 삭제를 정답으로 둠 — D에서 `[?tN]`으로 바꿈** | `test_render.py::test_citations_become_line_links_and_unknown_ids_are_dropped` |
| IN-25 kill 복구 | claim·run·단계 경계 가정 확인. 게시 중 kill은 D | 위 1.4 |
| IN-29 로컬 전용 | unknown·external 호출 0 가정 확인 | `test_providers.py::test_IN29_local_only_never_sends_unknown_or_external` |
| 8.3 오류 행렬 | 가정 확인 | `test_error_matrix_next_provider_and_failed_send_audit`, `test_structure_retry_once_then_fallback`, `test_tool_use_stops_without_fallback` |
| 그 밖 | 미확인(B·C·D·E·F 묶음) | — |

## 판단 근거 기록

- Ollama 로컬 판정(E 구현): loopback 주소 + `/api/show`의 로컬 가중치 정보(GGUF·architecture)일 때만 `local`, `remote_host`·`remote_model`이 있으면 `external`, 그 밖은 `unknown`. 근거: https://docs.ollama.com/api-reference/show-model-details.md, https://github.com/ollama/ollama/blob/main/api/types.go (2026-11-10 E 묶음 확인). 실제 Ollama 설치본으로는 미확인.
- Claude `verified`는 실제 시험한 2.1.319만. 다른 버전은 `unverified`로 내려간다.
- 언어 판정 0.6은 시작값이다. C 묶음의 합성 표본(한국어 데모 회의, 영어 합성 대화)은 판정 경로 확인용이며 기준값 검증이 아니다. 실제 혼용 회의 표본으로 조정 필요(담당 main, E6 표본 확보 때).

## 2차 E/F/G: 요약 구성·짧은 메모·데일리 연결

- 설정: `summary.sections = { meeting = ["안건", "결정 사항", "할 일"] }`,
  `summary.instructions = "간단히"`는 유형별 절 제목과 선호만 바꾼다. 기존 7유형만
  허용하며 핵심 요약·근거 인용·도구 금지는 고정이다. 두 설정 모두 요약 캐시 키에
  포함된다. 제목·선호는 지시 채널이 아닌 JSON 데이터이며 충돌하는 선호는 무시한다.
- 짧은 녹음은 기본대로 `too_short`. `memo.enabled = true`일 때만
  `memo.min_sec`(기본 10, 5~299) 이상부터 기존 최소 회의 길이 미만까지 메모로 처리한다.
  받아쓰기·교정은 동일하고, 1인 화자 산출물과 대화록 발췌 제목을 로컬에서 만들며
  분류 호출은 하지 않는다. 메모 요약 절은 핵심 요약·할 일만 허용한다.
- `daily_note.path = "Daily/{date}.md"`(기본 빈 문자열=꺼짐)는 출력의 Obsidian 볼트
  기준 상대 경로 또는 같은 볼트 안 절대 경로다. 녹음일 파일의 회의록 절에 노트 이름
  기준 한 줄만 더한다. 기존 제목·다른 줄·줄바꿈 바이트는 고치지 않는다.
  출력 언어가 `same`이면 게시 노트의 실제 처리 언어를 사용한다.

| 입력·경계 | 방침·시험 |
|---|---|
| 빈 설정·빈 선호 | 기본 구성·기본 too_short 유지, 데일리 쓰기 없음 |
| 잘못된 유형·빈 제목·12개 초과·40자 초과·500자 초과·제어/서식 문자 | 저장 전 `SettingsError`, `test_feature_settings_reject_invalid_inputs` |
| 인용 제거·도구 사용·가짜 system 지시 | 고정 규칙 뒤 JSON 선호로만 전달, 핵심 제목/인용 없는 응답 거부, `test_summary_preferences_are_data_after_immutable_rules` |
| 10초 미만·10초 경계·300초 경계·메모 꺼짐 | `test_memo_intake_duration_boundaries`; 화자 모델·분류 호출 생략은 별도 시험 |
| 다른 회의·처리 중 회의 | 새 회의 변경 API 없음. 실행 스냅샷과 게시된 노트 경로만 사용하며 다른 노트는 불변 |
| 데일리 없음·같은 노트 재게시·다른 제목 | 생성·멱등·기존 제목 불변, `test_daily_create_date_and_idempotence_without_changing_title` |
| 볼트 없음·볼트 밖·`..`·경로/조상/볼트 표시 심볼릭 링크 | 쓰기 전 거부; 작업 도중 조상 바꿔치기도 볼트 밖에 쓰지 않음 |
| 다른 줄·절·CRLF·마지막 개행 없음 | 원래 바이트 보존, `test_daily_preserves_other_lines_sections_and_crlf_bytes` |
| 스레드·별도 프로세스 동시 게시 | 프로세스 내부 잠금 + 파일 잠금으로 직렬화, 노트 이름별 한 줄 |
| 사용자 편집 경합 | 원자 교체 직전에 파일 정체성과 전체 바이트 재확인; 관측된 변경은 거부하고 사용자 글 보존 |

### MacBook 실제 실행 증거 (2026-11-10 15:18 KST)

- 운영 경로·`samples/`는 사용하지 않았다. 이 작업 트리 안 임시 root/볼트를 만들고
  macOS `say -v Yuna`의 가상 한국어 메모를 AAC 20.0초로 만들어 기본 파이프라인을
  **1회 끝까지 실행**, `queued → done`, `type: memo`, 화자 분리·분류 `not_run`을 확인했다.
- 실제 Qwen3-ASR `a8379a2e…`, ForcedAligner `0e1a68e9…`,
  Whisper turbo `a4aaeec0…`를 사용했다. 실제 Codex 0.167.0은 로그인·도구 차단 검증 후
  **교정 1회 + 요약 1회** 호출했다. 전체 실행 25.4초(속도 비교·성능 주장이 아닌 실행 기록).
- 게시 노트에서 핵심 요약·할 일·전체 대화록과 Codex 전송 기록을 확인했다.
  `daily.link`를 직접 두 번 호출하여 한 줄·기존 제목·노트 바이트 불변을 확인했다.
  게시 훅 자동 연결 및 메모 파일명 접두어의 최종 통합은 메인 소유 파일에서 확인한다.
- 임시 음성·루트·볼트·실행 스크립트·preflight 기록은 시험 후 삭제한다.
  검증 수준은 **가정으로 확인(합성 입력·가짜 엔진 시험) + 실제 모델/CLI로 확인(가상 음성)**이다.
  실제 사용자 녹음·운영 볼트·폰 전송은 이번 범위에서 검증하지 않았다.
- `tests/test_pipeline_custom.py`의 66개 시험 통과. 설정·인테이크·모델·후처리
  기존 회귀 4모듈도 별도 범위 실행에서 통과했다. 동시 잠금 파일 생성에서 발생한
  `ENOENT`를 시험으로 발견하여 배타 생성 후 기존 잠금을 여는 방식으로 수정했다.
  전체 시험 1회 및 공용 파일 통합 검증은 메인 세션에서 한다.


## A1 앱 첫 실행·엔진 맞추기 (2026-11-11, 앱 0.0.3 / 엔진 0.1.1)

| 항목 | 수준·실행 증거 |
|---|---|
| 첫 실행 안내 | **실제 앱 화면**: `~/Applications/QuietClerk-A1.app`에서 용량·백그라운드 실행 동의·설치 버튼 표시. `screencapture` 창 캡처 `/tmp/quietclerk-a1-consent.png`. 클릭·키 입력 자동화 없음 |
| 설치·서비스·인증 | **실제 기본 경로 + 공유 Rust 진입점**: `examples/first_run_probe.rs`가 버튼과 같은 `perform_install` 호출. 엔진/서비스 없는 기본 경로에 0.1.1 첫 설치 8.05초, 실제 launchd 등록·인증 성공. 기존 모델/uv 캐시가 있으므로 콜드 다운로드 시간 아님 |
| 마법사 열기 | **실제 앱 화면**: 설치 후 앱 창에서 `/setup/1`, 칩·메모리·디스크·ffmpeg·uv 다섯 검사 성공. `/tmp/quietclerk-a1-wizard-final.png`. 설치 동의 클릭 연결 자체는 미확인 |
| 앱 종료 | **실제 경로**: 시험 앱 SIGTERM 뒤 설치된 Python의 인증 status가 `engine=ready`; 이전 설치에서는 종료 전후 launchd PID 동일도 확인 |
| 앱 소유 엔진 update | **실제 경로 + 공유 Rust 진입점**: 엔진 0.1.0을 설치한 뒤 0.1.1을 담은 두 번째 로컬 번들로 교체, 기존 update 함수로 10.44초에 전환·인증 성공. 현재 interpreter의 패키지 0.1.1, 보존한 직전 interpreter의 0.1.0을 각각 실행해 확인. 작업 없는 상태의 실측이며 처리 중 대기는 자동 시험 |
| 모델 중복 받기 | **실제 완료 캐시 재사용**: HF blob 30개·5,556,951,429바이트의 크기·mtime이 첫 설치/업데이트 후 동일. 모델별 시작·완료 출력 확인. 다운로드 도중 단절/부분 이어받기는 가짜 snapshot 자동 시험이며 실제 빈 캐시 네트워크 단절은 미확인 |
| 패키징·서명 | **실제 빌드/검사**: Tauri가 uv·ffmpeg·ffprobe를 `Contents/MacOS`에서 각각 ad-hoc 서명. `codesign --verify --deep --strict` 성공, FFmpeg `-L`은 LGPL 2.1+, `otool -L`은 시스템 라이브러리/프레임워크만. 시험 앱 교체 때 파일 병합으로 남은 옛 wheel은 깨끗한 번들 교체로 제거 |
| 최소 FFmpeg 보안 경로 | **자동 시험 52개 통과 + 실제 공개 가상 음성**: 번들 도구를 명시한 기존 intake/intake_security/audio 시험. 한국어 데모 AAC 157.289083초와 영어 데모 89.974646초를 16kHz/mono PCM으로 변환. 실제 사용자 녹음·모델 전사 품질 시험 아님 |
| 비정상 입력 | **가정 자동 시험**: 네트워크/디스크/플랫폼, 손상 wheel·목록·manifest, CLI 공존/다른 버전, 작업 대기·rollback, 파일 잠금·심볼릭 링크, 원격 IPC 차단. SIGKILL 복구는 별도 프로세스와 임시 HOME에서 실행 |
| 언어·조작 경계 | **실제 한국어 안내 + 영어 엔진 마법사**, 두 언어 문자열은 코드에 유지. 버튼 클릭, 실제 새 사용자 계정·재로그인/재부팅, Homebrew 자체가 없는 Mac의 전체 경로, 빈 HF 캐시의 다운로드 시간은 미확인 |

- 모델을 설치 단계에서 받는 이유: 기존 마법사 2단계에는 다운로드 API가 없어 앱 설치를 건너뛰면 터미널이 다시 필요하다. 현재 마법사 2단계의 CLI 안내는 그대로지만 앱 사용자는 이미 모델을 받았으므로 다시 실행할 필요 없다.
- 실제 경로에서 발견한 macOS 타깃 기본값(uv는 13), 부트스트랩의 PyYAML 부재, launchd PATH에서 sysctl 부재를 각각 고정 14 타깃·동일 잠금의 bootstrap 부분 목록·절대 sysctl 경로로 해결했다.
- 정리: 설치된 Python의 S1 unregister로 실제 서비스/LaunchAgents plist 해제 후 시험 root/support·관리 CLI 링크 제거, 시험 앱은 `lsregister -u` 후 삭제, `target/*/release/bundle` 삭제. 이 경로들의 부재와 모델 blob 30개의 크기·mtime 불변을 확인했다. HF 모델 캐시는 보존했고 `/Applications/QuietClerk.app`은 건드리지 않았다. BTM 비활성 이력은 기존 S1과 같이 남을 수 있다.
- 사용자 확인: 릴리스 후 첫 실행 화면에서 ‘동의하고 엔진 설치’를 직접 눌러 진행·마법사 연결을 확인하고, 다음 로그인 때 앱을 열기 전 엔진이 실행 중인지 확인한다.
- 최종 게이트(각 1회): Python 전체 **982 통과**(Starlette/httpx deprecation 경고 1개), `cargo test` **14 통과**, `cargo clippy -- -D warnings` **성공**. Cargo/npm/Tauri/CHANGELOG의 0.0.3 일치 검사 성공. Rust 제품 코드 **1,053줄**(시험/실측 예제 제외, build.rs 포함)로 1,500줄 이하다. GitHub Actions 자체 실행·게시/업데이터 배포는 하지 않았다.
