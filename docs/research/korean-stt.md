# 국내 STT·회의록 서비스 조사 (확인일: 2026-11-09)

목적: 갤럭시 S25 Ultra 녹음(m4a) → Mac mini 자동 수집 → 한국어 STT + 화자 분리(2명 이상) + 요약/할 일 추출 파이프라인에 넣을 후보 선별.
작성: KoreanSttServices. 해외 서비스·로컬 모델은 이 문서 범위 밖(다른 에이전트 담당).

## 0. 표기 규칙

- **[확인]** = 2026-11-09에 공식 페이지/문서/약관을 직접 열어 확인한 사실. 출처 URL을 항목 뒤 또는 각 후보의 "출처" 목록에 단다.
- **[2차]** = 블로그·리뷰·제3자 글. 1차 확인이 안 되는 경우에만 보조로 사용.
- **[추정]** = 확인하지 못한 해석·가정.
- **확인 못 함** = 찾지 못함. 값을 채우지 않음.
- 정확도(CER/DER)는 공개 벤치마크가 있을 때만 기재. DER(화자 분리 정확도)은 이 조사에서 공개 수치를 하나도 찾지 못함.
- 가격은 VAT 별도 여부를 각 항목에 명시.

## 0-1. 먼저 알아야 할 결론 요약

1. **삼성·클로바노트(개인용)·다글로(웹) 세 가지는 "앱/웹 UI 전용"**이다. 업로드·결과 수령을 자동화하는 공식 API가 없다. 삼성은 앱 밖으로 꺼낼 공식 자동 경로 자체가 없고, 클로바노트·다글로 웹은 브라우저 자동화만 가능하며 클로바노트는 네이버 이용약관의 자동화 금지 조항에 걸릴 소지가 크다(§2 항목 10).
2. **공개 API로 파일 업로드→JSON(화자·타임스탬프)을 받을 수 있는 국내 서비스는 CLOVA Speech(NCP), RTZR, 다글로 Developers 셋뿐**이다. 이 셋은 Mac mini 상시 파이프라인에 그대로 붙일 수 있다.
3. 콜라보(Callabo, RTZR 계열)·티로(Tiro)·네이버웍스 클로바노트는 REST API가 있지만 **현재 문서상 조회(읽기) 전용**이다. 파일 업로드 API는 문서에서 찾지 못함 → 업로드는 앱/웹 UI 필요.
4. 한국어 정확도의 공개 근거는 **RTZR가 직접 운영하는 벤치마크(CLOVA Speech·RTZR 포함)** 와 **MDPI 논문 1편(20개 발표 녹음, CLOVA Speech 포함)** 뿐이다. 삼성·클로바노트·다글로·콜라보·티로는 제3자 공개 CER을 찾지 못함 → 실측이 필요한 이유.
5. 화자 분리 "최대 화자 수/화자 수 지정"이 문서에 명시된 곳: CLOVA Speech(최대 30명이나 **요청 파라미터는 on/off(`enable`)뿐**, min/max는 응답에만 표시), RTZR(`spk_count` 지정 가능, 최대치 미명시), 티로(화자 수 입력칸, Pro 이상). 다글로 API는 on/off만 문서화. 삼성·클로바노트는 확인 못 함. → **요청 시 화자 수를 지정할 수 있는 것은 RTZR와 티로(UI)** 뿐.

---

## 1. 삼성 갤럭시 기본 음성 녹음 — 텍스트 변환 어시스트(Transcript Assist)

대상: 갤럭시 S25 Ultra(SM-S938N), One UI 7~8. 한국 공식 문서가 S24~S25 세대 문구 위주라 S25 전용 차이는 확인 못 함.

| # | 항목 | 내용 |
|---|------|------|
| 1 | 한국어 STT | 지원 [확인]. 삼성 미국 지원문서 지원언어 목록에 Korean 포함 (https://www.samsung.com/us/support/answer/ANS10000942/). |
| 2 | 화자 분리 | 한국어 제품 페이지가 "개별 화자의 대화 내용이 텍스트로 표시"된다고 기술 [확인] (https://www.samsung.com/sec/smartphones/galaxy-s24). **최대 화자 수·화자 수 지정 옵션은 공식 문서에 없음 → 확인 못 함.** 화자 라벨 품질은 실측 필요. |
| 3 | 단어·구간 타임스탬프 | 재생 시 해당 단어가 오디오와 동기화되어 강조된다고 공식 페이지가 기술 [확인] (같은 S24 페이지). 내보낸 파일에 타임스탬프가 들어가는지는 확인 못 함. |
| 4 | 요약·할 일 | 요약 있음. 삼성 계정 로그인 필요, 글자 수가 너무 짧거나(최소) 너무 길면(최대) 요약 불가 [확인] (https://www.samsungsvc.co.kr/solution/1847983). 요약 후 "실행 제안"(캘린더 일정·리마인더·연락처 추가) 제공 [확인] (ANS10000942). 결정 사항/근거 타임스탬프 같은 구조화 항목은 문서에 없음. |
| 5 | 입력·길이·크기 | **삼성 음성 녹음 앱 또는 전화 앱으로 녹음한 파일만** 가능 [확인]: 삼성 한국 제품 페이지(S24) 고지문 "텍스트 변환 어시스트는 미리 설치된 삼성 음성 녹음 앱 또는 전화 앱을 통해 녹음된 파일에서만 사용할 수 있습니다. 3시간 미만의 오디오 파일만 처리할 수 있습니다." (https://www.samsung.com/sec/smartphones/galaxy-s24) + 삼성 멤버스 공식 답변 "당사 음성녹음 앱의 텍스트 변환 기능은 당사 앱에서 녹음한 m4a 파일(음성녹음, 통화녹음)에 대해서만 제공"(2024-04, https://r1.community.samsung.com/t5/갤럭시-s/다운받은-음성녹음-파일을-삼성음성녹음-앱-텍스트변환/td-p/26716514). **최대 3시간**, 3시간 초과는 Trim 후 변환 [확인] (삼성 멤버스 공식 답변 2024-10, https://r1.community.samsung.com/t5/갤럭시-z/통화음성-텍스트-변환-시간제한/td-p/29752217). **인터뷰 모드로 녹음한 파일은 텍스트 변환 불가** [확인] (같은 답변). 즉 외부에서 가져온 파일·Mac에서 재가공한 파일은 대상 아님. |
| 6 | 무료/유료 | Galaxy AI 기본 기능은 무료. 단 "향후 출시되는 향상된 기능이나 새로운 서비스는 유료일 수 있음" 고지 [확인] (https://www.samsung.com/sec/smartphones/galaxy-z-trifold/ 고지문, ANS10000942). |
| 7 | 접근 경로·자동화 | **앱 전용.** 공개 API 없음 [확인: 문서에 없음]. 온디바이스 여부: 한국 공식 안내는 "텍스트 변환 및 요약은 **네트워크 연결 및 삼성 계정 로그인 필요**" [확인] (samsungsvc 1847983) → 순수 온디바이스로 단정할 수 없음. 일부 사용자 글에 "휴대전화에서 안전하게 분석 중" 문구가 보이나 공식 확인 아님 [2차]. 처리 위치 **확인 못 함**. 자동화: (a) 원본 m4a는 `내장저장공간/Recordings/Voice Recorder`에 저장되어 Syncthing 동기화 가능 [확인: 사용자 글에서 해당 경로 언급, https://r1.community.samsung.com/t5/갤럭시-s/다운받은-음성녹음-파일을-삼성음성녹음-앱-텍스트변환/td-p/26716514]. (b) **변환 결과**는 앱 UI에서 수동 공유(더보기 > 공유 > 음성 파일/텍스트 파일) 또는 Samsung Notes 추가 [확인: ANS10000942]. 결과를 파일로 자동 생성하는 경로는 확인 못 함. UI 자동화(Tasker/접근성) 가능 여부는 [추정: 가능할 수 있으나 공식 경로 아님]. → 파이프라인 관점에서 **자동화 불가에 가깝다**. |
| 8 | 내보내기 | 텍스트 파일 공유, 음성 파일 공유, 텍스트 전체 복사(길게 눌러 "모두 복사"), Samsung Notes로 추가 [확인: ANS10000942; 삼성 멤버스 답변 https://r1.community.samsung.com/t5/갤럭시-z/음성녹음-텍스트변환-공유시-수정/td-p/31816173]. 공유한 txt가 타 앱에서 깨진다는 사용자 보고가 있음(인코딩 문제, 삼성 답변은 '복사' 권장) [확인: 같은 글, 사용자 보고]. docx/srt/json 없음. |
| 9 | 데이터 정책 | 학습 사용 여부·보관 기간·옵트아웃: **확인 못 함.** 삼성은 "Galaxy AI 기본 기능은 삼성 서비스 이용약관의 'Advanced Intelligence' 항목에 열거"라고만 안내 [확인: 위 트라이폴드 페이지 고지]. 약관 본문은 직접 열지 못함. |
| 10 | 약관상 자동화 제한 | 해당 없음(OS 기본 앱, 외부 접근 경로 자체가 없음). |
| 11 | 공개 한국어 정확도 | **없음.** 삼성은 "결과의 정확성은 보장되지 않음"으로 고지 [확인]. 제3자 CER 확인 못 함. |

**출처(확인일 2026-11-09)**: https://www.samsungsvc.co.kr/solution/1847983 (2026-10-21자), https://www.samsung.com/us/support/answer/ANS10000942/, https://www.samsung.com/sec/smartphones/galaxy-s24, https://www.samsung.com/sec/smartphones/galaxy-z-trifold/, https://r1.community.samsung.com/t5/갤럭시-z/통화음성-텍스트-변환-시간제한/td-p/29752217, https://r1.community.samsung.com/t5/갤럭시-s/다운받은-음성녹음-파일을-삼성음성녹음-앱-텍스트변환/td-p/26716514, https://r1.community.samsung.com/t5/갤럭시-z/음성녹음-텍스트변환-공유시-수정/td-p/31816173. One UI 7의 통화 녹음+텍스트 변환 연계는 ANS10000942 "추천 글" 요약에서만 확인(https://www.samsung.com/us/support/answer/ANS10004613/ 본문은 열람하지 않음).

**판단 한 줄**: 실측 비교에 넣을 가치 **있음(기준선 1순위, 단 수동 측정용)** — 폰에서 공짜로 되는 최저 기준선이고, 인터뷰 모드가 아니면 사용자가 이미 쓸 수 있으나, 자동화 경로가 없어 최종 파이프라인 후보는 아님(품질 하한 비교용).

---

## 2. 네이버 클로바노트 (개인용 웹·앱) + 네이버웍스 클로바노트(비즈니스)

개인용(naver)과 비즈니스용(네이버웍스)은 별개 상품이다. 개인용에는 유료 플랜·API가 없고, API는 네이버웍스 상위 요금제에만 있다.

| # | 항목 | 개인용 클로바노트 | 네이버웍스 클로바노트(비즈니스) |
|---|------|---|---|
| 1 | 한국어 STT | 지원. 인식 언어: 한국어, 한국어+영어, 영어, 일본어, 중국어 간/번체 [확인] (https://help.naver.com/service/24269/contents/14638?lang=ko) | 동일 계열. API 기준 ko/en/ja/zh-cn/zh-tw/enko/jako [확인] (https://developers.worksmobile.com/kr/docs/ainote-user-note-get) |
| 2 | 화자 분리 | 서비스 약관에 "화자 구분 기능" 명시 [확인] (https://terms2.line.me/ClovaNote_Terms?lang=ko). 파일 업로드 시 "음성 종류와 참석자 수는 기본 옵션으로 반영" 문구 [확인] (https://help.naver.com/service/24269/contents/12820?lang=ko) → 참석자 수 입력 옵션 존재로 보이나 **최대 인원 확인 못 함**. 참석자 이름 수정, 대화 점유율 표시 [확인] (https://help.naver.com/service/24269/contents/20565?lang=ko&osType=PC). | 기본 화자 구분은 위와 같고, 별도 기능 **"화자 자동 식별"(주소록 등록 목소리를 기억해 실명 자동 표기)은 Business(510,000원/월) 이상**에서만 [확인] (https://naver.worksmobile.com/pricing/clovanote). 이는 diarization 자체와 다른 "목소리 등록" 기능. |
| 3 | 타임스탬프 | 다운로드 옵션에서 "음성이 발화된 시간, 참석자 정보, 하이라이트 정보" 포함 선택 [확인] (https://help.naver.com/service/24269/contents/12831?lang=ko). 단어 단위 여부 확인 못 함. | API `scripts[]`에 `startOffset`(ms), `attendeeName`, `text` [확인]. 단어 단위 아님(블록 단위). |
| 4 | 요약·할 일 | AI 요약: "AI 맞춤 요약(주요 주제 + **다음 할 일**)" + "시간대별 요약(소제목+시간, 클릭 시 해당 구간 재생)". **한국어로 인식된 노트만** 가능 [확인] (https://help.naver.com/service/24269/contents/20568?lang=ko). 월 요약 횟수: 개인용은 "매월 갱신"만 안내, 횟수 비공개 [확인 + 2차 AIMAG 글도 '공개되지 않음' 확인]. 결정 사항 별도 항목은 없음. | 요약 횟수: Lite 25회/Team 150회/Business 750회. 요약은 "HyperCLOVA X와 OpenAI 모델 사용" 명시 [확인] (네이버웍스 가격 페이지). 사용자 템플릿 요약은 Business 이상. |
| 5 | 입력·길이·크기 | 파일 1건당 **180분, 300MB, .m4a .mp3 .aac .amr .wav만** (영상 불가) [확인] (12814, 12820 페이지). 180분 초과분은 변환되지 않음. | Lite/Team 180분, Business 이상 360분/회 [확인]. |
| 6 | 무료·유료 | **월 300분** [확인: 네이버 클로바 공식 블로그 2025-04-30, https://m.blog.naver.com/clova_ai/223850855638] + "서비스 품질 향상 데이터 수집에 동의 시 매달 300분 추가" [확인: https://help.naver.com/service/24269/contents/12814?lang=ko&osType=COMMONOS] (현재 도움말에는 기본 시간 숫자가 없어 월 300분이 지금도 유효한지는 앱에서 재확인 필요). **개인용은 유료 구매 불가** [확인]. 시간은 가입일 기준 월 갱신, 이월 없음. | Lite 20,000원/월(연 18,000) 1,000분·요약 25회·API 불가 / Team 108,000원(연 86,500) 6,000분·요약 150회·**외부 연동 API 가능** / Business 510,000원(연 423,000) 30,000분·화자 자동 식별. 기업(도메인) 단위·세금 별도 [확인]. 추가: 200분+요약 10회 5,000원 [확인]. |
| 7 | 접근 경로·자동화 | 웹·앱 전용. **공개 API 없음** [확인: 네이버 클로바노트 도움말에 API 안내 없음, 못 찾음]. 자동화 = 브라우저 자동화뿐이며 아래 항목 10의 약관 리스크 있음. | 네이버웍스 Developers에 ClovaNote API 존재(OAuth, scope `ainote`): 노트 목록·검색·상세 조회·삭제, 사용량 조회 [확인] (https://developers.worksmobile.com/kr/docs/ClovaNote). **업로드 API는 목록에 없음** → 파일은 앱/웹으로 올려야 하고 API는 결과 회수용. 상세 조회는 `scripts`(텍스트·화자·시작시각)와 `summaries`(마크다운) 반환 [확인]. |
| 8 | 내보내기 | 음성 기록·음성 파일·요약/메모 다운로드 [확인: 12831]. **파일 형식 목록은 공식 페이지에서 확인 못 함**(HWP 지원은 [2차] Subanana 글 주장, https://subanana.com/ko/blog/갤럭시-음성녹음-텍스트-변환 / 클로바노트 공식 문서 기반이라 주장하나 본인이 직접 확인 못 함). | API JSON(요약은 마크다운) [확인]. |
| 9 | 데이터 정책 | 노트 데이터는 사용자가 영구 삭제하거나 탈퇴하기 전까지 저장 [확인] (https://help.naver.com/service/24269/contents/12899). **선택 동의 시** 녹음파일을 음성인식 향상 연구에 사용: 7일 내 계정 연동을 끊어 비식별 처리, **5년 보관 후 파기**; 미동의 시 불이익 없음 [확인] (https://terms2.line.me/ClovaNote_QualityEnhancementTerms?lang=ko). 옵트아웃 = 이 선택 동의를 끄는 것(대신 추가 300분 포기). | "네이버웍스 클로바노트로 녹음/저장한 데이터는 AI 학습에 사용하지 않음" 명시 [확인]. 음원 저장 5년(표) [확인]. |
| 10 | 약관상 자동화 | 네이버 이용약관: "네이버의 사전 허락 없이 **자동화된 수단(매크로 프로그램, 로봇(봇), 스파이더, 스크래퍼 등)** 을 이용하여 ... 로그인을 시도하거나 ... 이용자(사람)의 실제 이용을 전제로 하는 네이버 서비스의 제공 취지에 부합하지 않는 방식으로 이용"하는 행위 금지 [확인] (https://policy.naver.com/rules/service.html). 클로바노트 약관은 "본 약관에서 정하지 아니한 사항은 네이버 이용약관 ... 에서 정한 바에 따른다"(마지막 장 ②) [확인] (https://terms2.line.me/ClovaNote_Terms?lang=ko). **[해석] 개인용 클로바노트를 봇으로 로그인·업로드·크롤링하는 방식은 약관 위반 소지가 크다.** 법적 판단은 아님. | API는 공식 제공이므로 자동 조회는 허용된 경로. 단 Team 요금제 이상 [확인]. |
| 11 | 공개 한국어 정확도 | 클로바노트 단독 제3자 CER **확인 못 함.** 네이버 계열 엔진 수치는 CLOVA Speech 항(§3)의 벤치마크 참고. 클로바노트가 CLOVA Speech와 같은 엔진·모델인지 공식 확인 못 함 [추정: 같은 계열이나 보장 없음]. | 동일 |

**출처(확인일 2026-11-09)**: https://help.naver.com/service/24269/contents/12814?lang=ko&osType=COMMONOS, https://help.naver.com/service/24269/contents/12820?lang=ko, https://help.naver.com/service/24269/contents/20568?lang=ko, https://help.naver.com/service/24269/contents/14638?lang=ko, https://help.naver.com/service/24269/contents/12831?lang=ko, https://help.naver.com/service/24269/contents/12899, https://terms2.line.me/ClovaNote_Terms?lang=ko, https://terms2.line.me/ClovaNote_QualityEnhancementTerms?lang=ko, https://policy.naver.com/rules/service.html, https://naver.worksmobile.com/pricing/clovanote, https://developers.worksmobile.com/kr/docs/ClovaNote, https://developers.worksmobile.com/kr/docs/ainote-user-note-get, https://naver.worksmobile.com/blog/clovanote-speaker-identification, https://m.blog.naver.com/clova_ai/223850855638. [2차] https://aimag.co.kr/clovanote-vs-daglo-free-price-compare (2026-10-22).

**판단 한 줄**: 실측 비교에 넣을 가치 **있음(수동 1회 측정용, 자동화 후보에서는 제외)** — 월 300분 무료이고 한국어 요약·"다음 할 일"이 나오는 대중 기준선이라 품질 비교엔 쓸모 있지만, 개인용은 API가 없고 봇 자동화는 약관 리스크가 커서 파이프라인에는 못 넣는다(자동화하려면 Team 108,000원/월 + 업로드 API 부재 문제).

---

## 3. 네이버 클라우드 CLOVA Speech (NCP) — 장문 인식 API

| # | 항목 | 내용 |
|---|------|------|
| 1 | 한국어 STT | 지원. 장문 인식: 한국어, 영어, 한/영 동시, 일본어, 중국어 [확인] (https://guide.ncloud-docs.com/docs/clovaspeech-spec, 갱신 2026-09-17). |
| 2 | 화자 분리 | **요청 파라미터는 `params.diarization.enable`(기본 true, on/off)뿐**이고 `speakerCountMin/Max`는 **응답 `params`에만 나타남**(예시값 -1) [확인: 로컬 파일·Object Storage·외부 URL 3개 문서 모두 동일] (https://api.ncloud-docs.com/docs/ai-application-service-clovaspeech-longsentence-local). **2026-09-17 릴리스: 장문 인식 화자 수 상한 10명 → 30명** [확인] (https://guide.ncloud-docs.com/docs/clovaspeech-releasenote, https://guide.ncloud-docs.com/docs/clovaspeech-builder-long). → **요청 시 화자 수를 지정하는 파라미터는 문서에 없음**(응답 min/max의 의미 확인 못 함). 한국어에서 동작: NCP가 언어별 제한을 명시하지 않음(응답 예시는 `enko`). |
| 3 | 타임스탬프 | `segments[].start/end`(ms) + `words`(단어별 [시작ms, 종료ms, 텍스트]) [확인] (`wordAlignment` 기본 true). 화자는 `segments[].diarization.label`, `speaker.label/name`. |
| 4 | 요약·할 일 | **없음**(STT 전용). 요약은 별도 상품(CLOVA Studio 등) 필요. 키워드 부스팅(최대 1,000개), 이벤트 탐지(박수·웃음·음악) 제공 [확인]. |
| 5 | 입력·길이·크기 | 장문: **동기 최대 2시간, 비동기(Batch) 최대 6시간, 파일 최대 2GB**. 오디오 MP3 AAC AC3 OGG FLAC WAV M4A, 비디오 AVI MP4 MOV WMV FLV MKV [확인] (clovaspeech-spec, 로컬 파일 인식 문서). 비동기는 `callback` URL 또는 Object Storage 저장 중 하나가 필수(둘 다 없으면 오류) [확인]. → 폴링으로 결과를 받는 방식이 없고 콜백/OBS 필요: Mac mini에서 받으려면 공개 콜백 URL 또는 동기 호출(2시간 이내)을 써야 함. |
| 6 | 무료·유료 | **Free 플랜 월 20분 무료**, 화자 인식·이벤트 탐지 Free 플랜도 무료 [확인] (https://www.ncloud.com/product/aiService/clovaSpeech 요금 표). 이용시간 **15초 단위 올림**, 요금 예시 "10초 이용 → 5원, 32초 → 15원"(화자 인식·이벤트 미사용) [확인] → 장문 음성인식 **15초당 5원(분당 20원, 시간당 1,200원), VAT 별도**. Basic 플랜 요금 표의 숫자 셀은 페이지에서 렌더링되지 않아 직접 못 읽음. **화자 인식 추가 요금 15초당 +2원(합계 15초당 7원 = 분당 28원 = 시간당 1,680원)** 은 [2차] 확인(https://github.com/mow-coding/momso/blob/main/docs/research/20260612_ncp_official_pricing_cost_basis.md, 2026-06-12, NCP 요금 API와 대조했다고 주장; https://blog.naver.com/my_life_soso/223309693832). 1차로 확정 못 한 항목이므로 실측 전 NCP 요금 계산기로 재확인 필요. |
| 7 | 접근 경로·자동화 | **공개 REST API**(콘솔에서 도메인 생성 → Invoke URL + Secret Key, 헤더 `X-CLOVASPEECH-API-KEY`) [확인]. 로컬 파일 업로드 `POST /recognizer/upload`, Object Storage `POST /recognizer/long`, 외부 URL `POST /recognizer/url`. 자동화 = **API 호출(완전 자동화 가능)**. NCP 계정·결제수단·Object Storage 설정 필요. |
| 8 | 내보내기 | API 응답 `format`: **JSON(기본), SRT, SMI** [확인]. 빌더 편집기 내보내기: json, smi, srt, txt, csv, xls [확인] (https://guide.ncloud-docs.com/docs/clovaspeech-builder-long). |
| 9 | 데이터 정책 | 결과 보관: 비동기에서 `resultToObs=true`일 때 Object Storage에 저장, 기본 false [확인]. **학습 사용 여부·옵트아웃은 CLOVA Speech 문서에서 확인 못 함.** 참고: NCP는 "인프라 서비스에 저장·업로드하는 고객 데이터는 고객 소유이며 동의 없이 접근하지 않는다"고 공지 [확인] (https://www.gov-ncloud.com/intro/securityPrivacy — 인프라 서비스 기준 문구라 CLOVA Speech 입력 음성에 그대로 적용되는지는 확인 못 함). 사용 가이드는 "NEST 엔진이 데이터를 학습해 지속 개선"이라고 홍보 문구만 있음. |
| 10 | 약관상 자동화 | 공식 API라서 API 키 호출 자동화는 정상 사용 범위. 별도 봇 금지 조항 해당 없음. |
| 11 | 공개 한국어 정확도 | ① RTZR 운영 벤치마크(AI Hub 테스트셋 각 3,000문장 샘플, 마지막 커밋 2025-08-15): Naver ClovaSpeech **평균 CER 7.52%**(회의 7.63, 상담 4.91, 저음질 전화망 6.49, 한국어 강의 7.08) [확인] (https://github.com/rtzr/Awesome-Korean-Speech-Recognition) — **경쟁사 RTZR가 직접 측정**한 값이므로 편향 가능성 있음. ② 독립 학술: MDPI Applied Sciences 2026-09-09, 20개 한국어 발표 녹음에서 CLOVA Speech **평균 CER 4.65%(최저)**, 단 5개 엔진 간 차이는 통계적으로 유의하지 않음(Friedman p=0.219) [확인] (https://doi.org/10.3390/app16188936). 화자 분리 정확도(DER) 공개 수치 확인 못 함. |

**판단 한 줄**: 실측 비교에 넣을 가치 **높음(API 자동화 후보)** — 최대 6시간/2GB, 30명 화자 구분, 단어 단위 타임스탬프, SRT 출력까지 갖춘 NCP 정식 API이며 월 20분 무료로 실제 녹음 테스트가 가능하다. 단점은 요약 없음, 콜백/OBS 설정 필요, 요청 시 화자 수 지정 불가(문서 기준).

---

## 4. 리턴제로 RTZR(구 VITO) STT API

| # | 항목 | 내용 |
|---|------|------|
| 1 | 한국어 STT | 지원. 모델 `sommers`(자체 모델, ko·ja 지원, 기본) / `whisper`(한국어 파인튜닝 Whisper, 다국어 `detect`/`multi` 가능) [확인] (https://developers.rtzr.ai/docs/stt-file.md). |
| 2 | 화자 분리 | `use_diarization`(기본 false) + `diarization.spk_count`(정수, 0=자동 예측). **화자 수 지정 가능**, 예: 전화 통화는 2 [확인] (https://developers.rtzr.ai/docs/stt-file/diarization). 최대 화자 수는 문서에 **명시 없음 → 확인 못 함.** 다중 채널 옵션을 쓰면 화자 분리는 동작하지 않고 채널 ID로 대체 [확인]. 한국어(`sommers`)에서 화자 분리 동작은 샘플 설정 `sommers_call_diarization`에 있음 [확인]. |
| 3 | 타임스탬프 | 발화(utterance) 단위 `start_at`·`duration`(ms) 기본 제공. **단어 단위는 `use_word_timestamp=true`로 옵션** [확인]. 응답 필드 `spk`(정수). |
| 4 | 요약·할 일 | STT 인사이트(`use_insight`): 제목·요약·분류(일상/문의/업무/스팸)를 한 건 반환 — **"enterprise" 라이선스 계약 필요** [확인] (https://developers.rtzr.ai/docs/stt-file/insight.md). 별도 텍스트 인사이트 API(텍스트→제목·요약·분류)도 이용 권한 부여 앱만 사용 가능, **무료 사용량으로 이용 불가**, 입력 100만 토큰당 6,500원/출력 32,500원 [확인] (https://developers.rtzr.ai/docs/text-insight.md, https://developers.rtzr.ai/docs/pricing). 결정 사항/근거 타임스탬프·할 일 구조는 없음. 즉 일반 개발자 계정으로는 **STT만** 사용 가능하다고 봐야 함. |
| 5 | 입력·길이·크기 | mp4, m4a, mp3, amr, flac, wav. **최대 2GB, 최대 4시간.** 요청 순서대로 처리, 평소 5분 내 작업 시작·혼잡 시 30분 이상 대기 가능 [확인] (stt-file.md). 폴링 방식(권장 5초 간격). 동시 처리: 무료 sommers 10 / 유료 20 [확인] (https://developers.rtzr.ai/docs/rate_limit.md). |
| 6 | 무료·유료 | **가입 시 600분 무료, 초기화 없음("월 10시간이 아님")** [확인] (https://developers.rtzr.ai/docs/faq.md). 유료: 월 사용량 구간 누진, **0~1,000시간 구간 시간당 1,000원**(분당 약 16.7원), VAT 별도, 최소 집계 단위 10초 [확인] (https://developers.rtzr.ai/docs/pricing). 화자 분리 추가요금 항목은 요금 페이지에 **없음**(일반 STT 동일 요율) [확인: 페이지에 별도 요율 표시 없음]. |
| 7 | 접근 경로·자동화 | **공개 REST API**(`https://openapi.vito.ai/v1/transcribe`, client_id/secret → JWT 토큰). 자동화 = **API 호출(완전 자동화 가능)**, 폴링 방식이라 Mac mini에 별도 공개 콜백 서버 불필요 [확인]. 한국어 샘플 코드(curl/Python/Java) 제공. |
| 8 | 내보내기 | API JSON(`results.utterances[]`: `start_at`, `duration`, `msg`, `spk`, `lang`) [확인]. srt/docx 등 직접 출력 형식은 **문서에 없음**(필요 시 변환 직접 구현). |
| 9 | 데이터 정책 | **일반 STT 결과는 요청 후 3일간만 보관 후 삭제**(이후 `410` 만료) [확인] (https://developers.rtzr.ai/docs/ 참고사항, `curl`로 HTML 본문 직접 확인). 입력 오디오의 모델 학습 사용 여부·옵트아웃: **확인 못 함**(API 개인정보처리방침 직접 열람 실패). |
| 10 | 약관상 자동화 | 공식 API라 호출 자동화는 정상 범위. API 약관 전문은 직접 열람하지 못함 → 세부 제한은 확인 못 함. |
| 11 | 공개 한국어 정확도 | RTZR 자체 운영 벤치마크(AI Hub, 샘플 3,000문장/세트, 2025-08-15 마지막 커밋): RTZR **평균 CER 5.91%**(회의 6.74·상담 3.51·저음질 전화망 4.40·강의 7.35), RTZR Whisper 6.59%, Naver ClovaSpeech 7.52%, Whisper 11.39%, Google v2 11.50% [확인] (https://github.com/rtzr/Awesome-Korean-Speech-Recognition). **측정 주체가 RTZR 본인**이고 독립 검증이 아님 → 참고용. 화자 분리(DER) 수치 확인 못 함. |

**판단 한 줄**: 실측 비교에 넣을 가치 **높음(API 자동화 1순위 후보)** — 600분 무료로 실제 녹음 시험이 가능하고, 화자 수 지정·단어 타임스탬프·폴링 API가 파이프라인에 가장 단순히 붙는다. 단점: 요약은 엔터프라이즈 계약 필요(요약은 별도 LLM으로 처리해야 함), 결과 3일 보관.

---

## 5. 다글로(Daglo, (주)액션파워) — 웹/앱 + Developers API

두 제품이 분리되어 있다: **웹/앱 daglo.ai(구독, 크레딧)** 와 **Developers API(종량제)**. 웹 보드 결과를 API로 꺼내는 기능은 확인 못 함 [추정: 별도 제품이라 연결되지 않음].

### 5-1. Developers API

| # | 항목 | 내용 |
|---|------|------|
| 1 | 한국어 STT | 긴 음성(Async): 한국어, 영어, 일본어, 한국어+영어 혼합. 요약·부가기능은 **한국어만** [확인] (https://developers.daglo.ai/guide/FAQ.html). |
| 2 | 화자 분리 | `sttConfig.speakerDiarization.enable` on/off [확인] (https://developers.daglo.ai/guide/STT-Subfeatures.html). 문서는 "화자 수가 많을수록 정확도 하락, 겹침·소음에 한계"라고만 명시. **최대 화자 수·화자 수 지정 파라미터는 문서에 없음 → 확인 못 함.** |
| 3 | 타임스탬프 | **단어 단위**: `words[]`에 `speaker`, `word`, `startTime`, `endTime`, `segmentId` [확인] (STT-Subfeatures). |
| 4 | 요약·할 일 | 별도 **회의록 요약 API(Minutes)**: 텍스트 입력 → 요약·핵심 포인트 비동기 생성 [확인] (https://developers.daglo.ai/guide/Language-minutes-summary.html). 출력 스키마·결정사항/할 일 항목은 이번에 상세 확인 못 함. STT와 함께 감정 분석·키워드 추출 옵션. 호출당 90원. |
| 5 | 입력·길이·크기 | **최대 2GB, 최대 4시간.** 오디오 .3gp .3gpp .ac3 .aac .aiff .amr .au .flac .m4a .mp3 .mxf .opus .ra .wav .weba, 비디오 .asx .avi .ogm .ogv .m4v .mov .mp4 .mpeg .mpg .wmv [확인] (https://developers.daglo.ai/guide/STT-Async.html). 노래·배경음악이 큰 오디오는 변환 불가. |
| 6 | 무료·유료 | **신규 가입 시 약 10시간 테스트 가능한 포인트** [확인] (FAQ; 문서 이력 2024년 기준). 소진 시 카드 등록(후불) 또는 선불 계약. **가격 페이지 표시: Async STT 분당 "20원→10원"(VAT 별도)**, Sync "30원→10원", Minutes 요약 호출 90원, TTS 1,000자 15원 [확인] (https://developers.daglo.ai/pricing — 화살표 표기라 "20원 정가 → 10원 현재가"로 해석되나 **[추정]**, 실제 청구액은 인보이스 기준이라고 FAQ가 안내). 화자 분리 추가 요금 표시 없음. |
| 7 | 접근 경로·자동화 | **공개 REST API**(`POST https://apis.daglo.ai/stt/v1/async/transcripts`, 토큰 인증, 폴링 또는 Callback) [확인]. 자동화 = API 호출 가능. 오디오는 URL(`source.url`) 방식 예제가 기본 → **로컬 파일 업로드가 가능한지/방법은 이번에 확인 못 함**(예제가 공개 URL 지정). 파이프라인 적용 시 확인 필요. |
| 8 | 내보내기 | API JSON(`sttResults`, 단어별 화자·시각). srt/docx 직접 출력은 문서에 없음. |
| 9 | 데이터 정책 | Developers 개인정보처리방침: **음성·영상 파일 3개월 보관**, 서버 운영·데이터 보관을 Google LLC(Google Cloud Platform, 미국 이전)에 위탁 [확인] (https://daglo.ai/d/ko/legal/developers-privacy). API 입력의 모델 학습 사용 여부: 이 방침에서 확인 못 함. |
| 10 | 약관상 자동화 | API는 정식 경로. 웹 약관의 금지행위(제17조)는 "접속권한 초과행위, 서비스 정상 운영 방해" 등 일반 문구이며 **'봇/스크립트' 명시 금지는 확인 못 함** (https://daglo.ai/d/ko/legal/terms). |
| 11 | 공개 한국어 정확도 | 제3자 CER **확인 못 함.** 다글로는 "이상적인 환경에서 98% 이상 정확도"라고 자체 주장 [확인: https://daglo.ai/d/ko/faq, 단 측정 조건·데이터셋 미공개 → 근거로 쓰지 않음]. 자체 블로그의 "회의 3건 테스트"는 체감 평가(수치 없음). |

### 5-2. 다글로 웹·앱(daglo.ai)

| # | 항목 | 내용 |
|---|------|------|
| 1~2 | 한국어·화자 분리 | 받아쓰기 전 **[화자표시] 활성화**로 화자 구분 [확인] (https://daglo.ai/d/ko/faq). 보이스매칭(등록한 목소리로 참석자 이름 자동 부여): Free 1명 / Pro 5명 / Premium 50명 / Team 100명 [확인] (https://daglo.ai/d/ko/pricing). **화자 수 지정·최대 화자 수 확인 못 함.** |
| 3 | 타임스탬프 | 스크립트 편집·재생 동기화는 제공(서비스 설명). 다운로드 시 포함 형식은 확인 못 함. |
| 4 | 요약·할 일 | 기본 요약(Free는 수동, Pro 이상 자동), 템플릿 요약(월 20/200/600회), 자체 블로그가 "결정사항·근거·리스크·액션아이템·담당자·마감일 6개 항목" 정리 기능을 소개 [확인: 다글로 블로그, https://daglo.ai/d/ko/blog/ai-hoeuirok-jadong-jakseong-jeonghwakdo-test]. 글자 수 4,000자 미만이면 기본 요약 미생성 [확인: FAQ]. |
| 5 | 길이·크기 | 1회 업로드 Free 500MB / Pro·Premium·Team 2GB [확인: 요금제 표]. 길이 4시간(통화 녹음 FAQ 기준)·1시간 음성에 약 10분 소요 [확인: FAQ]. 지원 형식은 API와 동일 오디오/비디오 목록 [확인: FAQ]. |
| 6 | 무료·유료 | Free: 녹음 받아쓰기 월 4시간 + 파일·YouTube 월 4시간, 월 1,000 크레딧. Pro: 연결제 월 11,900원(월결제 14,900원 [2차 AIMAG]) — 녹음 무제한, 파일·YouTube 월 45시간. Premium: 연결제 월 20,750원(월결제 24,900원 [2차 AIMAG]) — 파일 포함 무제한. Team: 좌석당 월 20,750원~. **가격 페이지 표기와 FAQ(Premium 연 199,000원 vs 249,000원) 불일치, VAT 표기 없음** [확인+2차 AIMAG]. 결제 화면 금액이 최종. |
| 7 | 접근·자동화 | 웹·모바일 앱·크롬 확장. **웹 업로드용 공개 API 없음**(확인 못 함 = 문서에 없음). 자동화 = 브라우저 자동화만. 한컴 오피스 애드온 존재. |
| 8 | 내보내기 | 보드에서 스크립트/음성 다운로드(PC: 보드 우측 상단 다운로드, 앱: 점 3개 메뉴). **여러 건 일괄 다운로드 불가** [확인: FAQ]. 파일 형식 목록은 확인 못 함. |
| 9 | 데이터 정책 | 사용자 사전 승인 없이 기록물을 서비스 외 목적에 사용하지 않음. **선택 동의 시** 음성·텍스트를 비식별 처리해 음성인식 연구에 활용, **5년 보관 후 파기**, 미동의 불이익 없음 [확인] (https://daglo.ai/d/ko/legal/useOfUserData, 2023-02-08 시행). Free 보드는 직접 삭제/탈퇴 전까지 유지 [확인: FAQ]. |
| 10 | 약관 | 위 5-1 항목 10과 동일. |

**출처(확인일 2026-11-09)**: https://developers.daglo.ai/pricing, https://developers.daglo.ai/guide/FAQ.html, https://developers.daglo.ai/guide/STT-Async.html, https://developers.daglo.ai/guide/STT-Subfeatures.html, https://developers.daglo.ai/guide/Language-minutes-summary.html, https://daglo.ai/d/ko/pricing, https://daglo.ai/d/ko/faq, https://daglo.ai/d/ko/legal/useOfUserData, https://daglo.ai/d/ko/legal/developers-privacy, https://daglo.ai/d/ko/legal/terms. [2차] https://aimag.co.kr/clovanote-vs-daglo-free-price-compare.

**판단 한 줄**: 실측 비교에 넣을 가치 **있음(API 후보 3순위)** — 단어 단위 화자 라벨, 분당 10~20원, 한국어 회의록 요약 API가 있어 파이프라인에 맞지만, 화자 수 지정·로컬 파일 업로드 방법이 미확인이고 정확도 근거가 자체 주장뿐이라 실측 없이는 판단할 수 없다.

---

## 6. 그 외 눈에 띄는 국내 서비스

### 6-1. 콜라보(Callabo, (주)리턴제로 — RTZR의 회의록 앱)

비토(VITO)는 통화 녹음 문자 변환 앱, 콜라보는 같은 회사(리턴제로)의 업무용 AI 회의록으로 VITO 후속 성격이다 [확인: 콜라보 요금제 하단에 (주)리턴제로 표기, https://callabo.ai/ko/pricing]. 사용하는 STT 엔진이 RTZR 모델인지는 공식 문서에서 확인 못 함 [추정: 같은 회사라 RTZR 계열일 가능성].

| # | 항목 | 내용 |
|---|------|------|
| 1 | 한국어 STT | 한국어 회의록 서비스(실시간 전사 포함). 언어별 상세는 확인 못 함. |
| 2 | 화자 분리 | 요금제 표에 **"실시간 화자 구분"은 Business 이상만** 표기 [확인] (https://callabo.ai/ko/pricing). 웹훅 `dialogs[].speaker`는 화자 번호(이름 아님) [확인] (https://callabo.ai/blog/webhook-guide). 파일 업로드 건의 화자 분리 동작·최대 인원은 확인 못 함. |
| 3 | 타임스탬프 | 웹훅 `dialogs[]`: `start_at`, `duration`(초, 소수 셋째 자리), `msg`, `speaker` [확인]. |
| 4 | 요약·할 일 | AI 회의록·인사이트(요약), 템플릿 인사이트, 스마트 콜라보 챗 [확인]. 결정 사항·할 일 필드 구조는 `insight_markdown`(마크다운) 내용에 달림 [확인: 웹훅 스키마]. |
| 5 | 입력·길이 | 앱 녹음, Zoom/Meet/Teams, 크롬 확장, **파일 직접 업로드(`manual_upload`)**, 통화 녹음 자동 업로드(Team 이상) [확인: 웹훅·요금제]. 파일 크기·최대 길이: 확인 못 함. |
| 6 | 무료·유료 | **레코딩 시간 Free 5시간 / Personal 20시간 / Team 100시간 / Business 500시간**(기간 단위는 월로 추정 [추정]), 초과 시 시간당 2,000원(Personal)·1,800원(Team)·1,000원(Business), 시트 추가 월 20,000원 [확인]. **Personal 이상 월 구독가는 페이지에서 직접 확인 못 함**(가격이 동적 렌더링). |
| 7 | 접근·자동화 | **REST API v2(Beta)**: PAT 인증, **조회 전용**(워크스페이스·회의·대화록·인사이트·원본 미디어 URL), 전 플랜 가능(Free 100회/60초). CLI/MCP 전 플랜. **웹훅은 Team 이상**(현재 일부 워크스페이스에만 활성화·문의 필요) [확인] (https://callabo.ai/ko/developers, https://callabo.ai/en/developers/api/records, https://callabo.ai/blog/webhook-guide). **업로드 API는 문서에 없음** → 파일 투입은 앱/웹 UI. |
| 8 | 내보내기 | API JSON, 웹훅 JSON(`transcript`, `insight_markdown`). 공유 링크 생성 API 있음. txt/docx/srt 직접 출력은 확인 못 함. |
| 9 | 데이터 정책 | 보안 페이지: "서비스 운영에 필요한 최소 데이터만 수집·보관, 목적 종료 시 즉시 삭제", ISO/IEC 27001 인증(유효 2024-12-26~2027-12-25) [확인] (https://callabo.ai/ko/security). **학습 사용 여부·옵트아웃·보관 기간 수치는 확인 못 함.** Business 이상에 데이터 보존·자동 삭제 정책 기능. |
| 10 | 약관 자동화 | 공식 API/CLI/MCP/웹훅 제공. 약관 본문 직접 확인 못 함. |
| 11 | 공개 한국어 정확도 | 콜라보 단독 수치 확인 못 함. RTZR 벤치마크(§4)는 RTZR 엔진 수치. |

**판단 한 줄**: 실측 비교에 넣을 가치 **낮음~보통** — 회의 중심 제품이고 API가 조회 전용이라 이 파이프라인에는 맞지 않으며, 같은 회사의 RTZR API(§4)를 직접 쓰는 편이 단순하다. 단 요약/인사이트 품질을 UI로 비교해 볼 용도로만 무료 5시간 사용 가능.

### 6-2. 티로(Tiro, 플라톤)

| # | 항목 | 내용 |
|---|------|------|
| 1 | 한국어 STT | 지원(한국어 회의록 서비스, 대화 언어 자동 인식). STT 하청 공급사: Deepgram, AssemblyAI, ElevenLabs, NAVER Cloud Clova, Google STT 중 라우팅 [확인] (https://tiro.ooo/security FAQ). 즉 자체 엔진이 아니라 외부 STT 조합이며 어느 엔진이 쓰이는지는 사용자에게 고정되어 있지 않음 [해석]. |
| 2 | 화자 분리 | **Pro 플랜($13/월) 이상**, 무료 체험 중에도 사용 가능. 업로드 시 **[화자수 입력]** 칸으로 인원 지정, 모르면 자동 감지 [확인] (https://docs.tiro.ooo/ko/guide/recording/diarization). 최대 화자 수 확인 못 함. |
| 3 | 타임스탬프 | API `GET /v1/external/notes/{id}/paragraphs`(문단 단위). 단어 단위는 확인 못 함. |
| 4 | 요약·할 일 | 한 페이지 문서(요약), 템플릿 문서, 노트 기반 AI 채팅 [확인]. 구조화 할 일 필드는 확인 못 함. |
| 5 | 입력·길이 | 파일당 **최대 1GB, 5시간**, MP3 MP4 M4A AAC WAV FLAC OGG OPUS WebM MOV MP2 PCM, 한 번에 1개 업로드, Google Drive 링크 가능 [확인] (https://docs.tiro.ooo/ko/guide/recording/upload.md). 갤럭시 통화 녹음 자동 감지 변환 기능 있음 [확인]. |
| 6 | 무료·유료 | 신규 100분 + 온보딩 완료 시 최대 300분(체험), Lite $7/월 300분, **Pro $13/월 1,000분(화자 분리 포함)**, Max $29/월 무제한(노트당 5시간), 연결제 2개월 무료, 초과 분당 $0.025(종량), 한국어 환경은 원화 별도 표기 [확인] (https://docs.tiro.ooo/ko/guide/workspace/plans.md). |
| 7 | 접근·자동화 | **API·MCP·CLI 전 플랜 무료 제공**, 계정 API Key(플랜 제한 없음), 호출 한도 600회/60초 [확인] (https://docs.tiro.ooo/ko/guide/notes/api-mcp-cli, https://docs.tiro.ooo/en/developers/resources/usage-policy). 현재는 **노트 조회·검색용**이며 "앞으로 파일 업로드 API가 추가되면 과금될 수 있다"는 문구로 보아 업로드 API는 아직 없음 [확인+해석]. 업로드는 앱/웹. |
| 8 | 내보내기 | API/MCP JSON. 앱 내 내보내기 형식은 확인 못 함. |
| 9 | 데이터 정책 | **AI 학습·모델 개선·마케팅에 사용하지 않음**(개인정보처리방침·보안 페이지, 무료/유료/엔터프라이즈 공통). 음성은 처리 후 즉시 파기, 노트 삭제 시 즉시 하드 삭제 [확인] (https://tiro.ooo/ko/privacy-policy, https://tiro.ooo/security). 사용자가 원본 오디오 보관을 켜면 별도 키로 보관. 서버: AWS 서울. |
| 10 | 약관 자동화 | 공식 API/CLI 제공. 서비스 약관의 봇 조항은 확인 못 함. |
| 11 | 공개 한국어 정확도 | 독립 수치 확인 못 함. 티로 블로그의 "클로바노트 vs 다글로 vs 티로" 비교는 자사 글이라 근거로 쓰지 않음. |

**판단 한 줄**: 실측 비교에 넣을 가치 **낮음** — 자체 STT가 아니라 위탁 엔진 조합이라 "티로의 한국어 성능"이 곧 어떤 엔진이 라우팅됐느냐의 문제이고, 업로드 자동화도 불가. 이미 선정할 RTZR/CLOVA Speech 직접 호출과 겹친다(UI에서 요약 템플릿 품질을 보고 싶을 때만).

### 6-3. 이번에 제외한 것

- **비토(VITO) 앱**: 통화 녹음 문자 변환 앱(https://www.vito.ai/). 파일 업로드 회의록 용도·API(앱 자체)는 확인 못 함. API는 RTZR(§4) 그대로.
- **에이닷 노트(SKT)**: 검색 결과에 비교 대상으로만 등장(https://roaring90s.tistory.com/180 [2차]), 공식 페이지는 열람하지 않음 → 이번 조사 범위 밖.

---

## 7. 한국어 정확도 공개 근거 정리 (사실만)

| 출처 | 대상 | 결과 | 한계 |
|------|------|------|------|
| RTZR 운영 GitHub (https://github.com/rtzr/Awesome-Korean-Speech-Recognition, 마지막 커밋 2025-08-15, AI Hub 6개 세트 각 3,000문장 샘플) | 평균 CER: **RTZR 5.91 / RTZR Whisper 6.59 / Naver ClovaSpeech 7.52 / ETRI 10.19 / Azure 10.88 / AWS 11.11 / OpenAI Whisper 11.39 / Google v2 11.50 / Gemini 2.0 flash 16.58 / Deepgram nova-2 21.02** | 측정 주체가 RTZR(이해관계자). 다글로·삼성·클로바노트·콜라보·티로 미포함. 화자 분리 지표 없음. 구형 모델 버전일 수 있음. |
| MDPI Applied Sciences 2026-09-09 (https://doi.org/10.3390/app16188936) | 20개 한국어 즉흥 발표 녹음, CLOVA Speech 평균 CER 4.65%(최저). 5개 엔진 차이 통계적 비유의(p=0.219). 대본 있는 성우 녹음에서는 순위가 뒤집혀 Whisper 2.8% 최저 | 20개 발표 녹음, 회의 대화 아님. RTZR 미포함. |

화자 분리 정확도(DER)·한국어 다화자 회의 기준 공개 비교는 이번에 찾지 못함 → **실측 필요**.

---

## 8. 비교 요약 표

| 후보 | 한국어 화자분리 | 공개 API | 무료 한도 | 가격 | 자동화 경로 | 요약/할 일 |
|------|----------------|----------|-----------|------|-------------|------------|
| 삼성 텍스트 변환 어시스트 | 있음(최대 인원·지정 확인 못 함) | 없음 | 무제한(기본 무료) | 무료(향후 유료 가능 고지) | **불가에 가깝다**(UI 수동 공유) | 요약+실행 제안(캘린더·리마인더) |
| 클로바노트 개인용 | 있음(참석자 수 옵션, 최대 확인 못 함) | **없음** | 월 300분(+동의 시 300분) | 유료 없음 | 브라우저 자동화(**네이버 약관 위반 소지 큼**) | 요약+다음 할 일(한국어만) |
| 네이버웍스 클로바노트 | 기본 있음, 목소리 등록형은 Business 이상 | 조회 전용(Team 이상) | 체험 30일 | Lite 20,000 / Team 108,000 / Business 510,000원/월 | API 조회 + UI 업로드 | 요약 25~750회/월 |
| **CLOVA Speech (NCP)** | **최대 30명**(on/off만 요청 가능, 화자 수 지정 파라미터 없음) | **있음** | 월 20분 | 분당 20원(+화자 인식 시 28원 [2차]) VAT별도 | **API 완전 자동화** (콜백/OBS 필요) | 없음(STT만) |
| **RTZR STT API** | `spk_count` 지정, 최대 미명시 | **있음** | 600분(1회, 초기화 없음) | 시간당 1,000원(분당 ~16.7원) VAT별도 | **API 완전 자동화**(폴링) | 엔터프라이즈 계약 시만(요약) |
| 다글로 Developers | on/off만 문서화 | **있음** | 약 10시간분 포인트 | Async 분당 10원(정가 20원 표기, 해석 [추정]) VAT별도 | **API 자동화**(로컬 업로드 방식 확인 못 함) | 회의록 요약 API 호출당 90원 |
| 다글로 웹 | 화자표시 토글 | 없음(웹용) | 월 4시간+4시간 | Pro 14,900 / Premium 24,900원/월 | 브라우저 자동화 | 템플릿 요약·6항목 정리 |
| 콜라보(Callabo) | 실시간 화자 구분은 Business~ | 조회 전용(Beta) | 5시간 | 시트 20,000원/월, 초과 시간당 1,000~2,000원 | API 조회 + UI 업로드 | 인사이트·템플릿 |
| 티로 | Pro부터, 화자수 입력 | 조회 전용 | 체험 100~300분 | $7 / $13 / $29 월 | API 조회 + UI 업로드 | 한 페이지 문서·템플릿 |

---

## 9. 실측 비교에 넣을 가치 — 최종 판단

1. **RTZR STT API — 넣는다(필수).** 600분 무료, `spk_count` 지정, 단어 타임스탬프, 폴링 API. 요약은 별도 LLM으로.
2. **CLOVA Speech (NCP) — 넣는다(필수).** 월 20분 무료 한도가 작아 시험용으론 짧으니 실측 전 결제수단 등록 + 요금 계산기 재확인(화자 인식 요금 1차 미확정). 30명 화자, 단어 타임스탬프, srt.
3. **다글로 Developers API — 넣는다(조건부).** 로컬 파일 업로드 방식과 화자 수 지정 파라미터를 먼저 문의/확인. 정확도 근거가 자체 주장뿐이라 실측 가치가 큼.
4. **삼성 텍스트 변환 어시스트 — 넣는다(수동 기준선).** 자동화 불가, 폰에서 직접 변환해 텍스트만 가져와 비교. 인터뷰 모드 녹음은 제외.
5. **클로바노트 개인용 — 넣는다(수동 1~2건만).** 자동화 후보에서는 제외. 업로드는 사람이 직접.
6. 콜라보·티로·네이버웍스 클로바노트 — **보류.** 각각 API가 조회 전용이거나 엔진 위탁이라 이 파이프라인과 맞지 않음. 요약 UX 참고가 필요할 때만 무료 체험.

## 10. 이 조사에서 확인하지 못한 것 (후속 확인 필요)

- CLOVA Speech 화자 인식 추가 요금의 1차 확인(NCP 요금 계산기 — 요금 표의 숫자 셀이 페이지에서 렌더링되지 않음), 응답 `speakerCountMin/Max`의 의미(요청에서 지정할 수 없는데 응답에 나타나는 이유), 입력 음성 학습 사용 여부.
- RTZR의 화자 분리 최대 인원, 입력 오디오 학습 사용 여부, API 약관 전문.
- 다글로 API: 로컬 파일 업로드 방식, 화자 수 지정, 요약 API 출력 스키마, 학습 사용 여부.
- 삼성: 처리 위치(온디바이스/서버), 최대 화자 수, 변환 결과 파일의 저장 위치 존재 여부, 학습·보관 정책 원문.
- 클로바노트: 다운로드 파일 형식 정식 목록(공식 페이지 미확인), 최대 화자 수, 개인용이 CLOVA Speech와 같은 엔진인지.
- 화자 분리 정확도(DER)와 한국어 다화자 회의 CER에 대한 제3자 공개 비교.
