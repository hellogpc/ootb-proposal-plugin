# OOTB Lab — Slide Blueprints v2 (Brandlogy-inspired, MiniMax-style)

이 문서는 **렌더링 엔진**이 각 슬라이드를 어떻게 그려야 하는지를 정의한다. `rfp-to-proposal-pipeline` 스킬의 Step 6에서 이 문서를 `anthropic-skills:pptx` 의 pptxgenjs 가이드 + `references/brand_tokens.json` 과 함께 합쳐 최종 `.pptx` 를 만든다.

단위: **인치(inches)**. 좌표계는 슬라이드 좌상단 (0,0), 우하단 (W=13.333, H=7.5).

모든 색은 `brand.palette.*` 토큰 참조. 모든 폰트 크기는 `brand.sizes_pt.*`, 두께는 `brand.weights.*` 참조.

---

## 0. Production Constraints (Read First)

### Output
- **16:9 슬라이드만** (PowerPoint standard 13.333" × 7.5", 참조 해상도 1920 × 1080 px). 다른 비율은 무효.

### Brand Assets (mandatory)
- **Logo**: 우상단에 원본 transparent PNG **있는 그대로**. 아래 위반 금지:
  - 배경 박스 / 밑줄 / 그림자 / 광택 / 보더 / 프레임
  - 색상 변경 / 그라데이션 / 투명도 변경 / 배경 채우기
  - crop / stretch / skew / rotate / duplicate
- **Logo 허용 작업만**: aspect-locked uniform scaling (≈1.22" × 0.24") + dark BG일 때 uniform white inversion.
- **Typography**: Pretendard ONLY. DM Sans / Outfit / Poppins / Roboto / Noto / system defaults 금지. Weight(100~900)로 모든 위계 표현.

### Slide Skeleton — 잠금 좌표 (모든 슬라이드 공통)

| Zone | Y 범위 | 내용 | 스타일 |
|---|---|---|---|
| Header strip | 0.4"–0.7" | Chapter (L) · Logo (R) | Chapter: Pretendard 600 12pt `text_tertiary`. Logo: original PNG, ≈1.22"×0.24", top-right ≈0.5" from right |
| Headline | 1.0"–1.75" | 대제목 | Pretendard 700 32–40pt `text_primary` line-height 1.20 |
| Subtitle | 1.63"–2.03" | 부제목 (one-sentence lead) | Pretendard 500 16pt `text_secondary` line-height 1.45 |
| Body | 2.39"–6.85" | 모든 본문 콘텐츠 | Mixed (§5 참조) |
| Clearance buffer | 6.85"–7.05" | **반드시 빈 채로** | — |
| Footer strip | 7.05"–7.3" | Page num (L) · Source (R) | Page: Pretendard 500 10pt `text_tertiary`. Source: Pretendard 400 9–10pt `text_tertiary` |

**Vertical rhythm**: Header → Headline 0.3" (loose). Headline zone → Subtitle zone 0.1" zone-to-zone (시각 gap ≈0.13"). Subtitle bottom → Body top 0.36" (medium). 비균일 리듬이 타이틀 블록을 슬라이드 anchor로 만든다.

**Lock rule**: 5개 zone은 슬라이드 간 좌표가 절대 바뀌지 않는다. Override는 section divider / full-bleed cover / closing slide만 허용 — "body가 길어서"는 사유 안 됨, 슬라이드 분할로 해결.

**Hard boundary**: Body는 2.39"–6.85" 안에만. 상단 zone 침범 / 하단 buffer · footer 침범 금지. 4.46" 높이 초과 시 분할.

### Body Density Rule
하단 body box를 반쯤 비워두지 말 것. 차트 / 다이어그램 / KPI 타일 / 비교 표 / dual-column으로 채워라. 단 **body box 안에서만 채우기** — 6.85" 아래로, 2.39" 위로 침범 금지.

콘텐츠가 얇을 때 사용할 density 전술:
- 사이드 패널에 supporting evidence (quote, data point, mini-chart, source)
- 하단에 "So What" callout box (6.85" 이내)
- 다이어그램으로 headline 시각 보강
- claim / evidence 2-column 분할
- Pattern F (Stacked Insight Layers, §5) — body box 안 3개 수평 band

장식용 shape / stock illustration으로 가짜 density 만들지 말 것.

### Visualization-First Rule (강한 default)
데이터 / 비교 / 프로세스 / 구조 / 관계가 있는 슬라이드는 **시각화**가 강제. 산문 나열 금지.

**Trigger**: 다음 중 하나라도 해당하면 시각화 필수.
- 2개 이상 숫자 비교 → chart 또는 KPI 타일 row
- 시간 추세 → line chart 또는 timeline (2–3 point도 OK)
- 구성 / 비중 → bar, donut, 100% stacked bar
- 프로세스 / 순서 → horizontal arrow flow, numbered stages
- 카테고리 비교 → grouped/stacked bar (table 보다 chart 선호)
- 구조적 관계 → diagram, matrix, 2×2
- 지리 / 계층 → map, tree, org chart

**Visualization priority order**:
1. Charts (bar / line / area / scatter / donut) — default
2. KPI tiles with sparklines
3. Diagrams (flow, sequence, 2×2, layered architecture, funnel, hierarchy)
4. Annotated images / screenshots
5. Tables — last resort

**Constraints**:
- Body box 내부에만
- 슬라이드당 visualization 1–2개 max
- 각 차트/다이어그램: title (Pretendard 600 14pt) + axis labels (400 10pt `text_secondary`) + source line (400 9pt `text_tertiary`)
- 9pt 미만 폰트 필요하면 데이터 과다 — 분할
- Pure-prose body는 section opener / hero takeaway / single-quote callout / definition에만

---

## 1. Slide Type Catalog

전체 슬라이드 타입은 5개로 단순화. 모두 잠금 5-zone 스켈레톤을 따른다.

| Type | 용도 | Body 구성 |
|---|---|---|
| `cover` | 표지 | Hero gradient card (Pattern E variant) |
| `section_divider` | 섹션 표지 | Override 허용 (full-bleed dark or gradient) |
| `content` | 본문 | Body Pattern A–F 중 1개 선택 |
| `hero_takeaway` | 단일 메시지 | Pull-quote + supporting evidence (Pattern E) |
| `closing` | 클로징 | Override 허용 (full-bleed dark or gradient) |

---

## 2. `cover` — 표지

- 배경: `palette.bg_primary` (`#ffffff`)
- Header strip / Footer strip 5-zone 규칙 그대로 (Chapter 없으면 left blank, page num 표시)
- Headline (1.0"–1.75"): 프로젝트명 / 발주처 — Pretendard 700 40pt `text_primary`
- Subtitle (1.63"–2.03"): 한 줄 lead — Pretendard 500 16pt `text_secondary`
- Body box (2.39"–6.85"): **단일 hero card with Hero Gradient**
  - Position: 중앙 정렬, 너비 ~9", 높이 ~3.5"
  - Background: `gradient.hero` (135°, blue spectrum)
  - Radius: 24px
  - Shadow: `brand_glow` (rgba(44,30,116,0.16) 0px 0px 15px)
  - 안에 핵심 KPI 또는 메시지 — Pretendard 700 48pt `bg_primary` (white) + 라벨 Pretendard 500 12pt rgba(255,255,255,0.85)
- Logo: top-right ≈0.5" right, y≈0.44", original PNG

데이터 필드: `title`, `date`, `subtitle`, `hero_kpi` (선택, `{value: string, label: string}`)

---

## 3. `section_divider` — 섹션 표지

- Override OK. 두 가지 옵션:
  - **Option A — Dark**: 전체 `palette.text_dark_bg` (`#181e25`)
  - **Option B — Gradient**: 전체 `gradient.hero` (premium)
- Section number: top-left, Pretendard 600 14pt rgba(255,255,255,0.6)
- Logo: top-right, **white-inverted variant** (uniform color inversion만 허용)
- Section title: 중앙 정렬, Pretendard 700 56pt `bg_primary`
- Section lead: title 아래, Pretendard 500 22pt rgba(255,255,255,0.7), line-height 1.45
- Page number: bottom-left, rgba(255,255,255,0.6)

데이터 필드: `number` (예: `"01"`), `title` (예: `"환경분석"`), `lead` (선택)

권장: `number`는 `"01"~"04"` 형식 (한 글자 `"I"` 등은 가독성 저하).

---

## 4. `content` — 본문 슬라이드

5-zone 잠금. Body box (2.39"–6.85", 12.333" × 4.46") 안에서 6 patterns 중 1개 선택.

### Pattern A — KPI Strip + Detail (가장 흔함)

| 요소 | 위치 | 스타일 |
|---|---|---|
| KPI row | body top, h ≈ 1.6" | 3–4 card, 각 ~3" × 1.6", white BG, 13px radius, `shadow.standard`, padding 20px |
| KPI number | card 내부 | Pretendard 700 32pt `palette.brand_blue` |
| KPI label | KPI number 아래 | Pretendard 500 11pt `text_secondary` |
| Bottom half | y ≈ 4.3"–6.85" | 차트(primary `chart_palette.primary`) 또는 2-column claim/evidence |

### Pattern B — Two-Column Compare

| 요소 | 위치 | 스타일 |
|---|---|---|
| Left column | x=0.5", w=5.5" | Header Pretendard 600 18pt `text_primary`, bullets 400 13pt `text_primary` line-height 1.50 |
| Right column | x=6.4", w=5.5" | 같은 구조 + 차트/다이어그램 |
| (선택) So What callout | body bottom 전폭, h≈0.7" | BG `bg_divider`, 13px radius, padding 16px, Pretendard 600 14pt `text_primary` |

### Pattern C — Diagram-Centered

| 요소 | 위치 | 스타일 |
|---|---|---|
| Centered diagram | body 70% | 다이어그램이 시각 hero |
| Caption boxes (3–4) | 다이어그램 주변 | 각 부분 설명, Pretendard 400 12pt |
| Bottom strip | body bottom 0.6" | Source + summary takeaway |

### Pattern D — Process Flow

| 요소 | 위치 | 스타일 |
|---|---|---|
| Stage circles (4–6) | body 상단 1/3 | 각 stage: numbered circle, label, 1–2 line desc |
| Arrows | circle 간 연결 | `palette.blue_300`, 2pt |
| Outcomes summary | body 하단 | Pull-quote 또는 결과 KPI |

### Pattern E — Quote + Evidence

| 요소 | 위치 | 스타일 |
|---|---|---|
| Pull-quote | 좌측 50% | Pretendard 500 24–28pt `text_primary` |
| Evidence stack | 우측 50% | 2–3 data card stack, white BG 13px radius |

### Pattern F — Stacked Insight Layers (얇은 콘텐츠 density 보강)

| 요소 | 위치 | 스타일 |
|---|---|---|
| Top band | body 상단 1/3 | KPI summary (1 row, 3–4 card) |
| Middle band | body 중단 1/3 | 1개 chart 또는 diagram |
| Bottom band | body 하단 1/3 | 3-up evidence card (claim + 1-line proof + source) |

데이터 필드 (`content` 공통):
- `chapter` (header strip 좌측)
- `headline`
- `subtitle`
- `pattern` (`"A"`/`"B"`/`"C"`/`"D"`/`"E"`/`"F"`)
- `body` (pattern별 schema 따름, §6 참조)
- `source` (선택, footer 우측)

---

## 5. `hero_takeaway` — 단일 메시지

`content` + Pattern E의 특수 케이스. 사용 빈도 낮음 (덱 전체 1–2장).

- Headline은 일반 content보다 큼 (Pretendard 700 48pt)
- Pull-quote가 body 70% 차지
- 우측에 1개 supporting card만 (또는 KPI 1개)

---

## 6. `closing` — 클로징

- Override OK. `section_divider`와 동일한 두 옵션:
  - Dark `#181e25` 또는 Hero Gradient
- Message: 중앙 정렬, Pretendard 700 56pt `bg_primary`
- Tagline: message 아래, Pretendard 500 22pt rgba(255,255,255,0.7)
- Logo: top-right white-inverted

데이터 필드: `message` (default `"감사합니다"`), `tagline`

---

## 7. Component Specifications

### Buttons / Pills
- **Pill Primary Dark**: BG `text_dark_bg`, text white, 11px 20px padding, 8px radius, Pretendard 600 13–14pt
- **Pill Nav**: BG `rgba(0,0,0,0.05)`, text `text_heading`, radius 9999px, Pretendard 500 11–12pt
- **Pill White**: BG white, text `rgba(24,30,37,0.8)`, radius 9999px

### Content Cards
- **Standard**: BG white, 13–16px radius, `shadow.standard`, padding 16–24px
- **Featured**: BG vivid gradient or white, 20–24px radius, `shadow.brand_glow`
- **Data (chart container)**: BG white, 13px radius, 1px border `palette.border`, title row (600 14pt), source row (400 9pt)

### Charts
- Primary series: `chart_palette.primary` (`#1456f0`) 또는 `chart_palette.secondary` (`#3b82f6`)
- Secondary: `tertiary` / `quaternary` / `deep`
- Comparison: `comparison` (`#ea5ec1`) 또는 `neutral`
- Gridline: `gridline`, 1px
- Axis labels: Pretendard 400 10pt `text_secondary`
- Data labels: Pretendard 600 11pt `text_primary`
- Source 인용: 차트 아래 9–10pt `text_tertiary`
- **차트에 Hero Gradient 적용 금지** (false hierarchy 발생). 차트는 flat 색만.

### Tables
- Header: BG `bg_divider`, Pretendard 600 12pt `text_primary`
- Body: 400 12pt, alternating BG white/#fafafa (선택)
- Row divider: 1px `palette.border`. **세로 divider 없음**
- Cell padding: 8px 12px

### Hero Gradient — 사용 규칙
- Linear-gradient(135°), 3 stops [#1456f0, #3b82f6, #60a5fa]
- 허용 위치 (덱 전체 최대 3개):
  1. Cover hero card
  2. Section divider 배경
  3. Featured KPI card (슬라이드당 1개)
- 금지 위치: chart 데이터 / headline·body 텍스트 / header·footer / 일반 content card
- 사용 시 `shadow.brand_glow` 와 함께. 위 텍스트는 white 500–700.
- Gradient card는 20–24px radius 사용 (큰 쪽).

### Depth & Elevation

| Level | Shadow token | Use |
|---|---|---|
| 0 — Flat | none | 배경, in-flow text |
| 1 — Subtle | `shadow.standard` | Standard cards |
| 2 — Ambient | `shadow.soft_glow` | 주변 부드러운 glow |
| 3 — Brand Glow | `shadow.brand_glow` | Featured/takeaway (슬라이드당 1개만) |
| 4 — Elevated | `shadow.elevated` | Hero, hover-equivalent |

### Border Radius Scale (px)
4 / 8 / 13 / 16 / 20 / 24 / 32 / 9999. body card 기본 13–16px, hero card 20–24px, pill 9999px.

### Spacing Scale (px)
Base 4. Steps: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64 / 80. Card gap 16–24px, internal padding 16–24px.

---

## 8. Validation (prepare_deck.py --validate)

- 모든 슬라이드 5-zone 좌표 동일 (override 슬라이드 제외)
- Body 콘텐츠 2.39"–6.85" 범위 내
- Header strip · Footer strip 6.85" 클리어런스 침범 없음
- Hero Gradient 요소 ≤ 3 (덱 전체)
- Hero Gradient 차트/텍스트에 적용 안 됨
- 슬라이드당 visualization 1–2개 (데이터 슬라이드 0개 = 경고)
- Chart에 axis labels + source line 있음
- 폰트는 Pretendard만
- Logo가 top-right, 추가 장식 없음
- Pretendard 폰트가 `.pptx`에 임베드됨

---

## 9. Do's and Don'ts

### Do
- 5 zone을 모든 슬라이드에서 동일 좌표로 잠금
- Body box를 dense하게 채우기 (차트 / KPI / 2-col / evidence stack)
- Pretendard weight로만 hierarchy 표현
- Pill radius 9999px / button 8px / content 16–24px
- Brand Glow shadow는 슬라이드당 1개 featured에만
- Body 400–500 기본, 700은 emphasis와 KPI 숫자에만
- 모든 데이터 source는 9–10pt `text_tertiary` 인용

### Don't
- Body bottom 20–30% 비워두기 (restructure하거나 evidence 추가)
- Pretendard 외 폰트 (DM Sans / Outfit / Poppins / Roboto / Noto / system) 금지
- 5-zone 좌표 슬라이드별로 흩어짐 금지
- 2.39" 위 / 6.85" 아래로 body 침범 금지
- Brand pink (`ea5ec1`) body text / 버튼 적용 금지 (장식만)
- Card sharp corner (radius ≥ 8px, body 13–24px)
- Shadow opacity > 0.16
- Hero Gradient를 chart bar / text / 일반 card에 적용 금지
- Hero Gradient 슬라이드당 1개, 덱 전체 최대 3개
- Gradient angle / stops / colors 변경 금지
- 장식 shape / stock illustration으로 가짜 density
- 두 번째 display family 추가 금지
- Weight 800–900 body heading 사용 (closing / divider에만)
- **Emoji 사용 금지** (슬라이드 어디에도)

---

## 10. Export Notes

- 16:9 only. 4:3 / 1:1 / 9:16 / A4 / letter 등 거부
- Export 해상도: 1920 × 1080 px minimum
- **Pretendard 폰트 임베드 필수** (PowerPoint Save options → Embed fonts)
- 모든 chart text + data label은 live text (raster 금지)

---

End of blueprints v2. 모든 슬라이드에 일관되게 적용.
