# Synthesis guide — RFP + 3 past proposals → outline.yaml (v2)

이 문서는 Step 4 에서 Claude 가 outline 을 구성할 때 따르는 규칙입니다. 출력은 `references/brand_design.md` 의 5-zone + 6 pattern 시스템 (Brandlogy v2) 을 따릅니다.

---

## 입력

- **RFP 측 정보** (`/tmp/rfp.json` 의 `rfp_meta` + `rfp_summary`)
  - 사업명, 발주기관, 분야, 과업범위(array), 타깃, 예산, 사업기간, 제안마감, 평가기준, 필수산출물, 키워드
- **과거 제안서 3건** (Step 3 결과, 유사도 순)
  - 각각 `title`, `industry`, `tags`, `abstract`, `key_points[]`, `objectives`, `strategy`, `deliverables[]`

---

## 출력

- v2 outline.yaml (`references/brand_design.md` 와 매칭)
- **5개 슬라이드 타입만 허용**: `cover`, `section_divider`, `content`, `hero_takeaway`, `closing`
- `content` 타입은 **Pattern A–F** 중 하나 명시 (`pattern: "A"`)
- v1 타입 (`toc`, `hero`, `content_image`) **사용 금지** — 아래 매핑으로 대체
  - `toc` → 제거 (v2는 linear flow)
  - `hero` → `hero_takeaway`
  - `content_image` → `content` + `pattern: B` (Two-Column)

---

## 작성 원칙

### 1) 뼈대는 RFP, 살은 과거 사례

- `cover.title` / `project.title` = RFP 의 `project_title`
- `project.date` = RFP 의 `deadline` (YYYY-MM-DD 또는 YYYY.M)
- 섹션 구성: RFP 의 `scope_of_work` 를 논리적으로 묶어 **3~4개 섹션**으로 압축
  - 권장 기본 구성: `환경분석 / 과업이해 / 수행전략 / 세부실행계획`
  - RFP 가 "성과관리"·"운영"·"리스크관리" 등을 명시하면 4번째를 그쪽으로 교체

### 2) 유사 사례 재사용 규칙

- **재사용 OK**: 커뮤니케이션 프레임워크, 크리에이터 협업 포맷, 제작 프로세스, KPI 체계, 품질관리 체크리스트
- **재사용 NG**: 특정 인물·기관명(방송사·인플루언서), 구체 예산 숫자, 특정 시청률·조회수
- **부분 재사용**: 과거 `strategy` 의 프레임은 가져와도 좋지만 대상·채널·톤은 RFP 맞춤으로 수정

### 3) ⭐ Pattern A–F 선택 룰북 (v2 핵심)

`content` 슬라이드는 **반드시 `pattern: "A"~"F"` 중 하나를 명시**합니다. 패턴은 **콘텐츠의 형태**가 결정합니다 — 같은 헤딩+텍스트 구조를 반복하지 않습니다.

| 트리거 (RFP·과거사례에서 이런 형태가 보이면) | → Pattern | 데이터 schema |
|---|---|---|
| 숫자·통계·KPI ≥3개 (예: "인지도 18%", "예산 3.5억", "기간 7개월") | **A** KPI Strip + Detail | `kpi: [{value, label}]` + `detail: {type: "bar_chart"\|"donut_chart", title, data, primary_color}` |
| 기존 vs 신규 / before vs after / 두 타깃 비교 | **B** Two-Column Compare | `left: {header, bullets}` + `right: {header, bullets}` + `callout` |
| 발주기관 조직도 / 구조적 관계 / 4분면·매트릭스 | **C** Diagram-Centered | `diagram: {type: "hub_spoke"\|"quad_matrix", center?, spokes?, quadrants?}` + `caption` |
| 단계별 일정·프로세스 ≥3 단계 (인지→참여→전환 등) | **D** Process Flow | `stages: [{num, label, desc}]` + `outcomes` |
| 단일 강조 메시지 / 콘셉트 선언 / 핵심 인사이트 | **E** Quote + Evidence | `quote` + `evidence: [{claim, proof, src}]` |
| 정성·서술형 분석 (heading 3~4 블록 형태였던 v1 스타일) | **F** Stacked Insight | `top: {kpi}` + `middle: {type, title, data\|text}` + `bottom: {evidence: [{claim, proof, src}]}` |

**판단 순서**:
1. 숫자가 있는가? → **A** 우선
2. 비교 구조인가? → **B**
3. 단계·시간 흐름인가? → **D**
4. 다이어그램으로 그릴 수 있는 구조관계인가? → **C**
5. 한 문장으로 압축되는 강조 메시지인가? → **E**
6. 위 어느 것에도 안 맞는 서술형이면 → **F** (v1 스타일의 v2 정착지점)

> ⚠️ **F 패턴 남용 금지**: F 는 다른 패턴이 안 맞을 때만. 한 덱에서 F 비율이 30% 넘으면 v1 스타일로 회귀한 것 — 다시 점검.

#### Pattern 선택 금지 조건 (NG rules — 내용 기반 다양성 보장)

긍정 트리거가 "이런 경우엔 이걸 골라라" 라면, 아래는 "이런 경우엔 절대 안 된다". 다양성을 억지로 맞추기 위해 부적합한 패턴을 끼워 넣으면 PPT 가 더 망가집니다.

| Pattern | 금지 조건 |
|---|---|
| **A** (KPI Strip) | 본문에 실제 숫자·통계 0개 → 가짜 숫자 만들지 말고 다른 패턴. KPI 자리에 정성 라벨만 채우는 것도 금지. |
| **B** (Two-Column) | 비교 대상이 1개뿐이거나 3개 이상 → B 부적절. 3개 이상이면 **C** (`quad_matrix`). |
| **C** (Diagram) | 다이어그램으로 그릴 수 있는 구조관계가 없음 (단순 항목 나열) → C 금지, **F**. 추상적 메타포만으로 hub/spoke 만들지 말 것. |
| **D** (Process Flow) | 단계가 ≤2 개 → 흐름 표현이 어색. **F** 또는 **E**. 6 단계 초과면 가독성 저하 → 슬라이드 분할. |
| **E** (Quote+Evidence) | 명확한 인용·선언문이 없음 → E 금지. 발주기관 발언이나 핵심 메타포 한 문장이 있을 때만. |
| **F** (Stacked Insight) | 다른 패턴 (A·B·C·D·E) 으로 표현 가능한 구조가 있음에도 F 선택 → 금지. F 는 마지막 안전망. |

부적합 패턴 강요의 결과:
- 숫자 없는데 A → 빈 KPI 타일 → "[수치 확인]" 라벨로 가득 찬 슬라이드
- 단계 1~2개에 D → 의미 없는 빈 stage 박스
- 구조 관계 없는데 C → 의미 없는 hub/spoke 다이어그램
- 인용문 없는데 E → 본문에서 억지로 한 문장 끌어다 quote 처리

이런 경우는 모두 **F 로 회귀**하는 것이 옳습니다 (단, 덱 전체 F 비율 ≤30% 유지).

### 4) ⭐ Visualization 데이터 추출 가이드

`brand_design.md` Visualization-First Rule 에 따라 **데이터·비교·프로세스·구조가 있는 슬라이드는 시각화 강제**. 산문 나열 금지. RFP 와 과거 사례에서 시각화 raw input 을 적극 추출:

| RFP / 과거사례에서 추출 | → 시각화 |
|---|---|
| `evaluation_criteria` 배점 (예: 수행전략 25점, 실행계획 20점...) | Pattern A 의 KPI tile + bar chart |
| `scope_of_work` 단계어 ("1단계", "Q1", "사전·발생·재발") | Pattern D 의 stages |
| `target_audience` 다중 (예: "2030 / 가족") | Pattern B 의 left/right |
| RFP 의 백분율·비율 ("숏폼 60% / 가족 30% / IP 10%") | Pattern A 의 donut_chart |
| 과거 `key_points` 인용 가능한 문장 | Pattern E 의 quote + evidence stack |
| 시계열 데이터 (연도별, 월별) | Pattern A 의 bar/line chart |
| 발주기관·조직 구조 | Pattern C 의 hub_spoke 다이어그램 |
| 채널·매체 4축 비교 | Pattern C 의 quad_matrix |

**추출이 막히면**:
- RFP 에 숫자가 없으면 → 과거 `key_points` 에서 검증된 통계 가져오고 `(ref: past#N)` 로 표시
- 과거에도 없으면 → `[수치 확인 필요]` placeholder 로 두고 절대 가짜 숫자 만들지 않음

### 5) ⭐ Pattern 다양성 예산

같은 패턴이 연속되면 PPT 가 단조로워집니다. 다음 규칙을 작성 중 자체 점검:

- **같은 pattern 3장 이상 연속 금지** (예: A → A → A 안 됨, A → A → B → A 는 OK)
- **30+ 슬라이드 덱 권장 분포**:
  - Pattern A (KPI): ≥3장
  - Pattern B (Compare): ≥2장
  - Pattern D (Process): ≥2장
  - Pattern F (Stacked): ≥3장 (단, 전체의 30% 초과 금지)
  - Pattern C (Diagram): ≥1장
  - Pattern E (Quote): 1~2장
- **15~20 슬라이드 덱 권장 분포**: A·B·D·F 각각 ≥1장, C·E 는 선택
- **Hero Gradient ≤ 3 (덱 전체)**: cover hero card / section_divider gradient / 슬라이드당 1개 featured KPI 만

자가 점검 의사코드:
```
patterns = [s.pattern for s in slides if s.type == "content"]
assert no_3_consecutive(patterns)
assert distribution_meets_minimum(patterns, deck_size=len(slides))
assert hero_gradient_count(slides) <= 3
```

### 6) 슬라이드 수 & 밀도

- **기본 범위: 12~40 장** (v1 12~16 제약 폐지). RFP 분량에 비례.
  - 1 cover
  - 3~4 section_divider
  - 0~2 hero_takeaway (강조 문구, **많아야 2장**)
  - 8~30 content (각 섹션당 2~8 장)
  - 1 closing
- 각 `content` 의 body 는 **pattern 별 schema 따름** (v1 의 "body 2~4 블록" 룰은 폐기)

### 7) hero_takeaway 는 한 장, 많아야 두 장

`hero_takeaway` 는 덱 중심 메시지를 말하는 큰 한 방. 5장 넣으면 공해입니다.
- RFP 가 브랜드 재정의를 요구하면 → 해당 서비스명·콘셉트를 `headline` (예: "복지로", "물든 캘린더")
- 아니면 → 핵심 가치제안 한 문장 (예: `headline="오늘, 바다로 가는 시간"`)

데이터 필드:
```yaml
- type: hero_takeaway
  chapter: "03 수행전략"
  headline: "<짧은 한 문장 메시지>"
  quote: "<메시지를 풀어쓴 한 문장>"
  evidence:
    - { value: "<숫자 1개>", label: "<라벨>" }
```

### 8) 출처 표기 규칙

각 `content.body` 안에서 과거 사례 인용이 있으면 다음 형식으로 표기:

```yaml
# Pattern A 예시
body:
  kpi:
    - { value: "47%", label: "회상률 향상 (ref: past#42 — 2026 수산물이력제)" }

# Pattern E 예시
body:
  evidence:
    - { claim: "단일 메타포 (past#1)", proof: "...", src: "오오티비랩 2026" }
```

`match_proposals_with_url` 결과에 `signed_url` 이 포함되면 **outline 빌드 결과 리포트** (YAML 아님, 사용자에게 보내는 메시지) 에 해당 URL 을 함께 동봉. 예: "참고한 과거 제안서: [#42 2026 수산물이력제](signed_url), [#18 2025 복지로](signed_url)". YAML 자체에는 URL 을 심지 않습니다 (만료됨).

각 `content` 슬라이드는 `source` 필드로 출처 1줄 명시 (footer 우측 노출):
```yaml
source: "해양수산부 2025 자체조사 (n=2,000)"
```

### 9) 한국어 자연스러움

- `(ref: ...)` 이외의 영어 남용 금지. 헤딩·본문은 한국어.
- 조사 섞기 금지 ("~을/를" 슬래시 옵션 그대로 쓰면 톤 망가짐).
- 숫자는 `만원` / `억원` 단위로 반올림하지 말 것. RFP 에 나온 정확 금액만.
- 가짜 숫자 금지 — 모르면 `[수치 확인 필요]` 로 두기.

---

## 구성 템플릿 (v2 권장 초안)

아래는 **출발점**이지 정답이 아닙니다. RFP 가 실행계획을 강조하면 III·IV 콘텐츠를 늘리고, 환경분석이 얇은 과제면 I 섹션을 줄입니다.

```yaml
schema_version: "2.0"

brand:
  company_name: "(주)오오티비랩"

project:
  title:  "<RFP.project_title>"
  client: "<RFP.issuing_org>"
  date:   "<RFP.deadline>"

slides:
  # ── Cover (Hero Gradient card) ──
  - type: cover
    title: "<RFP.project_title>"
    subtitle: "<RFP.summary 1문장 압축>"
    date: "<YYYY.MM>"
    hero_kpi:
      value: "<핵심 숫자 1개>"
      label: "<라벨>"

  # ── I. 환경분석 ──
  - type: section_divider
    number: "01"
    title: "환경분석"
    lead: "<섹션 한줄 요약>"
    bg: "gradient"   # cover hero 가 1개, divider gradient 1개 — 덱 전체 ≤3개

  # 시장 환경 — 숫자가 있으면 Pattern A
  - type: content
    chapter: "01 환경분석"
    headline: "<인사이트 한 문장>"
    subtitle: "<부제>"
    pattern: "A"
    body:
      kpi:
        - { value: "<숫자>", label: "<라벨>" }
        - { value: "<숫자>", label: "<라벨>" }
        - { value: "<숫자>", label: "<라벨>" }
      detail:
        type: "bar_chart"
        title: "<차트 제목>"
        data:
          - { x: "<카테고리>", y: <숫자> }
        primary_color: "1456f0"
    source: "<출처>"

  # 타깃 비교 — 두 그룹이면 Pattern B
  - type: content
    chapter: "01 환경분석"
    headline: "<인사이트>"
    subtitle: "<부제>"
    pattern: "B"
    body:
      left:
        header: "<좌측 타이틀>"
        bullets: ["...", "...", "..."]
      right:
        header: "<우측 타이틀>"
        bullets: ["...", "...", "..."]
      callout: "<핵심 인사이트 한 문장>"
    source: "<출처>"

  # ── II. 과업이해 ──
  - type: section_divider
    number: "02"
    title: "과업이해"
    lead: "<섹션 lead>"
    bg: "dark"

  # 과업 단계 — Pattern D
  - type: content
    chapter: "02 과업이해"
    headline: "<단계별 구조>"
    subtitle: "<부제>"
    pattern: "D"
    body:
      stages:
        - { num: "01", label: "<단계명>", desc: "<설명>" }
        - { num: "02", label: "<단계명>", desc: "<설명>" }
        - { num: "03", label: "<단계명>", desc: "<설명>" }
      outcomes: "<단계 종료 결과>"
    source: "<출처>"

  # ── III. 수행전략 ──
  - type: section_divider
    number: "03"
    title: "수행전략"
    lead: "<섹션 lead>"
    bg: "gradient"   # 또는 "dark" (Hero Gradient 예산 안에서)

  # Hero Takeaway — 덱 중심 메시지 (선택, 1~2장)
  - type: hero_takeaway
    chapter: "03 수행전략"
    headline: "<핵심 메시지 짧게>"
    quote: "<메시지 풀어쓰기 한 문장>"
    evidence:
      - { value: "<핵심 숫자>", label: "<라벨>" }

  # 콘셉트 선언 — Pattern E
  - type: content
    chapter: "03 수행전략"
    headline: "<콘셉트 한 문장>"
    subtitle: "<부제>"
    pattern: "E"
    body:
      quote: "<핵심 인용 또는 선언문>"
      evidence:
        - { claim: "<주장>", proof: "<근거 1줄>", src: "<출처 (past#N 가능)>" }
        - { claim: "<주장>", proof: "<근거 1줄>", src: "<출처>" }
    source: "<출처>"

  # 다이어그램형 구조 — Pattern C
  - type: content
    chapter: "03 수행전략"
    headline: "<구조적 관계 설명>"
    subtitle: "<부제>"
    pattern: "C"
    body:
      diagram:
        type: "hub_spoke"
        center: { label: "<중심 콘셉트>", desc: "<설명>" }
        spokes:
          - { label: "<영역1>", desc: "<설명>" }
          - { label: "<영역2>", desc: "<설명>" }
          - { label: "<영역3>", desc: "<설명>" }
      caption: "<다이어그램 설명 한 줄>"
    source: "<출처>"

  # ── IV. 세부실행계획 ──
  - type: section_divider
    number: "04"
    title: "세부실행계획"
    lead: "<섹션 lead>"
    bg: "dark"

  # 정성·서술형 — 다른 패턴이 안 맞을 때만 Pattern F
  - type: content
    chapter: "04 세부실행계획"
    headline: "<인사이트>"
    subtitle: "<부제>"
    pattern: "F"
    body:
      top:
        kpi:
          - { value: "<짧은 라벨>", label: "<설명>" }
          - { value: "<짧은 라벨>", label: "<설명>" }
      middle:
        type: "diagram_text"
        title: "<중단 영역 제목>"
        text: "<중단 영역 본문 1~2 문장>"
      bottom:
        evidence:
          - { claim: "<주장>", proof: "<근거>", src: "<출처>" }
          - { claim: "<주장>", proof: "<근거>", src: "<출처>" }
          - { claim: "<주장>", proof: "<근거>", src: "<출처>" }
    source: "<출처>"

  # ── Closing ──
  - type: closing
    message: "감사합니다"
    tagline: "<오오티비랩과 함께하겠습니다 또는 프로젝트 캐치프레이즈>"
    bg: "gradient"
```

---

## 검토용 체크리스트 (outline.yaml 작성 후)

### 구조
- [ ] `schema_version: "2.0"` 명시
- [ ] 타입은 cover · section_divider · content · hero_takeaway · closing 만 (v1 타입 0개)
- [ ] project.title 이 RFP 의 `project_title` 과 일치
- [ ] project.date 가 RFP 의 `deadline` 과 일치 (있다면)
- [ ] 모든 section_divider 의 `number` 가 연속 (01, 02, 03, ...)
- [ ] hero_takeaway 는 ≤2 장
- [ ] closing 1 장

### Pattern 다양성 (가장 중요)
- [ ] **모든 content 슬라이드에 `pattern: "A"~"F"` 명시**
- [ ] **같은 pattern 3장 이상 연속 없음**
- [ ] Pattern F 비율 ≤ 30%
- [ ] 데이터·숫자가 있는 슬라이드는 Pattern A·D·F (visualization 포함), 산문 단독 금지
- [ ] Hero Gradient 사용 ≤ 3 (cover hero / divider gradient / featured KPI)

### 데이터·출처
- [ ] 숫자·기관명·인물명 모두 `[확인 필요]` 또는 `(ref: past#N)` 표기
- [ ] 각 content 슬라이드에 `source` 필드 명시 (footer 출처)
- [ ] RFP 에 없는 숫자 가공·창작 0건

### 슬라이드 수
- [ ] 12~40 장 범위
- [ ] 발주기관 우선순위 (평가 가중치 높은 영역) 슬라이드가 더 많음
