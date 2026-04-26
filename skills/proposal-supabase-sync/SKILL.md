---
name: proposal-supabase-sync
description: "MUST USE for OOTB proposal DB tasks. Ingests 제안서 PDFs into Supabase `proposals` table and runs hybrid (vector + keyword + metadata) search via Supabase MCP. Triggers: (a) REGISTER — '이 PDF 등록해줘', 'DB에 넣어줘', '제안서 수집', 'PDF 쌓아줘'; (b) SEARCH — '복지로 관련 제안서', '수산 관련 제안서', '과거 제안서 검색', '제안서 몇 건 있어', '태그 통계'; (c) FIRST SETUP — 'DB 처음 셋업', 'proposals 테이블 만들어줘', 'Vault helper'. Requires Supabase MCP connected. Do NOT use for non-proposal documents."
---

# Proposal ↔ Supabase Sync (MCP edition)

This skill ingests 제안서 PDFs into Supabase and searches them, delegating all DB work to the **Supabase MCP server**. The user does **not** run DB scripts — Claude performs DB operations directly via MCP tools.

**Env-free 운영**: 로컬에 `GEMINI_API_KEY` / `SUPABASE_URL` / `SERVICE_ROLE_KEY` 불필요. 모든 인증은 Supabase Vault에 있고, Storage 업로드는 base64로 인코딩한 PDF를 MCP `execute_sql` 한 번에 보내 DB가 Edge Function을 호출하는 방식으로 처리합니다.

Local Python은 MCP가 못 하는 것만: PDF 텍스트 추출 + base64 인코딩.

## When to use

- "DB 처음 셋업해줘" → run Path A (migration)
- "이 PDF 제안서 DB에 넣어줘" → run Path B (ingest)
- "복지로 관련 제안서 찾아줘", "수산 관련 최근 거 뭐 있지?" → run Path C (search)

If the Supabase MCP is not connected, stop and call `suggest_connectors` for Supabase first. Every Path below assumes Supabase MCP is live.

## Prerequisites

1. **Supabase MCP connected** in Cowork/Claude Desktop (`/mcp` 또는 Cowork 설정에서 확인). MCP 도구가 `supabase` 네임스페이스에 노출됨 (`apply_migration`, `execute_sql`, `list_tables` 등).
2. **Vault에 시크릿 등록** (1회):
   - `gemini_api_key` — 임베딩 생성용
   - `supabase_service_role_key` — signed URL + Storage 업로드용
3. **Edge Function `upload-b64` 배포** (1회): `edge-functions/upload-b64/index.ts` → `mcp__supabase__deploy_edge_function`
4. **SQL 함수 적용** (1회): `sql/003_vault_helpers.sql` + `sql/004_upload_via_vault.sql`
5. **Python deps**: `pip install -r scripts/requirements.txt`

위 5가지가 끝나면 로컬 `.env` 없이 동작합니다.

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

**완전 env-free**. 텍스트 추출 + base64 인코딩만 로컬에서, 나머지는 모두 MCP를 통한 SQL.

### Path B-1 — 텍스트 추출 + base64 (Python)

```bash
cd scripts
python prep.py /abs/path/to/file.pdf --out /tmp/prep.json
```

출력: `{file_hash, file_name, file_size, page_count, storage_bucket, storage_path, full_text, pdf_b64}`

`pdf_b64`는 PDF 바이트의 base64 문자열. PDF 원본 보관이 불필요하면 `--no-b64` 추가 (storage_path가 null로 남고 Storage 업로드 단계 생략).

### Path B-2 — 구조화 추출 (Claude)

`/tmp/prep.json`의 `full_text`를 읽고, 아래 스키마에 맞춰 메타데이터를 추출:

```
title            string           제안서 제목
project_year     integer | null   사업 연도
client_name      string | null    발주처
client_type      enum | null      공공 / 민간 / 지자체 / 기타
industry         string | null    분야 (복지/수산/환경/관광 등)
service_category string[]         제공 서비스 분류 (홍보/콘텐츠/플랫폼 등)
budget_krw       integer | null   예산(원)
submitted_at     string | null    제출일 YYYY-MM-DD
abstract         string           한 문단 요약 (3~5문장)
key_points       string[]         핵심 포인트 3~7개
objectives       string | null    사업 목적
strategy         string | null    추진 전략
deliverables     string[]         주요 산출물
tags             string[]         검색 키워드 5~12개
```

확실하지 않은 필드는 null. 추측 금지.

### Path B-3 — Storage 업로드 (MCP, pdf_b64 있을 때만)

`pdf_b64`가 있으면 먼저 Storage에 올립니다 (한 번의 SQL 호출):

```sql
select public.upload_pdf_via_vault(
  '<storage_path>',
  $b64$<pdf_b64>$b64$,
  'proposals'
);
```

`upload_pdf_via_vault()`가 Vault에서 service role 키를 읽어 `upload-b64` Edge Function을 호출 → Edge Function이 base64 디코드 후 Storage에 PUT.

> **크기 주의**: base64 문자열이 SQL 본문에 포함되므로 한 PDF가 ~10MB 이내에서 안정적. 더 큰 파일은 `--no-b64`로 등록 후 Supabase Dashboard에서 직접 업로드.

### Path B-4 — DB 업서트 (MCP)

추출한 메타데이터와 prep.json 파일 정보를 조합해 아래 SQL을 빌드하고 MCP로 실행:

```sql
insert into public.proposals (
  storage_bucket, storage_path, file_name, file_hash, file_size, page_count, mime_type,
  doc_type, title, project_year, client_name, client_type, industry, service_category,
  budget_krw, submitted_at, abstract, key_points, objectives, strategy, deliverables, tags,
  full_text, embedding, embedding_model
) values (
  '<storage_bucket>', '<storage_path>', '<file_name>', '<file_hash>',
  <file_size>, <page_count>, 'application/pdf', '제안서',
  '<title>', <project_year|null>, '<client_name>', '<client_type>',
  '<industry>', array['<cat1>','<cat2>'],
  <budget_krw|null>, '<submitted_at>',
  $abs$<abstract>$abs$,
  array['<kp1>','<kp2>'],
  $obj$<objectives>$obj$,
  $str$<strategy>$str$,
  array['<del1>','<del2>'],
  array['<tag1>','<tag2>'],
  $ft$<full_text>$ft$,
  gemini_embed_vault($emb$TITLE: <title>
ABSTRACT: <abstract>
KEY_POINTS: <kp1> / <kp2>
TAGS: <tag1>, <tag2>$emb$),
  'gemini-embedding-001'
)
on conflict (file_hash) do update set
  title=excluded.title, abstract=excluded.abstract, tags=excluded.tags,
  embedding=excluded.embedding, full_text=excluded.full_text,
  updated_at=now()
returning id, title, project_year;
```

> `$ft$...$ft$`, `$emb$...$emb$` 는 Postgres dollar-quoting — 본문에 작은따옴표가 있어도 안전.

완료 후 user에게 보고: "✅ 등록 완료 — id=N, 제목: ..."

### Path B-3 — Storage backfill (no Gemini calls)

When rows exist but `storage_path` is a `file://` placeholder (typical after B-2), upload originals and patch the rows without re-embedding:

```bash
cd scripts
python upload_storage.py /abs/path/to/*.pdf
```

Per file this script: SHA-256s locally → looks up matching row via PostgREST → uploads to `proposals/<year>/<filename>` with `x-upsert: true` → PATCHes `storage_bucket`/`storage_path` on the row. Gemini key is not required. Run from a host that can reach `*.supabase.co` (typically the user's Mac).

## Path C — Search

`gemini_embed_vault()` DB 함수가 Supabase Vault에서 Gemini API 키를 읽어 임베딩을 생성합니다. 로컬 Python 실행 없이 MCP SQL 한 번으로 검색 완료.

### C-1 Hybrid 검색 (기본)

`match_proposals` RPC 안에 `gemini_embed_vault(query_text)` 를 인라인으로 넣어 한 번의 MCP 호출로 처리:

```
mcp__supabase__execute_sql:
  query: |
    select * from match_proposals(
      query_text       => '복지로 SNS 숏폼 전략 홍보 캠페인 콘텐츠 제작',
      query_embedding  => gemini_embed_vault('복지로 SNS 숏폼 전략 홍보 캠페인 콘텐츠 제작'),
      filter_year_min  => 2024,
      filter_industry  => '복지',
      filter_tags      => null,
      match_count      => 10,
      vec_weight       => 0.8,
      kw_weight        => 0.2
    );
```

**`query_text` 작성 요령**:
- 키워드 나열 대신 **한 문단 분량의 서술문** 사용. 예: `"복지부 산하 복지로 서비스의 2026년 SNS 홍보를 위한 숏폼 콘텐츠 기획·제작 및 인플루언서 운영"`
- PDF를 직접 읽을 수 없을 때는 파일명·발주처·사업 도메인에서 유추한 서술문을 구성
- 짧은 키워드(3단어 이하)보다 긴 문장이 코사인 유사도에서 더 좋은 결과를 낳음

**`vec_weight=0.8, kw_weight=0.2` 이유**: `search_tsv`는 `simple` config로 구축되어 한국어 형태소 분리를 하지 않음 → `kw_score`가 항상 ~0에 가까움 → 벡터 유사도에 더 높은 가중치 부여.

결과는 title, year, client_name, hybrid_score, abstract를 표 형식으로 제시.

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
