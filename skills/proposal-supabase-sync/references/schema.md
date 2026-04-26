# Schema reference (v2 — MCP edition)

Single-user schema: no `owner_id`, no RLS. See `sql/001_init.sql` for the authoritative DDL.

## Table: `public.proposals`

| column | type | notes |
|---|---|---|
| id | bigint PK | autoincrement |
| storage_bucket / storage_path | text | Supabase Storage reference (nullable if skipped) |
| file_name / file_hash / file_size / page_count / mime_type | — | file identity |
| doc_type | text | defaults to `'제안서'` |
| title / project_year / client_name / client_type / industry | — | business meta |
| service_category / tags | text[] | multi-valued |
| budget_krw / contract_period / submitted_at | — | numbers & periods |
| abstract / key_points / objectives / strategy / deliverables | — | LLM summary |
| full_text | text | raw extracted text |
| search_tsv | tsvector (trigger-maintained) | A: title, B: abstract+tags, D: full_text. Filled by `proposals_before_write`. |
| embedding | vector(1536) | Gemini Matryoshka-truncated |
| embedding_model / embedding_input_hash | — | re-embed detection |
| created_at / updated_at | timestamptz | audit |

**Unique**: `file_hash` — drives UPSERT.

## Indexes

- GIN: `search_tsv`, `tags`, `service_category`, `title gin_trgm_ops`, `client_name gin_trgm_ops`
- B-tree: `project_year desc`
- HNSW: `embedding vector_cosine_ops (m=16, ef_construction=64)`

## RPC `match_proposals(query_text, query_embedding, filter_year_min, filter_industry, filter_tags, match_count, kw_weight, vec_weight)`

Returns `(id, title, client_name, project_year, industry, tags, storage_path, abstract, kw_score, vec_score, hybrid_score)` ordered by `hybrid_score desc`.

Score: `kw_weight * ts_rank_cd + vec_weight * (1 - cosine_distance)`.

## Storage bucket `proposals`

Private, PDF-only, 100 MB default limit. The v2 schema has no auth-based RLS on storage objects — if you later front this with a web app, add policies then.
