---
name: ootb-proposal-pptx
description: "MUST USE for rendering OOTB 오오티비랩 proposal decks to .pptx. Takes outline.yaml (or deck_plan.json), produces Korean proposal .pptx in OOTB brand format (navy cover + blue accents + Index + flow-circle content + closing). ALWAYS use — do NOT use generic pptx tools — when: (a) user requests BUILD from outline ('이 outline 으로 pptx 빌드해줘', '제안서 슬라이드 뽑아줘'), or (b) upstream rfp-to-proposal-pipeline needs final render. Delegates to pptxgenjs via bundled render_deck.js. Brand tokens in brand/brand.json, layouts in brand/blueprints.md. Do NOT use for non-proposal decks, non-Korean decks, or editing existing .pptx (use anthropic-skills:pptx editing.md for those)."
---

# OOTB Proposal PPT (extraction + delegation)

이 스킬은 **콘텐츠를 OOTB 포맷에 맞게 구조화**하는 데에 집중하고, 실제 `.pptx` 렌더링은 `anthropic-skills:pptx`(pptxgenjs 가이드)에 맡긴다.

```
입력 (outline.yaml)
     │
     ▼
[ootb-proposal-pptx]    ← 이 스킬 (브랜드 지식 + 검증 + 정규화)
  prepare_deck.py        outline.yaml + brand/brand.json → deck_plan.json
     │
     ▼
[anthropic-skills:pptx]  ← 렌더링 엔진 (pptxgenjs)
  render_deck.js         deck_plan.json + brand/blueprints.md → output.pptx
     │
     ▼
   .pptx  (PowerPoint에서 경고 없이 열림)
```

이 분리의 이점:
- **브랜드 지식** (색상·폰트·레이아웃)은 `brand/brand.json` + `brand/blueprints.md` 한 곳에 고정.
- **렌더링**은 Anthropic이 유지보수하는 범용 `pptx` 스킬이 담당 — PowerPoint 호환성 이슈가 잡힘.
- 동일한 `deck_plan.json` 으로 여러 렌더링 엔진(pptxgenjs, python-pptx, 혹은 새 타겟)으로 재사용 가능.

## Prerequisites

```bash
# prepare_deck 용
pip install -r scripts/requirements.txt     # pyyaml

# render_deck 용 (anthropic-skills:pptx와 동일한 스택)
cd scripts && npm install                   # pptxgenjs

# QA 용
# LibreOffice(soffice) + pdftoppm + ImageMagick (quickcheck.py 실행에 필요)
```

## 언제 쓰나

- "2026년 수산물이력제 제안서 PPT 초안 만들어줘"
- "지난번 복지로 제안서랑 같은 포맷으로 새 제안서 만들어줘"
- "outline.yaml 이 있으니 슬라이드로 뽑아줘"

범용 PPT 편집/생성이 필요하면 이 스킬 대신 `anthropic-skills:pptx`를 직접 사용.

## Workflow

### Step 1 — outline.yaml 작성

`templates/outline.example.yaml` 참고. 7개 슬라이드 타입만 허용:

| `type` | 용도 | 핵심 필드 |
|---|---|---|
| `cover` | 표지 | `project.title`, `project.date`, `brand.company_name` |
| `toc` | Index | `items: [string, ...]` (권장 4개) |
| `section_divider` | 섹션 표지 | `number` (권장 `"01"`/`"02"`... ), `title` |
| `hero` | 한 장짜리 메시지 | `eyebrow`, `headline`, `subheadline`, `highlight` |
| `content` | 본문 플로우 | `breadcrumb`, `title`, `body: [{heading, text}]` (2~4개) |
| `content_image` | 이미지 + 텍스트 | `breadcrumb`, `title`, `image`, `text`, `image_position` |
| `closing` | 감사합니다 | `message`, `tagline` |

### Step 2 — 검증 (선택, 권장)

```bash
cd scripts
python prepare_deck.py path/to/outline.yaml --validate
```

- content.body 길이 2~4 체크
- TOC 항목 수 = section_divider 수 체크
- hero 슬라이드 ≤ 2 체크
- section number 연속성 체크

### Step 3 — deck_plan.json 생성

```bash
cd scripts
python prepare_deck.py path/to/outline.yaml -o /path/to/deck_plan.json
```

`deck_plan.json` 은 렌더러가 바로 소비할 수 있는 JSON:

```json
{
  "schema_version": "1.0",
  "brand":   { "company_name": "...", "palette": {...}, "fonts": {...}, "sizes_pt": {...}, "slide": {...}, "assets_dir": "..." },
  "project": { "title": "...", "date": "..." },
  "slides":  [
    { "type": "cover", "blueprint": "cover", "fields": { "title": "...", "date": "...", "company": "..." } },
    { "type": "toc",   "blueprint": "toc",   "fields": { "items": ["...","..."] } },
    ...
  ]
}
```

필드는 이미 `project`/`brand`/`assets_dir` 와 병합 완료. 렌더러는 여기에 레이아웃 계산(좌표/크기)만 더하면 됨.

### Step 4 — `.pptx` 렌더링 (anthropic-skills:pptx에 위임)

두 가지 방법이 있다.

#### 4a) Claude가 anthropic-skills:pptx를 그대로 사용 (권장)

이 때 Claude는:
1. `anthropic-skills:pptx/pptxgenjs.md` 읽기 (pptxgenjs API)
2. `brand/blueprints.md` 읽기 (슬라이드 타입별 OOTB 레이아웃)
3. 두 지식을 합쳐 pptxgenjs 스크립트 작성 및 실행

좋은 점: 커스터마이즈 유연 (특정 슬라이드 한 장만 다르게 하고 싶을 때).

#### 4b) 번들된 참조 구현 사용 (빠른 경로)

```bash
cd scripts
node render_deck.js /path/to/deck_plan.json -o /path/to/output.pptx
```

`render_deck.js` 는 `blueprints.md` 의 모든 레시피를 pptxgenjs 로 구현한 **참조 구현**이다. 템플릿에서 벗어날 필요 없으면 이 쪽이 가장 빠름.

### Step 5 — QA

```bash
python quickcheck.py /path/to/output.pptx
```

LibreOffice + pdftoppm 로 슬라이드별 JPG 생성. 각 장을 눈으로 확인:
- 한글 텍스트 오버플로
- breadcrumb/로고 충돌
- content 플로우 4개 이상 과밀
- hero highlight 대비

문제 시 `outline.yaml` 수정 → Step 3 부터 재실행.

## Files

```
ootb-proposal-pptx/
├── SKILL.md                      # 이 파일
├── brand/
│   ├── brand.json                # 팔레트·폰트·사이즈 (기계 읽기용)
│   └── blueprints.md             # 슬라이드 타입별 렌더링 레시피
├── scripts/
│   ├── prepare_deck.py           # outline.yaml → deck_plan.json
│   ├── render_deck.js            # deck_plan.json → .pptx (pptxgenjs 참조 구현)
│   ├── package.json              # pptxgenjs 의존성
│   ├── requirements.txt          # PyYAML
│   ├── quickcheck.py             # 시각 QA (pptx → pdf → jpg)
│   └── _legacy/                  # (구) python-pptx 직접 빌드 스크립트 — 참고용
│       ├── build.py
│       ├── layouts.py
│       └── style.py
├── templates/
│   └── outline.example.yaml      # 실사용 예시 outline
└── assets/
    └── README.md                 # 브랜드 에셋 네이밍 규칙
```

## Design notes

- **Dominant color is navy `#0F1E3C`** (`palette.navy_deep`) with accent `#0087FF` (`palette.blue`). 변경은 `brand/brand.json` 에서만.
- **Typography**: Pretendard (fallback: Noto Sans KR → Malgun Gothic). 뷰어 PC에 폰트 없으면 시스템 기본으로 대체됨 — 배포 시 폰트 확보 공지.
- **Never accent underlines below titles** — AI-generated 느낌. 여백과 크기 위계로 구분.
- **Dark cover + closing, light content** — reference deck의 sandwich 패턴.

## Common failure modes

- **PPT가 열 때 "수정 필요" 다이얼로그**: (구) python-pptx 빌드 스크립트(`_legacy/build.py`)의 preset 도형 XML 출력이 PowerPoint strict validator에 경고를 던져 발생했음. pptxgenjs 파이프라인은 이 문제 없음.
- **한글이 □□□로 표시**: 뷰어 PC에 Pretendard/Noto Sans KR 미설치. 폰트 설치 안내.
- **content body 넘침**: body 5개 이상. 슬라이드 분할. `prepare_deck.py --validate` 가 잡아냄.

## 레거시 빌드 (deprecated)

과거의 `scripts/build.py` 는 python-pptx 로 `.pptx` 를 직접 만들었으나, PowerPoint 호환 이슈와 브랜드-렌더러 결합 문제로 `_legacy/` 로 이동. 필요 시 한시적으로 쓸 수 있으나 신규 작업에는 위의 pptxgenjs 경로 사용.
