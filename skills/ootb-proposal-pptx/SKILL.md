---
name: ootb-proposal-pptx
description: "MUST USE for rendering OOTB 오오티비랩 proposal decks to .pptx (16:9 only). Brandlogy-inspired design system: 5-zone locked layout (Header/Headline/Subtitle/Body/Footer) + 6 body patterns (KPI strip / Two-column / Diagram-centered / Process flow / Quote+Evidence / Stacked insight) + visualization-first rule. White-dominant canvas, Pretendard-only, Hero Gradient accent. ALWAYS use when: (a) '이 outline 으로 pptx 빌드해줘', '제안서 슬라이드 뽑아줘', or (b) upstream rfp-to-proposal-pipeline needs final render. Brand tokens in brand/brand.json, layouts in brand/blueprints.md. Do NOT use for non-Korean decks, non-16:9 aspect ratios, or editing existing .pptx (use anthropic-skills:pptx)."
---

# OOTB Proposal PPT v2 (Brandlogy design system)

이 스킬은 **콘텐츠를 OOTB 디자인 시스템에 맞게 구조화**하고, 실제 `.pptx` 렌더링은 `anthropic-skills:pptx` (pptxgenjs 가이드) 에 위임한다.

```
입력 (outline.yaml)
     │
     ▼
[ootb-proposal-pptx]   ← 이 스킬 (브랜드 + 검증 + 정규화)
  prepare_deck.py       outline.yaml + brand/brand.json → deck_plan.json
     │
     ▼
[anthropic-skills:pptx] ← 렌더링 엔진 (pptxgenjs)
  deck_plan.json + brand/blueprints.md → output.pptx
     │
     ▼
   .pptx
```

분리의 이점:
- 브랜드 지식 (색·폰트·5-zone 레이아웃)은 `brand/` 한 곳에서 고정
- 렌더링은 Anthropic이 유지보수하는 범용 `pptx` 스킬이 담당 (PowerPoint 호환성 보장)
- 동일 `deck_plan.json` 으로 여러 렌더링 타깃 재사용 가능

## 핵심 원칙 (v2)

### 5-Zone Locked Skeleton (모든 슬라이드 공통)

| Zone | Y 범위 | 내용 |
|---|---|---|
| Header strip | 0.4"–0.7" | Chapter (L) · Logo (R) |
| Headline | 1.0"–1.75" | 대제목 (Pretendard 700 32–40pt) |
| Subtitle | 1.63"–2.03" | 부제목 (Pretendard 500 16pt) |
| Body | 2.39"–6.85" | 모든 콘텐츠 (4.46" 높이 박스) |
| Clearance | 6.85"–7.05" | **빈 채로 유지** |
| Footer | 7.05"–7.3" | Page num (L) · Source (R) |

좌표는 슬라이드 간 절대 바뀌지 않음 (section_divider · cover · closing은 override 허용).

### 6 Body Patterns

Body box 안에서 콘텐츠 구성은 6개 패턴 중 1개:
- **A. KPI Strip + Detail** (가장 흔함)
- **B. Two-Column Compare**
- **C. Diagram-Centered**
- **D. Process Flow**
- **E. Quote + Evidence**
- **F. Stacked Insight Layers** (얇은 콘텐츠 density 보강)

### Visualization-First Rule

데이터 / 비교 / 프로세스 / 구조가 있으면 **시각화 강제** (차트 / 다이어그램). 산문 나열 금지. 9pt 미만 폰트 필요하면 데이터 과다 → 슬라이드 분할.

### Pretendard-only

Pretendard 100~900 weight로 모든 hierarchy 표현. DM Sans / Outfit / Poppins / Roboto / Noto / system 금지.

### Hero Gradient (premium accent)

`linear-gradient(135°, #1456f0, #3b82f6, #60a5fa)`. 덱 전체 최대 3개 (cover hero card / section divider bg / 슬라이드당 featured KPI 1개). **차트/텍스트/header/footer 적용 금지**.

## Prerequisites

```bash
pip install -r scripts/requirements.txt   # pyyaml
cd scripts && npm install                 # pptxgenjs
# QA용 (선택): LibreOffice + pdftoppm + ImageMagick
```

## Workflow

### Step 1 — outline.yaml 작성

`templates/outline.example.yaml` 참고. 5개 슬라이드 타입만 허용:

| `type` | 용도 | 핵심 필드 |
|---|---|---|
| `cover` | 표지 (Hero Gradient card 옵션) | `title`, `subtitle`, `date`, `hero_kpi` (선택) |
| `section_divider` | 섹션 표지 (dark or gradient override) | `number`, `title`, `lead` (선택) |
| `content` | 본문 (Pattern A–F) | `chapter`, `headline`, `subtitle`, `pattern`, `body`, `source` |
| `hero_takeaway` | 단일 메시지 (Pattern E variant) | `chapter`, `headline`, `quote`, `evidence` |
| `closing` | 클로징 | `message`, `tagline` |

### Step 2 — 검증

```bash
cd scripts
python prepare_deck.py path/to/outline.yaml --validate
```

체크 항목:
- 5-zone 좌표 일관성
- Hero Gradient 요소 ≤ 3 (덱 전체)
- 데이터 슬라이드는 visualization 1개 이상
- Pretendard만 사용
- Logo 추가 장식 없음

### Step 3 — deck_plan.json 생성

```bash
python prepare_deck.py path/to/outline.yaml -o /path/to/deck_plan.json
```

`deck_plan.json` 구조:

```json
{
  "schema_version": "2.0",
  "brand":   { "slide": {...}, "palette": {...}, "gradient": {...}, "fonts": {...}, "sizes_pt": {...}, "weights": {...} },
  "project": { "title": "...", "date": "..." },
  "slides":  [
    { "type": "cover", "blueprint": "cover", "fields": { "title": "...", "hero_kpi": {...} } },
    { "type": "content", "blueprint": "content", "fields": { "pattern": "A", "headline": "...", "body": {...} } }
  ]
}
```

### Step 4 — `.pptx` 렌더링

#### 권장: anthropic-skills:pptx 직접 사용

1. `anthropic-skills:pptx/pptxgenjs.md` 읽기
2. `brand/blueprints.md` 읽기 (5-zone + 6 patterns + Visualization-First)
3. 두 가이드를 합쳐 pptxgenjs 스크립트 작성 및 실행

이 경로는 Body Pattern 별 layout 계산 + 차트 정밀 렌더링이 필요해 가장 안정적.

#### 보조: 번들 render_deck.js (단순 케이스용)

```bash
cd scripts && node render_deck.js /path/to/deck_plan.json -o /path/to/output.pptx
```

> `render_deck.js`는 v1 (navy 기반 7-type) 시절 참조 구현. v2 5-zone + 6 pattern은 일부만 커버되므로 복잡한 슬라이드는 4a 경로 권장.

### Step 5 — QA

```bash
python quickcheck.py /path/to/output.pptx
```

체크:
- 5-zone 좌표 시각 검사
- Body box 안 콘텐츠 (6.85" 침범 없음)
- Logo 추가 장식 없음
- Pretendard 임베드 확인
- 차트 데이터 라벨 가독성 (9pt 이상)

## Iteration Checklist (export 전)

1. Aspect 16:9? ✓
2. Pretendard만 사용? ✓
3. Logo top-right, 원본 PNG 그대로 (배경 박스 / 밑줄 / 그림자 / 색변 / crop 없음)? ✓
4. 5-zone 좌표 모든 슬라이드 동일? ✓
5. Body 2.39"–6.85" 안에만 (위·아래 zone 침범 없음)? ✓
6. Body box dense 채워짐 (하단 30% 비어있지 않음)? ✓
7. 데이터/비교/프로세스 슬라이드 = visualization 있음? ✓
8. 모든 데이터에 source line? ✓
9. Brand Glow 슬라이드당 1개? ✓
10. Hero Gradient 허용 위치만, 슬라이드당 1개, 덱 최대 3개? ✓
11. Headline 700 / Subtitle 500 / Body 400 위계 유지? ✓
12. Emoji 없음? ✓
13. Chart text live (raster 아님)? ✓

## Files

```
ootb-proposal-pptx/
├── SKILL.md                  # 이 파일
├── brand/
│   ├── brand.json            # v2 토큰 (5-zone + 6 patterns + Hero Gradient)
│   └── blueprints.md         # v2 레이아웃 가이드 (필독)
├── scripts/
│   ├── prepare_deck.py       # outline.yaml → deck_plan.json
│   ├── render_deck.js        # v1 참조 구현 (v2는 일부만 지원)
│   ├── quickcheck.py         # 시각 QA
│   ├── package.json          # pptxgenjs
│   └── requirements.txt      # PyYAML
├── templates/
│   └── outline.example.yaml  # 실사용 예시
└── assets/
    └── README.md             # 브랜드 에셋 네이밍
```

## Common failure modes

- **Logo에 검은/흰 박스가 보임** — 원본 PNG의 transparency가 깨졌거나 배경 fill이 들어감. 원본 다시 삽입.
- **헤드라인이 한 줄로 안 나옴** — 32–40pt 사이에서 본문에 맞춰 줄이거나 한 줄로 정리.
- **Body가 하단을 침범** — content 과다. Pattern F (Stacked Insight) 또는 슬라이드 분할.
- **차트 라벨 9pt 미만** — 데이터 너무 많음. 분할하거나 차트 단순화.
- **Pretendard □□□ 표시** — 뷰어 PC에 폰트 미설치. `.pptx` 임베드 확인.

## 마이그레이션 노트 (v1 → v2)

| v1 (이전) | v2 (현재) |
|---|---|
| 7 슬라이드 타입 (cover · toc · section_divider · hero · content · content_image · closing) | 5 타입 (cover · section_divider · content · hero_takeaway · closing) |
| Navy `#0F1E3C` + blue `#0087FF` 중심 | White-dominant + blue spectrum (`#1456f0` → `#60a5fa`) |
| Pretendard + Noto Sans KR fallback | Pretendard only (fallback 미허용) |
| 가변 레이아웃 | 5-zone locked skeleton |
| 자유 body | 6 patterns 중 1개 (A–F) |
| 산문 허용 | Visualization-first rule (데이터는 차트로) |
| `toc` 슬라이드 | 제거 (clean linear flow 권장) |
| `content_image` | `content` Pattern B (Two-Column Compare)로 흡수 |

v1 outline.yaml은 v2와 schema가 달라 직접 호환 안 됨. `prepare_deck.py --migrate` 옵션이 변환을 도와줌 (TODO).
