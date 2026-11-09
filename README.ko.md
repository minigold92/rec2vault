# rec2vault

**안드로이드 폰 기본 녹음 앱으로 녹음하고 저장하면, 몇 분 뒤 화자가 구분된 한국어 회의록이 Obsidian
볼트에 생깁니다. 받아쓰기는 내 Mac에서 합니다.**

[English README](README.md) · [한눈에 보는 소개 페이지](docs/overview.html)(내려받아 브라우저로 열기) · [벤치마크](docs/benchmark.md)

Plaud 같은 AI 녹음기는 전용 녹음기와 클라우드 받아쓰기, 월 분량 구독을 묶어 팝니다. 안드로이드 폰은
이미 녹음을 잘하고, Apple Silicon Mac은 음성 모델을 직접 돌릴 수 있습니다. 그래서 같은 네 단계를
갖고 있는 장비로 채웠습니다.

| 단계 | Plaud | 이 프로젝트 |
|---|---|---|
| 녹음 | 전용 녹음기 | 폰 기본 녹음 앱 그대로 |
| 옮기기 | 전용 앱 | Syncthing, 저장하면 자동 전송 |
| AI 처리 | 업체 서버, 월 분량 한도 | 내 Mac에서 화자 분리·받아쓰기, 한도 없음 |
| 결과 | 업체 앱 | Obsidian 볼트의 Markdown 노트 |

## 무엇을 해 주나

- 녹음을 저장한 뒤에는 할 일이 없습니다. launchd가 1분마다 새 파일을 확인하고, 실패하면 다시
  시도하고, 같은 녹음을 두 번 처리하지 않습니다.
- 화자 분리와 한국어 받아쓰기는 Mac 안에서(MLX) 합니다. **녹음 파일은 내 기기 밖으로 나가지
  않습니다.**
- 이미 쓰는 구독 CLI(Codex CLI, 선택으로 Gemini 계열 `agy`)가 잘못 들은 단어를 고치고, 회의 유형을
  나누고, 제목을 짓고, 유형(회의·현황공유·발표회·강의·1:1·브레인스토밍)에 맞는 양식으로 요약합니다.
- 요약 문장마다 근거 발언으로 이동하는 링크(`[[#^t012|02:20]]`)가 붙어 원문과 대조할 수 있습니다.
- 파일명은 `YYYY-MM-DD_<제목>_<HHMM>.md`이고, 날짜·시작 시각·길이·유형·주제·화자·원본 파일명과
  해시를 속성으로 넣어 Obsidian Bases로 정렬·필터할 수 있습니다. 노트 폴더에 `회의록.base`가 생깁니다.

Mac mini M4(16GB)에서 35분 녹음이 약 13.5분 뒤 회의록이 됩니다. 로컬 받아쓰기와 상용 서비스 두 곳의
차이는 두 상용 서비스끼리의 차이와 비슷합니다([벤치마크](docs/benchmark.md)).

## 동작 방식

**가상 회의 한 건의 실제 중간 결과로 단계별 설명: [docs/how-it-works.ko.md](docs/how-it-works.ko.md)**

폰 녹음(m4a) → Syncthing → Mac `~/rec/inbox` → 60초 안정·중복·5분 이상 확인 → 화자 분리(Nemotron 3)
→ 받아쓰기(Qwen3-ASR 1.7B + 정렬) → 2차 받아쓰기(Whisper large-v3 turbo) → 오인식 보정(Codex) →
분류·제목 → 근거 링크가 달린 요약 → Obsidian 노트

단계마다 결과를 `~/rec/work/<job_id>/`에 저장해, 중간에 끊기거나 실패하면 실패한 단계부터 이어서
합니다(5분 간격 최대 3번). 작업 상태는 SQLite(`~/rec/state.sqlite3`)에 있습니다. CLI에는 대화록
글자만 보내고, 대화록 안의 지시문은 데이터로만 다루게 합니다.

## 준비물

- 계속 켜 둘 Apple Silicon Mac(Mac mini M4 16GB에서 시험, 최대 메모리 약 5GB). 로그인 상태여야
  합니다. 사람 없이 돌리려면 자동 로그인을 켜 두세요.
- Homebrew와 `uv`, `ffmpeg`: `brew install uv ffmpeg`
- Mac에 [Syncthing](https://syncthing.net), 폰에 [Syncthing-Fork](https://github.com/Catfriend1/syncthing-android)
- [Codex CLI](https://github.com/openai/codex), `codex login`으로 로그인(ChatGPT 요금제 가능). 대체 경로로
  Antigravity CLI(`agy`)를 선택해서 설치할 수 있습니다.
- 모델용 디스크 약 5.2GB(설치할 때 한 번 내려받음)
- 갤럭시 S25 Ultra(`Recordings/Voice Recorder`)에서 시험했습니다. `.m4a`를 Syncthing으로 공유할 수 있는
  폴더에 저장하는 폰이면 됩니다.

## 설치

**1. Mac에 설치** (다른 Mac에 SSH로 설치하려면 앞에 `HOST=<ssh 호스트>`):

```sh
git clone https://github.com/minigold92/rec2vault.git && cd rec2vault
REC_OUTPUT="$HOME/Obsidian/MyVault/회의록" deploy/install.sh
```

앱을 `~/rec/app`에 복사하고, 의존성 설치, 테스트, 모델 내려받기를 한 뒤, 처음이면 `~/rec/settings.env`를
만들고 launchd 에이전트 `local.rec.pipeline`을 올립니다. 업데이트도 같은 명령이고 설정은 유지됩니다.

**2. 폰 연결**

1. Syncthing에서 폰과 Mac을 연결합니다.
2. 폰 Syncthing-Fork에서 `Recordings/Voice Recorder` 폴더를 **보내기 전용**으로 추가해 Mac과
   공유합니다. 배터리 최적화 예외로 설정합니다.
3. Mac에서 공유를 수락하고 경로를 `~/rec/inbox`, 유형을 **받기 전용**으로 지정합니다.

기존 녹음도 넘어오지만 처리하지 않습니다. 설치 시각(`REC_SINCE`) 이후 녹음만 처리합니다. 아예
안 넘어오게 하려면 수락하기 전에 Mac 쪽 폴더의 무시 패턴에 기존 파일 이름을 넣으세요.

> Syncthing-Fork 2.1.3에서 폴더를 고른 뒤에도 저장(✓) 버튼이 회색이면 화면을 가로로 돌렸다가
> 되돌리면 눌립니다.

**3. CLI 로그인**: Mac에서 `codex login`

**4. 확인**: 5분 넘게 녹음하고 저장한 뒤 `~/rec/logs/pipeline.log`를 보면, `REC_OUTPUT` 폴더에 노트가 생깁니다.

## 설정

`~/rec/settings.env`(KEY=VALUE, 실행할 때마다 읽음, 같은 이름의 환경 변수가 우선):

| 키 | 기본값 | 뜻 |
|---|---|---|
| `REC_OUTPUT` | `~/rec/notes` | 노트 폴더. Obsidian 볼트 안을 권장 |
| `REC_SINCE` | 설치 시각 | 이 시각 이전 녹음은 건너뜀(`YYYY-MM-DD HH:MM`) |
| `REC_MIN_DURATION_SEC` | `300` | 이보다 짧은 녹음은 건너뜀 |
| `REC_STABLE_SEC` | `60` | 파일이 이 시간 동안 그대로여야 처리 |
| `REC_CODEX_EFFORT` | `low` | 파이프라인의 Codex 추론 강도 |
| `REC_AGY_MODEL` | `gemini-4-argon-medium` | `agy` 대체 경로 모델 |

설치할 때만: `REC_LABEL`(launchd 이름, 기본 `local.rec.pipeline`)

`REC_SINCE` 이전 녹음을 골라 처리하기:

```sh
cd ~/rec/app && .venv/bin/python -m rec.backfill "음성 261106_142617.m4a"
```

이름을 `~/rec/include.txt`에 넣고 받는 폴더의 Syncthing 무시 패턴에서 지웁니다. 다음 주기에 새 녹음처럼
처리합니다. 통화 녹음(`통화*`)은 처리하지 않습니다.

## 데이터와 개인정보

- 녹음 파일은 폰과 Mac에만 있습니다. 받아쓰기와 화자 분리는 로컬에서 하고, 모델은 한 번 내려받은 뒤
  `HF_HUB_OFFLINE=1`로 돌립니다.
- 보정과 요약을 위해 **대화록 글자**가 CLI 제공자(Codex는 OpenAI, `agy`는 Google)로 갑니다. 계정의
  데이터 설정을 따릅니다.
- 다른 사람의 목소리를 녹음하려면 동의가 필요합니다. 회사 회의는 대화록을 외부 AI 서비스로 보내기 전에
  회사 승인이 필요할 수 있습니다.

## 한계

- 한국어 전용입니다(받아쓰기 언어, 프롬프트, 노트 속성).
- Apple Silicon macOS 전용입니다(MLX).
- 화자가 많은 회의(5명 이상)는 화자 구분이 눈에 띄게 나빠집니다(벤치마크 화자 일치율 약 0.78).
- 요약 품질은 사람이 쓴 회의록과 비교해 평가하지 않았습니다.
- Codex 로그인이 만료되고 `agy`도 없으면 3번 시도 후 실패로 남습니다. 받아쓰기 결과는 남아 있어 다시
  대기열에 넣으면 요약부터 이어서 합니다.

## 개발

```sh
uv run --no-project --with pytest python -m pytest -q tests
```

파일 구성은 [English README](README.md#development)를 보세요.

## 비슷한 프로젝트

이 파이프라인의 조각들은 다른 곳에도 있습니다. 2026-11-09 검색한 범위에서는 이 조합(안드로이드 기본 녹음 앱 →
Syncthing → MLX 로컬 한국어 받아쓰기·화자 분리 → 구독 CLI 요약 → 발언 단위 근거 링크가 있는 Obsidian 노트)을
그대로 하는 공개 프로젝트는 찾지 못했습니다. 목록과 비교는 [English README](README.md#related-projects)에
있습니다.

Samsung과 Galaxy는 삼성전자의 상표이고 Plaud는 해당 소유자의 상표입니다. 이 프로젝트는 어느 쪽과도 관계가 없습니다.

## 라이선스

이 코드는 MIT입니다. 모델은 각자의 라이선스를 따릅니다: Qwen3-ASR·Qwen3-ForcedAligner(Apache-2.0),
NVIDIA Nemotron 3 Diarization(OpenMDW-1.1), Whisper(MIT).
