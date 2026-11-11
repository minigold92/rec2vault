# 받아쓰기 도구·서버 비교 — QuietClerk에 가져올 점

- 확인일: 2026-11-10 (스타·커밋 수치는 이날 GitHub API 조회)
- 비교 기준: `local://quietclerk-features.md`(기능 목록), 저장소 `rec` 코드·문서 일부(아래 "QuietClerk 현재" 표기)
- 대상: vibe, Scriberr, noScribe, Buzz, TranscriptionSuite, whosaid, whisperX(화자·정렬 부분), Obsidian 플러그인 3개(WhisperCal, meetnote, resojot) + 같은 계열이라 함께 본 MeetingMaster3(oss-landscape C9), 보조로 steno·obsidian-vox
- **검증 수준: 문서·소스 열람.** 15개 저장소를 `--depth 1`로 받아 README·문서·소스를 직접 읽었다. 프로젝트 코드는 실행·설치하지 않았다. 예외 1건: 한국어 FTS5 동작은 로컬 sqlite3로 한 문장짜리 가정 입력을 실행해 확인했다(T11). **`samples/`의 실제 녹음으로 확인한 것은 없다.** 한국어 성능·효과는 전부 "확인 못 함"이다.
- 표기: `[추정]` = 문서에 직접 없고 내가 추론. `확인 못 함` = 접근한 자료에서 못 찾음. 스타·이슈 수는 사용자 호응의 약한 지표일 뿐 품질 증거가 아니다.
- 근거 표기: `프로젝트 경로 L줄` — 완전한 URL은 `<기준 URL><경로>#L<줄>`. 기준 URL은 6절 표에 고정 커밋으로 적었다.

---

## 1. 가져올 가치가 큰 것 상위 10개

| 순위 | 항목 | 출처 프로젝트 | 크기 | 원칙 충돌 |
|---|---|---|---|---|
| 1 | T01 화자 이름 지정 화면(목소리 샘플·후보 점수) + 노트·요약·내보내기 전체 반영 | MeetingMaster3, whosaid, Buzz, WhisperCal, vibe | M | 없음. 확정 이름이 요약 엔진으로 가므로 "보낸 데이터" 패널에 표시 |
| 2 | T02 목소리 등록(회의 간 화자 식별) | whosaid, MeetingMaster3, WhisperCal, meetnote | L | 없음(임베딩은 로컬 SQLite만). 생체정보라 기본 꺼짐·옵트인 필수 |
| 3 | T05 단어장(인식 편향 + 확정 치환) | mlx-audio(이미 쓰는 의존성), WhisperCal, resojot, whisperX | M | 없음. 단어장이 교정 엔진 텍스트로 가면 엔진별 동의 범위 안 |
| 4 | T06 대화록 줄 편집(키보드·검색·재생 속도) + 수정 후 요약만 재생성 | vibe, Buzz, MeetingMaster3 | M | 없음 |
| 5 | T03 화자 검토 사유·자동 확정 기준(`needs_review`에 화자 사유 추가) | WhisperCal, whosaid, mlx-audio 출력 | S–M | 없음 |
| 6 | T09 요약 템플릿 파일화(검증·되돌리기·"이번만 지시") | MeetingMaster3, WhisperCal, Scriberr | M | 없음 |
| 7 | T13 실행 기록(실제 옵션·버전) + "다시 처리하면 달라질 회의" 탐지(dry-run·백업) | whosaid, Scriberr | M | 없음. 재처리가 요약을 다시 부르면 엔진 동의 재확인 |
| 8 | T10 내보내기(SRT/VTT/TXT/JSON/DOCX) + 화자·시각 옵션 | vibe, whosaid, Buzz, noScribe | S–M | 없음(웹 화면 내려받기만, vault에 파일 추가 안 함) |
| 9 | T11 전체 회의 검색(FTS5) → 발췌 질문 | whosaid, MeetingMaster3 | 검색 M / 질문 L | 검색 없음. 질문은 회의 발췌가 엔진으로 가므로 **질문마다 동의·발췌 표시 필요(조건부)** |
| 10 | T18 데이터 인벤토리·위협 모델 표(위협-완화-코드-시험) | MeetingMaster3 | S(문서) | 없음 |

차점(본문 참고): T04 화자 병합·줄 단위 이동(M), T08 회의 합치기/나누기(L), T12 단계 안 진행률·ETA(S–M), T14 합성 회의 평가(M–L), T15 감시 폴더 점검(S), T16 완료 알림(S), T17 오프라인 고정 점검(S), T19 요약 피드백(S), T20 참석자 위키링크(S–M).

---

## 2. 조사 대상 요약

| 프로젝트 | ★ (2026-11-10) | 라이선스 | 마지막 커밋 | 이번에 읽은 범위 | 비고 |
|---|---|---|---|---|---|
| vibe | 8,049 | MIT | 2026-10-30 | README, 데스크톱 UI 소스(화자 라벨·줄 편집·내보내기·진행률), 서버 문서 | |
| Scriberr | 3,143 | MIT | 2026-09-20 | README, Go 모델·핸들러, 프런트 일부 | 작성자가 개발 중단 공지(README)·재개 선언. 전사 **편집 기능 요청이 열려 있음**(#348) |
| noScribe | 2,238 | **GPL-3.0** | 2026-11-09 | README, CHANGELOG, `main.py` 일부, docker·server 문서 | 편집기는 별도 저장소(noScribeEditor ★29, "work in progress") — 편집 UX 세부는 확인 못 함 |
| Buzz | 22,585 | MIT | 2026-11-09 | 사용자 문서 전부(화자·뷰어·플러그인·폴더 감시) | |
| TranscriptionSuite | 810 | **GPL-3.0** | 2026-09-24 | README(웹훅 등), 서버 코드 일부, 계획 문서(_bmad-output) | PRD는 계획이라 구현 여부 따로 확인 |
| whosaid | 9 | MIT | 2026-11-09 | README 전체(1,841줄), docs(평가·모델 조사) | 스타는 적지만 문서가 가장 깊다. 호응 근거는 이슈 번호만 |
| whisperX | 25,186 | BSD-2 | 2026-10-22 | `diarize.py`, `alignment.py`, `__main__.py` | CUDA 중심 — 알고리즘만 참고 |
| WhisperCal | 6 | 미감지(NOASSERTION) | 2026-11-06 | README 전체, 서비스 소스(음성 매칭·단어 치환), 프롬프트 | **코드 복사 불가 [추정]**(라이선스 불명) |
| meetnote | 4 | 라이선스 없음 | 2026-08-03 | README, CHANGELOG, 백엔드 화자 DB·교정·사용 설명서 | 코드 복사 불가 |
| resojot | 50 | 미감지 | 2026-11-08 | README(영문) | 일부 기능 인증코드 필요. 소스는 보이나 README 위주로 읽음 |
| MeetingMaster3 | 0 | Apache-2.0 | 2026-10-31 | 사용자·개발 문서 전부, 진행률·재개 소스 | **스타 0, 생성 2026-10-31 — 사용자 호응 근거 없음.** 설계·문서 품질을 보고 가져옴 |
| steno / obsidian-vox | 1 / 83 | MIT / MIT | 2026-03-15 / 2026-06-11 | README만 | 클라우드 전사(steno)는 원칙 충돌 |

QuietClerk는 MIT다. GPL-3.0 두 곳(noScribe, TranscriptionSuite)과 라이선스가 불명한 세 곳(WhisperCal, meetnote, resojot)에서는 **아이디어만** 가져오고 코드를 옮기지 않는다.

---

## 3. 항목 상세

각 항목: 무엇을·어떻게 / 근거 / 호응 / QuietClerk 형태·크기 / 원칙 충돌.

### 3-A. 화자

#### T01. 화자 이름 지정 화면 + 전체 반영 (M)

**QuietClerk 현재:** 화자는 `S1`, `S2`…로 두고, 이름은 LLM 추정에 근거 링크를 붙인다. 사람이 고치려면 손으로 노트를 고친다(`rec/docs/how-it-works.md` L401). 화자 표가 있다(기능 목록). 이름을 웹 화면에서 확정하는 기능은 기능 목록에 없다.

**무엇을·어떻게**
- MeetingMaster3: 작업이 "Confirm speakers"에서 멈추고 화자마다 ① 자리표시자 ② 발언 시간과 "겹침 없는 깨끗한 발언" 초 ③ **재생해 볼 샘플 클립 2~3개(시작·끝 시각)** ④ (목소리 인식 켰을 때) 후보 인물 순위와 점수와 "제안" 이름을 보여준다. 이름을 비워 두면 자리표시자 유지, **두 화자에 같은 이름을 주면 한 사람으로 병합**. 확정 이름은 대화록 턴·`participants`·`mm3-speakers` 속성·보조 대화록·**AI가 보는 텍스트**에 한꺼번에 반영된다. 나중의 "Rename speakers…"는 미리보기 후 대화록·속성·참석자 줄·**생성된 섹션 안의 이름(온전한 단어만)**까지 갱신하고, 사용자가 쓴 글은 건드리지 않는다(`docs/user-guide/speakers.md` L8-38, `reviewing-and-editing.md` "Renaming speakers" 절).
- whosaid: 화자 카드(턴 수·발언 시간·대표 문장), `whosaid samples`는 클러스터마다 **가장 긴 구간 8초 WAV**를 잘라 준다. 앱 화자 탭은 이름 칸·역할 칩(self/boss/peer/report/external)·"Carol 같음 (0.64)"(임계값에 못 미친 후보)·클립 재생(README L129-134, L251).
- Buzz: 식별된 화자의 임의 문장 **10초 미리듣기** 후 이름 변경, "같은 화자 연속 문장 합치기" 체크(`docs/docs/usage/5_speaker_identification.md` L9).
- WhisperCal: 확정 모달에 화자별 이름 칸(초대 참석자가 위에), **확신도 배지(CERTAIN/HIGH/LOW)와 근거 문장**, 접히는 발언 발췌, 타임스탬프를 누르면 **그 문장만 재생하고 다음 화자 시작에서 멈춤**(클립 길이 설정 5초), 나중에 "Edit speaker tags"로 LLM 재호출 없이 수정(README L1023-1043, L1101-1103).

**안전 장치로 함께 가져올 것**
- meetnote 0.4.1: 이름을 정한 뒤 요약 LLM이 `[홍길동]`을 "화자1"로 되돌려 쓰는 **실제 결함**이 났다. 요약 프롬프트에 "입력의 `[이름]`을 그대로, 절대 화자N으로 바꾸지 말 것"을 넣고, 노트에서 `화자{idx}`·`SPEAKER_NN`·현재 이름 모든 표기를 한 번 더 치환하는 안전판을 뒀다(`CHANGELOG.md` L7-12).
- TranscriptionSuite: 요약·채팅 프롬프트 앞에 "Speakers in this transcript: …" 서문을 붙이고 "이름을 그대로 쓰고 관계를 추론·축약·병합하지 말 것" 지시문을 덧붙인다(`server/backend/api/routes/llm.py` L775-815).
- noScribe: 화자 이름의 `_ < > " & :`를 제거한다. 이름이 `ts_{시작}_{끝}_{화자}` 오디오 동기 앵커와 "이름: 텍스트" 구분자로 그대로 들어가기 때문(`noScribe/main.py` L449-476). 이슈 #202: 편집기에서 고친 화자 이름이 VTT에 반영되지 않았다.

**호응:** Scriberr #328 "Speaker renaming feature"(닫힘, 댓글 1), #348 "edit speaker name and text"(열림, 댓글 6), TranscriptionSuite #28(열림, 댓글 12), Buzz #1618(열림, 재생 신뢰성 불만). 수치는 작다.

**QuietClerk 형태:** 회의록 보기의 화자 표에 이름 칸을 추가한다. "이 목소리 듣기" = 그 화자의 가장 긴 구간 5~8초(오디오 재생은 이미 있음). 저장하면 (a) `speakers` 속성·표·대화록의 이름, (b) 요약 본문의 이름(재호출 없이 치환), (c) 내보내기에 반영. 사용자가 확정한 이름과 LLM 추정을 속성에서 구분한다(현재 속성은 문자열 목록이라 형식 변경이 필요할 수 있음 [추정]). 사용자 영역 보존 규칙은 그대로.
**충돌:** 없음.

#### T02. 목소리 등록 — 회의 간 화자 식별 (L)

**QuietClerk 현재:** 회의 간 화자 식별 없음(기능 목록 "없는 것").

**4개 프로젝트가 같은 구조를 택했다**

| | 임베더 | 저장 | 매칭 규칙 | 근거 |
|---|---|---|---|---|
| whosaid | TitaNet-small(영어용) | `speakers.json` `{name, model, embedding, added, role}` | 코사인 ≥0.50, 낮으면 익명 유지 | README L1390-1395, L1441-1455 |
| MeetingMaster3 | pyannote 파이프라인 임베더(256차원) | SQLite `voiceprints` 테이블, 파일 0600, 기본 **꺼짐** | ≥0.6 **그리고** 2위보다 0.1 이상 앞 **그리고** 같은 회의의 다른 화자가 더 잘 맞지 않을 것 | `speakers.md` L40-85 |
| WhisperCal | Tome 성문(외부 도구) | vault `Caches/Voiceprints/*.json`, People 노트와 1:1 | ≥0.50 + 2위와 0.08 격차, 단독 라이브러리면 ≥0.55, **발화 5초 미만은 건너뜀** | `src/services/VoiceprintMatcher.ts` L24-36, L105-135 |
| meetnote | pyannote 임베딩 | JSON(이름·이메일) | ≥0.70, 한 프로필은 한 화자에만 | `backend/recorder/speaker_db.py` L22-24, L244-310 |

**실측 숫자(모두 영어·소규모 녹음):** whosaid는 0.40~0.53 구간에서 오인이 나서 임계값을 0.40→0.50으로 올렸고, 같은 사람 0.986 / 가장 가까운 타인 0.194를 보고했다(README L1592-1600). MeetingMaster3는 같은 사람 0.85~0.97 / 다른 사람 ≤0.43(두 녹음, `speakers.md` L59-72). **한국어 수치는 어디에도 없다.**

**등록·유지 방식**
- 회의 안에서 화자 이름을 확정할 때 "이 목소리 기억"을 **체크한 화자만** 저장(MeetingMaster3). 사람당 최근 샘플 20개, 같은 사람 이름으로 다시 확정하면 샘플 추가. 회의 속 임시 임베딩 파일은 이름 확정 즉시 삭제.
- **기존 녹음 구간에서 등록**: `whosaid enroll Alice --from meeting.m4a --ss 3:20 --t 20`(README L122). 갤럭시 녹음이 입력이라 마이크로 따로 녹음할 필요가 없다 — QuietClerk 원칙에 맞는 등록 경로.
- 덮어쓰기 가드: 새 클러스터가 기존 성문과 임계값 미만이면 거부(`--force`로만). 섞인 클러스터를 저장해 성문이 나빠지는 사고(whosaid #19)를 막으려고 **전사 전용 라벨**(`--no-save`)을 따로 둔다. `--blend`는 평균으로 강화(README L1463-1482).
- **임베더를 바꾸면 기존 항목이 전부 무효**: 항목에 모델 ID를 키로 달아 조용히 안 맞게 한다(README L1393-1395, `speakers.md` "Model changes"). 임계값도 임베더마다 다시 맞춰야 한다(`docs/model-survey-2026-10.md` L40-53).
- 삭제·백업: 목록·삭제·전체 삭제(2단계 확인 토큰, 5분 유효), 물리 삭제(`secure_delete`+WAL 비움), 레지스트리 내보내기/가져오기는 전체 검증 후 쓰기·병합 충돌 거부·0600(`speakers.md` L87-122, whosaid README L1424-1439).

**QuietClerk 쪽 사실(소스 확인)**
- 현재 쓰는 Nemotron 3 Diarization은 **세션 안의 화자 채널만** 낸다. nemotron-diar-mlx README의 출력은 `start end speaker_N`뿐이고 같은 README는 "비슷한 목소리는 병합될 수 있다"고 적는다(L311-317). QuietClerk 백엔드도 세그먼트만 쓴다(`rec/quietclerk/backends/mlx.py` L100-106). → **별도 임베더가 필요하다.**
- 이미 고정된 의존성 `mlx-audio==0.6.4` 안에 `EcapaSpeakerEmbeddingExtractor`(SpeechBrain VoxCeleb ECAPA, 16kHz mono → 단위 길이 192차원, 기본 모델 `aufklarer/SpeechBrain-ECAPA-VoxCeleb-20M-MLX`)가 있다 — 설치된 사본 `mlx_audio/codec/models/ecapa_tdnn/speaker.py` L14-50. **새 프레임워크 없이 가능해 보인다 [추정: 실행 안 함].** 한국어 화자 구분 성능은 확인 못 함(whosaid README L1656-1660도 "임베딩 모델은 말하는 언어에 맞춰야 한다"고 경고).

**호응:** Buzz #1429(열림, 👍2), TranscriptionSuite #85(열림, 👍2)·#28. whosaid 9★, MeetingMaster3 0★ — **구현체가 실제로 쓰였다는 근거는 확인 못 함.**

**QuietClerk 형태:** SQLite `voiceprints(id, name, model_id, created_at)` + `voiceprint_samples(vector, seconds, source_job)`. 설정 `voiceprints.enabled=false` 기본. 임계 0.6 / 격차 0.1(MeetingMaster3 기본)에서 시작하되 **한국어 실측 후 조정**. 임베딩은 노트·로그·API 응답·"보낸 데이터"에 절대 넣지 않는다. 후보는 제안일 뿐 확정은 사람이(T01 화면). 발화 5초(또는 10초) 미만은 저신뢰.
**충돌:** 음성은 Mac 밖으로 안 나감 — 충돌 없음(로컬 SQLite만). 갤럭시 기본 앱 — 충돌 없음. 단 **생체정보** 취급이라 기본 꺼짐·삭제 UI·문서화(T18)가 같이 가야 한다.

#### T03. 화자 검토 사유와 자동 확정 기준 (S–M)

**QuietClerk 현재:** `needs_review`와 `review_reasons`가 있다(사유: `type_uncertain`, `language_uncertain`, `summary_review`, 단계 실패 — `rec/quietclerk/render.py` L167-175). **화자 관련 사유는 없다.** 화면 "검토 대기" 보기도 있다(render.py L47-51).

**가져올 것**
- whosaid: 화자 수 추정이 상한(캡)에 닿으면 "목표가 아니라 경계" — 신뢰할 수 없다는 경고를 카드에 쓴다(README L1664-1693). 발언 1초 미만인 익명 클러스터는 `uncounted`로 빼 화자 수·표에서 제외하되 말은 대화록에 남긴다(L1585).
- WhisperCal: 자동 확정은 **모든 화자가 0.80 이상**일 때만, 발언 비율 5% 이하의 잡음 화자는 막지 않고 이름 없이 통과(README L596, L1340-1342). 자동 확정은 성문을 학습시키지 않는다(drift 방지).
- TranscriptionSuite PRD(FR25~27): 저신뢰 구간이 있으면 자동 요약을 **보류**하고 검토 끝날 때까지 유지 — 계획 문서이고 보류 기능 구현은 확인 못 함. 구현된 `per_turn_confidence`는 **단어 인식 신뢰도의 평균**이지 화자 신뢰도가 아니다(`diarization_confidence.py` L1-12, L39) — 이름만 보고 옮기면 안 된다.
- **QuietClerk만의 재료:** mlx-audio의 `DiarizationOutput`이 `speaker_probs`(프레임×8명 활동 확률)를 돌려주는데 QuietClerk는 버린다(설치본 `mlx_audio/vad/models/sortformer/sortformer.py` L700-707, `nemotron_diarization.py` L509-545; QuietClerk `backends/mlx.py` L100-106). 구간 평균 확률·동시 활성 화자 수로 **진짜 화자 확신도**를 만들 수 있다 [추정: 실행 안 함].

**QuietClerk 형태:** 새 사유 `speaker_cap`(8명 도달), `speaker_phantom`(1초 미만 화자), `speaker_low_conf`, `name_unmatched_near`. 홈 "검토 대기" 건수에 포함. 요약 보류는 기본 꺼짐(무인 처리 우선). 크기 S–M.
**충돌:** 없음.

#### T04. 화자 분리 오류 고치기 — 병합·줄 이동·화자 수 힌트 (M)

- vibe: 줄 앞 화자 칩을 누르면 이름 변경(그 화자 모든 줄에 적용, 비우면 기본값)과 **"이 줄의 화자"를 다른 화자나 새 화자로 이동**. 분리가 놓친 줄은 점선 "＋"로 지정(`desktop/src/pages/main/components/speaker-label.tsx` L24-139).
- MeetingMaster3: 한 사람이 둘로 쪼개지면 같은 이름 → 병합(`speakers.md` L21-24). Buzz: 연속 문장 합치기.
- whosaid: `relabel --auto --fold-unknown`은 **확신 높은 익명 클러스터만** 병합하고 이름 있는 화자·전사 전용 라벨은 보호, 병합 근거를 `fold_evidence`로 보존해 연쇄 병합을 막는다(README L1676-1683). 화자 수 힌트 `--speakers/--min-speakers/--max-speakers`, 워크스페이스 설정 `[watch] max_speakers`(L904-919).
- TranscriptionSuite #28 제안: 임베딩을 캐시해 화자 수 한도만 바꿔 싸게 재분리.
- **QuietClerk 제약:** 설치된 `nemotron_diarization.generate()`는 `threshold`, `min_duration`, `merge_gap`만 받고 **화자 수 인자가 없다**(설치본 `nemotron_diarization.py` L509-518). 그래서 힌트보다 **사후 병합·줄 이동**이 먼저다. `merge_gap`은 같은 화자 구간 사이 틈을 잇는 조정 후보 [추정].
**QuietClerk 형태:** T01 화면에 "이 화자를 다른 화자로 합치기", 대화록 줄 메뉴에 "이 줄 화자 바꾸기". 오버레이로 저장해 재처리해도 유지. 크기 M. **충돌:** 없음.

---

### 3-B. 단어장

#### T05. 단어장 — 인식 편향 + 확정 치환 (M)

**QuietClerk 현재:** 단어장 UI 없음(기능 목록). 코드에도 `hotword`/`initial_prompt` 전달이 없다(`rec/quietclerk` grep 결과 없음).

**1) 인식 편향(ASR에 힌트)**
- **이미 고정된 의존성에 배선이 있다.** `mlx-audio==0.6.4`의 Qwen3-ASR `generate(..., system_prompt=None, hotwords=None)`는 `hotwords`를 `system_prompt`에 `", "`로 이어 붙인다(설치본 `mlx_audio/stt/models/qwen3_asr/qwen3_asr.py` L1253-1267, `mlx_audio/stt/utils.py` L20-39). 2차 받아쓰기용 `mlx_whisper 0.4.3`은 `transcribe(initial_prompt=…)`를 받는다(설치본 `mlx_whisper/transcribe.py` L72, L257-259). Qwen 공식 패키지에도 `transcribe(context=…)`가 있다(`QwenLM/Qwen3-ASR` `qwen_asr/inference/qwen3_asr.py` L303-345).
- 다른 프로젝트: whisperX `--hotwords "WhisperX, PyAnnote, GPU"`(`whisperx/__main__.py` L61, faster-whisper 경로), Buzz "Initial prompt"(Advanced, `1_file_import.md` L16), Scriberr·TranscriptionSuite `initial_prompt`. TranscriptionSuite는 `vad_filter`·`suppress_tokens`·`initial_prompt`를 설정으로 열고 **환각 제어**를 같이 다뤘다(`_bmad-output/implementation-artifacts/spec-gh-74-whisperx-vad-hallucination-control.md`). noScribe의 `prompts/prompt.yml`은 반대로 말버릇("음, 이게, 뭐랄까…")을 **끌어내려고** 프롬프트를 쓴다 — 프롬프트는 문체에도 영향을 준다는 뜻 [추정].
- **효과·한국어 정확도·환각 부작용은 확인 못 함.**

**2) 확정 치환(결정적 교정)**
- WhisperCal: vault의 `Prompts/Word Replacements.md`에 `검색,치환` 한 줄 한 쌍, `#` 주석. 대소문자 구분, 긴 항 먼저, **한 번의 정규식 패스**(100+ 규칙 가능), frontmatter 보존, **적중 횟수 목록 알림**. LLM 교정보다 **먼저** 돌고 화자 태그 적용 때 한 번 더, 명령으로 수동 실행(실행 전 목록 확인 모달)(README L1105-1133, `src/services/WordReplacer.ts` L1-181).
- resojot: 자주 틀리는 단어 사전, 내보내기/가져오기(Markdown), **가져오기는 확인 후에만, 조용히 덮어쓰지 않음**, 서비스 하나가 실패하면 다음 서비스로 자동 전환(README-en L44, L185).
- **한국어에는 그대로 못 옮긴다.** WhisperCal의 단어 경계는 JS `\w`(ASCII 영숫자) 기준이라 한글 항은 경계 없는 부분 문자열 치환 경로로 간다(`WordReplacer.ts` L66-70, L102-110). 한글은 조사가 붙으므로 왼쪽 경계(앞 글자가 한글이 아님)·최소 2자·"치환 전/후 미리보기"가 필요하다 [추정].

**호응:** Buzz #1427(initial prompt가 HF 모델에서 안 된다는 제보, 닫힘, 댓글 4) 정도의 사용 흔적. 대량 요청 근거는 확인 못 함.

**QuietClerk 형태:** 설정 화면 "단어장" 표(용어 / 흔한 오인식(선택) / 메모) → 설정 폴더의 파일 하나. 세 경로: ① ASR `hotwords`·`initial_prompt` ② 교정 프롬프트에 목록 전달 ③ 결정적 치환(기본 꺼짐, 적중 로그). "보낸 데이터" 패널에 "단어장 N개 포함" 표시. 배선 S + UI·치환 M = M. 효과는 `samples/` 실녹음 + 정답본으로 CER을 켠/끈 비교해 결정(T14 방식).
**충돌:** 없음. 단어장(사람 이름·제품명)이 교정 엔진 텍스트로 가므로 엔진별 동의 범위 안에서만. 로컬 전용 모드에서는 ASR·치환만.

---

### 3-C. 전사 편집·노트 UX

#### T06. 대화록 줄 편집 + 키보드·검색·재생 속도 (M)

**QuietClerk 현재:** 근거 시각을 누르면 해당 구간이 재생된다. 줄 편집·화면 안 검색·재생 속도 조절은 기능 목록에 없다.

**무엇을·어떻게**
- vibe: 줄을 누르면 그 자리에서 textarea(클릭한 위치에 커서). **Enter=저장하고 다음 줄, Shift+Enter 줄바꿈, Tab/Shift+Tab 이동, 줄 끝·처음의 방향키로 이웃 줄, Esc 취소, 포커스를 잃으면 저장.** 빈 텍스트는 "편집"이 아니라 텍스트 소실로 보고 원문 유지. 검색·파일 전환 때 열린 편집기를 버린다. 스페이스로 재생/정지(입력 중 제외). 재생을 따라가다 사용자가 스크롤하면 해제, 재생 중일 때만 "재생 위치로" 알약 표시(`transcript-view.tsx` L109-189, L495-575).
- Buzz: Cmd+F 검색("n 중 m 일치", Enter/Shift+Enter), 구간 반복, **재생 속도 0.5~2.0(0.05 단위)**, 세그먼트 시작·끝 ±0.5초 단축키, 현재 위치로 스크롤(`6_transcription_viewer.md` L44-120).
- MeetingMaster3: J/K/L, ±5초, 0.75~2×, 단어 클릭 이동, 따라가기 토글(`reviewing-and-editing.md` "The recording and the transcript" 절).
- Scriberr #402: 사용자가 만든 변경 중 **재생 속도 0.75/0.5 요청**("알아듣기 어려울 때가 있다", 👍6).

**호응:** Scriberr #348 편집 요청(열림, 댓글 6), TranscriptionSuite #28의 사용자 의견: "편집 후 타이밍과 화자 분리가 깨진다". → 텍스트 편집이 시각·화자 필드를 건드리지 않게 분리해야 한다.

**QuietClerk 형태:** 편집은 SQLite `edits(line_id, text, edited_at)` 오버레이로 저장한다. 줄 블록 ID(`^t12`)와 시각·화자는 그대로라 요약의 근거 링크가 깨지지 않는다. 파이프라인을 다시 돌려도 수정이 남고 원문은 보존. 저장 뒤 "요약만 다시". 화면 안 검색·재생 속도 0.75/1.25/1.5/2 추가. 크기 M.
**충돌:** 없음. 화면은 이미 JSON 전용 렌더 원칙(`rec/quietclerk/server/__init__.py` L14)이고 줄 길이를 4000자로 자르므로 편집 입력도 같은 경로를 탄다.

#### T07. 섹션 단위 재생성 + diff + 이전 버전 보관 + 외부 수정 충돌 처리 (M)

**QuietClerk 현재:** 사용자 영역 보존, "요약만 다시"(요약 전체).

**MeetingMaster3 방식**
- 생성 영역은 `<!-- mm3:section:summary -->` 마커 쌍으로 구분. **마커 밖은 사용자 글로 취급해 절대 다시 쓰지 않는다.** 마커가 깨지면(닫는 마커 삭제 등) 깨진 텍스트를 사용자 글로 보고 추측하지 않으며, "새 사본 추가"를 `<id>-2`로 쓴다.
- 저장은 원자적이고 바뀐 부분만 바뀐다. **파일이 외부(Obsidian·동기화)에서 바뀐 경우** 덮어쓰지 않고 양쪽을 나란히 보여준 뒤 Keep mine / Take theirs / Keep editing. 저장 전 편집은 초안으로 보관되어 "Restore my edits".
- 섹션마다 "Regenerate…"(지시문·모델 선택) → **diff(나란히/통합)** → Accept / "Accept & archive previous"(`Archive/<날짜 - 제목>.<섹션>.<yyyymmdd-hhmm>.md`) / Discard. 템플릿 전환은 노트 전체를 아카이브한 뒤 새로 쓰고 마커 밖 글은 "Preserved notes"로 이어 붙임. 진행 막대·경과·남은 시간·취소(`reviewing-and-editing.md` "When the note changed elsewhere", "Regenerating a section", "Switching the template" 절).
- 제목·날짜 바꾸기: 파일·폴더·다른 노트의 링크(별칭·`#헤딩`·`^블록` 유지)까지 미리보기 후 바꾸고 바뀐 노트를 백업(같은 문서 "Changing the title or date" 절).

**QuietClerk 형태:** 요약 섹션별 "다시 쓰기"(지시문 입력) + 새/이전 diff + "이전 버전 보관(`.quietclerk/archive/…`)". 노트가 파일에서 외부 수정됐는지(해시 비교) 확인해 덮어쓰기 전에 알림. QuietClerk 노트에는 이미 `job_id`·`source_sha256`·`qc_schema` 속성이 있어 노트↔작업 연결은 이름을 바꿔도 유지된다. 제목 변경 시 링크 갱신은 후순위. 크기 M.
**호응:** 0★ — 확인 못 함. **충돌:** 없음.

#### T08. 회의 합치기·나누기 (L)

**QuietClerk 현재:** 분류에 `split_suspect`가 있다(한 녹음에 두 회의가 섞였을 의심). 합치기·나누기 동작은 없다. 5분 미만 녹음은 건너뛴다 → **한 회의가 중간에 끊겨 두 파일이 되면 짧은 뒷부분이 유실될 수 있다 [추정].**

**WhisperCal 방식(README L386-421)**
- **합치기:** 여러 부분 선택 → 대화록에 `### Part N` 제목, 원래 시각·녹음 임베드 유지, 길이 합산. **"Speaker N" 자리표시자는 부분 간에 겹치지 않게 번호 재부여**(이미 이름 확정된 것은 그대로). 대표 노트에 나머지 부분의 노트 본문을 `## Part — …`로 붙여 요약 손실 없게 한다. **원본 부분 노트는 그대로 두고 `merged_into` 백링크만 추가**, `merged_from`으로 역연결.
- **나누기:** 대화록에서 "분할선" 마커를 두면 **다음 화자 줄로 스냅**, 두 노트가 **같은 오디오를 공유**(시각은 녹음 기준 유지), 한쪽을 지워도 다른 쪽 오디오는 남음. **새 파일을 먼저 만든 뒤 원본을 수정**해 중단돼도 텍스트가 안 사라진다. 요약 후에는 못 나눈다(요약이 양쪽을 설명하므로).

**QuietClerk 형태:** 합치기 M(대화록 이어 붙임 + 화자 번호 재부여 + 합친 대화록으로 요약 다시) / 나누기 M(새 작업 두 개로 분리, 오디오 공유 삭제 규칙). 목소리 등록(T02)이 있으면 부분 간 화자 연결이 훨씬 쉬워진다. **충돌:** 없음.

#### T09. 요약 템플릿 파일화 (M)

**QuietClerk 현재:** 유형 7종 섹션 고정, 사용자 정의 없음(기능 목록).

- MeetingMaster3: 내장 24종이 **vault 안 일반 파일**(`MeetingMaster3/templates/`). 같은 `id`면 사용자 파일이 우선. `<!-- mm3:prompt:… -->` 블록으로 섹션별 지침. 앱 업데이트는 **손대지 않은 템플릿만** 갱신하고, 수정한 내장 템플릿에 새 버전이 나오면 알려 주고 "기본값으로 되돌리기"(내 사본은 Archive). 저장 전 검증은 **줄 번호가 붙은 오류**(`mm3 templates validate`). `favorite: true`를 파일 안에 저장(`docs/user-guide/templates.md` L33-45, L88-120).
- **할 일 규칙**: 소유자는 "하겠다고 했거나 요청받고 동의한 사람"뿐, "하면 좋겠다" 수준은 **Unassigned**, 기한은 말한 그대로 + "오늘·내일·요일"은 회의 날짜로 계산한 날짜 병기, `[mm:ss]` 시각(같은 문서 L58-68). 소유자는 실제 발언으로 검증한다.
- WhisperCal: 프롬프트 파일을 vault `Prompts/`에 설치하되 **기존 파일은 덮어쓰지 않음**, 프롬프트별 모델·추가 플래그, 실행 때 **"이번만 지시" 입력창**("예산 논의에 집중")(README L605, L981-995, L1017).
- Scriberr: `SummaryTemplate{name, description, model, prompt, include_speaker_info}`(`internal/models/summary.go` L10-20).

**QuietClerk 형태:** 유형별 템플릿 파일(설정 폴더). **근거 링크 규칙·출력 JSON 계약은 잠긴 영역**으로 두고 지침 문장만 수정 허용(근거 링크가 깨지면 안 되므로 [추정]). 줄 번호 검증, 기본값 되돌리기(수정본 보관), "요약만 다시" 옆에 "이번만 지시" 입력창. 할 일 소유자·기한 규칙이 현재 프롬프트에 있는지는 확인 못 함 — 비교 후 보강. 크기 M.
**호응:** MeetingMaster3 0★, WhisperCal 6★ — 확인 못 함. **충돌:** 없음(템플릿은 로컬 파일, 엔진 전송 범위는 그대로).

---

### 3-D. 내보내기·검색

#### T10. 내보내기 형식·옵션 (S–M)

**QuietClerk 현재:** 내보내기 없음(기능 목록). 단어 시각이 이미 있어 자막 형식을 만들 수 있다.

**다른 프로젝트**
- vibe: SRT·VTT·TXT·HTML·PDF·JSON·DOCX·CSV·MD(`desktop/src/components/format-select.tsx` L6-20). 대화상자에서 **내용(대화록/요약), 형식, "화자 표시", "타임스탬프 표시", 미리보기, 복사/저장**(`transcript-export-dialog.tsx`).
- whosaid: `.txt .srt .vtt .tsv .json .rttm` + `speakers.txt` + **사이드카 JSON**(화자 클러스터·`registry_matches`(근접 실패까지 기록)·`source`(길이·생성 시각)·`uncounted`)(README L1548-1600).
- Buzz: SRT/VTT/TXT/JSON + DOCX 플러그인("추가 의존성 없음"), **재분할(자막 길이·문장부호·무음 기준)**, 자막 끝 시각 연장(`7_plugins.md` L27-31, `4_edit_and_resize.md`).
- noScribe: HTML(오디오 동기 앵커 포함)·VTT·TXT. TranscriptionSuite: txt/srt/ass(README).

**사용자들이 겪은 결함 — 시험 항목이 된다**
- noScribe #253 "자막 길이가 음수"(닫힘, 댓글 26), vibe #1606 "다화자일 때 SRT 끝 시각이 다음 구간 시작으로 설정"(열림), noScribe #202 "고친 화자 이름이 VTT에 반영 안 됨", #296 "직접 내보내기와 편집기 경유 VTT가 다름".

**QuietClerk 형태:** 웹 화면 "내려받기"(vault에 파일 안 만듦): TXT, SRT, VTT, JSON(턴+단어 시각+화자, 사이드카) = S, DOCX = M. 옵션 "화자 이름/타임스탬프 표시". 시각은 단조 증가·음수 길이 금지, 이름의 특수문자 정리(VTT `<v 이름>`). 편집·이름 변경(T01·T06)이 내보내기에 반영되는지 시험.
**충돌:** 없음.

#### T11. 전체 회의 검색 → 발췌 질문 (검색 M / 질문 L)

**QuietClerk 현재:** 검색·질문 없음(기능 목록).

- whosaid: SQLite **FTS5**(`_search.db`)로 모든 턴을 색인(따옴표·AND/OR/NOT·접두어), 의미 검색은 **로컬 Ollama `nomic-embed-text`**(`--mode exact|meaning|hybrid`), Ollama가 없으면 정확 검색만(실패 안 함). 결과는 회의·시각·화자·스니펫, `context`는 그 시각 앞뒤 N초. 인덱스는 **파생물 — 지워도 다시 만들 수 있음**(README L683-732, L805-808).
- MeetingMaster3: Search 페이지: 회의별 묶음·회의당 4개 패시지·"의미+단어 / 단어만" 배지로 검색 방식 표시, 전사를 350토큰 창+시각+화자 이름으로 색인, 바뀐 파일만 재색인, **전사 중에는 GPU를 쓰지 않음**, 인덱스는 vault 밖(앱 데이터 폴더). Ask-AI: **질문마다(또는 "항상 허용" 스위치) 동의**, 답변은 인용+표(날짜·참석자는 파일에서 가져옴), `MM3 Answers/`에 노트로 저장. **클라우드 임베더는 별도 동의 스위치**(모든 회의 텍스트가 나가므로)(`search-and-ask.md` L1-95, README L40-52, L68-75).
- **한국어 FTS5 동작(로컬 sqlite3 3.54.0, 한 문장 가정 입력으로 확인):** `unicode61`에서 `회의`는 `회의를`을 못 찾고(0건), **접두어 질의 `회의*`는 찾는다**(1건). `trigram`은 3자 이상만 MATCH가 되고(`회의를`·`시작하` 1건) 2자 `회의`는 0건이지만 `LIKE '%회의%'`는 1건. 실제 회의록 규모·정확도는 확인 못 함.

**QuietClerk 형태:** ① `unicode61` + 접두어 질의 기본, 2자 질의는 `LIKE` 보조. 대화록 줄과 노트 섹션을 색인하고 결과를 누르면 노트의 `^t12` 블록·오디오 시각으로 이동. 크기 M. ② 질문: 구독 CLI에 선택 회의 발췌+근거 링크 → 크기 L.
**충돌:** ①없음. ②**조건부** — 회의 텍스트가 엔진으로 가므로 질문 단위로 보낼 발췌를 미리 보여주고 동의를 받고 "보낸 데이터" 기록에 남긴다(MeetingMaster3 방식). 의미 검색의 임베더는 로컬만.

---

### 3-E. 긴 파일·재개·진행률·운영

#### T12. 단계 안 진행률·ETA (S–M) — 차점

**QuietClerk 현재:** 현재 단계와 경과 시간만 있다(`rec/quietclerk/server/__init__.py` L108-122, `last_progress`는 `None`). 단계 시간 이력은 `stage_runs`에 쌓인다.

- MeetingMaster3 `jobs/progress.py` L19-47: 남은 시간 = `경과×(1−f)/f`, **f≥0.02이고 1초 이상 지난 뒤에만** 표시. 첫 추정은 하드웨어 프로필("대략 …"), 측정되면 실측 속도. **예상을 넘기면 0으로 카운트다운하지 않고 "예상보다 오래 걸리는 중"**. 막대 줄무늬·시계는 계속 움직여 멈춘 게 아님을 보여 준다. "Hide and keep running", 새로고침 뒤 이어 보기(이벤트 `seq`+재생 캐시), 취소는 청크 사이에서만(`reviewing-and-editing.md` "Progress while the model works" 절).
- vibe: 퍼센트 + 취소 + "중단 중" 상태(`desktop/src/pages/home/progress-panel.tsx`). whisperX: 화자 분리 단계 비율을 `progress_callback`으로 환산(`whisperx/diarize.py` L120-160).
- **QuietClerk 형태:** ASR 60초 청크·교정 60턴 청크 단위 카운트("교정 3/9")는 값싸게 얻을 수 있다 [추정]. ETA는 자체 `stage_runs` 이력(길이당 소요, 문서의 "1시간≈7분")을 쓰면 MeetingMaster3보다 정확할 수 있다 [추정]. 크기 S–M. **충돌:** 없음.

#### T13. 실행 기록 + "다시 처리하면 달라질 회의" 탐지 (M)

**QuietClerk 현재:** 노트 속성에 `pipeline_asr`·`pipeline_llm`·`qc_schema`, 모델 스냅샷 고정(`model_ids`), 단계 캐시 키 = 입력 해시+파라미터(how-it-works L402). **빠진 것:** 기록된 파이프라인과 현재 고정을 비교해 영향받는 회의를 모아 보여 주는 기능, 일괄 재처리.

- whosaid `reprocess <ws> --dry-run`: 각 회의의 사이드카를 읽어 **구버전 결함 패턴**을 찾는다(`brief-fragments`, `short-hinted-undercount`, `bound-pinned`…를 likely/possible로 구분, `whosaid_version` 기록으로 판단). 재처리는 **ASR 재사용**. 사용자 편집(전사 전용 라벨·손으로 고친 제목·상태)은 보존, **백업 `_reprocess-backups/<회의>/<UTC>`**, 실패하면 자동 복원(README L493-547). 합성 회의 8개에서 화자 수 총오차 11→6(자체 측정, 합성 데이터).
- Scriberr: 실행마다 `TranscriptionJobExecution`(시작·끝·소요 ms·**실제 사용 파라미터**·상태·오류)을 남기고 "Transcription Details" 대화상자에서 본다(`internal/models/transcription.go` L296-343, 프런트 `ExecutionInfoDialog.tsx`). **사고 사례 #469:** 중단 뒤 재실행/재개 시 **diarization 옵션이 조용히 사라져** 화자 없는 전사가 나왔다(열림). → 시험: 중단→재개해도 옵션이 보존된다.
- MeetingMaster3: 재개 = "완료 아님 **또는 산출물 파일이 없는** 첫 단계부터, 그 단계와 이후를 pending으로"(`dev-guide/jobs-and-stages.md` L189-191), 충돌로 멈춘 작업은 **자동 재개하지 않고 사용자가 재개**(같은 문서 L46 — 서버를 죽인 작업이 부팅마다 서버를 죽이지 않게). 단계 구성이 바뀐 옛 작업은 재개를 `E_PIPELINE_CHANGED`로 거부(L111). 생성 부분 결과는 (템플릿·백엔드·모델·지시문·전사)를 키로 저장(L254). QuietClerk는 모든 단계에 입력+파라미터 키를 이미 쓰므로 **동등 이상**.

**QuietClerk 형태:** 실행마다 "실제 옵션(언어 고정·화자 힌트·단어장 버전)·모델 스냅샷·엔진 버전"을 `stage_runs`에 기록. 설정 화면 "다시 처리하면 달라질 회의 N건"(dry-run 목록) → 선택해 재처리(백업 후, 요약 재호출 때는 엔진 동의 확인). 크기 M. **충돌:** 없음.

#### T14. 합성 회의 평가 하니스 + 모델 선택 근거 (M–L) — 차점

- whosaid `docs/diarize-eval.md`: TTS 34개 목소리(ElevenLabs 21+OpenAI 13)로 **정답이 샘플 단위로 정확한 가짜 회의**를 만든다. `(seed, index)`로 같은 회의를 바이트 단위 재현, 난이도 프로필(easy/hard/long)·발화 패턴(balanced/dominant/rare-speaker/cameo)·겹침·잡음·음량 차이, DER·WER·턴 정확도·이름 점수. "**TTS 목소리이므로 실제 통화 정확도를 예측하지 않는다**"고 문서가 못 박는다. 하니스 자체 버그(실제형 회의 WER이 인위적으로 72%)도 기록하고 고쳤다.
- 모델 조사 결과(방향성만): **Whisper turbo는 어려운 오디오에서 불안정** — 같은 회의 7회 실행 WER 2.6~17.2%, large-v3는 매번 1.4%. Qwen3-ASR(1.7B+Aligner)은 large-v3와 비슷(1.2%)하지만 **aligner가 구두점을 버려 휴지 기준 분할이 거칠어져 다른 화자의 짧은 대답을 삼킬 수 있다**. Parakeet는 잡음·겹침에서 최대 56초 무음. whosaid는 기본 모델을 large-v3로 바꿨다(긴 회의 약 1.85배 시간)(`docs/model-survey-2026-10.md` L28-33, TODO 목록).
- QuietClerk에 시사: ① QuietClerk는 이미 Whisper turbo를 "힌트"로만 쓰고 실녹음 4개에서 꼴찌·6~9% 누락을 문서화했다(how-it-works L397-398) — 판단이 겹친다. ② "**짧은 맞장구가 앞 턴에 흡수**"는 QuietClerk의 단어→턴 변환(겹침 최대 화자 + 1.5초 휴지, `transcript.py`·how-it-works L156-157)에 직접 해당하는 위험이다. `samples/` 실녹음으로 확인할 가치가 있다.
- **QuietClerk 형태:** `say`(macOS 한국어 음성) 등 **로컬 TTS**로 합성 회의를 만들어 화자 배정·턴 분리 회귀 시험으로 쓴다 — whosaid는 대본을 외부 TTS(클라우드)로 보내므로(실제 녹음이 아니라 대본이지만) QuietClerk에서는 로컬 TTS여야 "외부 전송 0"이 유지된다 [추정]. 크기 M–L. **충돌:** 로컬 TTS면 없음.

#### T15. 감시 폴더 점검 (S) — 차점

QuietClerk는 안정화·SHA-256 중복·길이·디코딩·크기 검사·격리를 이미 갖췄고(기능 목록), 상대 프로젝트보다 낫다(4절). 가져올 것은 두 가지:
- whosaid: `watch run --dry-run`("지금 처리될 파일 목록"), `install --dry-run`(plist·단계 출력), **수신 폴더와 작업 폴더가 같거나 중첩이면 시작 거부**(README L890-902). Buzz: 출력 폴더는 입력 폴더·그 하위가 될 수 없음(`preferences.md` L91-110).
- "기존 녹음" 화면에 "처리될 파일 미리보기" 한 줄. 크기 S. **충돌:** 없음.

#### T16. 완료 알림·훅 (S) — 차점

- TranscriptionSuite 웹훅: 이벤트 `longform_complete` 본문(`text, filename, duration, language, num_speakers`), 선택 Bearer 시크릿, "Send Test Webhook"(README L708-770). Scriberr도 웹훅(10초 타임아웃). whosaid는 훅 명령에 전사를 stdin·환경변수로 준다(README L384-430 근방).
- QuietClerk에 알림 없음(기능 목록). **형태:** macOS 알림센터("회의록 완성 / 검토 필요 N건 / 폰 N일 미연결"). 외부 웹훅을 넣는다면 **본문 없이 이벤트와 노트 경로만**, 대상은 로컬 주소 기본. **충돌:** 웹훅에 대화록 `text`를 싣는 방식은 "회의 텍스트는 동의한 엔진에만" 원칙과 충돌 → 가져오지 않는다.

#### T17. 설치 후 오프라인·텔레메트리 점검 (S) — 차점

- MeetingMaster3: `mm3 doctor`, `mm3 models download/status`, `transcription.offline: true`(`HF_HUB_OFFLINE`), pyannote 4가 기본으로 `otel.pyannote.ai`에 사용 통계를 보낸다는 사실을 문서화하고 **항상 끔**(`PYANNOTE_METRICS_ENABLED=false`)(`transcription.md` "Offline mode").
- whosaid: `--offline`이 `HF_HUB_OFFLINE=1`·`TRANSFORMERS_OFFLINE`·텔레메트리 끔을 launchd에 심음, 인증서 환경변수 복사(README L897-899, L201-203, L921-937). noScribe docker: 모델을 **리비전 고정+SHA-256 검증**(`docker/README.md`).
- QuietClerk는 모델 스냅샷 고정이 이미 있다. **형태:** 설치 마법사 마지막/홈에 "오프라인 변수·텔레메트리 상태·모델 해시 일치" 한 줄 표시(원칙 "음성은 Mac 밖으로 안 나감"을 사용자가 확인할 수 있게). 크기 S. **충돌:** 없음(원칙 강화).

#### T18. 데이터 인벤토리·위협 모델 표 (S, 문서)

- MeetingMaster3 `docs/PRIVACY.md`: **"어떤 데이터가 어디에 있고 언제 지워지나" 표**(오디오 → 작업 중 원본+16kHz WAV, 완료 후 Opus 사본, 기본 90일 뒤 삭제·고정 가능 / 성문 임베딩 → 이름 확정 직후 삭제 / 로그에는 대화록 텍스트를 남기지 않음 …), "What can leave your machine / never leaves", "Your controls"(L7-30, L32-76).
- `docs/THREAT_MODEL.md`: 경계(B1~B6)별 **`ID | 위협 | 완화 | 코드 | 시험`** 표. 예: T-MEDIA(악성 미디어 — 업로드는 서버가 이름 붙인 0600 파일, ffprobe 오디오 스트림 확인, 쉘 없이 인자 목록, `--`·`-nostdin`·타임아웃, **`-protocol_whitelist file`, playlist/list demuxer 거부**), T-DOS(2GB 한도, 변환 타임아웃=실시간+120초, 협조적 취소, OOM 시 작은 배치→작은 모델, 3시간 가짜 작업 메모리 측정), T-IMPORT(엄격 UTF-8·NUL/제어문자 거부, **작업을 만들기 전에 파싱**), T-BIO(성문). "잔여 위험(수용·이유)"과 "문서를 최신으로 유지하는 법" 절도 있다(L93-146).
- CI `docs-check`: lychee로 마크다운 링크를 오프라인 검사(`.github/workflows/docs-check.yml`).
- **QuietClerk에 이미 있는 코드**: `-protocol_whitelist file`, `-f mov`, `-enable_drefs 0`, `-nostdin`, 길이 기반 타임아웃(`rec/quietclerk/stages/audio.py` L14-19, `probe.py` L85). 문서가 이 표 형식을 따르면 제품 게이트의 "입력 유형별 처리 방침·비정상·악의 입력 테스트를 문서에 둔다"에 곧바로 맞는다. **형태:** `docs/threat-model.md`(입력 유형 × 위협 × 완화 × 코드 × 시험 이름) + `docs/data-inventory.md`. 크기 S. **충돌:** 없음.

#### T19. 요약 피드백 (S) — 차점
MeetingMaster3: 노트 전체 별 1~5, 섹션별 👍/👎+코멘트, 템플릿·백엔드·모델을 같이 기록, **로컬에만 저장**하고 CSV/JSON으로 내보내기(PRIVACY.md "Job state, feedback ratings"). Codex vs Claude Code 엔진을 비교할 근거가 쌓인다. 크기 S. 호응 확인 못 함. 충돌 없음.

#### T20. 참석자 위키링크 (S–M) — 차점
WhisperCal: 확정 이름을 `confirmed_speakers: ["[[Jane Smith]]"]`로 쓰고 People 노트와 정렬, 노트가 없으면 "+ Create note"(README L1003, L1096). QuietClerk의 `attendees`는 비어 있다(`render.py` L185). 확정 이름(T01)을 `attendees` 위키링크로 채우면 Bases에서 사람별 보기가 된다. 사람 노트 자동 생성은 기본 꺼짐. 충돌 없음.

---

## 4. QuietClerk 쪽이 이미 더 낫거나 동등한 것 (가져오지 않음)

| 영역 | 상대 | 근거 | QuietClerk |
|---|---|---|---|
| 수신 안정화 | Scriberr dropzone은 생성 이벤트 뒤 500ms 대기하고 복사(`internal/dropzone/dropzone.go` L186). Buzz는 30초, whosaid는 mtime 120초 안정 | 위 파일·문서 | 안정화 + 디코딩·크기·길이 검사 + 격리 복사 |
| 중복 | Buzz "Skip Already Transcribed"는 같은 이름의 결과 파일·DB 항목 기준(`7_plugins.md` L35-41) | | SHA-256 |
| ffmpeg 입력 보호 | MeetingMaster3 T-MEDIA와 동등 | `THREAT_MODEL.md` L96 | `-protocol_whitelist file -f mov -enable_drefs 0 -nostdin` + 길이별 타임아웃 |
| 재개 키 | MeetingMaster3는 생성 단계에만 입력 키 | `jobs-and-stages.md` L254 | 모든 단계에 입력 해시+파라미터 키 |
| 교정 응답 불일치 | meetnote는 줄 수가 다르면 **전체를 원문으로 되돌림**(`transcript_corrector.py` `apply_correction`) | | 60턴씩 호출하고 나쁜 응답은 반으로 나눠 재시도 |
| 요약 근거 | 대부분 `[mm:ss]` 시각 텍스트(MeetingMaster3 `templates.md` L62-66) | | 문장마다 대화록 줄 블록 링크 |
| 외부 전송 표시 | MeetingMaster3 동의 모달, whosaid README 선언 | | 엔진별 동의 + `external_text_to` 속성 + "보낸 데이터" 패널 |
| 구독 CLI 검증 범위 | WhisperCal은 `claude`만 검증(README L975) | | Codex·Claude Code 검증 |
| 원자적 쓰기 | MeetingMaster3 | | `.part`→rename(`render.py` L228) |

## 5. 가져오지 말 것

- 실시간·라이브 전사(meetnote 5초 청크, whosaid live, TranscriptionSuite Live) — 갤럭시 기본 녹음 앱 후 동기화라는 전제와 안 맞는다.
- 클라우드 전사(steno의 AssemblyAI/Deepgram, resojot의 클라우드 ASR 목록) — 음성이 Mac 밖으로 나가므로 원칙 충돌.
- 회의록 이메일 발송(meetnote SMTP), 외부 웹훅 본문에 대화록 포함(T16) — 동의한 엔진 밖으로 텍스트가 나간다.
- 다중 사용자·SSO·서버 모드(meetnote 단체 모드, noScribe server) — 단일 Mac 앱.
- 브라우저 탭 녹음·Teams 채팅(whosaid) — 범위 밖.
- GPL 코드·라이선스 불명 코드 복사(2절) — 아이디어만.
- Scriberr "컬렉션"(녹음 묶기, #402) — QuietClerk의 프로젝트 제안과 겹침. Scriberr 메모·하이라이트(`internal/models/note.go`)는 Obsidian 블록 링크로 이미 가능.

---

## 6. 근거 기준 URL (고정 커밋)

| 약칭 | 기준 URL (뒤에 `<경로>#L<줄>`) |
|---|---|
| whosaid | https://github.com/sblattj/whosaid/blob/bc3efb6/ |
| MeetingMaster3 | https://github.com/antonizick/MeetingMaster3/blob/789e80c/ |
| WhisperCal | https://github.com/dloomis/WhisperCal/blob/3312a02/ |
| meetnote | https://github.com/changsu-jin/meetnote/blob/c1cec0f/ |
| vibe | https://github.com/thewh1teagle/vibe/blob/da8c2ca/ |
| Scriberr | https://github.com/rishikanthc/Scriberr/blob/a353078/ |
| noScribe | https://github.com/kaixxx/noScribe/blob/1e146c3/ |
| Buzz | https://github.com/chidiwilliams/buzz/blob/0556d17/ |
| TranscriptionSuite | https://github.com/homelab-00/TranscriptionSuite/blob/541bde9/ |
| whisperX | https://github.com/m-bain/whisperX/blob/5d3678b/ |
| resojot | https://github.com/jiaoyingxing/resojot/blob/62ab358/ |
| steno | https://github.com/DavidBellamy/steno/blob/fb7c0a6/ |
| nemotron-diar-mlx | https://github.com/9clg6/nemotron-diar-mlx/blob/b042a0a/ |
| Qwen3-ASR | https://github.com/QwenLM/Qwen3-ASR/blob/7c6daf7/ |
| 이슈 | `https://github.com/<소유자>/<저장소>/issues/<번호>` (예: https://github.com/homelab-00/TranscriptionSuite/issues/28) |
| mlx-audio 0.6.4·mlx_whisper 0.4.3 | URL 아님. QuietClerk 빌드용 임시 가상환경의 설치본(`…/quietclerk-wheel-*/venv/lib/python3.12/site-packages/mlx_audio/…`)을 읽음. `rec/pyproject.toml` L19-20이 같은 버전을 고정 |
| QuietClerk | 로컬 저장소 `rec/…` |

호응 근거로 인용한 이슈 번호·댓글·👍 수는 2026-11-10 `gh issue view`로 읽은 값이다.

---

## 7. 이 항목들을 들일 때 필요한 입력 유형별 처리 방침·비정상/악의 입력 시험

기존 입력(안드로이드 m4a, Syncthing 부분 파일 등)은 기존 문서와 코드가 다룬다. 여기서는 **새로 생기는 입력**만 적는다. 이 문서는 시험을 실행하지 않았고, 아래는 도입 시 시험 목록이다.

| 항목 | 새 입력 | 정상 처리 | 비정상·악의 입력 시험 |
|---|---|---|---|
| T01·T04 | 사용자가 입력하는 화자 이름 | 길이 상한, 같은 이름은 병합, 빈 이름은 원래 라벨로 복귀 | 개행·제어문자, `\|`(표 셀), `[[ ]]`·`#^`(링크·블록 ID 주입), YAML 특수문자(`: `, 따옴표), `_ < > " & :`(noScribe가 걷어내는 문자), 이름만 다른 중복 → 노트 YAML·Obsidian 링크·VTT가 모두 정상 파싱 |
| T01 | 이름 변경 후 | 노트·요약·내보내기 모두 반영 | `S1`/`화자1`이 어디에도 남지 않음(meetnote 결함 재현 시험) |
| T02 | 등록 클립·임베딩 | 5초 이상, 순도 확인 | 무음·너무 짧음·섞인 클러스터 거부, 임베더 교체 후 구 항목 무시, DB 파일 권한, 백업 가져오기는 전체 검증 후 쓰기·병합 충돌 거부·덮어쓰기는 명시 |
| T05 | 단어장 파일·표 | 줄 수·길이 상한, 빈 항·자기 치환 무시 | 정규식 메타문자 이스케이프, 치환 연쇄(단일 패스), 거대 목록 성능, 단어장 안의 지시문(프롬프트 주입)은 데이터로 구획, 엄격 UTF-8 |
| T06 | 편집 텍스트 | 줄당 길이 상한(현재 4000자) | HTML·마크다운 주입(JSON 전용 렌더), 빈 텍스트는 무시, 동시·외부 수정(T07) |
| T07 | 노트 파일 | 마커 쌍·원자적 쓰기 | 닫는 마커 삭제, 사용자 글 속 마커 입력, 저장 중 중단, 외부 수정 감지 |
| T08 | 합치기·나누기 | 새 파일 먼저 쓰고 원본 수정 | 중간 중단, 같은 작업 두 번 합치기, 공유 오디오 한쪽 삭제 |
| T10 | 내보내기 | 시각 단조 증가 | 음수·역전·겹침 구간, 아주 긴 줄, 3시간 분량 성능, 형식별로 다시 읽어 라운드트립 |
| T11 | 검색어·질문 | FTS5 문법 문자는 일반 단어로 처리 | 따옴표·`*`·`-`·`NEAR`·`:` 입력, 한글 2자 질의, 회의 텍스트 안의 지시문(발췌에 섞인 프롬프트 주입) |
| T13 | 재처리 | 백업 후 실행, 실패 시 복원 | 중단→재개해도 옵션 보존(Scriberr #469), 백업 복원 후 상태 일치 |
| T16 | 훅 명령 | 사용자 설정만, 인자 목록(쉘 없이) | 노트 경로의 공백·따옴표·개행 |

---

## 8. 미결·확인 못 한 것

게이트 규칙에 따라 담당·확인 시각을 적는다. "담당"은 항목을 구현하는 사람이고 **Main이 지정**해야 한다. "확인 시각"은 내 제안이다.

| # | 미결 | 닫는 방법 | 담당 | 확인 시각(제안) |
|---|---|---|---|---|
| U1 | 한국어에서 mlx-audio ECAPA(VoxCeleb) 임베딩이 같은 사람·다른 사람을 가르는가(임계값·격차 결정) | `samples/`의 실제 갤럭시 녹음에서 같은 사람/다른 사람 구간 코사인 분포 측정 | T02 구현 담당(Main 지정) | T02 착수 결정 전, 2026-11-17 |
| U2 | 단어장(Qwen3-ASR `hotwords`, Whisper `initial_prompt`)이 한국어 CER을 줄이는지, 환각을 늘리는지 | `samples/` 녹음+정답본(CLOVA 등)으로 켠/끈 CER·누락 비교 | T05 구현 담당(Main 지정) | T05 착수 시 |
| U3 | `speaker_probs`로 만든 화자 확신도가 실제 오분리와 맞는지(T03) | 실녹음에서 오분리 구간 vs 확률 비교 | T03 구현 담당(Main 지정) | T03 착수 시 |
| U4 | 짧은 맞장구가 앞 턴에 흡수되는지(T14) | `samples/` 실녹음에서 턴 분리 점검 | Main 지정 | 다음 품질 점검 때 |
| U5 | 비교 대상 대부분의 **사용자 호응 정량** | 스타·이슈 외 근거 없음 — "확인 못 함"으로 유지 | — | — |
| U6 | TranscriptionSuite PRD의 "저신뢰 시 요약 보류"가 구현됐는가 | 서버·대시보드 코드의 요약 보류 로직 확인 | Main 지정 | T03 설계 시 |
| U7 | 한국어 실제 회의록 규모에서의 FTS5 검색 품질 | 실제 노트 색인 후 질의 비교 | T11 구현 담당 | T11 착수 시 |

닫은 것: nemotron `generate()`에 화자 수 인자가 없음(소스 확인), mlx-audio가 `hotwords`·`speaker_probs`·ECAPA 추출기를 제공함(소스 확인, 실행 안 함), 한국어 FTS5 기본 동작(가정 입력으로 확인).
