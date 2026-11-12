# QuietClerk 엔진 계약 v2

작성 2026-11-09. `contracts.md`(v1)를 독립 검토(`research/contract-review-v1.md`, R01–R20)로 고친 판이다. v1은 이 문서로 대체한다. 구현 에이전트는 이 문서만 기준으로 만들고, 바꿔야 하면 먼저 이 문서를 고친다(소유: 메인 세션).

- **이름**: 제품 QuietClerk(한국어 캐릭터 맥서기). 명령·import 패키지 `quietclerk`, 저장소 `rec2vault`. 파이썬 패키지 `rec` → `quietclerk` 이름 변경은 한 번에, 다른 작업보다 먼저 한다(10절).
- **요약 제공자**: Codex CLI, Claude Code CLI, Gemini CLI, Ollama. `agy`는 제거한다(사용자가 고른 4종에 없음). 기존 `agy` 설정은 자동 변환하지 않고 제거 사유를 화면에 안내한다.
- **운영 형태**: 로그인한 개인 Mac. 첫 업그레이드는 운영 중인 Mac mini(v1 DB, `~/rec`, 한국어 키 노트)다.
- **용어**: 입력(file) = 받는 폴더나 업로드에서 본 파일. 작업(job) = 확인된 SHA-256 하나. 실행(run) = 작업을 한 번 처리하는 시도. 단계(stage). 산출물(artifact). 게시(publish) = 노트를 볼트에 쓰는 일.

---

## 1. 프로세스와 실행

### 1.1 프로세스

| 프로세스 | 수 | 하는 일 | 감독 |
|---|---|---|---|
| `quietclerk serve` | 사용자당 1 | HTTP API·웹 화면, 스케줄러, 실행자 | launchd `KeepAlive`(label `local.quietclerk.serve`, 로그 `<root>/logs/launchd.{out,err}`, 설정 `<root>/settings.toml`). 자기 재시작 없음 |
| 모델 워커 `python -m quietclerk.worker` | 동시에 최대 1 | 화자 분리·언어 감지·받아쓰기·2차 받아쓰기 | 실행자가 자기 프로세스 그룹으로 띄우고 회수 |
| LLM CLI | 동시에 최대 1 | 교정·분류·요약 | 실행자. 자기 프로세스 그룹 |
| Ollama HTTP 요청 | 동시에 최대 1 | 같음 | 실행자. 제한 시간에 요청만 취소. Ollama 서버는 건드리지 않음 |

- **서비스 잠금**은 데이터 루트와 무관한 사용자 고정 위치 `~/Library/Application Support/QuietClerk/serve.lock`(`flock`). 못 잡으면 오류로 끝난다.
- `serve`는 시작 때 부팅 ID(무작위 128비트)를 만든다. 실행자 스레드가 예외로 죽으면 프로세스 전체가 0이 아닌 코드로 끝난다.
- 구 1분 주기 에이전트(`local.rec.pipeline`, 사용자 지정 label 포함)가 등록돼 있으면 `serve`는 시작하지 않고 "업그레이드 이행이 필요해요"를 남긴다. 교체는 10절 이행 절차로만.

### 1.2 스케줄러

60초마다(또는 API `scan` 요청 때) 입력을 스캔한다(5절). 일시정지(`paused`)는 **새 claim만** 막는다. 스캔·격리 복사·작업 등록은 계속한다(공간 부족은 예외, 5.4절).

### 1.3 처리 요청과 claim

모든 상태 변경은 `quietclerk.store`의 트랜잭션 함수로만 한다. API·스케줄러·실행자는 직접 UPDATE를 만들지 않는다.

**처리 요청**(`request_process(job_id, mode)`): 한 트랜잭션에서 ① 2.2절 허용 전이 검사 ② `requested_mode` 저장 ③ `attempts=0, interrupt_count=0, next_attempt_at=0, blocked_reason=NULL` ④ `status='queued'`.

**claim**(실행자만): `BEGIN IMMEDIATE` 안에서
1. 대상 선택: `status='queued' OR (status='retry_wait' AND blocked_reason IS NULL AND next_attempt_at<=:now)`, `exclude_requested=0`, `ORDER BY created_at, job_id LIMIT 1`.
2. 조건부 UPDATE(`status='running', claimed_by=:boot, claimed_at=:now`) — 영향 행 1이 아니면 끝(실행을 만들지 않음).
3. `runs` 삽입(`mode=requested_mode`, 설정 스냅샷, 동의 스냅샷 8.2절, 언어 고정값 스냅샷).
4. `jobs.active_run_id` 설정.
5. 커밋.

단계 기록·완료·실패 쓰기는 `job_id`와 `active_run_id`, `claimed_by`가 모두 일치할 때만 반영한다(빼앗긴 실행의 늦은 쓰기 방지).

### 1.4 시작 시 복구

`status='running' AND (claimed_by IS NULL OR claimed_by<>:boot)`인 작업:
- 해당 실행·진행 중 단계를 `interrupted`로 닫는다.
- 게시 기록(7.4절)이 진행 중이면 먼저 게시 복구를 한다(LLM을 다시 부르지 않음).
- 작업은 `retry_wait`, `last_error='interrupted'`, `interrupt_count+=1`, **`attempts`는 그대로**. `interrupt_count`가 3이면 `failed(interrupted_repeatedly)`.
- `interrupt_count`는 실행이 정상 종료하거나 사용자가 처리 요청을 하면 0으로.

### 1.5 제한 시간

| 단계 | 제한 시간 | 근거 |
|---|---|---|
| convert | max(5분, 0.2 × 길이) | 35분 녹음 3초(실측) |
| diarize | max(10분, 0.5 × 길이) | 35분 16초(실측) |
| detect_language | 5분 | 표집 구간만 |
| transcribe | max(20분, 1.5 × 길이) | RTF 0.111–0.122(벤치) |
| second_pass | max(20분, 1.5 × 길이) | RTF 0.081–0.086(벤치) |
| LLM 호출 1회 | 15분 | 지금 값 |

초과 시: 워커·CLI는 프로세스 그룹에 SIGTERM → 10초 → SIGKILL → 회수. Ollama는 요청 취소. 실패 사유 `timeout:<stage>`(재시도 가능).

진척: 워커는 stdout에 `{"type":"progress","value":0.0-1.0}` 이벤트를 낼 수 있다. 화면은 단계·경과 시간·마지막 진척만 보이고 남은 시간은 보이지 않는다.

---

## 2. 작업 상태

### 2.1 상태

| `jobs.status` | 뜻 | 보조 필드 |
|---|---|---|
| `skipped` | 정책상 처리 안 함 | `skip_reason`: `too_short`, `before_cutoff`, `no_speech`, `user_excluded` |
| `queued` | 대기 | `requested_mode` |
| `running` | 처리 중 | `stage`, `active_run_id`, `exclude_requested` |
| `retry_wait` | 다음 시도 대기 | `next_attempt_at`, `blocked_reason`(`auth`, `no_local_provider`, `no_verified_provider`, `disk_low`, `vault_migration`, `note_update_blocked`, `note_conflict`)이 있으면 시간으로 풀리지 않음 |
| `failed` | 끝난 실패 | `last_error`: `max_attempts`, `interrupted_repeatedly`, `unsupported_language`, `context_too_long`, `tool_use_detected`, `audio_decode` |
| `done` | 게시까지 완료 | `current_run_id`, `note_path` |

해시를 확인하기 전에 거부된 입력(너무 큼, 형식·코덱 거부, 디코드 실패)은 **작업이 아니다.** `files.intake_status='rejected'`와 `reject_reason`으로 남는다(5절).

### 2.2 전이

| 전이 | 계기 | 동작 |
|---|---|---|
| → `queued` | 스캔 | 5절 확인 통과, 전체 해시·아카이브 확정 |
| → `skipped(too_short|before_cutoff)` | 스캔 | 전체 해시 확인 후 등록, 아카이브는 만들지 않음 |
| `queued`/`retry_wait` → `running` | claim | 1.3절 |
| `running` → `done` | 게시 완료 | 7.4절 |
| `running` → `retry_wait` | 재시도 가능한 실패 | `new=attempts+1`; `new<3`이면 `retry_wait`, `next_attempt_at=now+300×new` |
| `running` → `failed` | `new>=3`, 또는 재시도 불가 사유 | 한 번에 기록 |
| `running` → `retry_wait(blocked)` | 인증·제공자·공간 또는 노트 충돌의 사용자 조치만 남음 | `attempts` 그대로. 노트 충돌은 자동 재시도하지 않음 |
| `running` → `skipped(no_speech)` | 언어 감지에서 발화 없음 | |
| `running` → `skipped(user_excluded)` | `exclude_requested=1`을 다음 확인 지점에서 발견 | 확인 지점: 각 단계 시작 전, 외부 호출 전, 게시 전 |
| `retry_wait` → `queued` | 사용자 처리 요청, 또는 막힌 사유가 해소됨(로그인 확인·설정 변경) | 1.3절 처리 요청 |
| `done`/`failed` → `queued` | 사용자 처리 요청(모드 3.3절) | 1.3절 |
| `skipped(too_short|before_cutoff|no_speech)` → `queued` | 사용자 "이 녹음 처리하기" | 5.5절 승격 |
| `skipped(user_excluded)` → 이전 상태 아님, `queued` | 사용자 "제외 해제" | 처리 요청과 같음 |
| 아무 상태 → `skipped(user_excluded)` | 사용자 "제외" | `running`이면 `exclude_requested=1`만 |

허용되지 않은 요청은 API가 409와 현재 상태를 돌려준다. 사용자가 풀 수 있는 정책 사유는 `too_short`, `before_cutoff`, `no_speech`, `user_excluded`뿐이다. 크기·형식·코덱·경로 거부는 어떤 요청으로도 우회하지 않는다.

---

## 3. 저장

### 3.1 DB 스키마 v2

```sql
PRAGMA foreign_keys = ON;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);           -- schema_version, vault_migration
CREATE TABLE files (
  path TEXT PRIMARY KEY,                 -- 받는 폴더 기준 상대 경로(표시용 NFC 이름은 name_nfc)
  name_nfc TEXT NOT NULL, source TEXT NOT NULL CHECK (source IN ('syncthing','upload','migrated')),
  size INTEGER NOT NULL, mtime REAL NOT NULL, last_change REAL NOT NULL,
  intake_status TEXT NOT NULL CHECK (intake_status IN ('waiting','rejected','registered','duplicate')),
  reject_reason TEXT, sha256 TEXT, first_seen REAL NOT NULL);
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL,
  source_name TEXT NOT NULL, recorded_at TEXT NOT NULL, archive_path TEXT, duration_sec REAL,
  status TEXT NOT NULL CHECK (status IN ('skipped','queued','running','retry_wait','failed','done')),
  skip_reason TEXT, stage TEXT, requested_mode TEXT NOT NULL DEFAULT 'auto',
  attempts INTEGER NOT NULL DEFAULT 0, interrupt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at REAL NOT NULL DEFAULT 0, blocked_reason TEXT, last_error TEXT,
  exclude_requested INTEGER NOT NULL DEFAULT 0, language_override TEXT CHECK (language_override IN ('ko','en')),
  claimed_by TEXT, claimed_at REAL, active_run_id TEXT, current_run_id TEXT,
  note_path TEXT, review_reasons TEXT,   -- JSON 목록
  legacy INTEGER NOT NULL DEFAULT 0,     -- v1에서 옮겨 온 결과(재사용 캐시 없음)
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  mode TEXT NOT NULL CHECK (mode IN ('auto','resume','from_transcribe','resummarize')),
  settings_json TEXT NOT NULL, consent_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running','done','failed','interrupted','skipped','cancelled')),
  started_at REAL NOT NULL, finished_at REAL, error TEXT);
CREATE UNIQUE INDEX one_active_run ON runs(job_id) WHERE status='running';
CREATE TABLE stage_runs (
  run_id TEXT NOT NULL REFERENCES runs(run_id), stage TEXT NOT NULL, seq INTEGER NOT NULL,
  parent_seq INTEGER, chunk TEXT,        -- 교정 분할 호출 식별
  status TEXT NOT NULL CHECK (status IN ('running','reused','done','failed','timeout','interrupted','cancelled','not_run')),
  backend TEXT, model TEXT, provider TEXT,
  endpoint_class TEXT CHECK (endpoint_class IN ('local','external','unknown')),
  sent_fields TEXT,                      -- 실제로 보낸 필드 JSON, 재사용이면 []
  reused_from TEXT,                      -- 재사용한 산출물의 원 run_id/stage
  started_at REAL, finished_at REAL, error TEXT,
  PRIMARY KEY (run_id, stage, seq));
CREATE TABLE publications (                -- 7.4절 게시 기록
  run_id TEXT PRIMARY KEY REFERENCES runs(run_id), job_id TEXT NOT NULL,
  target_path TEXT NOT NULL, prev_hash TEXT, new_hash TEXT NOT NULL, temp_path TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('prepared','renamed','committed','conflict')), updated_at REAL NOT NULL);
CREATE TABLE note_fields (                 -- 7.2절 소유권
  job_id TEXT NOT NULL REFERENCES jobs(job_id), field TEXT NOT NULL,
  owner TEXT NOT NULL CHECK (owner IN ('engine','user')), last_generated TEXT,
  PRIMARY KEY (job_id, field));
CREATE TABLE note_tasks (                  -- 7.3절 할 일
  task_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  first_run_id TEXT NOT NULL, text TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE tombstones (sha256 TEXT PRIMARY KEY, deleted_at REAL NOT NULL);   -- 9.3절
```

모든 연결: WAL, `busy_timeout=15000`, `foreign_keys=ON`. 실행자·API·스케줄러가 각자 연결을 연다.

### 3.2 v1 → v2 이행 (10절 업그레이드 안에서만 실행)

1. 구 서비스 정지·회수 확인(10.2절), 이행 배타 잠금.
2. `meta` 테이블이 없고 v1 구조(`files`, `jobs` 컬럼 일치)일 때만 v1로 인정. 모르는 구조나 더 높은 버전이면 아무것도 쓰지 않고 중단.
3. **백업**: Python `sqlite3.Connection.backup()`으로 `state.sqlite3.bak-<시각>`에 완성한 뒤 확정(WAL의 최근 커밋까지 포함).
4. 한 트랜잭션: `*_v2` 임시 테이블 생성 → 데이터 변환 → 기존 테이블 삭제 → 이름 변경 → `meta.schema_version=2`.
   - 상태: `failed_retryable`→`retry_wait`(기존 `updated_at + 300×attempts`를 `next_attempt_at`으로), `failed_final`→`failed`, `running`→`retry_wait(interrupted)`(attempts 그대로).
   - `error`가 `before_cutoff`·`too_short`면 `skip_reason`으로, `decode`·`too_big`·`too_long`·`format`이면 그 작업을 `files.intake_status='rejected'`로 옮기고 작업 행은 남기되 `status='skipped'`, `skip_reason='legacy_rejected'`(승격 불가).
   - `output_path`→`note_path`, `error`→`last_error`, `warnings`→`review_reasons`.
   - `recorded_at`은 기존 `job_id`의 앞 15자에서 그대로(재해석하지 않음).
   - `current_run_id`는 NULL, `legacy=1`(v1 work 파일은 보존하지만 재사용 캐시로 올리지 않음).
   - `files.source='migrated'`, 모르는 `sha256`은 NULL.
5. 중간에 끊기면 트랜잭션이 되돌아가고 다음 업그레이드 때 다시 한다. 백업은 새 버전으로 정상 실행이 확인된 뒤에만 오래된 것부터 지운다(최근 3개 유지).
6. 이행 도구는 v1 DB 사본 fixture(각 상태, WAL에만 있는 최근 변경, skipped 가상 archive_path)로 테스트한다.

### 3.3 설정

`settings.toml`. 우선순위: 환경 변수 `QC_*` > 파일 > 기본값. 화면은 유효값과 파일값을 구분해 보이고, 환경 변수로 덮인 항목은 화면에서 바꿀 수 없게 표시한다.

| 키 | 타입 | 기본값 | 환경 변수 | 실행 중 변경 |
|---|---|---|---|---|
| `root` | 경로 | 신규 `~/QuietClerk`, 업그레이드 시 기존 `~/rec` 채택 | `QC_ROOT` | 불가(유지보수 명령) |
| `inbox` | 경로 | `<root>/inbox` | `QC_INBOX` | 불가 |
| `output` | 경로 | `<root>/notes` | `QC_OUTPUT` | 다음 실행부터 |
| `since` | `YYYY-MM-DD HH:MM` | 설치 시각 | `QC_SINCE` | 다음 스캔부터 |
| `min_duration_sec` | 정수 | 300 | `QC_MIN_DURATION_SEC` | 다음 스캔부터 |
| `stable_sec` | 정수 | 60 | `QC_STABLE_SEC` | 다음 스캔부터 |
| `language.mode` | `auto`·`ko`·`en` | `auto` | `QC_LANGUAGE` | 다음 실행부터 |
| `language.default` | `ko`·`en` | 첫 설정 화면 언어 | — | 다음 실행부터 |
| `notes.output_language` | `same`·`ko`·`en` | `same` | — | 다음 실행부터 |
| `providers.order` | 목록 | 설치·검증된 제공자 | — | 다음 실행부터 |
| `providers.local_only` | 불리언 | `false` | `QC_LOCAL_ONLY` | 다음 실행부터 |
| `providers.consent` | 제공자별 허용 필드 | 비어 있음(8.2절) | — | 다음 실행부터 |
| `providers.ollama.model` | 문자열 | 없음 | — | 다음 실행부터 |
| `providers.ollama.endpoint` | URL | `http://127.0.0.1:11434` | — | 다음 실행부터 |
| `providers.allow_unverified` | 제공자 이름 목록 | `[]` | — | 다음 실행부터 |
| `providers.omp.profile` | 문자열 | `quietclerk` | — | 다음 실행부터 |
| `providers.codex.effort` | 문자열 | `low` | — | 다음 실행부터 |
| `providers.codex.speed` | `standard`·`fast` | `standard` | — | 다음 실행부터. `fast`는 Codex Fast mode(`service_tier="fast"`, `features.fast_mode=true`): 약 1.5배 빠르고 구독 사용량을 2.5배 쓴다. 2026-11-10 Mac mini 실측(같은 요약 요청 3회씩, 중앙값) 보통 15.4초 → 빠르게 10.9초 |
| `server.port` | 정수 | 설치 때 빈 포트 | `QC_PORT` | 재시작 |
| `retention.wav_days` | 정수 | 7 | — | 다음 정리부터 |
| `ui.language` | `ko`·`en` | 시스템 언어 | — | 즉시 |

- 이전 `REC_*`·`settings.env`는 업그레이드 이행이 한 번 변환한다: 임시 TOML에 쓰고 다시 읽어 검증 → rename → `settings.env`를 `settings.env.migrated`로. 런타임에 `REC_*` 별칭은 없다.
- 설정의 ‘버전’은 인증된 `/api/status`의 `engine_version`(설치된 `quietclerk` 패키지 메타데이터, 없으면 `null`), `installation_method`(`app`/`cli`, 유효한 앱 소유 기록이 있을 때만 `app`), `last_updated_at`(성공한 엔진 업데이트의 `finished_at`, 없으면 `null`)을 표시한다. 앱 버전은 엔진에서 추정하지 않고 앱 메뉴에서 확인하도록 안내한다.
- 화면에서 저장하면 파일 전체를 다시 쓴다(주석 보존 안 함, 문서에 명시).

---

## 4. 산출물과 캐시

### 4.1 위치와 원자성

- `work/<job_id>/runs/<run_id>/<name>`. 데이터는 `<name>.part` → rename, 그다음 `<name>.meta.json`을 `.part` → rename. **메타가 없는 데이터는 재사용하지 않는다.**
- 재사용은 하드링크(안 되면 복사). 하드링크된 파일은 불변이다. 새 결과는 항상 새 임시 파일에서 rename.
- `jobs.current_run_id`는 **마지막으로 게시까지 성공한 실행**만 가리킨다.

### 4.2 메타데이터

```json
{"stage": "transcribe", "producer": {"run_id": "…", "stage_seq": 1},
 "inputs": {"audio.wav": "<sha256>", "language.json": "<sha256>"},
 "params": {…단계별 표…}, "output_sha256": "<sha256>", "created_at": "…", "ok": true}
```

### 4.3 단계별 캐시 키

| 단계 | inputs | params |
|---|---|---|
| convert | 원본 SHA-256 | 변환 규격(16kHz/mono/s16), ffmpeg 버전, 변환 규칙 버전 |
| diarize | audio.wav | 모델 ID@revision, 백엔드, 규칙 버전 |
| detect_language | audio.wav, diarize | 표집 규칙 버전, 모델 ID@revision, 언어 설정(고정이면 단계 자체를 `not_run`) |
| transcribe | audio.wav, language | 처리 언어, ASR·aligner 모델 ID@revision, 분할 길이, 정렬 인자 |
| second_pass | audio.wav, language | 처리 언어, 모델 ID@revision |
| turns | transcribe, diarize | 결합 규칙 버전(겹침·간격 1.5초) |
| correct | turns, second_pass | 프롬프트 버전, 처리 언어, 허용 제공자 집합·순서, 제공자 모델 설정 |
| classify | correct, source_name | 프롬프트 버전, 정렬된 프로젝트 목록 해시, 노트 출력 언어, 허용 제공자 집합 |
| summarize | correct, classify | 프롬프트·양식 버전, 노트 출력 언어, 허용 제공자 집합 |
| note | — | **캐시하지 않음.** 매번 현재 볼트 파일과 병합(7절) |

재사용 조건: 메타 `ok=true`, inputs 해시 일치, params 일치, 데이터 파일의 해시가 `output_sha256`과 일치. 재사용은 `stage_runs.status='reused'`, `reused_from`, `sent_fields=[]`로 기록한다(과거 외부 전송 이력은 원 실행에 남아 있음).

같은 작업의 실패·중단 실행도 재사용 후보이며, `legacy=1`은 메타 없는 v1 결과를 캐시로 승격한다는 뜻이 아니다. 이후 생성된 검증된 v2 산출물은 재사용한다. 메타의 JSON 표현과 같은 형태로 params를 비교한다. 자동 재시도는 같은 처리 요청에서 완료된 단계를 재사용하며, `resummarize`/`from_transcribe`의 강제 재계산 범위는 새 사용자 요청의 첫 실행에만 적용한다.

### 4.4 재처리 모드

| 모드 | 화면 이름 | 재사용 금지 범위 |
|---|---|---|
| `auto` / `resume` | (자동) / 이어서 처리 | 없음(캐시 키가 안 맞는 단계만 새로) |
| `from_transcribe` | 처음부터 다시 | detect_language와 그 이후 전부(diarize는 키가 맞으면 재사용) |
| `resummarize` | 요약만 다시 | classify, summarize |

메타 없는 v1 결과는 어떤 모드에서도 재사용하지 않는다. 이행된 작업에서 이후 만들어진 v2 실행 산출물은 4.3절 검증으로 재사용한다.

### 4.5 의존 관계

```
archive ─▶ convert ─▶ diarize ─▶ detect_language ─┬▶ transcribe ─┐
                                                   └▶ second_pass ─┤
                     diarize ──────────────────────────────────────┼▶ turns ─▶ correct ─▶ classify ─▶ summarize ─▶ publish
```
(correct는 turns와 second_pass를, turns는 transcribe와 diarize를 받는다.)

---

## 5. 입력

### 5.1 받는 순서 (모든 경로 공통)

1. 경로 확인: 받는 폴더 바로 아래 일반 파일, 숨김·하위 폴더·심볼릭 링크·`통화*` 제외(무시, 기록 안 함).
2. 안정 대기: 크기·mtime이 `stable_sec` 동안 그대로. 0바이트는 `files.intake_status='waiting'`, 60분 넘으면 화면에 "빈 파일".
3. **격리 복사**: `O_NOFOLLOW`로 연 파일 핸들에서 상한(1GB)까지만 읽어 `quarantine/<임시>`에 쓰면서 SHA-256을 계산. 읽기 전후 `(dev, inode, size, mtime)`이 같아야 확정. 상한 초과면 중단하고 `rejected(too_big)`(해시 없음).
4. 형식 확인(격리본에서): `ffprobe`와 이후 `ffmpeg` 모두 `-protocol_whitelist file -f mov` 강제(MP4/M4A 데멀티플렉서만), 제한 시간 30초. 오디오 스트림 1개, 코덱 AAC(M1 허용 목록), 길이는 유한한 양수. 실패면 `rejected(format|codec|decode)`.
5. 해시로 중복 확인: 같은 해시 작업이 있으면 `duplicate`, 격리본 삭제. `tombstones`에 있으면 `rejected(deleted_by_user)`.
6. 정책 확인: 길이 < `min_duration_sec` → `skipped(too_short)`, 녹음 시각 < `since` → `skipped(before_cutoff)`(포함 목록에 있으면 통과), 3시간 초과 → `rejected(too_long)`.
7. 통과: 격리본을 `archive/<job_id>/source.m4a`로 rename(같은 볼륨), 작업 `queued`. 정책 건너뜀이면 격리본을 지우고 작업 `skipped`(원본은 받는 폴더에 남음).
8. convert 단계에서 실제 디코드 길이가 probe 길이와 10% 넘게 다르거나 3시간을 넘으면 `failed(audio_decode)`.

`job_id`는 `<녹음 시각>-<해시 앞 8자>`. 이미 있는 다른 해시와 겹치면 16자, 32자로 늘린다. 녹음 시각은 파일 이름의 `YYMMDD_HHMMSS`, 없으면 mtime. NFC/NFD 정규화는 이름 표시·포함 목록 비교에만 쓰고 내용 식별은 해시로만.

### 5.2 업로드 (v0.4)

같은 순서를 따르되 3단계를 스트리밍 수신으로 대체(받는 중 상한), 미지원 확장자는 415, 장치당 동시 2개·시간당 60개, 이어 올리기 오프셋 만료 24시간.

### 5.3 기존 녹음(아직 받지 않은 것)

Syncthing 목록에서 고른 이름을 포함 목록에 넣고 무시 패턴에서 뺀다(지금 `backfill`). 받으면 5.1 순서. 이것은 2.2절의 승격과 다른 경로다.

### 5.4 공간 부족

여유 공간 < 2GB면 claim, 격리 복사, 아카이브 확정을 모두 멈추고 화면에 경고한다. 실행자는 claim 전에 여유 공간을 확인하고 부족하면 claim하지 않는다(작업 상태는 그대로, 엔진 상태에 `disk_low`). 이미 실행 중인 작업이 공간 부족으로 실패하면 `retry_wait(blocked=disk_low)`, 공간이 회복되면 풀린다. 단계 출력 중 `ENOSPC`는 그 단계 실패(재시도 가능), 부분 파일은 산출물이 아니다.

### 5.5 건너뛴 녹음 승격

1. 사유가 풀 수 있는 것(`too_short`, `before_cutoff`, `no_speech`, `user_excluded`)인지 확인.
2. `files.sha256`이 같은 현재 원본을 찾는다(경로가 바뀌었어도). 없으면 `skipped` 유지, 화면 "원본이 없어요".
3. 5.1의 3–4단계를 다시 하고 해시가 작업 해시와 같은지 확인. 다르면 기존 작업은 그대로 두고 새 입력으로 등록.
4. 아카이브 확정 → 1.3절 처리 요청.

---

## 6. 언어

### 6.1 감지

- 우선순위: 작업 고정값 > 전역 고정(`language.mode`) > 자동 감지 > 기본 언어. 고정이면 감지 단계는 `not_run`(`stage_runs.status='not_run'`, `language.json`의 status도 `not_run`), `language_detected=null`.
- 표집: diarize 결과의 화자 구간을 합친 **발화 시간 집합**을 녹음 길이 6등분과 교차해, 각 부분에서 가장 긴 발화 구간을 최대 20초로 자른다. 5초 이상이 없으면 있는 구간을 쓰고, 표집 합이 15초 미만이면 `uncertain`.
- 발화 시간 집합이 비어 있을 때만 `no_speech`.
- 구간마다 Whisper 언어 판별 → 그 구간의 최고 점수 언어 하나. **몫** `share(l) = Σ dᵢ·[argmaxᵢ = l] / Σ dᵢ`(dᵢ = 실제 표집 길이). 동률은 기본 언어 우선, 그다음 사전순.
- 판정: 최다 몫 ≥ 0.6이고 ko·en이면 확정. < 0.6이면 `uncertain` → 기본 언어로 처리, 검토 사유 "언어가 섞여 있어요". 최다 언어가 ko·en 밖이고 ≥ 0.6이면 `failed(unsupported_language)`.
- 산출물 `language.json`: `{status: decided|uncertain|unsupported|no_speech|not_run, top, shares, windows}`. 점수를 확률·정확도로 표시하지 않는다. 0.6은 시작값이며 언어 표본으로 조정한다.

### 6.2 네 값

| 값 | 저장 | 결정 |
|---|---|---|
| 감지 언어 | `language.json`, 노트 `language_detected` | 6.1 |
| 처리 언어 | 단계 params, 노트 `language` | 우선순위 |
| 노트 출력 언어 | classify·summarize params, 노트 본문 | `notes.output_language`(`same`이면 처리 언어) |
| 화면 언어 | 설정 | `ui.language` |

---

## 7. 노트

### 7.1 속성 (언어 중립 키)

| 키 | 값 | 기본 소유 |
|---|---|---|
| `qc_schema` | `2` | 엔진 |
| `title` | 문자열 | 엔진 → 사용자가 바꾸면 사용자 |
| `aliases` | [제목, 원본 이름 줄기] | 엔진 |
| `date`, `started_at`, `duration_min` | `YYYY-MM-DD`, `YYYY-MM-DDTHH:MM:SS`, 숫자 | 엔진 |
| `language`, `language_detected` | `ko`·`en` / `ko`·`en`·`uncertain`·null | 엔진 |
| `type` | `meeting`·`status_update`·`presentation`·`lecture`·`one_on_one`·`brainstorm`·`other` | 엔진 |
| `division` | `work`·`personal` | 엔진 → 사용자 |
| `topics` | 목록 | 엔진 |
| `project` | 목록 | 사용자(첫 게시 때만 `[unassigned]`) |
| `project_suggest` | 문자열 | 엔진 |
| `attendees` | 목록 | 사용자(첫 게시 때 빈 목록) |
| `speakers`, `speaker_count` | 목록, 숫자 | 엔진 |
| `status` | `draft`·`reviewed` | 사용자(첫 게시 때 `draft`) |
| `needs_review`, `review_reasons` | 불리언, 목록 | 엔진 |
| `source_file`, `source_sha256`, `job_id` | 문자열 | 엔진 |
| `pipeline_asr`, `pipeline_llm`, `external_text_to` | 목록 | 엔진 |
| `processed_at` | ISO | 엔진 |
| `tags` | 목록 | 엔진은 `meeting-notes`만 넣고 빼며 나머지 보존 |

알 수 없는 키는 그대로 보존한다. 한국어 표시는 Bases 보기의 열 이름과 수식으로 한다(확인: E7a).

### 7.2 소유권

- `note_fields`에 필드별 `owner`와 `last_generated`를 둔다. 게시할 때 노트의 현재 값이 `last_generated`와 다르면 그 필드를 `user`로 바꾸고, 사용자가 화면에서 "자동 관리로 돌리기"를 누르기 전에는 되돌리지 않는다.
- 소유권 기록이 없는 노트(이행 직후 등)는 `title`, `division`을 사용자 소유로 본다. 사용자 필드의 빈 목록도 사용자 값이다.
- **노트 찾기**: frontmatter를 파싱해 `qc_schema=2`, `job_id`, `source_sha256`이 DB 작업과 모두 맞는 파일. `note_path`에 없으면 출력 폴더 아래에서 다시 찾고, 맞는 파일이 둘 이상이면 자동 선택하지 않고 `note_conflict`. 심볼릭 링크, 출력 폴더 밖 경로, 위 조건이 안 맞는 파일은 덮어쓰지 않는다.
- 파일 이름은 `YYYY-MM-DD_HHMM_{메모_}{slug}.md`(녹음 시각, 메모 유형만 `메모_`)이며 export도 같다. 다음 게시 때 job의 `recorded_at` 날짜·분과 일치하는 옛 `YYYY-MM-DD_{메모_}{slug}_HHMM.md`만 시간 우선으로 바꾼다. 기존 slug는 그대로 두며 사용자 지정 이름·새 이름 충돌은 원이름으로 게시한다.
- 이미 `YYYY-MM-DD_HHMM_`로 시작하면 새 형식으로 보아 그대로 둔다. 구형 slug의 시작도 같은 시각이면 두 형식이 모호하므로 자동 변경보다 이름 보존을 우선한다.

### 7.3 본문

```
## 할 일 / Tasks                    ← 사용자 소유 목록
- [ ] … ^task-<n>
## 회의 내용 / Meeting record         ← 엔진 구간 시작(이 제목 줄이 노트에 정확히 하나)
> [!info] …  (화자 표, 요약, 결정, 새로 제안된 할 일, 확인 필요, 전체 대화록)
## 메모 / Notes                     ← 엔진 구간 끝(시작 뒤 첫 번째), 그 아래는 사용자 영역
```
- 주석 표식은 쓰지 않는다(Obsidian 편집 화면에 글자로 보인다, 2026-11-10 사용자 보고). H1도 쓰지 않는다(Obsidian이 파일 이름을 제목으로 보여 준다). 모델 글에 경계 제목과 같은 줄이 있으면 한 단계 낮춰 쓴다.
- 다시 게시할 때 "새로 제안된 할 일"에는 이미 사용자 목록에 들어간 할 일(같은 문장)을 다시 넣지 않는다.

- 다시 게시하면 엔진 구간만 바꾸고 나머지는 바이트 그대로 둔다. 경계 제목이 없거나 시작 제목이 중복이면 게시하지 않고 `note_conflict`(작업은 `done`으로 바꾸지 않고 `current_run_id`도 그대로).
- **할 일**: 첫 게시 때 요약의 할 일을 `note_tasks`에 영속 `task_id`(무작위)로 저장하고 사용자 소유 "할 일" 목록에 쓴다. 이후 다시 요약해도 그 목록(문장·체크·삭제)을 건드리지 않는다. 새 요약의 할 일은 생성 구간 안 "새로 제안된 할 일"에 보여 주고, 사용자가 옮길 때만 목록에 들어간다. 문장 해시로 같은 할 일을 추정하지 않는다.
- 대화록 줄 ID: `t` + 1부터 번호(자릿수 고정 없음). 근거 표기 `\[t\d+(\s*,\s*t\d+)*\]`. 없는 ID는 지우지 않고 `[?t123]`로 남기고 `review_reasons`에 추가.
- 화면·노트 모두 대화록의 HTML을 이스케이프하고 링크는 노트 안 이동만 허용.

### 7.4 게시 (원자성과 복구)

1. 생성 결과를 임시 파일(출력 폴더 안 `.quietclerk-tmp/`)에 완성.
2. `publications`에 `prepared`(대상 경로, 지금 파일 해시, 새 파일 해시, 임시 경로) 커밋. 이름 변경 시 durable payload에 원경로도 기록한다.
3. 대상/원파일의 현재 해시가 `prev_hash`와 다르면 `conflict`로 끝(덮어쓰지 않음).
4. 이름 변경은 원파일을 새 경로로 원자적 no-replace rename(충돌 시 원경로로 게시). 임시 파일을 대상으로 rename → `renamed` 커밋.
5. 한 트랜잭션: `note_fields`·`note_tasks` 반영, `jobs.current_run_id`, `note_path`, `status='done'`, 해당 작업의 기존 `publications.target_path`, `publications.state='committed'`.

시작 복구: `prepared`면 임시 파일을 지우고 게시 전 상태로(이름을 옮겼다면 원경로·이전 바이트 복원). `renamed`면 대상 파일 해시가 `new_hash`인지 확인하고 5단계를 마저 한다. 노트는 하나만 남기며 LLM을 다시 부르지 않는다. 이름 변경의 데일리 링크 수정은 durable payload로 재시도하며, 잠금 아래 `- HH:MM [[옛stem|별칭]]`의 stem만 고친다(별칭·나머지 바이트 보존, 설정 꺼짐이면 쓰지 않음). 데일리 쓰기 실패는 기존 게시 후 hook처럼 기록하고 노트 게시를 되돌리지 않는다.

### 7.5 기존 노트 이행 (사용자 동의 필요)

- 명령·화면 `quietclerk notes migrate`: ① 미리보기(대상 노트, 키·값 전체 대응표, 경로, 소유권 초기화 내용, 충돌 목록) ② 동의 ③ 백업을 **볼트 밖** `<root>/note-backups/<시각>/`에(볼트 동기화로 퍼지지 않게) ④ 진행 manifest를 남기며 노트마다 변환(중단 후 다시 하면 이어서) ⑤ 볼트 상태 `meta.vault_migration='done'`.
- 대응표: `구분`→`division`(`업무`→`work`, `개인`→`personal`), `유형`→`type`(`회의`→`meeting`, `현황공유`→`status_update`, `발표회`→`presentation`, `강의`→`lecture`, `1:1`→`one_on_one`, `브레인스토밍`→`brainstorm`, `기타`→`other`), `상태`(`AI초안`→`draft`, `검토함`→`reviewed`), `프로젝트`(`미분류`→`unassigned`), `날짜`→`date`, `녹음시작`→`started_at`, `길이분`→`duration_min`, `원본파일`→`source_file`, `원본해시`→`source_sha256`, `처리_작업ID`→`job_id`, 그 밖은 7.1절 이름으로. 구형(`job_id`가 이미 영문, 2026-11-09 이전) 키도 표에 포함. 사용자가 정의한 값·키는 바꾸지 않고 충돌 목록에 보인다.
- 이행한 노트는 엔진 구간 제목(`## 회의 내용`)이 없으므로 다시 렌더하지 않는다. 그런 작업에서 "요약만 다시"를 하면 결과를 실행 산출물로 두고 `note_update_blocked`를 표시하며, 사용자가 미리보기를 보고 "새 형식으로 바꾸기"를 눌렀을 때만 새 형식 본문으로 게시한다.
- **볼트 이행 전에는 엔진이 볼트에 쓰지 않는다**(새 녹음 노트 포함). 이행을 미루면 새 노트는 실행 산출물로만 남고 화면에 "노트 이행 후 볼트에 넣어요"가 뜬다. 첫 업그레이드 화면에서 이행을 바로 제안한다.
- Bases: 기존 `회의록.base`는 덮어쓰지 않고 v2 보기 파일을 새로 만든다.
- v2 Bases는 `formula.when = date(started_at).format("YYYY-MM-DD HH:mm")`을 "녹음 시각"으로 표시하고 최근/검토 대기 뷰 모두 `started_at DESC`로 정렬한다. [Obsidian Bases 함수](https://help.obsidian.md/bases/functions)의 `date()`·날짜 `format()`을 사용한다. 기존 v2 파일은 알려진 옛 템플릿 SHA-256 또는 엄격한 YAML 파싱 결과가 일치할 때만 갱신한다. 들여쓰기·따옴표·리스트 표기만 바뀐 Obsidian 재직렬화는 허용하되 뷰 추가 등 값 변경·파싱 실패·심볼릭 링크는 보존한다.
- 명령 세부(D 구현, 2026-11-10): `python -m quietclerk.notes migrate --preview`는 아무것도 바꾸지 않고 JSON(전체 대응표·소유권 초기화·충돌)을 출력, `--apply`는 `--consent` 없이는 거부. 백업 `<root>/note-backups/<UTC 시각>/`, 진행 기록 `<root>/note-backups/migration.json`. 사용자 정의 키·프로젝트 값은 보존하고 비차단 충돌로 보고. 알 수 없는 enum 값·식별 불일치·같은 작업의 중복 노트는 그 노트의 이행을 차단하고 보고.
- **개별 본문 교체**: `GET /api/jobs/{id}/convert-note`는 현재/새 경로, 새 요약, 이전 본문(UTF-8 표시 및 정확한 바이트의 Base64), 최신 실행 ID와 미리보기 토큰을 반환하며 파일·DB를 바꾸지 않는다. `POST`는 `{consent:true, preview_token:"…"}`가 필수다. 기존 9장 세션·Origin·CSRF·Idempotency-Key 규칙을 적용한다. 미리보기 이후 노트·작업·산출물이 바뀌면 409이고 다시 미리보기한다.
- 최신 실행(실패한 실행 포함)의 `turns`, `correct`, `classify`, `summarize` 산출물만 사용한다. 메타 `ok`, 단계·입력 연결·SHA를 검증하고 없거나 손상되면 이유와 함께 거절한다. LLM·모델은 호출하지 않는다.
- 교체 직전 노트를 볼트 밖 `<root>/note-backups/<UTC 시각>-convert/`에 fsync 백업하고, 기존 merge 규칙으로 사용자 frontmatter 값을 유지한다. 이전 본문 전체는 `## 메모`/`## Notes` 아래 접힌 note callout에 안전한 텍스트로 보관한다. HTML·Obsidian/플러그인·Markdown 문법은 비활성화하고 원래 바이트는 callout 안 Base64로도 보관한다(줄끝·마지막 개행까지 복원 가능).
- 새 이름은 `날짜_시각_제목`이며 충돌 시 교체하지 않는다. 7.4 저널로 이름 이동·본문 교체를 복구하고 기존 hook으로 데일리 링크·검색을 갱신한다. 커밋 시 `done`, 대기 사유 제거, 개별 migrated 표식 제거, `legacy=0`으로 이후 보통 재게시를 허용한다.
- **2026-11-12 운영 발견**: 이행된 노트의 게시 차단이 일반 재시도 실패로 분류되어 같은 모델·텍스트 단계를 반복 실행했다. 노트 충돌은 사용자 조치 대기로 고치고, 실패 실행의 검증된 산출물 재사용 및 동의 기반 개별 교체를 명시한다. 이 문서는 실제 회의 내용·식별자를 포함하지 않는다.

---

## 8. 요약 제공자

### 8.1 인터페이스

```python
class Provider(Protocol):
    name: str                                   # 'codex' | 'claude' | 'gemini' | 'ollama'
    def status(self) -> ProviderStatus: ...     # installed, logged_in, version, tool_block: verified|unverified|unsupported
    def endpoint_class(self) -> Literal['local', 'external', 'unknown']: ...
    def complete(self, prompt: str, *, timeout: float) -> Completion: ...
```

`Completion`: `text`, `model`, `endpoint_class`, `duration`. 오류: `NotInstalled`, `AuthExpired`, `RateLimited`, `Timeout`, `ContextTooLong`, `ToolUseDetected`, `ProviderError`.

- Codex·Claude·omp 실행 파일은 기존 PATH 순서가 우선이다. 없으면 사용자 HOME의 `.local/bin`, `.bun/bin`, `.npm-global/bin`, `.volta/bin`, `.cargo/bin` 순서로 실행 가능한 파일을 찾는다(각 사용자 설치 도구의 기본/관례적인 bin 위치). 셸 초기화 파일을 읽거나 plist를 변경하지 않는다. 같은 탐색을 버전·인증 확인과 실제 호출에 사용하며, 발견만으로 `tool_block` 검증 상태를 올리지 않는다.

### 8.2 선택 가능 조건과 동의

- 자동 선택·대체 경로 후보는 **`tool_block='verified'`인 제공자만.** verified는 지원 버전 범위, 도구·MCP·사용자 설정 로딩 차단 방법, 인증 저장 위치를 문서화하고 격리 미끼 시험(`research/cli-no-tool.md`)을 통과한 조합이다. 호출 직전 버전이 검증 범위 밖이면 `unverified`로 내린다.
- `unverified`는 설정 화면에서 사용자가 이유를 보고 명시적으로 켤 때만 쓴다(`providers.allow_unverified`, 그 제공자에 한해, 대체 경로에는 안 들어감). `unsupported`는 쓸 수 없다. omp는 MCP 없는 전용 프로필(`providers.omp.profile`)을 전제로 하며 미끼 시험 전까지 `unverified`.
- **외부 전송 동의**: 제공자를 켤 때 보낼 필드(`transcript`, `source_name`, `project_list`)를 보여 주고 동의받아 `providers.consent`에 저장. 실행 스냅샷(`runs.consent_json`)에 복사. 호출은 `providers.order ∩ 동의 ∩ (local_only면 local만)`.
- **로컬 전용**: `endpoint_class='local'`만. `unknown`·`external`은 어떤 단계에서도 호출하지 않는다. Ollama 판정: 접속 주소가 loopback이 아니면 `external`. loopback이면 `/api/show`로 모델을 조회해 `remote_host`·`remote_model`이 있으면(클라우드 모델) `external`, 로컬 가중치(`model_info`·GGUF 형식)가 확인되면 `local`, 그 밖은 `unknown`. 확인은 호출 때마다(모델 변경·리다이렉트 대비). 사용자 확인 문구는 기술적 확인을 대신하지 않는다. (근거: Ollama API 문서, E 묶음 구현 때 재확인)

### 8.3 오류별 처리

| 오류 | 같은 제공자 재시도 | 다음 제공자 | 모두 소진 시 |
|---|---|---|---|
| 구조 검증 실패(JSON·ID·근거) | 1회 | 예 | 단계 실패(재시도 가능) |
| `NotInstalled`, `AuthExpired` | 아니오 | 예 | 남은 조치가 로그인뿐이면 `retry_wait(blocked=auth)` |
| `RateLimited`, `Timeout`, `ProviderError` | 아니오 | 예 | 일반 `retry_wait` |
| `ContextTooLong` | 아니오 | 예 | `failed(context_too_long)` |
| `ToolUseDetected` | — | **아니오, 실행 즉시 중단** | `failed(tool_use_detected)`, 보안 사유 기록 |
| 허용 제공자 없음 | — | — | `retry_wait(blocked=no_verified_provider 또는 no_local_provider)` |

- **교정**만 실패한 묶음의 원문을 유지하고(`review_reasons`에 "일부 교정 실패") 계속 진행한다. **분류·요약**은 실패하면 단계 실패이고, 기존 게시 노트는 그대로 둔다.
- 외부 호출 **전에** `stage_runs` 행을 만들고, 호출 뒤 실패해도 `provider`·`sent_fields`를 남긴다. 교정 분할 호출은 `chunk`(줄 범위)·`parent_seq`로 구분한다.
- 노트의 `external_text_to`는 이 결과를 만드는 동안 실제로 글자를 보낸 모든 제공자다(최종 성공 제공자만이 아니다).

### 8.4 호출 방식

- 프롬프트는 stdin. 환경 변수는 PATH, HOME, 제공자 인증에 필요한 것만. 작업 디렉터리는 빈 임시 폴더. 구체적 플래그는 S3 결과로 제공자마다 고정한다. stdin·환경 최소화만으로 무도구라고 주장하지 않는다.
- Ollama: 요청마다 `keep_alive: 0`, 입력에 맞춘 `num_ctx`, 제한 시간에 요청 취소.

### 8.5 S3 결과 반영 (2026-11-09, `research/cli-no-tool.md`)

| 제공자 | `tool_block` | 호출 방식 | 근거 수준 |
|---|---|---|---|
| Claude Code 2.1.319 | `verified` | `claude -p --tools "" --strict-mcp-config --safe-mode --disable-slash-commands --setting-sources "" --permission-mode dontAsk`(stdin 프롬프트). 모델에 보이는 도구 0개 | 실제 CLI·가상 입력(MacBook). Mac mini에는 아직 미설치·미로그인 |
| Codex 0.163–0.167 | `verified`(아래 명령 조건) | `codex exec --sandbox read-only --ephemeral --ignore-user-config --ignore-rules -c features.shell_tool=false -c web_search="disabled" -c features.apps=false -c features.plugins=false -c features.view_image=false -c features.image_generation=false -c features.hooks=false`. 도구 선언 일부(`apply_patch`, `spawn_agent` 등)는 남고 샌드박스·설정이 거부하는 방식이라, `--json` 이벤트에서 `command_execution`·`file_change`·`mcp_tool_call`·`web_search`가 보이면 `ToolUseDetected` | 실제 CLI·가상 입력(MacBook·Mac mini). **운영 파이프라인에 2026-11-09 적용**, Mac mini에서 직접 지시 대조 시험으로 파일 읽기 실패 확인 |
| Gemini CLI 0.46.0 | `unsupported` | 개인 Google 계정 구독 인증을 서버가 거절(`IneligibleTierError`). 모의 서버로는 `--admin-policy` 전체 거부로 도구 0개 | 모의 서버(가정)·문서 |
| Ollama | 미정 | 8.2절, 로컬 실행 판별 방법 확인 전까지 `unknown` | — |
| omp 18.18.3 | `unverified` | `omp -p --no-session --no-tools --no-extensions --no-skills --no-rules --no-context-files --no-lsp --no-title`. 내장 도구는 0개가 되고 직접 지시해도 미끼 파일을 못 읽었다. 그러나 `~/.omp/agent/mcp.json`의 MCP 도구(41개)가 `--tools=`로도 빠지지 않는다 → MCP 없는 전용 프로필(`--profile quietclerk`)에서 다시 시험해야 함(그 프로필에 한 번 로그인 필요, 사용자 작업·나중) | 실제 CLI·가상 입력(MacBook, 2026-11-09). Mac mini 미설치 |
| pi(`@mariozechner/pi-coding-agent` 0.73.1) | 미정 | 이 MacBook·Mac mini 모두 미설치. 구독 로그인 후 같은 미끼 시험 필요(사용자 작업·나중) | 확인 못 함 |

- 따라서 사용자가 고른 4종 중 **지금 쓸 수 있는 구독 CLI는 Codex와 Claude**다. Gemini CLI는 구독 경로가 막혀 지원 대상에서 빠진다(API 키 방식은 사용자 결정 범위 밖). 
- 남은 확인: Codex `web_search` 차단 실측(E8b 구현 직후), 실제 녹음 파이프라인에서 차단 호출 확인(E8b 완료 기준).

---

## 9. 로컬 API와 보안 (M1: loopback 전용)

### 9.1 인증

- `quietclerk open`: 같은 OS 사용자만 읽을 수 있는 파일(`0600`, 서비스 지원 폴더)에서 서버가 만든 일회용 토큰을 읽어, `http://127.0.0.1:<port>/#bootstrap=<토큰>`으로 브라우저를 연다. 로컬 번들 JS가 주소에서 토큰을 즉시 지우고 `POST /api/session`으로 한 번 교환한다. 토큰 수명 60초, 한 번만 사용.
- 인증 없이 토큰을 발급하는 HTTP 경로는 없다.
- 세션: 암호학적 난수, `HttpOnly; SameSite=Strict; Path=/`, 유휴 12시간·최대 7일 만료, "로그아웃" 시 폐기. bootstrap 응답은 `Cache-Control: no-store`, `Referrer-Policy: no-referrer`.
- 모든 `/api` 요청(GET, 오디오, SSE 포함)에 세션 필요. 예외는 데이터를 담지 않는 `GET /`와 `GET /bootstrap.js`뿐(bootstrap 교환을 위한 정적 응답, 같은 CSP·no-store·Host 검사 적용). `Host`는 `127.0.0.1:<port>`·`localhost:<port>`만. 상태 변경은 `Origin` 일치 + `X-CSRF-Token`. CORS 없음. 상태 변경 GET 없음.
- CSP: `default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`.
- 같은 네트워크 접근은 M1에서 **끈다**(설정 항목 없음). 켜는 작업은 TLS·장치 권한·폐기·Host 규칙을 따로 설계한 뒤.

### 9.2 엔드포인트 (JSON 스키마는 `quietclerk/server/schema.json`으로 함께 관리)

| 메서드·경로 | 요청 | 응답·오류 |
|---|---|---|
| `POST /api/session` | `{token}` | 204 + 쿠키 / 401 |
| `GET /api/status` | — | 엔진·`engine_version`·`installation_method`·`last_updated_at`·일시정지·현재 작업·단계·경과·제공자 상태·폰 연결(인증 필요) |
| `GET /api/jobs?status=&limit=&cursor=` | — | 목록 |
| `GET /api/jobs/{id}` | — | 상세, 실행·단계 이력(보낸 필드 포함) |
| `POST /api/jobs/{id}/process` | `{mode}` | 202 / 409 `{status}` / 404 |
| `GET /api/jobs/{id}/convert-note` | — | 무변경 미리보기(현재/새 경로·새 요약·보존할 본문·실행 ID·토큰) / 409 `{error,reason,detail}` |
| `POST /api/jobs/{id}/convert-note` | `{consent:true, preview_token}` | 200 `{job_id,note_path,backup_path,status:"done"}` / 400(동의 없음) / 409(결과 없음·변경·충돌) |
| `POST /api/jobs/{id}/exclude`, `/include` | — | 202 / 409 |
| `PUT /api/jobs/{id}/language` | `{override: ko|en|null}` | 204 / 400 |
| `POST /api/jobs/{id}/delete-local` | `{scope: "processing_data"}` | 202 / 409(실행 중이면 제외 후 처리) |
| `GET /api/jobs/{id}/audio` | Range | 200/206, 파일 없음 410, 잘못된 Range 416. DB의 아카이브 경로만 사용, 요청 값을 경로에 결합하지 않음 |
| `GET /api/notes` | — | 엔진이 게시한 노트 목록 |
| `GET /api/settings`, `PUT /api/settings` | 3.3절 키만, 타입 검사 | 200 / 400 `{field, error}` / 409(환경 변수로 덮인 키) |
| `GET /api/backlog`, `POST /api/backlog/request` | `{names: []}` | 목록 / 202. Syncthing 색인으로 폰의 전체 기존 목록을 얻을 수 있는지는 S1 미결이므로 `inventory: complete|partial|unavailable`, `phone_recordings: 숫자|null`로 정직하게 표시 |
| `POST /api/notes/migrate/preview`, `/apply` | — | 7.5절 |
| `POST /api/pause`, `/resume`, `/scan` | — | 204 |
| `GET /api/events` | SSE | 상태 변화 |
| `GET /api/setup/checks` | — | 칩·메모리·디스크·ffmpeg·uv 상태와 해결법 |
| `GET /api/setup/models`, `POST /api/setup/models/download` | — | 모델별 상태·크기·진행률 / 202, 이어받기, 공간 부족 409 |
| `GET /api/setup/vaults` | — | Obsidian 볼트 후보(Obsidian 설정 파일의 볼트 목록), 경로 존재 여부 |
| `GET /api/providers`, `POST /api/providers/{name}/check` | — | 설치·로그인·버전·tool_block·endpoint_class / 시험 호출 결과(가상 텍스트, 동의 범위 안에서만) |
| `GET /api/sync/pairing`, `POST /api/sync/pairing/approve` | `{device_id}` | Mac 장치 ID·QR 데이터·연결 요청 목록 / 승인 |
| `GET /api/sync/folder` | — | 받는 폴더 공유 상태(요청 보냄·수락 대기·연결됨), 폰에 있는 녹음 수(S1 결과 후) |

같은 요청을 두 번 보내도 상태가 한 번만 바뀐다(처리 요청은 이미 `queued`면 204).

### 9.3 보존과 삭제

| 데이터 | 위치 | 기본 보존 | 삭제 |
|---|---|---|---|
| 원본 사본 | `archive/<job>/source.m4a` | 계속 | 작업 단위 "처리 데이터 삭제" |
| v1 통합 결과 | `archive/<job>/result.json` | 계속 | 같음 |
| 변환 WAV | 실행 폴더 | 게시 성공 7일 뒤 | 자동 |
| 실행 산출물 | `work/<job>/runs/*` | 마지막 성공·진행 중·게시 복구 중 실행 보호. 나머지는 **새 게시 성공 후** 삭제. 실패 실행은 재사용 가능한 산출물이 다음 실행에 쓰일 때까지 보존 | 자동 |
| 노트 소유권·할 일 | DB | 작업과 함께 | 처리 데이터 삭제 시 함께 |
| 노트 | 볼트 | 사용자 소유 | 엔진은 지우지 않음 |
| 로그 | `logs/` | 14일, 작업 ID만(제목·대화 내용·토큰 기록 안 함) | 자동 |
| DB 백업 | `state.sqlite3.bak-*` | 최근 3개 | 자동 |
| 노트 이행 백업 | `<root>/note-backups/` | 사용자가 지울 때까지 | 화면에 안내 |

- "처리 데이터 삭제": 실행 중이면 제외 요청 → 단계 종료 후 수행. 원본 사본·실행 산출물·v1 결과·소유권·할 일·DB의 대화 관련 필드를 지우고, **해시 tombstone**을 남겨 받는 폴더의 같은 파일이 다시 처리되지 않게 한다(화면의 "복원"으로만 해제). 폰 원본, 받는 폴더 파일, 볼트 노트, 외부 제공자 쪽 보존은 건드리지 못한다고 알린다. 삭제 후 오디오 API는 410.

---

## 10. 구현 순서와 업그레이드

### 10.1 순서

1. **이름 변경(단독, 한 번)**: `rec`→`quietclerk`, pyproject, import, 워커 `-m`, deploy, 테스트 격리 설정, export 허용 목록, 문서 명령. 기능 변경 없음. 기존 테스트 통과가 완료 기준.
2. **A. 실행·저장**: 3.1·3.2절 DB와 이행 도구, 1.3·1.4절 claim·복구, 4절 산출물·캐시, 1.5절 제한 시간. 공용 `store` 함수를 먼저 내놓는다.
3. 병행(A의 store 인터페이스 확정 후):
   - **B. 입력**: 5절 전체, 기존 녹음, Syncthing 자동 설정(S1 결과 후).
   - **C. 모델**: 워커 프로토콜(10.3절), Backend, 언어 감지, 모델 관리·prefetch.
   - **D. 텍스트·노트**: 프롬프트(ko/en)·단계 검증·7절 노트(소유권·할 일·게시·이행).
   - **E. 제공자**: 8절(활성화는 S3 결과 후).
4. **F. API·화면 전달**: 9절, 알림.
5. **G. 설치·업그레이드**: 서비스·플랫폼 어댑터·10.2절 업그레이드.
6. 메인 세션 통합 인수(11절).

파일 소유: `pyproject.toml`·export는 이름 변경 담당만. `docs/contracts-v2.md`·설계 문서는 메인 세션. 같은 파일을 두 에이전트가 동시에 고치지 않는다.

### 10.2 업그레이드 (Mac mini 첫 이행 포함)

1. 업그레이드는 기존 루트를 그대로 채택한다(`~/rec`). 루트 이동은 별도 유지보수 명령으로만(Syncthing 폴더 일시정지 → DB 닫기 → 파일·DB 내부 경로·설정·서비스 경로 일괄 갱신 → venv 새로 만들기 → 실패 시 되돌리기). 양쪽 루트가 다 있으면 병합하지 않고 충돌을 보고한다.
2. 구 서비스 정지: 등록된 구 label을 모두 unload → `tick.lock`을 잡을 수 있는지(=구 실행 없음) 확인 → 구 자식 프로세스 없음 확인.
3. 새 venv를 만들고 의존성·모델 확인.
4. 설정 이행(3.3절) → DB 이행(3.2절).
5. 새 서비스 등록·시작, 상태 확인. 실패하면 새 서비스를 내리고 DB·설정 백업을 되돌리고 구 서비스를 다시 등록한다. 새 서비스가 성공하기 전에는 구 서비스를 지우지 않는다.
6. 노트 이행은 화면에서 동의를 받아 따로 한다(7.5절).
7. 첫 운영 업그레이드는 Mac mini의 DB·설정·노트 사본으로 같은 절차를 먼저 끝까지 해 본 뒤에만.

앱 설치도 같은 서비스·같은 Python 실행 경로를 쓴다(S1, 2026-11-11). `install --app-install`만
앱 소유 `engine-installation.json`과 재등록 원본 `service.plist`를 support에 추가하고,
plist에 `AssociatedBundleIdentifiers`를 넣는다(ad-hoc에서는 BTM이 무시할 수 있음).
engine update/rollback은 두 기록도 기존 plist와 같은 트랜잭션으로 갱신/복구한다.
`login-service status|register|unregister`는 JSON으로 앱 소유·등록·로그인 설정 상태를 돌려준다.
등록은 잠금·bootstrap/start·신선한 인증 상태 확인, 해제는 bootout·실행 잠금 회수·LaunchAgents
plist 삭제다. 앱 소유 기록 없는 기존 CLI 설치는 변경하지 않는다. Rust는 이 명령을 부르기만 하며,
별도 plist/launchctl 쓰기 구현을 두지 않는다. 상세 파일 형식·공존·실측은 `contracts-app.md` 6절.

A1(0.0.3)의 앱 경로는 `--app-manifest <번들 manifest>`·`--app-tools <서명된 도구 폴더>`를
`install --app-install`/앱 소유 `update`에만 전달한다. manifest의 wheel·의존성 목록 SHA-256을
확인하고, macOS arm64/Python 3.12 목록을 `uv pip --require-hashes --only-binary :all:`로 설치한다.
CLI 기본 설치·업데이트는 기존 PATH·모델 검사 동작을 그대로 쓴다. 앱만 venv에 복사한 LGPL 도구를
`QC_FFMPEG`/`QC_FFPROBE` 절대 경로로 plist에 기록한다. 마법사의 uv 확인도 venv 도구의 `QC_UV` 절대 경로를 쓴다.
모델은 첫 설치에서 받고 업데이트에서는 로컬 스냅샷만 확인한다.
업데이트는 인증된 pause → 기존 작업 종료 대기 → 기존 update/rollback →
원래 pause 상태 복원이다. 강제 종료 복구용 `app-transaction.json`은 서비스/기록만 복구하며,
업데이트에서 DB·설정·노트는 되돌리지 않는다. 상세 상태/실패/트러스트 경계는 앱 계약 7절이다.
앱 최초 인증의 bootstrap fragment는 `next=setup`일 때만 `/setup/1`, 그 밖은 `/home`로
이동한다. 임의 외부/상대 URL을 받지 않고 token을 HTTP URL·로그로 전달하지 않는다.

### 10.3 워커 프로토콜

- 인자: `--run-settings <실행 설정 JSON 경로>`(읽기 전용) `--stage <이름>` `--in <입력>`… `--out <출력>`. 워커는 환경 변수로 설정을 다시 합성하지 않는다.
- stdout: 줄마다 JSON 이벤트 `{"type":"progress"}`, 마지막에 `{"type":"result","models":{"asr":"id@rev","aligner":"id@rev"},"output":"<경로>"}`. 라이브러리 로그는 stderr.
- 출력 규칙: 시간은 유한한 초, `0 ≤ start ≤ end ≤ duration`, 단어는 시작 시각 순(같으면 출력 순), 빈 텍스트 단어는 버림, 위반이면 `InvalidOutput`(재시도 가능 1회 후 실패). 단 녹음 끝을 **0.5초 이내**로 넘는 시각은 `duration`으로 맞춘다(정렬기 반올림 오차). 그 이상은 위반. 단어 시작이 앞 단어보다 **0.1초 이내**로 앞서면 앞 단어 시작으로 맞춘다(실제 56분 회의에서 구간 경계마다 0.02초 역행, 2026-11-10). 그 이상 역행은 위반.
- 받아쓰기 분할: 길이를 `n = ceil(duration / 60)` 조각으로 **균등 분할**(조각 길이 = duration / n, 최대 60초). 끝에 1초짜리 조각이 생기면 모델이 없는 말을 만들어 내는 것이 합성 영어 61초 표본에서 관찰됐기 때문(2026-11-10, C 묶음). 분할 규칙 버전을 transcribe 캐시 params에 넣는다.
- 오류는 종료 코드와 마지막 stderr JSON `{"error":"ModelMissing"|"BackendUnavailable"|"AudioDecodeError"|"InvalidOutput", "detail":…}`. 공통 계층이 재시도 가능 여부를 정한다(앞 셋은 불가).
- 화자 라벨은 공통 계층이 등장 순서로 `S1…`로 바꾼다.

---

## 11. 인수 기준 (입력·상황별 증거 연결)

검증 수준: **실제 입력** = 실제 녹음·실제 경로, **가정** = 합성 입력·가짜 제공자 단위·통합 테스트, **실행만** = 파일 존재·프로세스 실행. 미실행은 "미확인".

| ID | 상황 | 기대 결과 | 테스트·절차 | 표본 | 필요한 수준 |
|---|---|---|---|---|---|
| IN-01 | 정상 m4a, 한국어 | `done`, ko 노트 | `test_intake_ok`, E2E | 비공개 실녹음 4건(`samples/audio/`, 해시 매니페스트) + 데모 합성 | 실제 입력 |
| IN-02 | 정상 m4a, 영어 | `done`, en 노트 | E2E | 공개 영어 코퍼스(라이선스 확인 후) | 실제 입력 |
| IN-03 | 299·300초 경계 | `skipped(too_short)` / `queued` | 단위 | 합성 | 가정 |
| IN-04 | 설치 전 녹음 | `skipped(before_cutoff)` | 단위 | 합성 | 가정 |
| IN-05 | 건너뛴 녹음 승격(원본 있음·없음·내용 바뀜·다른 경로 같은 해시) | 5.5절 | 단위 | 합성 | 가정 |
| IN-06 | 통화·하위 폴더·링크·숨김 | 무시 | 단위 | 합성 | 가정 |
| IN-07 | 미지원 확장자 | 무시 | 단위 | 합성 | 가정 |
| IN-08 | 0바이트 | `waiting`, 60분 후 표시 | 단위 | 합성 | 가정 |
| IN-09 | 전송 중 | 대기 | 단위 | 합성 | 가정 |
| IN-10 | 잘린 m4a | `rejected(decode)` | 단위 | 합성 | 가정 |
| IN-11 | 위장 형식 | `rejected(format)` | 단위 | 합성 | 가정 |
| IN-12 | 외부·로컬 참조 컨테이너, 재생목록 | `rejected(format)`, 요청 0건, 미끼 파일 미열람 | 단위 + 로컬 HTTP 수신기 | 합성 | 가정 |
| IN-13 | 1GB 초과 | `rejected(too_big)`, 해시 안 함 | 단위(희소 파일) | 합성 | 가정 |
| IN-14 | 3시간 초과·길이 허위 메타·NaN 길이 | `rejected(too_long)` / `failed(audio_decode)` | 단위 | 합성 | 가정 |
| IN-15 | 공간 부족 | 격리·claim 중지, `disk_low` | 단위(공간 함수 주입) | — | 가정 |
| IN-16 | 같은 해시 재전송 | `duplicate` | 단위 | 합성 | 가정 |
| IN-17 | 같은 이름 다른 내용 | 새 작업 | 단위 | 합성 | 가정 |
| IN-18 | NFC/NFD 이름 | 같은 이름으로 표시·포함 비교 | 단위(있음) | 합성 | 가정 |
| IN-19 | 침묵·잡음 | `skipped(no_speech)` | 단위 | 합성 | 가정 |
| IN-20 | 지원 외 언어 | `failed(unsupported_language)` | 통합 | 합성 TTS | 가정 |
| IN-21 | 대화록 속 지시문 | 도구 실행 0, 미끼 파일 미열람 | S3 미끼 시험 | 합성 | 실제 CLI(격리) |
| IN-22 | 대화록 속 HTML·링크 | 이스케이프, 외부 요청 0 | 단위(렌더·화면) | 합성 | 가정 |
| IN-23 | 잘못된 JSON·중복 ID·줄 누락 | 8.3절 | 단위(가짜 제공자). 중복 ID 검출 추가 | 합성 | 가정 |
| IN-24 | 없는 근거 ID | `[?tN]` + 검토 사유 | 단위(지금 테스트는 삭제를 정답으로 둠 → 고침) | 합성 | 가정 |
| IN-25 | 단계 중 kill·claim 직후 kill·게시 중 kill | 1.4·7.4절 복구 | 통합(프로세스 kill) | 합성 | 가정 |
| IN-26 | 인증 만료 | 8.3절, `blocked=auth` | 단위 | — | 가정 |
| IN-27 | 사용자 노트 보존(제목·상태·참석자·프로젝트 변경, 할 일 체크, 메모, 경계 제목 삭제·중복, 복제 노트) | 7.2–7.4절 | 단위 | 합성 노트 | 가정 |
| IN-28 | v1 DB·한국어 키 노트 이행 | 3.2·7.5절 | 통합 | Mac mini 사본(비공개) | 실제 입력(사본) |
| IN-29 | 로컬 전용 + Ollama 미확인 | 호출 0, `blocked=no_local_provider` | 단위 | — | 가정 |
| IN-30 | API 비인증·다른 Origin·토큰 재사용 | 거부 | 단위 | — | 가정 |

- 각 행의 결과는 `docs/acceptance-v2.md`(새로 만듦)에 테스트 이름·실행 시각·결과·수준으로 기록한다. 비공개 실녹음은 공개 export에 넣지 않고, 표본 매니페스트에 출처·권리·해시·기대 결과를 둔다.
- 업로드 관련(이어 올리기, 폭주)은 v0.4 범위.

---

## 12. 남은 확인 (담당·시각)

| 항목 | 방법 | 담당 | 확인 예정 |
|---|---|---|---|
| 제공자별 무도구 호출(8.2·8.4절) | S3 미끼 시험 | main | 2026-11-09 완료(8.5절). Codex web_search 실측은 E8b 직후 |
| Ollama 로컬 실행 판별 | Ollama API·문서 + 시험 | main | S3와 함께 |
| 삼성 녹음 앱의 녹음 중 파일 쓰기(`contract.md` 미결) | S2 P-c: 폰 USB 연결 후 녹음 중 크기 변화 기록 | main + user(폰 연결) | 2026-11-10 18:00 KST, 폰 연결이 안 되면 다음 확인 시각을 다시 적는다 |
| Syncthing 기존 목록만 얻기(S1) | 4.1절(설계 v2) | main + user | 폰 연결 시 |
| 언어 몫 0.6 | 언어 표본 | main | E6 착수 때 |
| Bases 수식 한국어 표시 | Obsidian에서 확인 | main | E7a 착수 때 |
| 하드링크 재사용(APFS) | 단위 테스트 | impl(A) | A 완료 때 |
| launchd `KeepAlive` + 로그인 세션 | Mac mini 재시작 시험 | main | G 완료 때 |
| 공개용 표본 매니페스트·제품 게이트 표본 경로 연결 | `samples/` 매니페스트 작성 | main | A 착수 전 |

### 10.4 리뷰 B-F1 반영 (2026-11-10, `docs/research/review-bf.md`)

- 실행 배타: `serve`와 `tick`은 모두 루트의 `tick.lock`을 잡은 뒤에만 실행자에 들어간다. 업그레이드는 구 실행 없음 확인에 쓴 `tick.lock`을 새 serve 시작 직전에 놓고, 롤백 때 새 서비스를 멈춘 뒤 다시 잡는다.
- 볼트 이행 완료·동의는 **출력 볼트별**(정규화한 절대 경로) 기록이다. 실행 설정의 output과 같은 볼트의 기록이 있어야 게시한다. 엔진 identity가 확인된 파일만 이행 후보이고, 일반 Markdown은 무시한다. `.quietclerk-tmp`는 모든 노트 탐색에서 제외한다.
- 게시 확정·복구에서도 보류 중인 제외 요청이 이긴다. 취소·예외 경로의 prepared 게시도 회수한다.
- 삭제 대기(tombstone)인 작업은 `request_process`·승격·claim 모두 같은 트랜잭션 안에서 거부한다.
- bootstrap 토큰 갱신은 실행자와 독립된 타이머(60초 만료·일회성 유지).
- 기존 녹음 요청은 Syncthing ignore 갱신부터 include 목록 확정까지 루트 잠금으로 직렬화.
- 설정 저장·제공자 확인 성공 뒤에는 그 조치로 **해소된 사유**의 blocked 작업만 재대기.
- 제공자 호출 실행권은 프로세스 전체에서 LLM CLI 1개·Ollama 1개. 확인 API는 실행권이 사용 중이면 `409 busy`.
- 분류·교정·요약 응답의 필드 타입 오류는 구조 오류(`ValueError`)로 같은 제공자 재시도 1회 후 다음 제공자.

### 10.5 Mac mini 사본 리허설 반영 (2026-11-10)

- 롤백은 새 서비스 bootout 뒤 그 프로세스가 잠금을 놓을 때까지 최대 60초 기다린다(bootout은 프로세스 종료 전에 돌아온다).
- 설치기는 웹 의존성 없이 bootstrap 파일을 읽는다(`quietclerk/bootstrap_file.py`).
- v1에서 올리는 경우 `language.default`·`ui.language`를 `ko`로 기록한다(v1은 한국어 전용).
- 볼트 이행 대기는 실패가 아니라 `blocked_reason='vault_migration'`(시도 횟수 소모 없음). 이행이 끝나면 그 작업들을 다시 대기시킨다.
- 설정 파일을 손으로 고쳐도 실행 중인 serve에는 반영되지 않는다. 설정은 `PUT /api/settings`(화면)로 바꾼다.
- 노트 이행 API: `GET /api/notes/migration`(미리보기·완료 여부, 읽기 전용), `POST /api/notes/migration {consent:true}` → serve 실행자 스레드에서 작업 사이에 실행. 200(manifest) / 202(처리 중인 작업 뒤에 실행) / 409(충돌 사유) / 400(동의 없음).
- 화면 경로(`/home` 등)는 세션이 없으면 데이터 없이 `/`로 보낸다. 회의록 보기는 `GET /api/notes/{id}`가 생길 때까지 본문을 화면 HTML 안의 JSON 데이터 블록으로 싣는다(실행 스크립트는 `/static/app.js` 하나).

### 10.6 Obsidian 표시 (2026-11-10, 실제 노트에서 발견)

- 표 칸 안의 링크는 `[[#^t99\|04:53]]`처럼 `|`를 이스케이프한다(그대로 두면 칸이 갈라져 표가 깨진다).
- 주석 표식은 없앴다(7.3절). 엔진 구간은 제목 줄로 나눈다.
- 할 일 블록 ID는 짧게 `^task-<n>`. Obsidian 편집(Live Preview) 모드는 블록 ID를 글자로 보여 준다. 읽기 모드에서는 숨는다.
- 이미 만들어진 11/5 노트(게시 후 수정 없음 확인)와 11/9 노트 표는 같은 규칙으로 고쳤다.

### 10.7 유사 프로젝트에서 가져온 1차 품질 묶음 (2026-11-10, `docs/research/peers-*.md`)

- 설정: `vocabulary.terms`(최대 200개, 1~40자, 제어문자 금지, 중복 제거)는 Qwen3-ASR 편향·Whisper `initial_prompt`(합쳐 2048자 이내, 지시문·구분자 형태 낱말은 ASR 편향에서 제외)와 교정 프롬프트의 철자 목록에 쓴다. `vocabulary.replace`(`[{from,to}]`, 최대 200개, 양쪽 1~40자, 같은 `from`에 다른 `to`는 거부)는 받아쓰기 직후 로컬에서만 적용하는 확정 치환이다. 한국어 낱말 경계(시작·공백·문장부호, 뒤 조사 허용)를 지킨다.
- 동의 필드 `vocabulary`: 단어장이 엔진 프롬프트에 들어갈 때만 필요하다. 동의 없는 엔진에는 단어장 없이 보낸다(차단하지 않음). 보낸 경우 `sent_fields`에 남는다.
- 산출물 형식: `asr.json`·`alt.json`은 `{words, dropped, replaced}`, `diarize.json`은 `{segments, speaker_review}`. 예전 목록 형식 캐시는 다시 쓰지 않고 `transcript.artifact_rows`로 둘 다 읽는다.
- 받아쓰기 안전망: 청크 토큰 상한(Qwen `ceil(초×16)+32`, Whisper 창당 최대 224 — Whisper 기본값. 448은 시작 토큰·프롬프트와 합쳐 문맥을 넘어 디코딩이 깨졌다(실제 녹음 2건, 2026-11-10)), 반복 루프는 1회 재시도 후 잘라내고, 무음·저에너지 구간의 알려진 환각 문구는 제거한다. 지운 것은 `dropped[{start,end,text,why}]`.
- 화자 검토: 총 발화 1초 미만이고 다른 화자와 2초 이내인 유령 화자는 합친다(`ghost`). 원시 8명 도달(`cap_reached`), `speaker_probs` 평균 0.60 미만(`low_confidence`)은 표시만 한다. **제한:** 1초를 넘는 맞장구만 하는 화자는 화자 분리가 받아쓰기보다 먼저라 판별하지 않는다. 받아쓰기 뒤 별도 산출물로 다루는 것은 나중 일이다.
- 요약 사후 검증(단일 요약 유지, 코드 대조, 모델 값은 지우지 않음): 할 일 담당은 인용 줄에 이름이 있거나, 그 화자가 인용 줄에서 맡겠다고 하거나(제가, ~하겠습니다, ~할게요) 요청에 동의(네)하면 근거가 있다. 기한은 녹음 날짜 기준 21일 날짜표로 풀 수 있으면 `YYYY-MM-DD [남은 말] · 확정/잠정`, 풀 수 없는 말("배포 전")은 인용 줄에 있으면 그대로 둔다. 근거가 없으면 담당·기한 모두 원래 값 뒤에 `· 근거 확인`을 붙이고 `unsupported_owner`·`unsupported_deadline`. 숫자는 인용 줄의 말한 형태(삼십 개, 포, 여섯 자리, 네 시 반=4·16시 30분, 일 이 삼 사, 일부터 십까지)도 근거로 치며, 모델이 계산한 수(68+30=98)나 단위가 다른 수(38명≠38%)만 `⚠ 숫자 확인`·`unsupported_number`. 문장 속 ISO 날짜는 날짜표 변환이라 숫자 검사에서 뺀다. 인용 줄과 어휘가 거의 겹치지 않으면 `weak_citation`. (실제 회의 4건, 2026-11-10: 처음 규칙은 담당·기한을 거의 다 지우고 말한 숫자를 오경고해 이렇게 고쳤다.)
- 렌더 방어: 모델·대화록 텍스트의 백틱, 코드 펜스, Dataview 블록·인라인 쿼리, Templater 문법을 무력화한다. 엔진이 만든 근거 링크는 유지한다.
- 새 `review_reasons`: `asr_dropped`, `speaker_review`, `unsupported_owner`, `unsupported_deadline`, `unsupported_number`, `weak_citation`.
- 재처리: "요약만 다시"는 convert~correct를 모델·규칙·단어장이 바뀌었어도 가장 최근의 검증된 산출물로 재사용하고 그 단계의 파라미터를 계산하지 않는다. 새 규칙은 "처음부터 다시"에서만 적용된다.

### 10.8 2차 묶음 계약 (2026-11-10, 사용자 승인 "2차 전부 진행")

공통: 모든 새 API는 9장의 인증·CSRF·Idempotency-Key 규칙을 따른다. 사용자 입력 문자열은 앞뒤 공백 제거 후 길이 제한, 제어·서식 문자(유니코드 C 범주) 거부. 회의록 다시 쓰기는 LLM 호출 없이 저장된 산출물과 사용자 값으로 한다(노트 게시 규칙 7장 그대로: 사용자 영역 보존, 원자 게시). 처리 중인 작업(`running`)의 회의에 대한 쓰기 요청은 409 `{"error":..., "reason":"job_running"}`.

**A. 화자 이름·병합** (출처: MeetingMaster3, whosaid, minutes 이름 신뢰 규칙)
- `GET /api/jobs/{id}/speakers` → `{"speakers":[{"label":"S1","role":str|null,"name":str|null,"name_source":"engine"|"user"|null,"confirmed":bool,"talk_sec":float,"share":float,"sample":{"start":float,"end":float}|null,"merged_into":str|null}]}`. `sample`은 그 화자의 가장 긴 발언 중 5~15초 구간(오디오 재생용).
- `PUT /api/jobs/{id}/speakers/{label}` 본문 `{"name": str|null, "confirmed": bool}`(이름 1~40자). 사용자가 확정한 이름만 노트에 실명으로 쓴다: 화자 표, `speakers` 속성, 전체 대화록 머리(`**[00:01] 홍길동 (S1)**`), 요약 본문의 `S1` 낱말(앞뒤가 글자가 아닐 때만)을 이름으로 바꾼다. 엔진 추정 이름은 지금처럼 `(추정)`.
- `POST /api/jobs/{id}/speakers/merge` 본문 `{"from":"S3","into":"S2"}` → 화자 분리가 한 사람을 둘로 나눈 경우. 대화록 줄의 화자만 바꾸고 줄 ID·글자는 그대로. 되돌리기 `{"from":"S3","into":null}`.
- 저장: `speaker_overrides(job_id, label, name, confirmed, merged_into, updated_at)`. 처음부터 다시(scratch)로 화자 번호가 바뀌면 덮어쓰기를 버리고 `review_reasons`에 `speaker_overrides_dropped`.

**B. 대화록 줄 고치기** (출처: vibe, Buzz)
- `GET /api/jobs/{id}/transcript` → `{"lines":[{"id":"t12","start":float,"end":float,"speaker":"S1","text":str,"edited":bool,"original":str}]}`.
- `PUT /api/jobs/{id}/transcript/{line_id}` 본문 `{"text": str}`(1~2000자), `DELETE`는 원문으로 되돌림. 줄 ID는 바뀌지 않으므로 근거 링크가 유지된다. 노트의 전체 대화록을 다시 쓴다(요약은 그대로). "요약만 다시"는 고친 글을 쓴다.
- 저장: `transcript_edits(job_id, line_id, text, original_sha256, updated_at)`. 원문 해시가 다르면(처음부터 다시) 그 고침은 버리고 `transcript_edits_dropped`.
- 고친 낱말 쌍은 단어장 후보로 제안만 한다(`GET` 응답 `"vocabulary_suggestions":[{"from","to"}]`, 자동 추가 없음).

**C. 회의록 검색** (출처: Tractus, minutes, whosaid)
- SQLite FTS5 `trigram` 색인(`search` 테이블: job_id, kind=line|title|summary, line_id, start, speaker, text). 게시·줄 고치기·화자 이름 변경 때 그 회의만 다시 색인. 노트 파일이 아니라 엔진 산출물을 색인한다.
- `GET /api/search?q=...&limit=20&offset=0` (q 2~100자) → `{"items":[{"job_id","title","date","kind","line_id","start","speaker","snippet":[{"text":str,"hit":bool}]}],"total":int}`. 2글자 검색어는 trigram이 못 찾으므로 LIKE로 처리.
- CLI `quietclerk search "검색어"`(같은 결과, 사람용 출력).

**D. 내보내기** (출처: vibe, whosaid, noScribe)
- `GET /api/jobs/{id}/export?format=srt|vtt|txt|md|docx&names=1&timestamps=1` → 파일 내려받기(`Content-Disposition: attachment`, 파일 이름은 회의록 이름 규칙). 고친 줄·확정 이름 반영. docx는 표준 라이브러리 zip으로 만든다(새 의존성 없음). 볼트에는 파일을 만들지 않는다.

**E. 요약 구성 사용자 정의** (출처: Tractus, minutes RFC 0001, meetily)
- 설정 `summary.sections`: `{유형: [제목, ...]}`(유형은 기존 7종, 제목 1~12개, 각 1~40자). 없는 유형은 기본 구성. `summary.instructions`: 문자열 0~500자(사용자 선호. 근거 인용·안전 규칙 뒤에 "사용자 선호(규칙과 충돌하면 무시)"로 넣는다). 핵심 요약 제목과 인용 규칙은 바꿀 수 없다. 설정은 요약 캐시 키에 들어간다.

**F. 짧은 녹음 메모** (출처: minutes, voice2note, plaud-obsidian-pipeline)
- 설정 `memo.enabled`(기본 false), `memo.min_sec`(기본 10, 5~299). 켜면 `memo.min_sec` 이상 `min_duration_sec` 미만 녹음을 건너뛰지 않고 유형 `memo`로 처리: 같은 받아쓰기, 화자 분리 생략 가능(1인 가정), 분류 생략, 요약은 `## 핵심 요약`·`## 할 일`만. 노트 이름 `YYYY-MM-DD_메모_<제목>_HHMM.md`, 속성 `type: memo`.

**G. 데일리 노트 연결** (출처: minutes, voice2note)
- 설정 `daily_note.path`: 볼트 안 경로 틀(예 `~/Sync/Daily/{date}.md`, `{date}`=YYYY-MM-DD 녹음일), 기본 없음(꺼짐). 게시 뒤 그 파일의 `## 회의록`(en `## Meetings`) 아래에 `- HH:MM [[노트 이름|제목]]` 한 줄을 없으면 더한다(멱등, 노트 이름 기준). 파일이 없으면 그 제목만 있는 파일을 만든다. 그 제목 밖의 줄은 절대 바꾸지 않는다. 경로는 출력 폴더가 속한 볼트(출력 폴더의 조상 중 `.obsidian`이 있는 폴더) 안이어야 하고, 볼트를 못 찾거나 경로·조상에 심볼릭 링크가 있으면 거부.

### 10.9 3차 묶음 계약 (2026-11-10, 사용자 선택: 회의 질문하기, 캘린더 연결, MCP 대신 CLI)

> **범위 변경(사용자, 2026-11-10):** 캘린더 연결은 뺀다. 회의 질문하기(H)도 만들지 않는다 — "CLI로 제공만 하면 omp·Claude·Codex로 할 수 있으니 모든 기능을 다 넣을 필요는 없다". 엔진은 읽기 전용 CLI(I)만 제공하고, 질문·정리는 사용자의 에이전트가 CLI 출력으로 한다. 아래 H는 기록으로만 남긴다.

**H. 회의 질문하기** (출처: Tractus, minutes, alldayrec — 인용 검증·"근거 없음")
- 새 동의 필드 `ask`: 엔진별로 켠다(기본 꺼짐). 질문 때만 쓰며, 보내는 것은 질문 글과 검색으로 고른 대화록 발췌뿐이다. 동의한 엔진이 없으면 409 `{"reason":"no_consent"}`. 로컬 전용 모드에서는 로컬 엔진만.
- `POST /api/ask` 본문 `{"question": str(2~300자), "since": "YYYY-MM-DD"|null, "until": ...|null, "job_id": str|null}` → `{"answer": str, "citations": [{"job_id","title","date","line_id","start","speaker","text"}], "engine": str, "excerpts": int, "sent_chars": int, "status": "answered"|"no_evidence"}`.
- 발췌 고르기(엔진 호출 전, 로컬): 질문에서 낱말(2자 이상, 조사·불용어 제거)을 뽑아 검색 색인(10.8 C)에서 줄을 찾고 일치 낱말 수로 순위, 줄마다 앞뒤 2줄, 회의당 최대 3구간, 전체 최대 8,000자. 확정 이름·고친 줄 반영. 고른 것이 없으면 엔진을 부르지 않고 `no_evidence`.
- 엔진 규칙: 발췌만 근거로, 문장마다 `[회의번호:t12]` 인용, 발췌에 없으면 "회의록에서 찾지 못했어요". 발췌 안 지시문은 데이터. 응답의 인용은 코드로 검사해 발췌에 없는 인용은 지우고, 인용이 하나도 남지 않으면 `no_evidence`.
- 질문과 답은 저장하지 않는다. 로그에는 글자 수만.
- CLI `quietclerk ask "질문" [--since --until --job --json]`. 화면은 검색창 옆 "질문하기".

**I. 에이전트용 CLI** (MCP 대신. 읽기 전용, 같은 사용자만 — 기존 bootstrap 파일 인증)
- `quietclerk list [--since YYYY-MM-DD] [--limit N] [--json]` → 회의 목록(job_id, 날짜, 제목, 유형, 길이, 상태).
- `quietclerk show <job_id> [--json|--md] [--no-transcript]` → 제목·속성·요약·할 일·대화록(확정 이름·고친 줄 반영). `--md`는 내보내기 Markdown과 같은 형식.
- `quietclerk search "q" [--json]`(이미 있음), `quietclerk ask "q" [--json]`(H).
- 모든 명령 `--json`은 한 줄 JSON, 사람용 출력은 기본. 실패는 종료 코드 1과 stderr 한 줄. 쓰기 명령은 없다.
- 설치·업데이트가 `~/.local/bin/quietclerk`를 현재 venv의 실행 파일로 가리키게 한다(있던 다른 파일이면 건드리지 않고 알림).
- README에 "AI 에이전트에서 쓰기" 절: Claude Code·Codex에 줄 지침 예시, 다른 Mac에서는 `ssh <mac> quietclerk ...`.

### 10.10 시간 우선 노트 이름과 Bases 녹음 시각 (2026-11-12)

- 같은 날짜 안에서 제목순으로 섞이던 파일 이름을 `날짜_시각_제목`으로 바꾼다(7.2절). 이미 끝난 작업도 `POST /api/jobs/{id}/process {"mode":"resume"}`으로 캐시된 산출물을 재사용하고 비캐시 note 단계만 다시 게시하여 옛 이름을 바꿀 수 있다. 운영 일괄 변경 전 백업은 운영자가 별도로 한다.
- 파일 이동은 기존 게시 저널의 durable payload를 확장한다(DB 스키마 변경 없음). `prepared` 복구는 원이름으로 롤백, `renamed` 복구는 새 경로로 완료하며 사용자 영역은 바이트 보존한다. 충돌 파일은 덮어쓰거나 삭제하지 않는다.
- Base 의미 비교를 채택한다: Obsidian이 엔진 YAML을 재직렬화한 파일도 갱신해야 하므로, 알려진 옛 템플릿과 파싱 결과가 같으면 형식만 버리고 갱신한다. 주석·공백·따옴표 차이는 유지되지 않는다. 의미가 다른 사용자 파일은 건드리지 않는다.

