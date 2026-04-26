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
- 슬라이드 순서: cover → toc → section_divider × N → hero × 선택 → content × M → content_image × 선택 → closing
- YAML 을 쓰고 반드시 자체 검토:
  - [ ] project.title 이 RFP 의 `project_title` 과 일치
  - [ ] project.date 가 RFP 의 `deadline` 과 일치 (있다면)
  - [ ] TOC 의 items 수 == section_divider 의 수
  - [ ] content 슬라이드 각각 body.length ∈ [2, 4]
  - [ ] hero 슬라이드 총 1~2 장 이내

### Step 5 — analyze reference (선택)
- [ ] 사용자가 "기존 덱 색 따라가게 해줘" / "같은 스타일로" 요청 시에만 실행
- [ ] Step 2 결과의 `signed_url` 을 `--url` 인자로 넘기면 됨 (로컬 PDF 경로도 OK)
- [ ] `per_deck` 내 각 덱의 `roles` 가 너무 편향되면(검정/흰색이 '색' 역할을 차지) consensus 주입 결과가 밋밋해질 수 있음 → 그럴 땐 skip

### Step 6 — prepare deck plan
- [ ] `prepare_deck.py outline.yaml -o deck_plan.json` exit code 0
- [ ] Step 5 의 palette JSON 이 있으면 `--reference-palette` 로 주입
- [ ] 검증 에러 메시지(TOC 수·body 길이·연속 번호)를 그대로 사용자에게 노출
- [ ] `--validate` 만 따로 돌려 사전 체크 가능

### Step 7 — render to .pptx
- [ ] `node render_deck.js deck_plan.json -o output.pptx` 성공
- [ ] 사전에 `cd ootb-proposal-pptx/scripts && npm install` 완료 (최초 1회)

### Step 8 — QA
- [ ] `quickcheck.py` 로 생성된 `slide-*.jpg` 를 눈으로 확인
- 자주 나는 문제:
  - hero 의 headline 이 7 자 이상이면 줄바꿈 → 문구 축약 또는 `brand/brand.json` 의 `hero_headline` 사이즈 조정
  - content 의 body 가 4개 초과 → 2 개 슬라이드로 분리
  - 한국어 tofu → 뷰어 머신에 Pretendard/Noto Sans KR 설치 여부 안내

## 안티패턴

- Step 4 에서 RFP 의 예산/숫자 없이 자체 추정값 채우기 ❌
- Step 3 결과를 그대로 번역·복붙 ❌ (출처 표기 없이 타 기관 사례 재사용)
- Step 6 전에 YAML 문법 오류 미검증 → `yaml.safe_load` 메시지를 그대로 사용자에게 전달
- Step 7 에서 `_legacy/build.py` 사용 ❌ (PowerPoint strict validator 경고 유발; `render_deck.js` 사용)
