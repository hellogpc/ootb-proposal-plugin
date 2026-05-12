# 워크플로우 플레이북 (Claude 전용)

스킬을 실행 중 컨텍스트가 흐릿해지면 이 파일을 다시 읽어 정확한 순서를 복원하세요.

## 한눈에 보기

```
[RFP.pdf]
    │
    ▼
Step 1  prep_rfp.py              → /tmp/rfp.json
        (pdfplumber + Gemini)      { rfp_meta, rfp_summary, query_text, query_embedding }
    │
    ▼
Step 2  Supabase MCP             → top-K similar 제안서
        (match_proposals_with_url) { id, hybrid_score, abstract, signed_url }
    │
    ▼
Step 3  Supabase MCP             → 해당 ID들의 full content
        (SELECT FROM proposals)   { abstract, key_points, strategy, deliverables }
    │
    ▼
Step 4  synthesize outline.yaml   (Claude 추론; synthesis_guide.md 참조)
        → /tmp/outline_YYYYMMDD.yaml
    │
    ▼
Step 5  analyze_reference.py     → /tmp/reference_palette.json  [선택]
        (Storage signed URL → 썸네일 → K-means 지배색 추출)
    │
    ▼
Step 6  prepare_deck.py          → /tmp/deck_plan_YYYYMMDD.json
        (outline + brand.json + [reference_palette] → 검증된 deck plan)
    │
    ▼
Step 7  render_deck.js           → /path/<project>_초안.pptx
        (pptxgenjs; anthropic-skills:pptx 표준 경로)
    │
    ▼
Step 8  quickcheck.py            → slide-*.jpg (시각 점검)
```

## 각 단계 체크리스트

### Step 1 — prep
- [ ] `prep_rfp.py` 실행 성공, JSON 유효
- [ ] `rfp_meta.project_title`, `.summary`, `.keywords` 비어있지 않음
- [ ] `query_embedding` 길이 ≈ 17KB (1536 floats × 약 11 chars)

### Step 2 — similar search
- [ ] `match_count => 3` (기본) 또는 사용자 요청에 따라 `=> 5`/`=> 10`
- [ ] `match_proposals_with_url` 사용 시 `signed_url` 가 포함되는지 확인
- [ ] `hybrid_score` 가 극단적으로 낮으면 (< 0.1) 사용자에게 "적절한 참고 사례가 부족합니다" 경고
- [ ] 0 건 반환이면 Step 4 에서 "유사 사례 없음" 경고 + zero-shot draft

### Step 3 — fetch context
- [ ] `in (...)` 에 정확히 top-K ID 전달
- [ ] 각 row 의 `key_points`, `strategy`, `deliverables` 가 비어있지 않은지 확인 (비어있으면 해당 row 는 synthesis 에서 가중치 낮춤)

### Step 4 — synthesize outline
- `references/synthesis_guide.md` 를 읽고 작성
- 슬라이드 순서 (v2): cover → section_divider × N → content × M (Pattern A–F) → hero_takeaway × 0~2 → closing
- YAML 을 쓰고 반드시 자체 검토:
  - [ ] project.title 이 RFP 의 `project_title` 과 일치
  - [ ] project.date 가 RFP 의 `deadline` 과 일치 (있다면)
  - [ ] section_divider number 가 `"01"`/`"02"`... 연속
  - [ ] content 슬라이드는 Pattern A–F 중 하나 명시 (`pattern: "A"`)
  - [ ] hero_takeaway 슬라이드 총 1~2 장 이내
  - [ ] Hero Gradient 사용 요소 덱 전체 ≤ 3

### Step 5 — analyze reference (선택)
- [ ] 사용자가 "기존 덱 색 따라가게 해줘" / "같은 스타일로" 요청 시에만 실행
- [ ] Step 2 결과의 `signed_url` 을 `--url` 인자로 넘기면 됨 (로컬 PDF 경로도 OK)
- [ ] `per_deck` 내 각 덱의 `roles` 가 너무 편향되면(검정/흰색이 '색' 역할을 차지) consensus 주입 결과가 밋밋해질 수 있음 → 그럴 땐 skip

### Step 6 — render to .pptx (anthropic-skills:pptx)
- [ ] `anthropic-skills:pptx/pptxgenjs.md` 읽음
- [ ] `references/brand_tokens.json` + `references/brand_design.md` 읽음
- [ ] Step 5 palette JSON 이 있으면 `brand_tokens.palette` 위에 비-null 값으로 덮어쓰기
- [ ] 5-zone 좌표 모든 슬라이드 동일 (override 슬라이드 제외)
- [ ] Body 2.39"–6.85" 안에만 — 위·아래 zone 침범 없음
- [ ] 데이터/비교/프로세스 슬라이드 = 차트 또는 다이어그램 필수
- [ ] Hero Gradient 덱 전체 ≤ 3
- [ ] Logo 원본 PNG 그대로 (배경 박스 / 밑줄 / 그림자 / 색변 / crop 금지)
- [ ] Pretendard 만, 다른 폰트 금지
- [ ] `.pptx` 저장 후 PowerPoint 에서 경고 없이 열림

### Step 7 — QA
- [ ] LibreOffice 또는 PowerPoint 로 열어 5-zone 정합성 검수
- 자주 나는 문제:
  - headline 한 줄 안 들어감 → Pretendard 32–40pt 사이에서 줄이거나 문구 축약
  - body 가 6.85" 아래 침범 → Pattern F (Stacked Insight) 로 재구성 또는 슬라이드 분할
  - 차트 데이터라벨 9pt 미만 → 차트 데이터 너무 많음, 분할 필요
  - 한국어 tofu → `.pptx` 에 Pretendard 임베드 (Save options → Embed fonts) 확인

## 안티패턴

- Step 4 에서 RFP 의 예산/숫자 없이 자체 추정값 채우기 ❌
- Step 3 결과를 그대로 번역·복붙 ❌ (출처 표기 없이 타 기관 사례 재사용)
- Step 6 전에 YAML 문법 오류 미검증 → `yaml.safe_load` 메시지를 그대로 사용자에게 전달
- Step 7 에서 `_legacy/build.py` 사용 ❌ (PowerPoint strict validator 경고 유발; `render_deck.js` 사용)
