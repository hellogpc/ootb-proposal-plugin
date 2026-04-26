# Synthesis guide — RFP + 3 past proposals → outline.yaml

이 문서는 Step 4 에서 Claude 가 outline 을 구성할 때 쓸 규칙입니다.

## 입력

- **RFP 측 정보** (`/tmp/rfp.json`의 `rfp_meta` + `rfp_summary`)
  - 사업명, 발주기관, 분야, 과업범위(array), 타깃, 예산, 사업기간, 제안마감, 평가기준, 필수산출물, 키워드
- **과거 제안서 3건** (Step 3 결과, 유사도 순)
  - 각각 `title`, `industry`, `tags`, `abstract`, `key_points[]`, `objectives`, `strategy`, `deliverables[]`

## 출력

- `ootb-proposal-pptx/templates/outline.example.yaml` 과 동일 스키마의 YAML
- 7개 슬라이드 타입만 허용: `cover`, `toc`, `section_divider`, `hero`, `content`, `content_image`, `closing`

## 작성 원칙

### 1) 뼈대는 RFP, 살은 과거 사례
- `cover.title` / `project.title` = RFP의 `project_title`
- `project.date` = RFP의 `deadline` (YYYY. M. 형식으로 변환)
- TOC 4 항목은 RFP 의 `scope_of_work` 를 논리적으로 묶어서 4개 섹션으로 압축:
  - 권장 기본 구성: `환경분석 / 과업이해 / 수행전략 / 세부실행계획`
  - RFP 가 "성과관리"나 "운영" 섹션을 명시하면 4번째를 그쪽으로 교체

### 2) 유사 사례 재사용 규칙
- **재사용 OK**: 커뮤니케이션 프레임워크, 크리에이터 협업 포맷, 제작 프로세스, KPI 체계, 품질관리 체크리스트
- **재사용 NG**: 특정 인물/기관명(방송사, 인플루언서), 구체 예산 숫자, 특정 시청률/조회수
- **부분 재사용**: 과거 `strategy` 의 프레임은 가져와도 좋지만 대상·채널·톤은 RFP 맞춤으로 수정

### 3) 슬라이드 수 & 밀도
- 기본: 약 12–16 장
  - 1 cover
  - 1 toc
  - 4 section_divider (4 섹션)
  - 1~2 hero (강조 문구)
  - 5~8 content (각 섹션당 1–2 장)
  - 1~2 content_image
  - 1 closing
- 각 `content` 의 `body` 는 **2–4 블록**. 5 개 이상이면 다음 슬라이드로 분할.

### 4) 히어로 슬라이드는 한 장, 많아야 두 장
히어로는 덱의 중심 메시지를 말하는 큰 한 방. 5장 넣으면 공해다. 추천 활용:
- RFP 가 브랜드 재정의를 요구하면 → 해당 대상 서비스명을 hero.headline (예: "복지로", "수산물이력제")
- 아니면 → 핵심 가치제안을 한 문장 (예: hero.headline="믿고 먹는 수산물")

### 5) 출처 표기 규칙
각 `content.body[].text` 마지막에 과거 사례에서 실질적으로 인용했다면 다음 형식으로 주석:

```
  - heading: "추진방향"
    text: "타깃 맞춤형 온·오프라인 통합 캠페인 (ref: past#42 — 2025 복지로)"
```

사용자가 초안을 검토할 때 어디를 검증해야 할지 바로 보입니다. 과거 ID 와 연도 둘 다 표기.

`match_proposals_with_url` 결과에 `signed_url` 이 포함되면 **outline 빌드 결과 리포트**(YAML 아님, 사용자에게 보내는 메시지)에 해당 URL 을 함께 동봉하세요. 예: "참고한 과거 제안서: [#42 2025 복지로](signed_url), [#18 2023 K-관광](signed_url)". YAML 자체에는 URL 을 심지 않습니다(만료됨).

### 6) 한국어 자연스러움
- `(ref: ...)` 이외의 영어 남용 금지. 헤딩/본문은 한국어.
- 조사 섞기 금지. "~을/를" 처럼 슬래시 옵션을 그대로 쓰면 RFP 톤 망가짐.
- 숫자는 `만원` / `억원` 단위로 반올림하지 말 것. RFP 에 나온 정확 금액만 쓰기.

## 구성 템플릿 (권장 초안)

```yaml
brand:
  company_name: "(주)오오티비랩"
project:
  title: "<RFP.project_title>"
  date:  "<RFP.deadline 또는 제안서 제출 예정일>"

slides:
  - type: cover

  - type: toc
    items: ["환경분석", "과업이해", "수행전략", "세부실행계획"]

  # ── I. 환경분석 ──
  - type: section_divider
    number: "I"
    title: "환경분석"
  - type: content
    breadcrumb: "환경분석 | 과업의 배경"
    title: "<RFP.summary 첫 문장>"
    body:
      - heading: "과업배경"
        text: "<RFP.scope_of_work 의 주요 항목 재서술>"
      - heading: "서비스 환경"
        text: "<과거사례#N 의 환경 분석 인사이트 일부 재사용 (ref: past#N)>"
      - heading: "타깃 특성"
        text: "<RFP.target_audience 재서술>"

  # ── II. 과업이해 ──
  - type: section_divider
    number: "II"
    title: "과업이해"
  - type: content
    breadcrumb: "과업이해 | 핵심 과업"
    title: "사업 추진 목적 및 핵심 과업"
    body:
      - heading: "홍보목적"
        text: "<RFP.summary 에서 도출>"
      - heading: "핵심과업"
        text: "<RFP.scope_of_work 에서 3개>"
      - heading: "성과지표"
        text: "<RFP.evaluation_criteria 에서 유추>"

  # ── III. 수행전략 ──
  - type: section_divider
    number: "III"
    title: "수행전략"
  - type: hero
    eyebrow: "[핵심 키메시지]"
    headline: "<짧은 한 단어·한 구 메시지 (예: '또 하나의 복지')>"
    subheadline: "<그 메시지를 풀어쓴 한 문장>"
    highlight: "<subheadline 의 핵심 키워드>"
  - type: content
    breadcrumb: "수행전략 | 채널·콘텐츠"
    title: "채널 전략 및 콘텐츠 유형"
    body:
      - heading: "채널전략"
        text: "<과거 3건의 strategy 중 RFP 타깃에 맞는 채널 구성 재설계>"
      - heading: "콘텐츠전략"
        text: "<과거 key_points 에서 재사용 가능한 콘텐츠 포맷 + 이번 과업 맞춤 제작>"

  # ── IV. 세부실행계획 ──
  - type: section_divider
    number: "IV"
    title: "세부실행계획"
  - type: content_image
    breadcrumb: "세부실행계획 | 대표 콘텐츠"
    title: "대표 콘텐츠 포맷 (숏폼·인포그래픽·영상)"
    image_position: right
    text: |
      · <과거 deliverables 중 재사용 가능한 항목>
      · <그 항목을 이번 과업 타깃에 맞게 변형>
      · <주차/월별 업로드 빈도 — 구체 숫자는 확인 필요 표시>

  - type: closing
    message: "감사합니다"
    tagline: "㈜오오티비랩과 함께하겠습니다"
```

이 템플릿은 **출발점**이지 정답이 아닙니다. RFP 가 실행계획을 특별히 강조하면 세부실행계획 콘텐츠를 2~3 장으로 늘리고, 환경분석이 얇아도 되는 과제면 해당 섹션을 1 장으로 줄입니다.

## 검토용 체크리스트 (outline.yaml 작성 후)

- [ ] 타이틀이 RFP 사업명과 일치
- [ ] 모든 섹션 divider 의 `number` 가 연속 (I, II, III, IV)
- [ ] TOC `items` 수 = section_divider 수
- [ ] 각 content.body 길이 2–4
- [ ] 숫자·기관명·인물명에 `[확인 필요]` 또는 `(ref: ...)` 표기
- [ ] hero 는 최대 2 장
- [ ] 슬라이드 총 수 12–16 장
