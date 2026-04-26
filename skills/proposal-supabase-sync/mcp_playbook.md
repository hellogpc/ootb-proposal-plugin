# Supabase MCP playbook

Claude's cheat sheet for what MCP calls to make for each operation.

All calls are to the **Supabase MCP server** (connected via Cowork settings → MCP → Supabase). Tool names are exposed as `mcp__supabase__<tool>`.

> ⚠️ Every `execute_sql` / `apply_migration` call requires `project_id`. If you don't know which project, first call `list_projects` and confirm with the user.

---

## 1) First-time setup — apply migration

```python
# 1. (once) figure out the project
mcp__supabase__list_projects()

# 2. apply the init migration
mcp__supabase__apply_migration(
    project_id = "<ref>",
    name       = "proposals_init",
    query      = <contents of sql/001_init.sql>,
)

# 3. verify
mcp__supabase__list_tables(project_id="<ref>", schemas=["public"])
# expect 'proposals' in the result
```

## 2) Duplicate check before upsert

```python
mcp__supabase__execute_sql(
    project_id = "<ref>",
    query = f"select id, title from proposals where file_hash = '{file_hash}';",
)
```

If it returns a row and user didn't pass "force", report "already ingested: id=<id>" and stop. Otherwise continue to step 3.

## 3) Upsert after prep

```python
# prep.py produced payload.sql_upsert — a full INSERT ... ON CONFLICT statement
mcp__supabase__execute_sql(
    project_id = "<ref>",
    query      = payload["sql_upsert"],
)
# returns one row: {id, title, project_year}
```

The statement contains the entire 1536-dim vector literal. Do not modify it.

## 4) Hybrid search (gemini_embed_vault inline)

`gemini_embed_vault()` reads the Gemini key from Vault and generates the embedding inside Postgres. No local Python step is needed.

```python
mcp__supabase__execute_sql(
    project_id = "<ref>",
    query = """
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
    """,
)
```

## 5) Keyword-only (skip Gemini)

```python
mcp__supabase__execute_sql(
    project_id = "<ref>",
    query = """
        select id, title, client_name, project_year, tags,
               ts_rank_cd(search_tsv, plainto_tsquery('simple','수산물이력제')) as score,
               abstract
        from proposals
        where search_tsv @@ plainto_tsquery('simple','수산물이력제')
          and project_year >= 2025
        order by score desc
        limit 10;
    """,
)
```

## 6) Ad-hoc introspection

| User asks | SQL |
|---|---|
| 몇 건? | `select count(*) from proposals;` |
| 연도별 분포 | `select project_year, count(*) from proposals group by 1 order by 1 desc;` |
| 태그 통계 | `select tag, count(*) from proposals, unnest(tags) t(tag) group by 1 order by 2 desc limit 30;` |
| 최근 10건 | `select title, client_name, submitted_at from proposals order by created_at desc limit 10;` |

## 7) Get a signed URL for a stored PDF

Supabase MCP *may* include a `create_signed_url` tool depending on server version. If it doesn't, tell the user to open the file from Dashboard → Storage → proposals → `<storage_path>`. For programmatic access from an app, use `supabase.storage.from_('proposals').createSignedUrl(path, 3600)` on the client side.

## 7a) Preferred for Cowork: `match_proposals_with_url` + Vault secrets

If the project has applied `sql/003_vault_helpers.sql` and stored secrets in Vault:

```sql
-- One call, no keys in SQL, returns signed URLs for the top-N rows.
select * from public.match_proposals_with_url(
  query_text        => '복지로 숏폼',
  query_embedding   => public.gemini_embed_vault('복지로 숏폼'),
  match_count       => 5,
  url_expires_seconds => 3600
);
```

Each row comes back with `signed_url` usable for 1 hour. Rows whose Storage
object is missing (`storage_path` still `file://...`) return `signed_url = null`.

## 7b) Fallback: embed via the DB itself (no local Gemini access)

Use only if `prep.py` is blocked from reaching `generativelanguage.googleapis.com`.

One-time setup — apply `sql/002_embed_in_db.sql` via `apply_migration`. This installs the `http` extension and `public.gemini_embed(text, key)`.

Then, in Path B (ingest) or Path C (search), replace every "local vector literal" with an inline call:

```sql
-- ingest (inside an INSERT ... VALUES (...))
..., public.gemini_embed(
      'TITLE: ...' || E'\n\nABSTRACT: ...' || E'\n\n...',
      'AIza...'
    ), ...
```

```sql
-- search RPC
select * from match_proposals(
  query_text       => '복지로 숏폼',
  query_embedding  => public.gemini_embed('복지로 숏폼', 'AIza...'),
  match_count      => 5
);
```

⚠ The key is visible in `pg_stat_statements` and migration history. Rotate the Gemini key after batch ingest, or switch to the Vault-based variant documented at the bottom of `sql/002_embed_in_db.sql`.

## 8) Common errors

| Message | Fix |
|---|---|
| `relation "proposals" does not exist` | Run section 1. |
| `function match_proposals(...) does not exist` | Re-apply migration — function may have been dropped. |
| `dimension mismatch (expected 1536)` | `EMBED_DIM` in .env diverged from schema. Rebuild row or alter column. |
| `invalid input syntax for type vector` | Vector literal malformed — ensure `[a,b,c]` not `(a,b,c)`. |
| HTTP 401 from MCP | OAuth session expired — reconnect Supabase in Cowork settings. |
| `generation expression is not immutable` during `apply_migration` | The schema still uses a GENERATED column for `search_tsv`. Use the trigger form in the current `sql/001_init.sql` (v2). |
| `function public.gemini_embed(...) does not exist` | Path A-2 (`sql/002_embed_in_db.sql`) wasn't applied. Apply it, then retry. |
| `Gemini embed failed: status=403` from `gemini_embed()` | Gemini API key invalid/revoked. Rotate the key and rerun. |
