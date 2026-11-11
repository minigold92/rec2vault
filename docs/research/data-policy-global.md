# 글로벌 STT·AI 서비스 데이터 처리 조사 (회사 정보가 섞인 한국어 녹음 기준)

- 확인일: **2026-11-09** (아래 모든 URL을 이 날 직접 열어 읽음. 페이지에 갱신일이 보이면 옆에 적음)
- 선행 조사: `docs/research/global-stt.md`(9번 데이터 정책 항목)를 먼저 읽고, 거기서 "확인 못 함"이던 곳을 채우고 이미 맞는 내용은 출처만 다시 확인함. 정정·보강된 곳은 맨 끝 §9.
- 표기: **[확인]** = 약관·방침·도움말 원문에서 직접 읽음 / **[해석]** = 원문을 내가 풀어 쓴 것 / **[추정]** = 원문에 없고 내가 추론 / **[2차]** = 블로그·서드파티 / **확인 못 함** = 찾지 못함 또는 열람 불가.
- 법률 판단은 하지 않음. 조항 인용 + 짧은 풀이만 함.
- 등급 기준(요청문 그대로): **A** 녹음이 기기·자체 서버 밖으로 안 나감 / **B** 외부 처리지만 학습 미사용이 기본(또는 확실한 옵트아웃)이고, 보관이 짧거나 사용자 통제 가능, 사람 검토 없음(오남용 예외는 명시) / **C** 기본값이 학습 사용이거나, 사람 검토가 있거나, 장기 보관, 또는 핵심 항목이 확인 불가.
  - **B(잠정)** = 이 문서에서만 쓰는 표기. B 요건은 충족하지만 ① 설정에 의존하거나 ② 옵트아웃이 소급 적용되지 않거나 ③ 인증 범위·사람 검토 같은 항목 하나가 확인 안 된 경우. 회사 정보가 든 녹음에는 [해석] 확인 전까지 C로 취급하는 편이 안전.

---

## 0. 먼저 읽을 핵심

1. **개인 구독 앱(ChatGPT Plus/Pro, Gemini Free/AI Pro)은 기본값이 학습 사용 + 사람 검토 가능.** 둘 다 설정으로 끌 수 있지만 **과거 데이터에는 소급 안 됨**(Gemini는 이미 사람이 검토한 대화를 삭제해도 최대 3년 보관). 개인 구독 안에서 "비즈니스 수준 보호"를 통째로 켜는 스위치는 없음 — 비즈니스 수준은 별도 상품(ChatGPT Business 최소 2좌석, Google Workspace 계정)으로만 제공.
2. **API 경로가 약관상 가장 깨끗함.** OpenAI `/v1/audio/transcriptions`는 표에서 학습 No / 오남용 로그 None / 앱 상태 None / ZDR 적격 Yes. Gemini API는 **유료(결제 연결) 프로젝트만** 학습 미사용이고 오남용 로그가 55일 남음. **Gemini API 무료 티어는 입력·출력이 개선에 쓰이고 사람이 읽을 수 있으며 "민감·기밀·개인 정보를 넣지 말라"고 명시**(한국은 EEA 예외 대상 아님).
3. **ElevenLabs는 기본값이 학습 사용 + 영구·취소불가 콘텐츠 라이선스(약관 §4(d))**이고, Zero Retention Mode는 **엔터프라이즈 전용**·웹 UI는 대상 아님. 계정 설정 토글(Data use)로 끌 수 있으나 **소급 안 됨**. 무료 플랜은 **비상업 용도만** 허용 → 회사 정보 녹음이면 유료 플랜 전제.
4. **국외 이전은 사실상 전부.** OpenAI 개인용: 한국 이용자 개인정보는 미국 서버 보관(한국 부록). Google: 전 세계 서버. ElevenLabs: "어디에 살든 미국으로 이전해 저장". Cloud STT Chirp 3·Vertex Gemini 3.5 Transcribe는 처리 리전이 US/EU 멀티리전뿐(한국 없음). OpenAI API 한국 리전은 **저장만**(처리는 US/EU) + 영업 승인 필요.
5. **법적 보존 명령 이력**: OpenAI는 2025-06~09 NYT 소송 보존 명령으로 Free/Plus/Pro/Team·API(ZDR 제외)의 삭제된 대화까지 보존해야 했음(2025-09-26 종료). 2025-04~09 데이터 일부는 지금도 별도 보관 중. 즉 "삭제 → 30일 내 삭제"가 소송 변수로 깨진 선례가 있음.
6. **로컬(pyannote community-1)은 녹음이 나가지 않음(A).** 단 기본값으로 텔레메트리(파일 길이·화자 수 등)가 `otel.pyannote.ai`로 나감 — 끄는 법 §7.
7. **회사 정보 녹음에서 별개로 확인할 조항**: (a) OpenAI 이용약관 "Corporate domains" — 회사 이메일로 만든 개인 계정은 조직 계정으로 편입되어 **관리자가 Content에 접근** 가능. (b) ElevenLabs STT 약관 §3.1 — 녹음 대상자에 대한 고지·동의는 이용자 책임. (c) Google·OpenAI 모두 "녹음 대상 동의" 문구 있음(§1·§2 출처).

---

## 1. ChatGPT 개인 구독 (Free / Go / Plus / Pro) — 오디오 업로드는 유료 플랜 한정

| # | 항목 | 내용 | 구분 | 출처 |
|---|---|---|---|---|
| 1 | 학습·개선 사용 | 개인용(Free/Plus/Pro)은 콘텐츠를 모델 학습에 쓸 수 있음. 개인 워크스페이스는 **기본 활성화**. 옵트아웃: ChatGPT **Settings > Data controls > "Improve the model for everyone" 끄기** 또는 Privacy Portal "Do not train on my content"(둘 중 하나면 충분). 옵트아웃 후 **"새 대화"는 학습에 쓰지 않음**. 과거 대화 소급 여부는 문구 없음 → **확인 못 함**. 예외: 👍/👎 피드백을 누르면 **그 대화 전체가 학습에 쓰일 수 있음**(옵트아웃해도). 삭제 시 "이미 비식별화·계정 분리된 데이터"는 삭제 대상에서 빠짐. 학습 전 개인정보 축소 조치를 한다고 함. 음성 모드·Codex는 별도 설정. | [확인] | O1, O3, O6 §4 |
| 1-1 | 임시 채팅 | 임시 채팅은 임시인 동안 학습에 안 쓰임(개인화 선택과 무관). **저장하면 일반 채팅이 되어 계정 설정을 따름.** 임시 채팅 중 업로드한 파일도 저장 시 Library/Space에 저장될 수 있음. | [확인] | O1, O2 |
| 1-2 | 오디오 업로드 / Record | **업로드 오디오(일반 채팅)**: 학습·보관이 위 일반 채팅 규칙을 따른다는 문구는 있으나 오디오 전용 보관 규정은 **확인 못 함**. **Record 모드(macOS 앱)**: 오디오는 전사 목적에만 쓰고 전사 후 삭제, 학습 미사용. 단 **전사문·canvas는 토글이 켜져 있으면 학습에 쓰일 수 있고 "학습용으로 쓸 때 팀이 전사문을 검토해야 할 수 있음"**. | [확인] | O9, O10 |
| 2 | 사람 검토 | 소수의 승인된 OpenAI 직원과 비밀유지 의무가 있는 **서비스 제공자**가 접근: ① 오남용·보안 사고 조사 ② 이용자가 문의했을 때 지원 ③ 법적 사안 ④ **모델 성능 개선(옵트아웃 전까지)**. "듣고 싶지 않은 민감 정보는 넣지 말라"고 명시. 접근은 기록·교육을 전제. 안전 목적의 제한적 맥락 사용은 메모리·개인화를 꺼도 유지됨. | [확인] | O5, O2 |
| 3 | 보관 기간 | 일반·보관(archived) 채팅: 사용자가 삭제할 때까지. **삭제 시 화면에서 즉시 제거, OpenAI 시스템에서는 30일 내 영구 삭제 예약**(단 이미 비식별화됐거나 보안·법적 의무가 있으면 예외). **임시 채팅: 안전 목적으로 최대 30일 사본 보관 가능.** Library/Space에 저장된 파일은 대화 삭제와 별개로 남음(따로 삭제). GPT 지식 파일은 GPT 삭제 때까지, 프로젝트 파일은 프로젝트·파일 삭제 때까지. 삭제 복구 불가. | [확인] | O4, O2, O10 |
| 3-1 | 법적 보존 | 개인정보 처리방침: 합법적 소환장 등 법적 의무가 있으면 그 기간 보유. **NYT 소송 보존 명령**: Free/Plus/Pro/Team·API(ZDR 제외)가 대상이었고 **2025-09-26 종료**(2025-10-22 갱신 공지). 단 **2025-04~09 사용자 데이터 일부는 별도 보관 중**(법무·보안 소수만 접근, 법적 의무 외 사용 불가). 2026-11-09 현재 유효한 새 보존 명령 여부는 **확인 못 함**(위 공지가 가장 최근 확인본). | [확인]/확인 못 함 | O11, O6 §4 |
| 4 | 처리·저장 위치 / 위탁사 | 콘텐츠는 OpenAI와 서비스 제공자 시스템에 **미국 및 전 세계**에 저장, 데이터 주석·안전 목적으로 일부를 제공자에게 보낼 수 있음. **한국 이용자: 개인정보는 별도 표시 없으면 미국 서버에 보관, 국외 수탁자 목록 공개**(인증 Auth0·Twilio·Arkose·Ekata, 지원 General Agent(한국)·Intercom·Transcend·TaskUs(미국·필리핀), 결제 Stripe·RevenueCat, 호스팅·IT Microsoft·Snowflake·Cloudflare·Fivetran·Mixpanel·Atlassian·Mode·Confluent·Google·Airbyte·Datadog, 이메일 Mailchimp·HubSpot, 설문 Qualtrics). 국외 이전 거부 시 서비스 이용 불가라고 명시. 국내대리인: OpenAI Korea. | [확인] | O5, O7 |
| 5 | 제3자 제공·광고 | 채팅 내용을 광고주와 공유하지 않고 마케팅·광고 목적으로 공유하지 않으며 데이터를 판매하지 않는다고 명시(일부 지역 광고 기능에 별도 설정 존재). 계열사·정부기관(법적 요구)·사업 양도 시 제공 가능. **이용약관 "Corporate domains": 회사 이메일 계정은 조직의 비즈니스 계정에 편입될 수 있고 관리자가 Content에 접근 가능.** | [확인] | O5, O6 §3, O8 |
| 6 | 개인 vs 비즈니스 | §1-B 참고. **개인 구독 안에서 켤 수 있는 최선 = 학습 옵트아웃 + 임시 채팅 + 개인 이메일 사용**이며 이래도 30일 안전 사본·지원/오남용 목적 사람 접근은 남음. | [확인]/[해석] | O1, O2, O5 |
| 7 | API ZDR | 해당 없음(앱). API는 §4. | — | — |
| 8 | 인증 | OpenAI 제품 컴플라이언스 표에 **ChatGPT Business(SOC 2 Type 2만)·Enterprise·Edu·API Platform 등은 있으나 개인용 Plus/Pro는 목록에 없음.** | [확인] | O15 |
| 9 | 판정 | **C(기본값 학습 사용 + 사람 접근 사유에 모델 개선 포함).** 옵트아웃+임시 채팅 시 **B(잠정)**: 학습 제외는 새 대화만, 30일 사본·법적 보존 선례, 인증 범위 밖. | | |

### 1-B. ChatGPT Business / Enterprise와의 차이

| 항목 | 개인(Plus/Pro) | Business | Enterprise | 출처 |
|---|---|---|---|---|
| 학습 | 기본 사용(옵트아웃 가능) | **기본 미사용**(별도 계약 없으면 학습 불가, 피드백 👍/👎도 학습 허용 안 됨) | 기본 미사용 | O1, O12 |
| 사람 접근 | 지원·오남용·법적·(개선) | 승인 직원(엔지니어링 지원·오남용·법적) + **비밀유지 의무가 있는 외주 계약자가 오남용 검토 목적에 한해** 접근. 워크스페이스 관리자는 대화 열람·내보내기·삭제 가능 | 직원은 사고 해결·사용자 동의 복구·법적 요구 시만. 관리자는 Compliance API | O12 |
| 보관 | 삭제 후 30일, 임시 30일 | 관리자가 보관 기간 설정, 삭제·미저장 대화 30일 내 삭제(법·위해 방지 필요 시 예외) | 관리자가 설정, 삭제 30일 내 삭제 | O12 |
| 인증 | 목록 없음 | SOC 2 Type 2 | SOC 2 Type 2 + ISO 27001·27701 | O15 |
| 법적 보존(2025 명령) | 대상 | Team(현 Business) 대상 | **제외** | O11 |
| 가입 | — | **셀프서브, 유료 좌석 최소 2개**(Standard $20/월 연간·$25 월간). 기존 개인 구독·데이터는 자동 이전·해지 안 됨(개인 워크스페이스와 별개) | 영업 | O13, O14 |
| ZDR·BAA | — | **셀프서브 Business에는 없음**(계약형 상품 필요) | 계약 | O13 |

→ **개인 구독으로 Business 수준 보호를 "켤" 방법은 없음.** Business 워크스페이스를 따로 사야 함(최소 2좌석). [해석]

### 출처 (ChatGPT)
- O1 https://help.openai.com/en/articles/5722486-how-your-data-is-used-to-improve-model-performance (도움말 표기 "Updated: 20 days ago")
- O2 https://help.openai.com/en/articles/8914046-temporary-chat-in-chatgpt ("8 days ago")
- O3 https://help.openai.com/en/articles/7730893-data-controls-in-chatgpt ("3 days ago")
- O4 https://help.openai.com/en/articles/8983778-chat-and-file-retention-in-chatgpt ("5 days ago")
- O5 https://help.openai.com/en/articles/7039943-how-openai-handles-data-in-consumer-services ("20 days ago")
- O6 https://openai.com/policies/row-privacy-policy/ (Updated Feb 6, 2026)
- O7 https://openai.com/ko-KR/policies/kr-privacy-policy-addendum/ (업데이트 2026-03-27)
- O8 https://openai.com/policies/row-terms-of-use/ (Effective Jan 1, 2026)
- O9 https://help.openai.com/en/articles/11487532-chatgpt-record ("11 days ago")
- O10 https://help.openai.com/en/articles/8555545-uploading-files-and-audio-to-chatgpt ("3 hours ago")
- O11 https://openai.com/index/response-to-nyt-data-demands/ (원문 2025-06-05, 갱신 2025-10-22)
- O12 https://openai.com/enterprise-privacy/ (Updated Jan 8, 2026)
- O13 https://help.openai.com/en/articles/8792828-chatgpt-business-overview
- O14 https://help.openai.com/en/articles/8980713-sign-up-for-chatgpt-business
- O15 https://openai.com/product-compliance-status/ (v1.1, 2026-08-04)

---

## 2. Gemini 앱 개인 구독 (Free / Google AI Plus / Pro / Ultra)

Gemini Apps 개인정보 고지는 **개인 계정(로그인 상태)** 대상이며, 업무·학교 계정은 다른 조건(Workspace 허브)이 적용된다고 명시. 구독 등급(Pro 등)에 따른 데이터 처리 차이는 이 허브에 **없음**(구독 정보는 수집 항목으로만 언급). [확인]

| # | 항목 | 내용 | 구분 | 출처 |
|---|---|---|---|---|
| 1 | 학습·개선 사용 | **Keep Activity(Gemini Apps Activity) ON이 기본**: 활동을 "생성형 AI 모델 학습 포함" 서비스 개발·개선에 사용. **업로드(파일)도 활동에 저장**되는 항목으로 명시. 옵트아웃 = **Gemini Apps Activity에서 Keep Activity 끄기**(myactivity.google.com/product/gemini): "앞으로의 채팅"은 피드백을 보내지 않는 한 학습에 안 씀. **소급 안 됨**(이미 검토된 대화는 계속 보관). 피드백 제출 시 최근 24시간 대화와 포함 콘텐츠(업로드 포함)를 수집·검토. **임시 채팅**: 학습 미사용. 오디오·Live 영상은 별도 토글, **기본 학습 미사용**. 업로드한 오디오 파일을 "오디오" 토글이 아닌 Keep Activity가 지배하는지는 문구가 "업로드는 Keep Activity" 쪽이므로 [해석] Keep Activity를 따름. | [확인]/[해석] | G1 |
| 2 | 사람 검토 | "대화 일부를 **사람 검토자(서비스 제공자 소속 포함)** 가 검토" — 품질 평가·안전·약관 위반 대응. "**기밀 정보를 넣지 말라**"고 명시. 계정과 분리해 제공자에게 보냄. **Keep Activity를 꺼도·임시 채팅이어도** 응답 제공·"Google·이용자·대중 보호" 목적으로 사람 검토자 도움을 받을 수 있다고 명시. | [확인] | G1 |
| 3 | 보관 기간 | Keep Activity ON: 기본 **18개월 자동 삭제**(3·36개월·무기한 선택 가능), 수동 삭제 가능. OFF·임시 채팅: **계정에 72시간 보관**(응답 맥락 24시간 + 시스템 장애 대비 72시간). **사람이 검토한 대화(와 언어·기기·위치·피드백)는 활동을 삭제해도 지워지지 않고 계정과 분리된 채 최대 3년 보관.** 일부는 계정 삭제 시까지·법적 사유로 더 길게. | [확인] | G1 |
| 4 | 위치·위탁사 | Google 개인정보처리방침: "전 세계에 서버를 두며 거주 국가 밖에서 처리될 수 있음". 한국 소비자는 Korean Location Terms 추가 적용. 사람 검토를 맡는 서비스 제공자 목록·국가: **확인 못 함**. | [확인]/확인 못 함 | G16, G1 |
| 5 | 제3자·광고 | **채팅을 광고 표시에 쓰지 않음("바뀌면 명확히 알리겠다")**, 개인 정보를 판매하지 않음. 연결 앱(Connected Apps)·서드파티는 각자 정책. | [확인] | G1 |
| 6 | Workspace 대비 | 아래 표 | | G7 |
| 7 | API ZDR | 해당 없음. | — | — |
| 8 | 인증 | 소비자용 Gemini 앱 범위의 SOC/ISO 문구는 **확인 못 함**(인증 문구는 Workspace 허브에만 있음). | 확인 못 함 | G7 |
| 9 | 판정 | **C(기본 Keep Activity 학습 사용 + 사람 검토 + 검토본 3년 보관).** Keep Activity 끔 + 임시 채팅 + 피드백 미제출 시 **B(잠정)**: 72시간 보관·사람 검토는 안전 목적으로 남음·소급 불가·소비자 인증 확인 못 함. | | |

### 2-B. Google Workspace의 Gemini와의 차이

| 항목 | 개인 Gemini 앱 | Workspace(적격 에디션) | 출처 |
|---|---|---|---|
| 학습 | Keep Activity ON이면 사용 | **고객 사전 허가 없이 생성형 모델 학습에 사용 안 함**(Service Specific Terms "Training Restriction") | G7 |
| 사람 검토 | 대화 일부 검토 | "도메인 밖에서는 **사람이 검토하지 않으며** 학습에 쓰이지 않음" | G7 |
| 보관 | 18개월 기본(조정) / 72시간 / 검토본 3년 | Gemini 앱 대화 **관리자가 3·18·36개월 중 설정(기본 18개월, 최대 36개월)**, 기록 끔이면 72시간. 피드백 데이터 최대 18개월 | G7 |
| 계약 | 소비자 약관 | Cloud Data Processing Addendum | G7 |
| 인증 | 확인 못 함 | SOC 1/2/3, ISO 9001·27001·27701·27017·27018·42001, FedRAMP High(Gemini 앱·Workspace 앱). Gemini Notebook·Chrome의 Gemini는 ISO/SOC 미지원 | G7 |
| 가입 | Google One 개인 플랜(Gemini 업그레이드는 "개인 계정용 Google One 유료 플랜의 일부") | 업무·학교 계정(조직 도메인) 필요 — **최소 좌석·가격은 이 조사에서 확인 못 함** | G17(검색 결과 발췌만 확인), G7 |

→ **개인 Google AI Pro 구독으로 Workspace 수준 보호를 켤 방법은 없음.** 보호를 높이는 개인 설정은 Keep Activity 끄기·임시 채팅·피드백 미제출뿐. [해석]

### 출처 (Gemini 앱)
- G1 https://support.google.com/gemini/answer/13594961 (Gemini Apps Privacy Hub, Last updated Oct 26, 2026 / Privacy Notice Oct 13, 2026)
- G7 https://knowledge.workspace.google.com/admin/generative-ai/generative-ai-in-google-workspace-privacy-hub (Last updated Oct 6, 2026; support.google.com/a/answer/15706919가 여기로 연결됨)
- G16 https://policies.google.com/privacy ("Data transfers" 절)
- G17 https://support.google.com/gemini/answer/16275805 — 검색 결과 발췌문만 확인, 페이지 본문은 열지 않음

---

## 3. Gemini API · Vertex(Gemini Enterprise Agent Platform) · Cloud Speech-to-Text v2

### 3-A. Gemini API (`gemini-3.5-transcribe`, `gemini-3.8-flash` 등 공통)

| # | 항목 | 내용 | 구분 | 출처 |
|---|---|---|---|---|
| 1 | 학습·개선 사용 | **무료(Unpaid) 서비스**(AI Studio 직접 사용·무료 쿼터): 입력·출력(프롬프트·시스템 지시·캐시·이미지/영상/문서 파일 포함)을 Google 제품 개선·ML 기술 개발에 사용, "**민감·기밀·개인 정보를 무료 서비스에 넣지 말라**". **유료(결제 계정 연결된 Cloud 프로젝트의 API 호출)**: 프롬프트·응답을 제품 개선에 **쓰지 않음**. 결제가 연결되면 AI Studio 접근도 Paid. **EEA·스위스·영국은 무료 쿼터도 Paid 조건 적용 — 한국은 이 예외에 없음**([해석]). 선택 사항: 로그를 **데이터셋으로 공유(옵트인)**하거나 **Contributor Tier(초대제 프리뷰, 토큰 최대 50% 할인)** 에 들면 무료 서비스 조건으로 학습에 쓰임 → 기본값 아님. | [확인] | G2, G4 |
| 2 | 사람 검토 | **무료**: "품질 개선을 위해 사람 검토자가 API 입력·출력을 읽고 주석 달 수 있음(계정·키·프로젝트와 분리 후)". **유료**: 오남용 탐지로 플래그된 프롬프트·출력을 **승인된 Google 직원이 내부 플랫폼에서 검토**(정책 집행 목적, 모델 학습 불가). 정상 호출에서 전부를 사람이 보는 구조는 아님. | [확인] | G2, G3 |
| 3 | 보관 기간 | 유료: **프롬프트·맥락·출력을 오남용 탐지·법적 공개 목적으로 55일 보관**(끌 수 있는 설정은 문서에 없음). **새 기본값**: 프로젝트 소유자용 **API 로그가 기본 ON**(Interactions API 전부, Generate Content는 **2026-10-26 이후 생성 프로젝트**) — 프로젝트 내부 전용, 기본 최대 **55일**(7·14·28·55일 선택), AI Studio "Logs and Datasets"에서 끌 수 있음. **Files API로 올린 파일은 48시간 후 자동 삭제**(수동 삭제 가능, 업로드한 파일은 다운로드 불가). | [확인] | G3, G4, G5 |
| 4 | 위치·위탁사 | 유료 데이터는 **"Google 또는 대리인이 시설을 둔 어느 국가에서든 일시 저장·캐시될 수 있음"**. 리전 선택·한국 처리 옵션: **확인 못 함**(문서에 없음). 서비스 가능 지역은 `available-regions` 문서(미열람). 위탁사 목록: **확인 못 함**. | [확인]/확인 못 함 | G2 |
| 5 | 제3자·광고 | 유료는 "Data Processing Addendum for Products Where Google is a Data Processor" 적용(Google = 처리자). 계정·결제·사용량·IP 등 기타 데이터는 Controller-Controller 조건과 Google 개인정보처리방침 적용. 광고 사용 언급 **확인 못 함**. | [확인] | G2 |
| 6 | 개인 vs 비즈니스 | 약관 문구: "AI Studio·Gemini API는 **전문·비즈니스 목적 개발자용이며 소비자용 아님**". | [확인] | G2 |
| 7 | ZDR | Gemini API(AI Studio 경로)의 **ZDR·로그 미보관 옵션은 문서에서 못 찾음 → 확인 못 함.** (ZDR 문서는 Vertex 경로에만 있음 → 3-B.) | 확인 못 함 | G3 |
| 8 | 인증 | Google Cloud ISO 27001 서비스 목록에서 **"Gemini API/AI Studio"는 검색되지 않음**(Vertex=Gemini Enterprise Agent Platform·Speech-to-Text는 있음). | 확인 못 함 | G15 |
| 9 | 판정 | **무료 티어: C**(학습 + 사람 검토 + "민감 정보 금지" 명시). **유료 티어: B** — 학습 미사용(약관 명시), 사람 검토는 오남용 플래그분만(명시), 보관 55일(끌 수 없음)·국가 불특정이 감점 요인. | | |

### 3-B. Vertex 경유 = Gemini Enterprise Agent Platform(구 Vertex AI) — `gemini-3.5-transcribe`

| # | 항목 | 내용 | 구분 | 출처 |
|---|---|---|---|---|
| 1 | 학습 | Cloud Service Specific Terms **Training Restriction**: "고객 허락 없이 고객 데이터로 AI/ML 모델을 학습·파인튜닝하지 않음"(GA·프리 GA 포함). | [확인] | G10, G13 |
| 2 | 사람 검토·오남용 로그 | Google 모델: 분류기가 의심 활동을 탐지하면 **프롬프트를 오남용 검토 목적으로 로깅·사람 검토 가능, 최대 90일, 고객이 고른 리전/멀티리전 안에 저장, 학습 불가**. **단 Google Cloud 온라인 약관(자가결제) 고객만 해당 — Cloud Master Agreement(CMA) 고객은 기본 제외.** 이 페이지가 3.5 Transcribe에 어느 등급을 적용하는지는 모델 문서에 명시 안 됨 → **확인 못 함**(Frontier·Advanced AI 지정 대상 아님으로 [추정]). | [확인]/[추정] | G12 |
| 3 | 보관·ZDR | ZDR 달성하려면: Gemini 기본 **암묵 캐시**(메모리 + 내구성 저장, 최대 24시간 후 삭제)를 프로젝트 단위로 끄기(전체 캐시 OFF 가능), Grounding with Google Search(3일 로그)/Maps(30일) 미사용, Request-response logging(기본 OFF) 유지, Interactions API는 `store=false`. | [확인] | G13 |
| 4 | 위치 | `gemini-3.5-transcribe`는 **global / us / eu** 엔드포인트, **ML 처리 데이터 위치: US·EU 멀티리전**(한국 없음). 데이터 저장 위치는 Cloud 약관 AI/ML Data Location 조항으로 멀티리전 지정 가능("고객 데이터" 저장·ML 처리를 그 멀티리전에서만). **Batch·프로비저닝 처리량 미지원.** | [확인] | G14, G10, G11 |
| 9 | 판정 | **B**(조건: us/eu 멀티리전 엔드포인트 사용 + 캐시 설정 + 필요 시 CMA). 자가결제(온라인 약관)면 오남용 플래그분의 사람 검토 90일이 남음. | | |

### 3-C. Google Cloud Speech-to-Text v2 (Chirp 3, `ko-KR` 화자 분리 GA)

| # | 항목 | 내용 | 구분 | 출처 |
|---|---|---|---|---|
| 1 | 학습 | **기본값: 고객 오디오·전사를 로깅하지 않음.** 선택 "data logging" 프로그램에 가입한 **프로젝트에 한해** Google이 개선에 사용하고 할인. 가입해도 데이터 소유는 고객, 모델 소유는 Google. 기본 Training Restriction도 적용. (이 문서는 v1 경로로 연결되어 읽힘 → v2 별도 문서는 **확인 못 함**, 같은 프로그램으로 [추정].) | [확인] | G8, G10 |
| 2 | 사람 검토 | data logging 가입 시 "제한된 승인 직원·계약자"만 접근. 기본값에서는 로깅이 없어 검토할 데이터가 없음([해석]). Chirp 3에 위 오남용 프롬프트 로깅이 적용되는지는 **확인 못 함**(오남용 문서는 "Generative AI Services" 대상). | [확인]/확인 못 함 | G8, G12 |
| 3 | 보관 | 가입 프로젝트의 로그 데이터는 **프로젝트를 삭제해도 지워지지 않음 → 삭제 요청 양식 필요**. 기본값 요청 처리 중 임시 보관 기간: **확인 못 함**. BatchRecognize는 오디오·결과가 사용자 GCS에 있음(사용자 통제). | [확인] | G8, G9 |
| 4 | 위치 | Chirp 3 GA 리전은 **`us`·`eu` 멀티리전**뿐(오디오가 미국·EU로 전송). Cloud STT는 약관 "AI/ML Data Location" 적용 서비스 목록에 있음 → 멀티리전 고정 가능. | [확인] | G9, G11 |
| 8 | 인증 | Google Cloud ISMS ISO/IEC 27001 서비스 목록에 **Speech-to-Text 포함**(인증서는 Compliance Reports Manager에서 요청). | [확인] | G15 |
| 9 | 판정 | **B**(기본 로깅 없음·학습 없음·사용자 GCS 통제). 감점: 한국 리전 없음, 오남용 로그 적용 범위 확인 못 함. | | |

### 출처 (Google Cloud·API)
- G2 https://ai.google.dev/gemini-api/terms (읽은 사본: https://aistudio.google.com/docs/terms, Effective March 23, 2026)
- G3 https://ai.google.dev/gemini-api/docs/usage-policies ("Abuse monitoring", 읽은 사본 aistudio.google.com/docs/usage-policies.md)
- G4 https://ai.google.dev/gemini-api/docs/logs-policy ("Data logging and sharing")
- G5 https://ai.google.dev/gemini-api/docs/files
- G8 https://docs.cloud.google.com/speech-to-text/docs/data-logging (v1/data-logging로 연결)
- G9 https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3
- G10 https://cloud.google.com/terms/service-terms (§16 AI/ML Data Location, §18 Training Restriction)
- G11 https://cloud.google.com/terms/data-residency (Last modified September 8, 2026)
- G12 https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/abuse-monitoring
- G13 https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/zero-data-retention (data-governance URL이 이 페이지로 연결됨)
- G14 https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-transcribe
- G15 https://cloud.google.com/security/compliance/iso-27001

---

## 4. OpenAI API — `gpt-transcribe`(및 `gpt-4o-transcribe-diarize`)

| # | 항목 | 내용 | 구분 | 출처 |
|---|---|---|---|---|
| 1 | 학습 | **2023-03-01 이후 API로 보낸 데이터는 학습·개선에 쓰지 않음**(명시적으로 공유 옵트인하지 않는 한). 조직 소유자가 켜는 피드백/Playground 공유만 예외. 엔드포인트 표: `/v1/audio/transcriptions` 학습 **No**. | [확인] | O18, O1 |
| 2 | 사람 검토 | 일반 API 데이터: 승인된 직원(엔지니어링 지원·오남용·법적)과 **비밀유지 의무 외주 계약자가 오남용 검토 목적**으로 접근. 위탁사로 TaskUs(필리핀)·Accenture(미국·캐나다·필리핀)가 "API·Business: 콘텐츠 모더레이션"(플래그된 샘플만, 검토 기간 동안만 보관). **ZDR 사용 시 Snowflake·Cinder는 제외 표기.** 전사 엔드포인트는 오남용 로그 보관이 None이라 검토할 로그가 남지 않음([해석]). | [확인]/[해석] | O12, O17, O18 |
| 3 | 보관 | **`/v1/audio/transcriptions`: 오남용 모니터링 보관 None · 앱 상태 보관 None · ZDR 적격 Yes.** (비교: chat completions·responses는 오남용 로그 30일, assistants·threads·files는 삭제 시까지.) 법적으로 필요하면 예외("unless legally required"). NYT 보존 명령은 ZDR 엔드포인트는 영향 없었고 2025-09-26 종료. 저장이 없으면 보존할 대상도 없음([해석]). | [확인]/[해석] | O18, O11 |
| 4 | 위치·위탁사 | 기본은 전 세계. **데이터 레지던시**(프로젝트별, 영업 승인): `/v1/audio/transcriptions`는 **저장 리전은 한국(`kr.api.openai.com`) 포함 전체 지원, 처리(추론) 리전은 미국·EU만.** **한국 등 비US 리전은 오남용 통제 승인(MAM/ZDR 등) + Modified Retention 수정 계약 필요, 신모델 10% 추가 요금.** "시스템 데이터"(계정·메타·사용량 등)는 리전 밖 처리 가능. 위탁사: Microsoft(한국 포함 다수 국가)·CoreWeave·Oracle·Google Cloud·AWS·Cerebras·Cloudflare·Snowflake·TaskUs·Salesforce·Accenture 등(목록 2026-10-14). 전사는 저장이 없으므로 저장 리전 한국 지정의 실익은 작음([해석]). | [확인]/[해석] | O18, O17 |
| 5 | 제3자 | "입력·출력 권리는 서비스 제공·법 준수·정책 집행에 필요한 범위만 받는다". DPA는 폼으로 체결 가능. Business Terms 본문 자체는 **확인 못 함**(미열람). | [확인] | O12 |
| 6 | 개인 vs 비즈니스 | API는 ChatGPT 구독과 과금·약관이 별개(§1-B). API는 처음부터 "비즈니스 데이터" 취급. | [확인] | O12, O13 |
| 7 | ZDR | **승인 필요**(영업 문의, 추가 요건 수락). 조직·프로젝트 단위 설정(Settings → Organization → Data controls → Data retention). ZDR은 `store`를 항상 false로 취급. **Modified Abuse Monitoring**(콘텐츠를 오남용 로그에서 제외, 앱 상태는 일부 유지)와 선택. OpenAI는 특정 모델을 ZDR에서 제외할 수 있고(사전 서면 통지), 이때는 암호화 오남용 로그를 두고 **법적 요구 외 사람 검토 제외**(Private Retention) 또는 분류기 플래그분 **보관·사람 검토**(Safety Retention). 이미지·파일 입력은 CSAM 분류기 플래그 시 ZDR이어도 보관. **전사 엔드포인트는 ZDR 승인 없이도 문서상 None**이므로 승인은 실익이 작음([해석]). | [확인]/[해석] | O18 |
| 8 | 인증 | **API Platform: SOC 2 Type 2, ISO/IEC 27001:2022, 27701:2019 범위 ✓**(Trust Portal 공지: 27017·27018도 API·Enterprise·Edu 범위). 암호화 AES-256 저장·TLS 1.2+. | [확인] | O15, O16, O12 |
| 9 | 판정 | **B**(학습 No·보관 None·ZDR 적격·SOC2/ISO). 감점 요인 없음에 가깝지만 한국 내 처리는 불가. | | |

### 출처 (OpenAI API)
- O17 https://openai.com/policies/sub-processor-list/ (Last updated October 14, 2026)
- O18 https://developers.openai.com/api/docs/guides/your-data (Data controls in the OpenAI platform)
- O16 https://trust.openai.com/ (Trust Portal)
- O12·O15·O11: §1 출처 참고

---

## 5. ElevenLabs Scribe (API · 웹)

| # | 항목 | 내용 | 구분 | 출처 |
|---|---|---|---|---|
| 1 | 학습·개선 사용 | **기본: 사용.** 이용약관 §4(d): 이용자 Content(음성 포함)에 대해 서비스 제공·**개선·신규 서비스 개발** 목적의 사용·복제·수정·재배포 등 라이선스를 부여 — **영구적·취소 불가·비독점·로열티 없음·전 세계·다단계 재허락 가능**. §2: 개인 데이터를 "AI 모델 연구·개발"에 쓸 수 있음. 개인정보 처리방침도 입력·출력으로 "AI 모델 연구·학습"을 명시. **옵트아웃: 계정 프로필 → Terms and privacy → Data use → "Improve the models for everyone" 끄기 → Update your choice** — 이후 새 데이터는 학습에 안 쓰이지만 **처리 전 사용분은 영향 없음(소급 안 됨)**, 처리는 팀 처리 후 적용. 엔터프라이즈는 기본 비학습. | [확인] | E1, E2, E3 |
| 2 | 사람 검토 | 약관 §4(j): 콘텐츠를 전부 검토할 의무는 없으나 필요 시 삭제·정지 등 조치 가능. DPA §13.1: **안전(모더레이션) 팀이 Prohibited Use Policy 준수 확인 목적으로 고객 콘텐츠에 접근 가능, 지원 인력도 접근 가능.** 처리방침: 콘텐츠 모더레이션 외주 벤더 사용. STT 모델이 외부 LLM을 쓰는지는 **확인 못 함**(ZRM 문서는 LLM 제공자의 학습 금지 계약을 언급). | [확인] | E6, E1, E2, E4 |
| 3 | 보관 기간 | **기본: 이력 보존 ON**(STT 입력 오디오·출력 텍스트 모두 기본 보관 표시). 사용자는 API `DELETE /v1/speech-to-text/transcripts/{id}`로 삭제 가능; 삭제하면 DB의 오디오·텍스트는 **즉시 제거되지만 디버깅·모더레이션 로그에 관련 데이터가 남을 수 있음**; **백업에는 삭제 후 최대 30일 남음.** 계정 삭제 시 전체 영구 삭제(디버깅 데이터는 "상업적으로 합리적 노력"). 셀프서브는 비활동 180일 후 삭제할 권리가 있으나 의무는 없음. 음성에 관해 생성한 데이터는 **마지막 상호작용 후 3년 초과 보관 안 함.** 고정 보관기간은 문서에 없음 → **확인 못 함**. | [확인] | E4, E6 §9, E2 §6, E8 |
| 4 | 위치·위탁사 | 처리방침 §5: "어디에 살든 **개인정보는 미국으로 이전·저장**". 표준 저장은 미국. **EU·인도·싱가포르 격리 환경은 Enterprise 전용**이며 그 경우에도 저장만 해당하고 **처리는 위탁사·지원·모더레이션으로 리전 밖에서 발생 가능**(EU는 ZRM+API 조합으로 EU 내 처리로 제한 가능). 위탁사 목록은 Trust Center(`compliance.elevenlabs.io/subprocessors`)에 있으나 **JS 렌더링으로 열람 못 함 → 확인 못 함**. | [확인]/확인 못 함 | E2, E5, E6 §13 |
| 5 | 제3자·광고 | 목적별 표에서 광고·마케팅에 쓰는 데이터 범주는 위치·기기·사용 정보이며 **입력·출력은 포함되지 않음**, 음성 데이터로 개인을 타기팅하지 않는다고 명시. 위탁 벤더·제휴 광고 파트너·법적 요청·사업 양도 시 제공 가능. Content 라이선스는 다단계 재허락 가능(§4(d)). | [확인] | E2 §3·§4, E1 |
| 6 | 개인 vs 비즈니스 | 무료 이용자는 **비상업 용도만**, 유료는 상업 허용(약관 §1(c)). 엔터프라이즈: 기본 비학습, **Zero Retention Mode**, 데이터 레지던시, BAA. 웹 UI 트래픽은 ZRM 대상이 **아님**. DPA는 "개체를 대신해 약관에 동의한 경우" 콘텐츠 내 개인정보에 적용(약관 §2)이므로 **개인 이메일 계정에는 적용 안 될 수 있음**([해석]). STT 약관 §3.1: 녹음·전사에 필요한 **고지·동의는 전적으로 이용자 책임**. | [확인]/[해석] | E1, E4, E5, E7 |
| 7 | ZDR | **Zero Retention Mode = 엔터프라이즈 선별 고객 전용.** 요청별 `enable_logging=false`(Speech to Text `/v1/speech-to-text/*` 적격) → 입력·출력 로깅 제한, 요청 메모리에서만 처리, **로그·전사 저장 기능 사용 불가**. 위험도 높은 사용·자동 플래그 시 제한 가능. 디버깅 지원 제한. 웹 UI·계정 이메일·지원 티켓 등은 대상 아님. 비엔터프라이즈가 `enable_logging=false`를 보내면 API 문서상 "엔터프라이즈만 사용 가능". | [확인] | E4, E8 |
| 8 | 인증 | 문서에 **SOC 2 인증 보유** 명시, DPA는 SOC 2 Type II 보고서 제공 가능 언급. GDPR 정렬, HIPAA BAA(적격 고객). **ISO 27001 등은 Trust Center를 열지 못해 확인 못 함.** | [확인]/확인 못 함 | E5, E6 §10 |
| 9 | 판정 | **C**(기본 학습 사용 + 영구·취소불가 라이선스 + ZRM 엔터프라이즈 한정). Data use 토글 OFF + 유료 플랜 + 처리 후 전사 삭제 호출 시 **B(잠정)**: 옵트아웃 비소급, 라이선스 문구는 그대로, 위탁사·ISO 확인 못 함. 엔터프라이즈+ZRM이면 B. | | |

### 출처 (ElevenLabs)
- E1 https://elevenlabs.io/terms-of-use (ToS non-EEA, Last Updated 09 October 2026)
- E2 https://elevenlabs.io/privacy-policy (Updated 9 October 2026)
- E3 https://elevenlabs.io/docs/help-center/legal/is-my-data-used-to-improve-eleven-labs-ai-models
- E4 https://elevenlabs.io/docs/eleven-api/resources/zero-retention-mode
- E5 https://elevenlabs.io/docs/overview/administration/data-residency
- E6 https://elevenlabs.io/dpa (Last Updated 8 April 2026)
- E7 https://elevenlabs.io/speech-to-text-terms (Last updated October 09, 2026)
- E8 https://elevenlabs.io/docs/api-reference/speech-to-text/convert , https://elevenlabs.io/docs/api-reference/speech-to-text/delete
- 열람 못 함: https://compliance.elevenlabs.io (Trust Center, 위탁사·인증서) — JS 렌더링으로 본문 비어 있음

---

## 6. 짧게: AssemblyAI · Deepgram · Speechmatics

| 항목 | AssemblyAI | Deepgram | Speechmatics |
|---|---|---|---|
| 학습 기본값 | **일부 파일이 학습에 쓰임**(약관상 허용 범위, PII 제거 후). 제외 조건: 옵트아웃·EU 서버·BAA | **Model Improvement Program(MIP) 기본 참여 → 오디오·전사를 모델 개선용으로 보관** | **기본 학습 미사용**: Model training(= data logging)은 **옵트인 할인 프로그램**(33% 할인), 가입해도 데이터를 쓸지는 Speechmatics 재량 |
| 옵트아웃 | 유료만 셀프서브(대시보드 Data Controls, Owner/Admin). **무료 사용자는 옵트아웃 불가.** **소급 불가(이후 신규 요청에만 적용)** | 요청마다 `mip_opt_out=true`(콘솔 Usage→Logs로 확인). 계정 단위 강제는 문의 | 해당 없음(옵트인 쪽). 변경은 미래 사용에만 적용 |
| 사람 접근 | 약관 검색에서 사람 검토 언급 **확인 못 함** | 개인정보 방침 검색에서 언급 **확인 못 함** | 옵트인 시 데이터가 계열사·직원·계약자·제3자에게 공유되어 처리될 수 있음(Model Training Addendum §2.2). 기본값 사람 검토 **확인 못 함** |
| 보관 | 비동기: 오디오는 TTL 설정 시 최소 1시간, 미설정 24~48시간 후 삭제 시작(최대 48시간), 전사 결과 미설정 시 30일 후 삭제 시작, TTL 최소 1시간. 옵트아웃 시 스트리밍·Sync는 오디오·전사 **무보관**(메타데이터만) | 옵트아웃(`mip_opt_out=true`) 시 처리 요청 동안만 보관, **MIP 기본은 보관·학습**. 메타데이터·사용 로그 90일 | **배치: 오디오·전사·설정 7일 보관 후 자동 삭제**(API로 조기 삭제), 실시간은 저장 안 함 |
| 위치·위탁 | 기본 리전 **확인 못 함**(AWS 사용). **EU 서버 선택 가능**(EU 서버는 학습 제외) | 기본 전역 엔드포인트, **EU·호주·인도 리전 엔드포인트**(한국 없음). 모델 개선은 리전 밖에서 처리될 수 있어 완전 현지 처리는 리전 엔드포인트 + 옵트아웃이 모두 필요 | 클라우드는 Azure 호스팅. 전 세계 처리 환경·온프렘·온디바이스 제공(Enterprise). 기본 리전 **확인 못 함** |
| 인증 | SOC 2 Type 1·2. ISO 27001 확인 못 함 | SOC 2 Type 1·2, HIPAA, PCI DSS, GDPR/CCPA. ISO 확인 못 함 | **ISO/IEC 27001:2022, SOC 2 Type II**, GDPR, HIPAA(보고서는 Trust Center, NDA) |
| 판정 | **C**(기본 학습 + 무료 옵트아웃 불가). 유료+옵트아웃+TTL 시 **B(잠정)**(소급 불가·사람 접근 확인 못 함) | **C**(기본 MIP). `mip_opt_out=true` 시 **B(잠정)**(요청마다 설정, 사람 접근 확인 못 함) | **B(잠정)**(사람 접근 확인 못 함, 7일 보관) |

출처:
- AssemblyAI: https://www.assemblyai.com/docs/data-retention-and-model-training.md , https://www.assemblyai.com/docs/faq/how-to-opt-out-of-data-sharing-for-our-model-improvement-program.md , 약관 https://www.assemblyai.com/legal/terms-of-service (사람 검토 관련 문구 검색 → 없음)
- Deepgram: https://developers.deepgram.com/trust-security/your-data.md , https://developers.deepgram.com/docs/the-deepgram-model-improvement-partnership-program.md , https://developers.deepgram.com/trust-security/data-privacy-compliance.md , 방침 https://deepgram.com/privacy (사람 검토 문구 검색 → 없음)
- Speechmatics: https://docs.speechmatics.com/administration/security-and-compliance.md , https://docs.speechmatics.com/administration/plans (Model training = data logging, 미래 사용에만 적용), https://www.speechmatics.com/security , 가격 FAQ 텍스트 https://www.speechmatics.com/llms-full.txt ("If you have not opted in … Pre-recorded data auto-deletes after 7 days … never used to improve our models", 벤더 사이트 텍스트), Model Training Addendum https://www.speechmatics.com/legal/data-retention-terms

---

## 7. 로컬 모델 참고 — pyannote.audio community-1, Hugging Face

### 7-1. pyannote.audio 텔레메트리 (소스 직접 확인)

| 항목 | 내용 | 구분 |
|---|---|---|
| 기본값 | README는 "optional"이라 쓰지만 `telemetry/config.yaml`의 **`metrics_enabled: true`**(기본 ON), `otlp_endpoint: https://otel.pyannote.ai/v1/traces`. 환경변수 `PYANNOTE_METRICS_ENABLED`가 없으면 config 값을 읽음. | [확인] |
| 전송 항목 | ① 모델 초기화: `origin`(pyannote/pyannoteAI 공식 HF 모델이면 그 이름, 다른 HF 조직이면 `huggingface`, 로컬 경로면 `local`), `version`, `session_id`(실행마다 랜덤 UUID) ② 파이프라인 초기화: origin, 파이프라인 클래스명, version, session_id ③ **파일 처리마다: `duration`(초), `num_speakers`·`min_speakers`·`max_speakers`**. 오디오 본문·파일명·경로·텍스트는 전송 코드에 없음. 연결은 OpenTelemetry OTLP/HTTP(타임아웃 5초). README: "이용자를 식별할 정보는 추적하지 않음". | [확인] |
| 끄는 법 | (1) 환경변수 `export PYANNOTE_METRICS_ENABLED=0`(가장 확실, import 전에 설정) (2) 세션 한정 `set_telemetry_metrics(False)` (3) 전역 저장 `set_telemetry_metrics(False, save_choice_as_default=True)` → 패키지 내 `config.yaml`을 수정(패키지 재설치·업그레이드 시 되돌아갈 수 있음 [추정]). 코드상 비활성이면 span을 만들지 않음. | [확인]/[추정] |
| 한계 | HTTP 연결의 출발지 IP는 수신 서버에서 보일 수밖에 없음 — 문서에 IP 처리 언급 **확인 못 함** [추정]. `precision-2`는 **pyannoteAI 서버에서 실행되어 오디오가 나감**(README) → 이 조사 범위 밖, 정책 **확인 못 함 → C 취급**. | [확인]/확인 못 함 |
| 판정 | **A**(community-1은 로컬 실행: "runs locally", 녹음 미전송). 단 기본 텔레메트리로 길이·화자 수 메타데이터는 나감 → `PYANNOTE_METRICS_ENABLED=0` 권장. | |

### 7-2. Hugging Face 다운로드 외 통신

| 항목 | 내용 | 구분 |
|---|---|---|
| 모델 접근 | community-1은 **gated**(HF API 메타: Access: Gated, cc-by-4.0). README 안내: 사용자 조건 동의 + HF 토큰 필요. 동의 시 모델 카드가 요구하는 입력 항목은 **본문이 401이라 확인 못 함**. | [확인]/확인 못 함 |
| 로드 시 통신 | 캐시가 있어도 `hf_hub_download`는 새 버전 확인 HTTP 요청을 함. **`HF_HUB_OFFLINE=1`이면 Hub로 HTTP 호출을 하지 않음**(캐시에 없으면 오류). | [확인] |
| 토큰 전송 | 로그인 상태면 기본적으로 모든 Hub 요청에 토큰을 보냄. 줄이려면 `HF_HUB_DISABLE_IMPLICIT_TOKEN=1`(쓰기 호출에만 토큰). | [확인] |
| HF 라이브러리 텔레메트리 | transformers·datasets·gradio 등이 기본으로 사용 정보를 수집 → **`HF_HUB_DISABLE_TELEMETRY=1`** 또는 **`DO_NOT_TRACK=1`**. pyannote.audio 자체가 이 경로를 쓰는지는 **확인 못 함**(별도 OTel 경로만 코드로 확인). | [확인]/확인 못 함 |
| 권장 설정 | `PYANNOTE_METRICS_ENABLED=0`, `HF_HUB_OFFLINE=1`(모델 캐시 후), `HF_HUB_DISABLE_TELEMETRY=1`(또는 `DO_NOT_TRACK=1`). 이러면 처리 시점 외부 통신이 없어야 함(실제 패킷 확인은 안 함 → **검증 필요** [추정]). | [해석]/[추정] |

출처: P1 https://raw.githubusercontent.com/pyannote/pyannote-audio/main/README.md , P2 https://raw.githubusercontent.com/pyannote/pyannote-audio/main/src/pyannote/audio/telemetry/metrics.py , P3 https://raw.githubusercontent.com/pyannote/pyannote-audio/main/src/pyannote/audio/telemetry/config.yaml , H1 https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables , H2 https://huggingface.co/api/models/pyannote/speaker-diarization-community-1 (모델 카드 원문은 401)

---

## 8. 등급 요약

| 서비스 | 등급(기본 설정) | 결정적 근거 | 등급을 올리는 설정·상품 |
|---|---|---|---|
| ChatGPT Plus/Pro 앱 | **C** | 기본 학습 사용(O1), 사람 접근 사유에 모델 개선 포함(O5), 소비자 플랜은 SOC2/ISO 범위표에 없음(O15) | **B(잠정)**: Data controls 옵트아웃 + 임시 채팅 + 개인 이메일. 한계: 새 대화만, 30일 사본, 2025 소송 보존 선례(O11) |
| ChatGPT Business | **B** | 기본 비학습, 오남용 목적 외주 검토만 명시(O12), SOC 2 Type 2(O15) | ISO·ZDR 필요 시 Enterprise/계약형. 셀프서브는 최소 2좌석(O13,O14) |
| Gemini 앱(개인 Free/AI Pro 등) | **C** | Keep Activity 기본 ON → 학습 + 사람 검토, 검토본 최대 3년(삭제해도 유지)(G1) | **B(잠정)**: Keep Activity 끔 + 임시 채팅 + 피드백 미제출. 72시간 보관·안전 목적 사람 검토 잔존·소급 불가 |
| Gemini Workspace | **B** | 학습·사람 검토 없음(도메인 밖), 관리자 보관 설정, ISO/SOC/FedRAMP(G7) | 개인 구독으로는 불가, Workspace 에디션 필요 |
| Gemini API 무료 | **C** | 입력·출력 개선 사용 + 사람 검토 + "민감 정보 금지"(G2). 한국은 EEA 예외 아님 | 결제 계정 연결(유료)로 전환 |
| Gemini API 유료(3.5 Transcribe 등) | **B** | 학습 미사용(G2), 사람 검토는 오남용 플래그분만(G3). 감점: 55일 보관(G3)·국가 불특정(G2)·ZDR/ISO 확인 못 함 | AI Studio Logs 끄기(프로젝트 로그), 파일 48시간 자동삭제 활용(G4,G5) |
| Vertex(Agent Platform) 3.5 Transcribe | **B** | Training Restriction(G10), ZDR 달성 절차 문서화(G13), us/eu 멀티리전 처리(G14) | CMA 계약(오남용 사람 검토 제외, G12), 캐시 끄기 |
| Cloud STT v2 Chirp 3 | **B** | 기본 로깅 없음, 가입 시에만 개선 사용(G8), ISO 27001 범위(G15), 처리 리전 US/EU뿐(G9) | data logging 미가입 유지, `eu`/`us` 고정 |
| OpenAI API `gpt-transcribe` | **B** | 학습 No·보관 None·ZDR 적격(O18), SOC2/ISO(O15) | ZDR/MAM 승인은 실익 작음(이미 None). 한국 리전은 저장만 가능(O18) |
| ElevenLabs Scribe | **C** | 기본 학습 사용 + §4(d) 영구·취소불가 라이선스(E1), ZRM 엔터프라이즈 한정(E4), 옵트아웃 비소급(E1 §4(i)) | **B(잠정)**: Data use 토글 OFF + 유료 플랜 + 전사 삭제. **B**: 엔터프라이즈+ZRM |
| AssemblyAI | **C** | 일부 파일 학습 사용, 무료 옵트아웃 불가, 옵트아웃 비소급(A2) | **B(잠정)**: 유료 + 옵트아웃 + TTL(최소 1시간) 또는 EU 서버 |
| Deepgram | **C** | 기본 MIP 보관·학습(D1) | **B(잠정)**: 모든 요청에 `mip_opt_out=true` |
| Speechmatics | **B(잠정)** | 기본 학습 미사용·배치 7일 삭제(S1,S3). 사람 접근 확인 못 함 | 옵트인 할인(Model training) 켜지 않기 |
| pyannote community-1(로컬) | **A** | 로컬 실행, 오디오 미전송(P1). 기본 텔레메트리는 길이·화자 수만(P2,P3) | `PYANNOTE_METRICS_ENABLED=0`, `HF_HUB_OFFLINE=1` |

활용 메모([해석], 법률 판단 아님): 회사 정보가 섞인 녹음은 **A·B**만, 개인 대화만 있는 녹음은 **B(잠정)까지** 검토 대상으로 두고 C는 제외하는 구분이 기준표와 일치함. 같은 녹음이라도 **이메일 계정 종류**(OpenAI "Corporate domains")와 **녹음 대상자 동의**(ElevenLabs STT 약관 §3.1)는 서비스 등급과 별개로 확인해야 함.

---

## 9. global-stt.md 대비 정정·보강

| global-stt.md 내용 | 이번 확인 결과 |
|---|---|
| Gemini API 유료: "오남용 탐지용 로그를 한시적 보관" | **55일**, 프롬프트·맥락·출력(G3). 사람 검토는 플래그분 한정. 새 프로젝트는 개발자용 API 로그도 기본 ON(55일, 끌 수 있음)(G4) |
| Gemini 앱: Keep Activity 끔/임시 채팅 72시간 후 학습 안 함 | 맞음(G1). **추가: 그 상태에서도 안전 목적 사람 검토 가능, 검토본은 삭제해도 최대 3년 보관** |
| OpenAI API `/v1/audio/transcriptions` 보관 None, 한국 저장만 | 맞음(O18). **추가: 한국 리전은 MAM/ZDR 승인 + Modified Retention 수정 계약 필요, 신모델 10% 가산** |
| ChatGPT: 옵트아웃 가능, 삭제 30일 | 맞음. **추가: 임시 채팅 30일 사본, 2025 소송 보존 명령 이력(2025-09-26 종료), 소비자 플랜은 인증 범위 표에 없음, 회사 이메일 계정 편입 조항** |
| ElevenLabs: 옵트아웃 가능(이전 사용분 제외), ZRM 엔터프라이즈 | 맞음. **추가: 약관 §4(d) 영구·취소불가 라이선스 전문, 무료 플랜 비상업, STT 약관 §3.1 동의 책임, 삭제 후 백업 30일·모더레이션 로그 잔존, 웹 UI는 ZRM 대상 아님** |
| AssemblyAI: 옵트아웃·EU 서버·BAA 사용 시 학습 제외 | **무료 사용자 옵트아웃 불가, 소급 불가** 추가 |
| Deepgram: MIP 기본, `mip_opt_out` | 맞음. **추가: 옵트아웃 시 오디오·전사 비보관(처리 중에만), 완전 현지 처리는 리전 엔드포인트 + 옵트아웃 둘 다 필요** |
| Speechmatics: 학습 사용 여부 확인 못 함 | **기본 미사용, 옵트인 할인 프로그램**으로 확인(S2,S3) |
| Cloud STT: 기본 로깅 안 함 | 맞음(G8). **추가: 가입 프로젝트 로그는 프로젝트 삭제 후에도 남음, Chirp 3 처리 리전은 us·eu뿐** |

---

## 10. 확인 못 함 목록 (공백)

- ChatGPT: 옵트아웃의 과거 대화 소급 여부, 일반 채팅에 업로드한 오디오 파일 전용 보관 규정, 2026-11-09 현재 유효한 새 보존 명령 여부(검색에 2026-07 NYT 소송 문서가 보이나 열어보지 않음), 소비자용 사람 검토 위탁사 목록.
- Gemini 앱: 소비자 계정의 SOC/ISO 범위, 사람 검토 위탁사·국가, Workspace 에디션 최소 좌석·가격.
- Gemini API: ZDR 옵션, 데이터 저장 리전 선택, ISO 범위, 서비스 위탁사. Cloud STT: Chirp 3에 오남용 프롬프트 로깅이 적용되는지, v2 전용 data logging 문서, 처리 중 임시 보관 기간.
- ElevenLabs: Trust Center의 위탁사·ISO 인증, STT 데이터 사람 검토 범위의 구체, 기본 이력 보관 기간(정해진 기간 문구 없음), Scribe가 외부 LLM을 쓰는지.
- AssemblyAI·Deepgram·Speechmatics: 사람 검토 여부, ISO(AssemblyAI·Deepgram), Speechmatics·AssemblyAI의 기본 처리 리전.
- pyannote: community-1 모델 카드의 동의 시 수집 항목(401), 텔레메트리 IP 처리, 실제 오프라인 동작의 패킷 검증.
