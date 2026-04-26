---
name: proposal-supabase-sync
description: "MUST USE for OOTB proposal DB tasks. Ingests 제안서 PDFs into Supabase `proposals` table and runs hybrid (vector + keyword + metadata) search via Supabase MCP. Triggers: (a) REGISTER — '이 PDF 등록해줘', 'DB에 넣어줘', '제안서 수집', 'PDF 쌓아줘'; (b) SEARCH — '복지로 관련 제안서', '수산 관련 제안서', '과거 제안서 검색', '제안서 몇 건 있어', '태그 통계'; (c) FIRST SETUP — 'DB 처음 셋업', 'proposals 테이블 만들어줘', 'Vault helper'. Requires Supabase MCP connected. Do NOT use for non-proposal documents."
---

# Proposal ↔ Supabase Sync (MCP edition)

This skill ingests 제안서 PDFs into Supabase and searches them, delegating all DB work to the **Supabase MCP server**. The user does **not** run DB scripts — Claude performs DB operations directly via MCP tools.

Local Python does only what MCP can't: PDF text extraction, Gemini structured extraction, Gemini embedding, and binary Storage upload over HTTP (since MCP's JSON-RPC can't stream binary).

## When to use

- "DB 처음 셋업해줘" → run Path A (migration)
- "이 PDF 제안서 DB에 넣어줘" → run Path B (ingest)
- "복지로 관련 제안서 찾아줘", "수산 관련 최근 거 뭐 있지?" → run Path C (search)

If the Supabase MCP is not connected, stop and call `suggest_connectors` for Supabase first. Every Path below assumes Supabase MCP is live.

## Prerequisites

1. **Supabase MCP connected** in Cowork/Claude Desktop (check via `/mcp` or Cowork settings). The MCP tools appear under the `supabase` namespace (`apply_migration`, `execute_sql`, `list_tables`, `list_projects`, etc.).
2. **.env filled in** at `scripts/.env`:
   - `GEMINI_API_KEY` (always required)
   - `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (required only if uploading PDF originals to Storage — which is the default)
3. **Python deps**: `pip install -r scripts/requirements.txt`

Claude: if any of these are missing, stop and ask the user to fix them before proceeding.

## Path A — First-time DB setup (apply migration)

1. Read `sql/001_init.sql`.
2. Call `mcp__supabase__list_projects` if the user hasn't pinned a project; ask them which to use.
3. Call `mcp__supabase__apply_migration` with:
   - `project_id`: the chosen project ref
   - `name`: `"proposals_init"`
   - `query`: the full contents of `sql/001_init.sql`
4. Verify with `mcp__supabase__list_tables` — `public.proposals` should appear.
5. Confirm the RPC exists: `mcp__supabase__execute_sql` with
   `select proname from pg_proc where proname = 'match_proposals';` — should return one row.

If `apply_migration` returns an "extension already exists" warning, that's fine — the SQL is idempotent.

### Path A-2 (optional) — DB-side embedding helper

Apply `sql/002_embed_in_db.sql` only when the local Python environment cannot
reach Gemini (sandbox / CI with egress restrictions). It installs the `http`
extension and a `public.gemini_embed(text, key)` function that POSTs to Gemini
from inside Postgres. **Read the security warning in that file** — the API
key ends up in query logs; rotate the Gemini key after use or move on to A-3.

### Path A-3 (strongly recommended after A-2) — Vault-based helpers

Apply `sql/003_vault_helpers.sql`. This adds three helpers that read keys from
Supabase Vault instead of accepting them as parameters:

- `public.gemini_embed_vault(text) → vector(1536)` — replaces the parametric
  `gemini_embed(text, key)` in day-to-day use.
- `public.sign_storage_url(bucket, path, expires_seconds) → text` — returns a
  fresh signed URL for a Storage object.
- `public.match_proposals_with_url(...)` — same args as `match_proposals` plus
  `url_expires_seconds`; returns an additional `signed_url` column per row
  (null for rows whose `storage_path` is still a `file://` placeholder).

One-time Vault setup (run once in SQL editor or via `execute_sql`):

```sql
select vault.create_secret('<GEMINI_API_KEY>', 'gemini_api_key', 'Gemini embed');
select vault.create_secret('<SERVICE_ROLE_KEY>', 'supabase_service_role_key', 'Sign URL');
```

After this, every subsequent SQL call uses these secrets silently; keys no
longer appear in query text or `pg_stat_statements`.

## Path B — Ingest PDFs

For each PDF the user wants to add:

### Path B-1 (default) — Local Gemini (Python)

1. **Prep locally** (Python):
   ```bash
   cd scripts
   python prep.py /abs/path/to/file.pdf --out /tmp/proposal_$HASH.json
   ```
   `prep.py` does:
   - SHA-256 of file (for dedup)
   - Extract text with `pdfplumber`
   - Gemini structured extraction (strict JSON schema)
   - Gemini embedding (1536 dims via Matryoshka)
   - (default) Upload the PDF to Supabase Storage bucket `proposals` via HTTP using `SUPABASE_SERVICE_ROLE_KEY`
   - Emit a JSON payload that includes a **pre-built SQL `sql_upsert` statement** — Claude just forwards it to MCP.

2. **Read the JSON** (you now have `{file_hash, storage_path, title, ..., sql_upsert}`).

3. **Check for duplicates** (optional, recommended):
   ```
   mcp__supabase__execute_sql:
     query: select id from proposals where file_hash = '<hash>';
   ```
   If a row exists and user didn't say "force", tell them it's already ingested.

4. **Upsert via MCP**:
   ```
   mcp__supabase__execute_sql:
     query: <contents of payload.sql_upsert>
   ```
   The statement is `INSERT ... ON CONFLICT (file_hash) DO UPDATE SET ... RETURNING id`.

5. Report to user: "3건 등록 — id=[12,13,14]".

> **Note**: The SQL `sql_upsert` contains a large vector literal (~20 KB of floats). MCP handles this fine; do not try to summarize or truncate.

### Path B-2 (fallback) — DB-side Gemini (when local network is blocked)

Use this when `prep.py` fails on `httpx.ProxyError` / `403 Forbidden` toward `generativelanguage.googleapis.com` (typical in restricted sandboxes/CI).

Prerequisite: apply Path A-2 once.

1. Extract text + synthesize metadata locally **without** calling Gemini. Either run `prep.py --no-upload --skip-embed` (if available) or have Claude read the PDF text via `pdfplumber` and build the structured metadata itself. Produce the same field set as Path B-1, **minus** the `embedding` vector literal.
2. Build the UPSERT SQL with `public.gemini_embed(<embed_input>, <key>)` inline in place of the vector literal:
   ```sql
   insert into public.proposals (..., embedding, ...)
   values (..., public.gemini_embed('TITLE: ...\nABSTRACT: ...\n...', 'AIza...'), ...)
   on conflict (file_hash) do update set ...;
   ```
3. Execute via `mcp__supabase__execute_sql`. The DB calls Gemini from its own network and stores the vector.
4. **Rotate the Gemini key** once ingestion is done (the key appears in query logs).
5. Storage upload is not possible via the DB. Store `storage_path = 'file:///<name>.pdf'` temporarily, then run Path B-3 below from a machine with network access.

### Path B-3 — Storage backfill (no Gemini calls)

When rows exist but `storage_path` is a `file://` placeholder (typical after B-2), upload originals and patch the rows without re-embedding:

```bash
cd scripts
python upload_storage.py /abs/path/to/*.pdf
```

Per file this script: SHA-256s locally → looks up matching row via PostgREST → uploads to `proposals/<year>/<filename>` with `x-upsert: true` → PATCHes `storage_bucket`/`storage_path` on the row. Gemini key is not required. Run from a host that can reach `*.supabase.co` (typically the user's Mac).

## Path C — Search

Two sub-paths depending on whether an embedding is worth it:

### C-1 (default) Hybrid — embed + keyword + filters

1. Embed the query:
   ```bash
   cd scripts
   python embed_query.py "복지로 SNS 숏폼 전략" > /tmp/q.vec
   ```
   Output is a single line: `[0.012,-0.134,...]`.

2. Build SQL using the `match_proposals` RPC and call MCP:
   ```
   mcp__supabase__execute_sql:
     query: |
       select * from match_proposals(
         query_text       => '복지로 SNS 숏폼 전략',
         query_embedding  => '<paste vec>'::vector(1536),
         filter_year_min  => 2024,
         filter_industry  => '복지',
         filter_tags      => null,
         match_count      => 10
       );
   ```

3. Present results to the user with title, year, client_name, hybrid_score, and a 1-line abstract each.

### C-2 Keyword-only (no Gemini call)

Skip `embed_query.py` entirely. Useful for precise Korean keyword queries ("수산물이력제") or when Gemini is down:

```
mcp__supabase__execute_sql:
  query: |
    select id, title, client_name, project_year, tags,
           ts_rank_cd(search_tsv, plainto_tsquery('simple', '수산물이력제')) as score,
           abstract
    from proposals
    where search_tsv @@ plainto_tsquery('simple', '수산물이력제')
      and project_year >= 2025
    order by score desc
    limit 10;
```

## Path D — Ad-hoc inspection

Because MCP is connected, the user can just ask things and you answer via `execute_sql`:

- "몇 건 들어 있지?" → `select count(*) from proposals;`
- "2026년에 우리가 제안한 복지 관련 사업 목록" → `select title, client_name from proposals where project_year = 2026 and industry = '복지' order by submitted_at desc;`
- "태그 통계" → `select tag, count(*) from proposals, unnest(tags) t(tag) group by tag order by 2 desc;`

Prefer `execute_sql` with small explicit `select` over pulling whole rows.

## Files

- `SKILL.md` — this file.
- `sql/001_init.sql` — full schema bootstrap, feed into `apply_migration` on first use.
- `scripts/prep.py` — local PDF → text → Gemini → (optional Storage upload) → JSON with `sql_upsert`.
- `scripts/embed_query.py` — query string → Gemini embedding → vector literal on stdout.
- `scripts/requirements.txt` — `pdfplumber`, `google-genai`, `python-dotenv`, `requests` (no `supabase-py`).
- `scripts/.env.example` — env template.
- `references/mcp_playbook.md` — exact MCP call parameters for each Path (read this if unsure of the tool name or arg shape).

## Design notes (why this split)

- **SQL through MCP, binary through HTTP.** MCP JSON-RPC is great for SQL and project admin but wasn't designed for streaming 10–30 MB PDF bytes. Storage upload stays in Python over `POST /storage/v1/object/proposals/...`.
- **Gemini stays in Python.** MCP doesn't expose Gemini; we need LLM calls anyway for both structured extraction and embeddings, so the Python prep step carries them.
- **Single-user schema.** No `owner_id`, no RLS policies — this matches a single-developer proposal library and keeps MCP's admin context a good fit. Adding RLS later is additive (add column + policies) and doesn't break anything here.
- **Idempotent by `file_hash`.** Same PDF uploaded twice just UPDATEs the row. Different content = different hash = new row.

## Common failure modes

- **"ERROR: relation proposals does not exist"** — Path A wasn't run. Run it.
- **"auth error" from MCP** — Supabase MCP OAuth session expired. Tell user to reconnect in Cowork settings.
- **Vector literal rejected with "dimension mismatch"** — `EMBED_DIM` in `.env` diverged from `vector(1536)` in init SQL. Rebuild embeddings or alter column.
- **Storage upload 413 Payload Too Large** — bucket file size limit hit. Default is 100 MB; raise in `sql/001_init.sql` (`file_size_limit`) and reapply, or skip storage upload with `prep.py --no-upload`.
