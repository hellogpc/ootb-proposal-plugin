---
name: rfp-to-proposal-pipeline
description: "MUST USE for creating 오오티비랩 proposal decks from RFPs. Takes an RFP / 제안요청서 / 과업지시서 / 공고 (PDF or text), finds 3 similar past proposals via proposal-supabase-sync, synthesizes outline.yaml, then delegates to anthropic-skills:pptx for .pptx rendering (using bundled brand_tokens.json + brand_design.md as the OOTB design reference). ALWAYS use when user says: '제안서 만들어줘', '제안서 초안 짜줘', 'PPT 초안 뽑아줘', 'PPT 로 만들어줘', '슬라이드 초안', '피치덱', '과업지시서 로 초안', 'RFP 로 초안', '이번 과제로 제안서', '비슷한 거 참고해서', '같은 포맷으로'. Requires proposal-supabase-sync + Supabase MCP + anthropic-skills:pptx."
---

# RFP → Proposal Pipeline

This skill is a thin **orchestrator**. It doesn't reimplement DB or PPT logic — it chains:

1. **`proposal-supabase-sync`** (via Supabase MCP) — search past proposals, fetch content.
2. **`anthropic-skills:pptx`** — build the final `.pptx` from outline.yaml using OOTB brand reference (`references/brand_tokens.json` + `references/brand_design.md`).

Claude is the synthesis engine in the middle. `prep_rfp.py` handles PDF text extraction only — structured extraction and embedding are handled by Claude + `gemini_embed_vault()` in DB. PPT 렌더링은 Claude 가 `anthropic-skills:pptx` 의 pptxgenjs 가이드 + 본 스킬의 brand reference를 합쳐 직접 코드 생성·실행.

## Preconditions (check before starting)

- Supabase MCP is connected (look for `mcp__supabase__execute_sql` availability).
- `proposals` table exists and has ≥ 1 ingested past proposal (ask: "DB에 과거 제안서가 몇 건 있나요?" → run `select count(*) from proposals;`).
- Supabase Edge Function `embed` 가 배포되어 있고 환경변수 `GEMINI_API_KEY` 가 등록되어 있음 (Project Settings → Functions → Secrets). 로컬 `GEMINI_API_KEY` 불필요.
- `anthropic-skills:pptx` 가 Claude Cowork에서 사용 가능 (Anthropic 제공 기본 스킬).

If none of the above, stop and direct the user to the relevant skill first.

## The workflow (6 steps)

Paths below assume the sibling skill lives next to this one:

```
오오티비랩/
├── proposal-supabase-sync/
└── rfp-to-proposal-pipeline/     ← you are here
                                     (PPT 렌더링은 anthropic-skills:pptx 사용)
```

### Step 1 — Prep the RFP (local + Claude)

**1-a. 텍스트 추출** (Python — Gemini 불필요):
```bash
cd rfp-to-proposal-pipeline/scripts
python prep_rfp.py /abs/path/to/RFP.pdf -o /tmp/rfp.json
```
출력: `{rfp_full_text, page_count, file_name}`

**1-b. 구조화 추출** (Claude): `/tmp/rfp.json`의 `rfp_full_text`를 읽고 아래 필드 추출:

```
project_title     사업명
issuing_org       발주기관
industry          분야
scope_of_work     과업범위 5~12개
target_audience   주요 타깃
budget_krw        예산(원) 또는 null
duration          사업기간
deadline          제안 마감 YYYY-MM-DD
evaluation_criteria 평가항목/배점
required_deliverables 필수 산출물
keywords          검색 키워드 6~15개
summary           3~5 문장 요약
```

**1-c. `query_text` 구성** (Claude): 키워드 나열 대신 한 문단 서술문으로:
```
"{project_title} — {issuing_org}이 발주한 {industry} 분야 사업. {summary} 주요 과업: {scope_of_work 상위 5개}. 타깃: {target_audience}."
```
→ 이 `query_text`가 Step 2의 `gemini_embed_vault()` 입력으로 사용됨.

### Step 2 — Find top-3 similar past proposals (via MCP)

Read `/tmp/rfp.json`. `gemini_embed_vault()` DB 함수가 Gemini 임베딩을 DB 내부에서 직접 생성하므로, 로컬 Python 실행 없이 MCP SQL 한 번으로 처리:

```python
mcp__supabase__execute_sql(
    project_id = "<ref>",
    query = f"""
        select id, title, client_name, project_year, industry, tags,
               hybrid_score, vec_score, kw_score, abstract, signed_url
        from match_proposals_with_url(
          query_text          => $q$ {rfp.query_text} $q$,
          query_embedding     => gemini_embed_vault($q$ {rfp.query_text} $q$),
          match_count         => 3,
          vec_weight          => 0.8,
          kw_weight           => 0.2,
          url_expires_seconds => 3600
        );
    """
)
```

(`$q$ ... $q$` 는 Postgres dollar-quoting — RFP 본문에 작은따옴표가 있어도 안전.)

`vec_weight=0.8, kw_weight=0.2` 이유: `search_tsv`가 `simple` config를 사용해 한국어 형태소 분리 불가 → `kw_score` 항상 ~0 → 벡터에 더 높은 가중치.

`match_proposals_with_url`이 없으면 `match_proposals(...)` 를 같은 방식으로 호출 (signed_url 생략).

If fewer than 3 rows return, continue with what we have; tell the user "유사 사례 N건 발견".

### Step 3 — Fetch full content for those 3 IDs

```python
ids = [r["id"] for r in step2_result]
mcp__supabase__execute_sql(
    project_id = "<ref>",
    query = f"""
        select id, title, project_year, client_name, industry, tags,
               abstract, key_points, objectives, strategy, deliverables,
               service_category, budget_krw
        from proposals
        where id in ({",".join(str(i) for i in ids)})
        order by array_position(array[{",".join(str(i) for i in ids)}], id);
    """
)
```

You now have, in memory:
- The new RFP's structured fields + summary (from `/tmp/rfp.json`).
- Three past proposals' abstracts, key_points, strategies, deliverables.

### Step 4 — Synthesize `outline.yaml` (you, Claude, write this)

Read `references/synthesis_guide.md` for how to compose the YAML. High-level:

- Use the **RFP's own title / year / client / industry** as the spine.
- Mine the three past proposals for **reusable motifs** (e.g., "방송기자 출신 크리에이터 협업", "월간 2편 이상 숏폼 업로드", "KPI 대시보드 주간 공유"). Pull the ones that actually fit the new RFP's 과업범위 and tag set — don't copy blindly.
- **Use OOTB v2 schema only**: `cover → section_divider × N → (content | hero_takeaway) × M → closing`. 5 types only — `toc`, `hero`, `content_image` (v1) **사용 금지**.
- **Each `content` slide MUST specify `pattern: "A"~"F"`** matching the content shape (numbers→A, compare→B, diagram→C, process→D, quote→E, stacked narrative→F). See synthesis_guide.md Pattern Rubric + NG conditions.
- **Diversity rule**: same pattern ≤ 2 consecutive; balance A·B·D·F across the deck; Pattern F ratio ≤ 30%.
- **Visualization-first**: 숫자·비교·프로세스가 있으면 산문 나열 금지. RFP 의 평가배점·단계어·타깃 다중 등에서 시각화 raw input 적극 추출.
- **Cite the source.** In each content slide's body, add `(ref: past#<id>)` if a phrase was materially drawn from one of the three past proposals. 각 슬라이드에 `source` 필드도 명시 (footer 우측).

Write the outline to `/tmp/outline_<YYYYMMDD>.yaml` (or a user-specified path).

### Step 5 (optional) — Extract reference palette

유사 제안서의 **시각 스타일**(지배 색상)까지 새 덱에 반영하고 싶으면 `analyze_reference.py` 로 PDF(로컬 경로 또는 Step 2의 signed URL)를 분석해 `reference_palette.json` 을 만듭니다.

```bash
python scripts/analyze_reference.py \
  --url "<signed_url_A>" "<signed_url_B>" \
  -o /tmp/reference_palette.json \
  -t /tmp/reference_thumbs/
```

출력은 `per_deck`(덱마다 추출된 역할별 색) + `consensus`(덱 간 공통), 그리고 Claude 가 시각 검토할 수 있는 슬라이드 썸네일 JPG들. 이 JSON 의 `consensus` 값을 Step 6 에서 Claude 가 직접 읽어 `references/brand_tokens.json` 의 `palette` 위에 비-null 값만 덮어쓴 뒤 pptxgenjs 코드에 반영합니다.

### Step 6 — Render to .pptx (anthropic-skills:pptx)

PPT 렌더링은 **Claude 의 기본 `anthropic-skills:pptx` 스킬** 에 위임합니다. 별도 빌드 스크립트 없이 Claude 가 pptxgenjs 코드를 생성·실행해 `.pptx` 를 만듭니다.

Claude 가 해야 할 일:

1. `anthropic-skills:pptx/pptxgenjs.md` 를 읽어 pptxgenjs API 파악
2. 본 스킬의 **brand reference** 두 개를 함께 읽어 OOTB 디자인 시스템 반영:
   - `references/brand_tokens.json` — 색상 / 폰트 / 사이즈 / 레이아웃 토큰 (Brandlogy v2)
   - `references/brand_design.md` — 5-zone locked skeleton + 6 body patterns + Visualization-First Rule
3. (선택) Step 5 의 `reference_palette.json` 이 있으면 `brand_tokens.json.palette` 위에 비-null 값으로 덮어쓰기
4. `/tmp/outline_<YYYYMMDD>.yaml` 의 각 슬라이드를 brand_design.md 의 5-zone + 6 pattern 규칙에 따라 pptxgenjs 코드로 렌더링
5. `/abs/path/to/<project>_초안.pptx` 로 저장

핵심 제약 (brand_design.md 의 §0 참조):
- 16:9 LAYOUT_WIDE 만
- Pretendard only
- Logo 원본 PNG 그대로 (배경 박스 / 밑줄 / 그림자 / 색변 / crop 금지)
- 5-zone 좌표 모든 슬라이드 동일 (section divider / cover / closing 만 override 가능)
- Body 2.39"–6.85" 안에만, 위·아래 zone 침범 금지
- 데이터/비교/프로세스 슬라이드는 **차트 강제** (산문 나열 금지)
- Hero Gradient 덱 전체 최대 3개

### Step 7 — QA (optional but recommended)

생성된 `.pptx` 를 LibreOffice/PowerPoint 에서 열어 시각 검수:
- 5-zone 좌표 일관성 (Header / Headline / Subtitle / Body / Footer)
- Body box 내 콘텐츠 (위 2.39", 아래 6.85" 침범 없음)
- Logo 추가 장식 없음 (원본 PNG 그대로)
- Pretendard 임베드 확인
- 차트 데이터 라벨 가독성 (9pt 이상)

문제가 보이면 outline.yaml 수정 후 Step 6 재실행.

## Files in this skill

- `SKILL.md` — this file.
- `scripts/prep_rfp.py` — RFP PDF → JSON (text extraction).
- `scripts/analyze_reference.py` — reference PDFs → dominant color palette + thumbnails.
- `scripts/requirements.txt` — Python deps (`pdfplumber`, `python-dotenv`, plus `Pillow`, `scikit-learn`, `numpy`, `requests` for `analyze_reference.py`).
- `references/workflow.md` — compact step-by-step playbook (for Claude to re-read mid-run if context gets fuzzy).
- `references/synthesis_guide.md` — heuristics for composing v2 outline.yaml from the RFP + 3 past proposals (Pattern A–F rubric + NG conditions + diversity budget + v2 template).
- `references/brand_design.md` — OOTB v2 design system (5-zone locked skeleton + 6 body patterns + Visualization-First Rule). Read in Step 6.
- `references/brand_tokens.json` — OOTB brand tokens (palette / fonts / sizes / layout). Read in Step 6.

## When to deviate from the default workflow

- **No past proposals yet.** Skip Steps 2–3. Feed Step 4 with only the RFP + `references/brand_design.md` (5-zone skeleton + 6 patterns) as the structural guide. Tell the user the output is a zero-shot draft — weaker than the full pipeline.
- **RFP is actually a paragraph, not a PDF.** Skip Step 1 (prep_rfp.py). Use the paragraph text directly as `rfp.query_text` in Step 2's `gemini_embed_vault()` call. Write the structured fields yourself from what the user pasted, then jump to Step 2.
- **User wants more than 3 references.** Override `match_count => 5` or `10`. More references make synthesis richer but diminishing returns past ~5.
- **User disagrees with the synthesis.** The outline.yaml is the source of truth — edit it directly, re-run Step 6 (render). Don't regenerate from scratch.

## Honesty guardrails (read this)

A real RFP response depends on accurate 예산, 일정, KPI, 사례. The pipeline will happily synthesize confident-sounding numbers if you let it. Don't.

- **예산/숫자**: never fabricate. Copy only if the past proposal's `budget_krw` is provided AND the new RFP's scope is comparable. Otherwise leave `[금액 확인 필요]`.
- **사례 재사용**: if you surface a stat from a past proposal ("2024년 쇼츠 200편 제작, 총 조회수 2M"), mark it as `(ref: 2025_복지로)` so the user knows to verify it's OK to quote.
- **조직/인물명**: don't put real names (방송기자, 인플루언서) in the draft unless they appear in an attributed past proposal AND you clearly cite the source.
- **마감일**: if the RFP deadline is in the RFP, put it on the cover; do not invent one.
