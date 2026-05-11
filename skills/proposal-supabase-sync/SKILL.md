---
name: proposal-supabase-sync
description: "MUST USE for OOTB proposal DB tasks. Ingests 제안서 PDFs into Supabase `proposals` table and runs hybrid (vector + keyword + metadata) search via Supabase MCP. Triggers: (a) REGISTER — '이 PDF 등록해줘', 'DB에 넣어줘', '제안서 수집', 'PDF 쌓아줘'; (b) SEARCH — '복지로 관련 제안서', '수산 관련 제안서', '과거 제안서 검색', '제안서 몇 건 있어', '태그 통계'; (c) FIRST SETUP — 'DB 처음 셋업', 'proposals 테이블 만들어줘', 'Edge Function 설정'. Requires Supabase MCP connected. Do NOT use for non-proposal documents."
---

# Proposal ↔ Supabase Sync (MCP edition)

This skill ingests 제안서 PDFs into Supabase and searches them, delegating all DB work to the **Supabase MCP server**. The user does **not** run DB scripts — Claude performs DB operations directly via MCP tools.

**Env-free 운영**: 로컬에 `GEMINI_API_KEY` / `SUPABASE_URL` / `SERVICE_ROLE_KEY` 불필요. 모든 시크릿은 Supabase **Edge Function Secrets** (Project Settings → Functions → Secrets) 에 있고, SQL 함수가 Edge Function을 호출해 사용합니다. PDF 업로드는 prep.py가 `upload-binary` Edge Function에 직접 HTTP POST (~50MB).

Local Python은 MCP가 못 하는 것만: PDF 텍스트 추출 + base64 인코딩.

## When to use

- "DB 처음 셋업해줘" → run Path A (migration)
- "이 PDF 제안서 DB에 넣어줘" → run Path B (ingest)
- "복지로 관련 제안서 찾아줘", "수산 관련 최근 거 뭐 있지?" → run Path C (search)

If the Supabase MCP is not connected, stop and call `suggest_connectors` for Supabase first. Every Path below assumes Supabase MCP is live.

## Prerequisites

1. **Supabase MCP connected** in Cowork/Claude Desktop (`/mcp` 또는 Cowork 설정에서 확인). MCP 도구가 `supabase` 네임스페이스에 노출됨 (`apply_migration`, `execute_sql`, `list_tables` 등).
2. **Edge Function 환경변수 등록** (1회, Supabase Dashboard → Project Settings → Functions → Secrets):
   - `GEMINI_API_KEY` — 임베딩 생성용
   - `SERVICE_ROLE_KEY` — signed URL 생성용
3. **Edge Function 배포** (1회): `upload-binary`, `embed`, `sign-url` 셋 다 `mcp__supabase__deploy_edge_function` 으로 배포.
4. **SQL 마이그레이션 적용** (순서대로): `sql/001_init.sql` → `sql/002_embed_in_db.sql` → `sql/006_edge_secrets.sql` (proj_url + anon_key는 자기 프로젝트 값으로 치환).
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

### Path A-3 — Edge Function-backed helpers

Apply `sql/003_vault_helpers.sql` (for `match_proposals_with_url`), then immediately overwrite with `sql/006_edge_secrets.sql` which redefines `gemini_embed_vault`/`sign_storage_url` to call Edge Functions instead of reading Supabase Vault.

함수 구성:

- `public.gemini_embed_vault(text) → vector(1536)` — `embed` Edge Function 호출 (env var `GEMINI_API_KEY` 사용).
- `public.sign_storage_url(bucket, path, expires_seconds) → text` — `sign-url` Edge Function 호출 (env var `SERVICE_ROLE_KEY` 사용).
- `public.match_proposals_with_url(...)` — `match_proposals` 결과에 signed_url 컬럼 추가.

> Edge Function 환경변수는 Supabase Dashboard → Project Settings → Functions → Secrets에서 등록. SQL 함수 안에는 시크릿이 들어가지 않습니다.

## Path B — Ingest PDFs

PDF 바이너리는 **Edge Function `upload-binary`** 가 직접 받아 Storage에 저장합니다 (HTTP 본문 ~50 MB 한계). MCP `execute_sql` 의 ~3.4 MB payload 제한을 우회하기 위함. Service role은 Edge Function 환경변수에 있고, 호출 시에는 **공개해도 안전한 anon key + project URL** 만 prep.py에 전달.

### Path B-1 — 프로젝트 URL/anon key 가져오기

매 등록 시작 시 MCP로 1회씩 조회:
```
mcp__supabase__get_project_url(project_id="<ref>")
mcp__supabase__get_publishable_keys(project_id="<ref>")  # type="legacy" name="anon" 사용
```
얻은 값을 다음 단계 prep.py 호출에 CLI 인자로 전달.

### Path B-2 — 텍스트 추출 + 업로드 (Python)

```bash
cd scripts
python prep.py /abs/path/to/file.pdf \
  --project-url https://<ref>.supabase.co \
  --anon-key <anon_or_publishable_key> \
  --out /tmp/prep.json
```

prep.py가 하는 일:
- SHA-256 해시 (중복 방지)
- `pdfplumber`로 텍스트 추출
- Edge Function `upload-binary`에 PDF 바이너리 직접 POST (Storage 업로드)
- 출력: `{file_hash, file_name, file_size, page_count, storage_bucket, storage_path, uploaded_bytes, full_text}`

> Storage 보관이 불필요하면 `--no-upload` 추가 (storage_path가 null로 남음).

### Path B-3 — 구조화 추출 (Claude)

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

## Path C — Search

`gemini_embed_vault()` SQL 함수가 `embed` Edge Function을 호출해 임베딩을 생성합니다 (Edge Function이 `GEMINI_API_KEY` 환경변수 사용). 로컬 Python 실행 없이 MCP SQL 한 번으로 검색 완료.

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
- `sql/002_embed_in_db.sql` — installs `http` extension + `gemini_embed(text, key)` (prereq for 003).
- `sql/003_vault_helpers.sql` — `gemini_embed_vault()`, `sign_storage_url()`, `match_proposals_with_url()`.
- `sql/004_upload_via_vault.sql` — legacy SQL-based base64 upload (≤2 MB). Kept for reference; current default is HTTP upload via `upload-binary`.
- `scripts/prep.py` — local PDF → text extraction + HTTP POST to `upload-binary` Edge Function. No Gemini, no SUPABASE creds beyond public anon key.
- `scripts/requirements.txt` — `pdfplumber`, `python-dotenv`, `requests`.
- `edge-functions/upload-binary/index.ts` — **primary** Edge Function (raw PDF body, ≤50 MB).
- `edge-functions/upload-b64/index.ts` — legacy base64 Edge Function (used by `upload_pdf_via_vault` SQL fn).
- `mcp_playbook.md` — exact MCP call parameters for each Path.

## Design notes

- **All credentials live in Edge Function Secrets.** 로컬 Python은 어떤 시크릿도 필요 없음. SQL 함수 (`gemini_embed_vault`, `sign_storage_url`) 가 Edge Function (`embed`, `sign-url`) 을 호출하면 Edge Function의 환경변수 (`GEMINI_API_KEY`, `SERVICE_ROLE_KEY`) 가 사용됨. SQL 로그/`pg_stat_statements`에 시크릿이 남지 않음.
- **Binary upload via direct HTTP.** PDF는 prep.py가 `upload-binary` Edge Function에 raw body로 직접 POST. ~50MB 까지 안정적.
- **Idempotent by `file_hash`.** Same PDF uploaded twice just UPDATEs the row. Different content = different hash = new row.

## Common failure modes

- **"ERROR: relation proposals does not exist"** — Path A wasn't run. Run it.
- **"auth error" from MCP** — Supabase MCP OAuth session expired. Tell user to reconnect in Cowork settings.
- **"GEMINI_API_KEY env var not set"** — Edge Function `embed` 의 환경변수 미설정. Supabase Dashboard → Functions → Secrets에서 `GEMINI_API_KEY` 등록.
- **"SERVICE_ROLE_KEY env var not set"** — Edge Function `sign-url` 의 환경변수 미설정. Dashboard에서 `SERVICE_ROLE_KEY` 등록.
- **Edge Function 413 Payload Too Large** — PDF가 ~50MB 초과. Supabase Dashboard에서 직접 업로드 후 `storage_path` PATCH.
