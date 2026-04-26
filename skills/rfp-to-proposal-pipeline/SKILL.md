---
name: rfp-to-proposal-pipeline
description: "MUST USE for creating 오오티비랩 proposal decks from RFPs. Takes an RFP / 제안요청서 / 과업지시서 / 공고 (PDF or text), finds 3 similar past proposals via proposal-supabase-sync, synthesizes OOTB-format outline.yaml + .pptx via ootb-proposal-pptx. ALWAYS use (do NOT fall back to generic pptx) when user says: '제안서 만들어줘', '제안서 초안 짜줘', 'PPT 초안 뽑아줘', 'PPT 로 만들어줘', '슬라이드 초안', '피치덱', '과업지시서 로 초안', 'RFP 로 초안', '이번 과제로 제안서', '비슷한 거 참고해서', '같은 포맷으로'. Requires sibling skills + Supabase MCP. Do NOT use for non-proposal decks."
---

# RFP → Proposal Pipeline

This skill is a thin **orchestrator**. It doesn't reimplement DB or PPT logic — it chains the sibling skills:

1. **`proposal-supabase-sync`** (via Supabase MCP) — search past proposals, fetch content.
2. **`ootb-proposal-pptx`** — build the final `.pptx` from a YAML outline.

Claude is the synthesis engine in the middle. A single small helper `prep_rfp.py` lives here because it needs a different Gemini schema (RFP-specific fields, not 제안서 fields) than the sibling skills.

## Preconditions (check before starting)

- Supabase MCP is connected (look for `mcp__supabase__execute_sql` availability).
- `proposals` table exists and has ≥ 1 ingested past proposal (ask: "DB에 과거 제안서가 몇 건 있나요?" → run `select count(*) from proposals;`).
- `proposal-supabase-sync/scripts/.env` has `GEMINI_API_KEY`.
- `ootb-proposal-pptx/scripts/` requirements installed.

If none of the above, stop and direct the user to the relevant skill first.

## The workflow (6 steps)

Paths below assume the two sibling skills live next to this one:

```
오오티비랩/
├── proposal-supabase-sync/
├── ootb-proposal-pptx/
└── rfp-to-proposal-pipeline/     ← you are here
```

### Step 1 — Prep the RFP (local)

```bash
cd rfp-to-proposal-pipeline/scripts
cp ../../proposal-supabase-sync/scripts/.env .env        # share Gemini key
python prep_rfp.py /abs/path/to/RFP.pdf -o /tmp/rfp.json
```

`prep_rfp.py` extracts:
- `rfp_meta` — 사업명, 발주기관, 과업범위, 예산, 일정, 타깃, 평가항목 (structured JSON)
- `rfp_summary` — 3~5 문장 요약 (used later as synthesis context)
- `query_text` — keyword string for tsvector search
- `query_embedding` — 1536-dim vector literal for hybrid search

### Step 2 — Find top-3 similar past proposals (via MCP)

Read `/tmp/rfp.json`. Then call MCP. **Prefer `match_proposals_with_url`** when
the sibling skill's `sql/003_vault_helpers.sql` has been applied — you'll get
signed URLs to the original PDFs for free:

```python
mcp__supabase__execute_sql(
    project_id = "<ref>",
    query = f"""
        select id, title, client_name, project_year, industry, tags,
               hybrid_score, vec_score, kw_score, abstract, signed_url
        from match_proposals_with_url(
          query_text        => $q$ {rfp.query_text} $q$,
          query_embedding   => '{rfp.query_embedding}'::vector(1536),
          match_count       => 3,
          url_expires_seconds => 3600
        );
    """
)
```

If Vault helpers aren't available, fall back to `match_proposals(...)` without
`signed_url` and either (a) ship `storage_path` to the user for manual Dashboard
access, or (b) call `public.sign_storage_url()` per-row.

(`$q$ ... $q$` is Postgres dollar-quoting — safe because RFP text may contain single quotes.)

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
- Preserve OOTB format: `cover → toc → section_divider → hero → content × N → content_image × M → closing`.
- For each `content` slide, produce 2–4 flow-box blocks (heading + text). This is where past `strategy` / `key_points` become the raw material — rephrased for the new context, not pasted.
- **Cite the source.** In each content slide's body text, add a trailing `(ref: <past proposal id>)` if a phrase was materially drawn from one of the three; this makes it obvious to the user where to fact-check.

Write the outline to `/tmp/outline_<YYYYMMDD>.yaml` (or a user-specified path).

### Step 5 (optional) — Extract reference palette

유사 제안서의 **시각 스타일**(지배 색상)까지 새 덱에 반영하고 싶으면 `analyze_reference.py` 로 PDF(로컬 경로 또는 Step 2의 signed URL)를 분석해 `reference_palette.json` 을 만듭니다.

```bash
python scripts/analyze_reference.py \
  --url "<signed_url_A>" "<signed_url_B>" \
  -o /tmp/reference_palette.json \
  -t /tmp/reference_thumbs/
```

출력은 `per_deck`(덱마다 추출된 역할별 색) + `consensus`(덱 간 공통), 그리고 Claude 가 시각 검토할 수 있는 슬라이드 썸네일 JPG들. 이 JSON 을 Step 6 의 `prepare_deck.py --reference-palette` 에 넘기면 `brand.palette` 위에 덮어씌웁니다 (null 값은 스킵).

### Step 6 — Build the deck_plan.json (ootb-proposal-pptx)

```bash
python ../../ootb-proposal-pptx/scripts/prepare_deck.py \
  /tmp/outline_<YYYYMMDD>.yaml \
  --reference-palette /tmp/reference_palette.json   # Step 5 를 건너뛰었다면 생략 가능
  -o /tmp/deck_plan_<YYYYMMDD>.json
```

`prepare_deck.py` 는 구조 검증(TOC 수, content body 2~4, hero ≤ 2, section number 연속)도 함께 수행합니다.

### Step 7 — Render to .pptx (ootb-proposal-pptx, pptxgenjs)

```bash
cd ../../ootb-proposal-pptx/scripts
node render_deck.js /tmp/deck_plan_<YYYYMMDD>.json \
  -o /abs/path/to/<project>_초안.pptx
```

pptxgenjs 가 `anthropic-skills:pptx` 의 표준 경로이므로 PowerPoint 에서 경고 없이 열립니다.

### Step 8 — QA (optional but recommended)

```bash
python ../../ootb-proposal-pptx/scripts/quickcheck.py /abs/path/to/<project>_초안.pptx
```

Inspect the rendered JPGs for overflow / overlap. If a `content` slide has too many bullets, split it and rerun Step 7.

## Files in this skill

- `SKILL.md` — this file.
- `scripts/prep_rfp.py` — RFP → JSON (structured fields + summary + query vector).
- `scripts/analyze_reference.py` — reference PDFs → dominant color palette + thumbnails.
- `scripts/requirements.txt` — same deps as sibling skills (`pdfplumber`, `google-genai`, `python-dotenv`, plus `Pillow`, `scikit-learn`, `requests` for `analyze_reference.py`).
- `references/workflow.md` — compact step-by-step playbook (for Claude to re-read mid-run if context gets fuzzy).
- `references/synthesis_guide.md` — heuristics for composing the outline.yaml from the RFP + 3 past proposals.

## When to deviate from the default workflow

- **No past proposals yet.** Skip Steps 2–3. Feed Step 4 with only the RFP + `ootb-proposal-pptx/templates/outline.example.yaml` as structural guide. Tell the user the output is a zero-shot draft — weaker than the full pipeline.
- **RFP is actually a paragraph, not a PDF.** Skip Step 1 (prep_rfp.py). Run `embed_query.py` from `proposal-supabase-sync/scripts/` on the paragraph to get the vector, write the structured fields yourself from what the user pasted, then jump to Step 2.
- **User wants more than 3 references.** Override `match_count => 5` or `10`. More references make synthesis richer but diminishing returns past ~5.
- **User disagrees with the synthesis.** The outline.yaml is the source of truth — edit it directly, re-run Step 5. Don't regenerate from scratch.

## Honesty guardrails (read this)

A real RFP response depends on accurate 예산, 일정, KPI, 사례. The pipeline will happily synthesize confident-sounding numbers if you let it. Don't.

- **예산/숫자**: never fabricate. Copy only if the past proposal's `budget_krw` is provided AND the new RFP's scope is comparable. Otherwise leave `[금액 확인 필요]`.
- **사례 재사용**: if you surface a stat from a past proposal ("2024년 쇼츠 200편 제작, 총 조회수 2M"), mark it as `(ref: 2025_복지로)` so the user knows to verify it's OK to quote.
- **조직/인물명**: don't put real names (방송기자, 인플루언서) in the draft unless they appear in an attributed past proposal AND you clearly cite the source.
- **마감일**: if the RFP deadline is in the RFP, put it on the cover; do not invent one.
