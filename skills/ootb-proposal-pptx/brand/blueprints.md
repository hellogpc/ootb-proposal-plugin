# OOTB Lab — Slide Blueprints (for pptxgenjs rendering)

이 문서는 **렌더링 엔진**이 각 슬라이드 타입을 어떻게 그려야 하는지를 정의한다. `ootb-proposal-pptx` 스킬은 이 문서의 내용을 그대로 `anthropic-skills:pptx`의 pptxgenjs 가이드(`pptxgenjs.md`)와 함께 사용해 최종 `.pptx`를 만든다.

단위: **인치(inches)**. 좌표계는 슬라이드 좌상단 (0,0), 우하단 (W=13.333, H=7.5).

모든 색은 `brand.palette.*` 토큰 참조. 모든 폰트 크기는 `brand.sizes_pt.*` 토큰 참조.

## Global rules

- **텍스트박스는 margin: 0**. 도형/아이콘과 정렬이 맞아야 하므로 padding 제거.
- **한글 텍스트에는 `fontFace` 외에 `eastAsiaFontFace`를 같이** 설정 (pptxgenjs 옵션 부재 시 XML 후처리로 `<a:ea>` 삽입). Latin=`brand.fonts.latin`, EA=`brand.fonts.east_asian`.
- **accent underline 사용 금지** (AI-generated 느낌). 간격과 크기로 구분.
- 슬라이드 사이즈는 `LAYOUT_WIDE` (13.333" × 7.5").

---

## 1) `cover`

대형 표지. Dark background.

| 요소 | 위치/크기 | 스타일 |
|---|---|---|
| 배경 | 전체 | `palette.navy_deep` solid |
| 배경 이미지 (선택) | 전체 bleed | `data.background` 또는 `brand.cover_bg` 지정 시 — 덮어쓰기 |
| 악센트 평행사변형 바 | x=-1.0, y=1.2, w=7.0, h=0.12 | `PARALLELOGRAM`, fill `palette.blue`, line none |
| 타이틀 | x=1.2, y=2.4, w=11.0, h=2.4 | `sizes_pt.cover_title` / bold / color `palette.white` / center-align / middle-anchor |
| 날짜 | x=1.2, y=5.8, w=11.0, h=0.4 | `sizes_pt.cover_date` / color `palette.white` / center |
| 회사명 | x=1.2, y=6.3, w=11.0, h=0.4 | `sizes_pt.cover_company` / bold / color `palette.blue_light` / center |
| 마스코트 (선택) | x=0.5, y=4.5, w=2.6 | `assets/mascot.png` 있으면 삽입 |

데이터 필드:
- `title` (없으면 `project.title`)
- `date`  (없으면 `project.date`)
- `company` (없으면 `brand.company_name`)

---

## 2) `toc`

Index 페이지. Light background.

| 요소 | 위치/크기 | 스타일 |
|---|---|---|
| 배경 | 전체 | `palette.bg_light` |
| "Index" 라벨 | x=1.5, y=1.2, w=3.5, h=1.2 | `sizes_pt.toc_label` / bold / `palette.blue` / center / middle-anchor |
| (항목 i) 번호 배지 | x=5.8, y= (1.4 + i × 1.10), w=0.9, h=0.95 | `ROUNDED_RECTANGLE` rectRadius=0.15, fill `palette.blue`, 안에 텍스트 `"01"`/`"02"`.. `sizes_pt.toc_num` / bold / `palette.white` / center / middle-anchor |
| (항목 i) 이름 | x=7.2, y=같음, w=5.5, h=0.95 | `sizes_pt.toc_item` / bold / `palette.navy_deep` / left / middle-anchor |
| 우상단 회사명 | x=(W−2.7), y=0.3, w=2.2, h=0.4 | `sizes_pt.breadcrumb`×1.1 / bold / `palette.navy_deep` / right |

데이터 필드: `items: [string, ...]` (권장 4개)

항목 수(N)에 따라 `row_h=0.95, gap=0.15` 고정. N이 5 이상이면 row_h를 `(5.0 − 0.15×(N−1)) / N` 으로 축소해 영역에 맞춤.

---

## 3) `section_divider`

섹션 표지. Dark background.

| 요소 | 위치/크기 | 스타일 |
|---|---|---|
| 배경 | 전체 | `palette.navy_deep` |
| 배경 이미지 (선택) | 전체 | `assets/section_bg.jpg` 있으면 사용 |
| 번호 | x=0, y=2.3, w=W, h=1.5 | `sizes_pt.section_num` / bold / `palette.blue_light` / center / middle-anchor |
| 액센트 얇은 바 | x=(W−0.6)/2, y=3.5, w=0.6, h=0.04 | fill `palette.blue` |
| 타이틀 | x=0, y=3.6, w=W, h=1.5 | `sizes_pt.section_title` / bold / `palette.white` / center / middle-anchor |

데이터 필드: `number` (예: `"I"`, `"01"`), `title` (예: `"환경분석"`)

권장: `number`는 `"01"`/`"02"`/`"03"`/`"04"` 형식. `"I"` 한 글자는 세로 얇은 획이 되어 가독이 떨어지므로 지양.

---

## 4) `hero`

단일 큰 메시지. Blue background.

| 요소 | 위치/크기 | 스타일 |
|---|---|---|
| 배경 | 전체 | `palette.blue_bright` |
| eyebrow | x=1.0, y=1.8, w=11.3, h=0.5 | `sizes_pt.hero_eyebrow` / color `palette.blue_light` / center |
| headline | x=1.0, y=2.4, w=11.3, h=1.9 | `sizes_pt.hero_headline` / bold / `palette.white` / center / middle-anchor |
| subheadline | x=1.0, y=4.9, w=11.3, h=1.2 | `sizes_pt.hero_sub` / bold / center / wrap |

`highlight` 필드가 지정되고 `subheadline` 안에 해당 문자열이 포함되면, 3개의 run으로 분할:
1. before 부분: `palette.white`
2. highlight 부분: `palette.navy_deep` + **흰색 배경 하이라이트** (텍스트박스 바로 뒤에 폭=대강 `(len(highlight)×0.14)` 인치 × 높이 0.55인치의 `RECTANGLE` fill=palette.white를 놓는다 — z-index 낮게)
3. after 부분: `palette.white`

highlight용 배경 박스의 x,y를 정확히 구하려면 텍스트 측정이 필요한데, 대안으로 간단하게 `palette.navy_deep` 색만으로 강조해도 OK. contrast가 살면 배경 박스 생략 가능.

---

## 5) `content`

본문 플로우 (2~4 블록). Light background + 하단 dark 컨테이너에 원형 노드들.

| 요소 | 위치/크기 | 스타일 |
|---|---|---|
| 배경 | 전체 | `palette.bg_light` |
| breadcrumb | x=`M_LEFT`, y=0.3, w=8.0, h=0.3 | `sizes_pt.breadcrumb` / `palette.text_muted` / left |
| 타이틀 | x=`M_LEFT`, y=0.9, w=(W−M_LEFT−M_RIGHT), h=1.4 | `sizes_pt.content_title` / bold / `palette.navy_deep` |
| 컨테이너 rect | x=`M_LEFT`, y=2.6, w=(W−M_LEFT−M_RIGHT), h=4.2 | fill `palette.navy_deep`, line none |
| 컨테이너 하단 액센트 바 | 같은 x/w, y=(2.6+4.2−0.05), h=0.05 | fill `palette.blue` |
| 우상단 회사명/로고 | x=(W−2.7), y=0.3, w=2.2, h=0.4 | 상동 |

컨테이너 내부, N개 블록 (1 ≤ N ≤ 4):

- `col_w = container_w / N`
- `circle_d = 2.0` (인치)
- `top_pad = 0.6`

블록 i별:
- `cx = container_x + col_w × i + (col_w − circle_d)/2`
- `cy = container_y + top_pad`
- **외부 원**: `OVAL` at (cx, cy, circle_d, circle_d), fill = `i % 2 == 1 ? palette.blue : palette.navy`
- **내부 원**: `OVAL` at (cx+0.15, cy+0.15, circle_d−0.3, circle_d−0.3), fill = `i % 2 == 1 ? palette.white : palette.navy_soft`
- **heading 텍스트** (원 안): x=cx, y=(cy + circle_d × 0.32), w=circle_d, h=0.45 — `"[{heading}]"` — `sizes_pt.flow_heading` / bold / center / middle-anchor / color = `i % 2 == 1 ? palette.navy_deep : palette.blue_light`
- **body 텍스트** (원 아래): x=(container_x + col_w × i + 0.1), y=(cy + circle_d + 0.1), w=(col_w − 0.2), h=1.3 — `sizes_pt.flow_body` / bold / `palette.white` / center / top-anchor / wrap
- **화살표** (i < N−1일 때): LINE at (cx + circle_d + 0.05, cy + circle_d/2) → (container_x + col_w × (i+1) + (col_w − circle_d)/2 − 0.05, 같은 y), color `palette.blue_light`, width 2pt

데이터 필드:
- `breadcrumb` (예: `"환경분석 | 과업의 배경"`)
- `title`
- `body: [{ heading: string, text: string }, ...]` (2~4개)

---

## 6) `content_image`

좌우 이미지 + 텍스트. Light background.

공통 상단부(breadcrumb · title · 우상단 회사명)는 `content`와 동일.

하단 2단:
- `col_w = (W − M_LEFT − M_RIGHT − 0.5) / 2`
- `top = 2.7`, `h = 3.8`
- `pos = data.image_position ∈ {left, right}` (default right)
- `pos == "right"` 이면:
  - 텍스트 영역: x=`M_LEFT`, y=top, w=col_w, h=h
  - 이미지 영역: x=(W − M_RIGHT − col_w), y=top, w=col_w, h=h
- `pos == "left"` 이면 반대

**이미지 영역**:
- `data.image` 경로가 주어지고 파일이 존재: `slide.addImage(path, x, y, w, h)` (sizing contain)
- 없으면 placeholder — `ROUNDED_RECTANGLE` fill `palette.blue_light` + 중앙 텍스트 `"(image)"` 14pt `palette.navy`

**텍스트 영역**:
- `sizes_pt.img_body` / `palette.text_dark` / left / top-anchor / wrap

`text` 가 여러 줄일 경우 `\n`으로 분리해 breakLine 처리. `· ` 접두사는 그대로 둔다 (불릿 스타일 X).

데이터 필드: `breadcrumb`, `title`, `text`, `image` (선택), `image_position` (`"left"`/`"right"`, default right)

---

## 7) `closing`

클로징 슬라이드. Dark background.

| 요소 | 위치/크기 | 스타일 |
|---|---|---|
| 배경 | 전체 | `palette.navy_deep` |
| message | x=0, y=2.8, w=W, h=1.5 | `sizes_pt.closing` / bold / `palette.white` / center / middle-anchor |
| tagline | x=0, y=4.4, w=W, h=0.8 | `sizes_pt.closing_tagline` / `palette.blue_light` / center |
| 마스코트 (선택) | x=0.5, y=3.0, w=2.8 | `assets/mascot.png` 있으면 |

데이터 필드: `message` (default `"감사합니다"`), `tagline`

---

## Asset paths (선택)

`brand.assets_dir` (혹은 outline.yaml 옆 `assets/`) 에서 아래 파일이 있으면 자동 사용:

| File | 쓰이는 곳 |
|---|---|
| `logo.png` | 우상단 (content/toc/content_image 슬라이드) |
| `mascot.png` | cover · closing |
| `cover_bg.jpg` | cover 풀블리드 |
| `section_bg.jpg` | section_divider 풀블리드 |

모두 없어도 정상 동작 (fall-back은 pure shape 렌더).

---

## Validation

- section_divider 의 `number` 는 연속 (예: `"01","02","03","04"` 또는 `"I","II","III","IV"`).
- TOC 항목 수 = section_divider 수.
- `content.body` 길이는 2~4.
- 각 `content.body[].text` 길이는 약 80자 이내 (오버하면 슬라이드 분할 권장).
- hero 슬라이드는 덱 전체에 1~2장까지만 (synthesis_guide 참조).

렌더링 전 `prepare_deck.py --validate` 가 위 규칙을 체크한다.
