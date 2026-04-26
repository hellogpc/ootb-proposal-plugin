-- proposal-supabase-sync / 003_vault_helpers.sql
--
-- Secret-free variants of the helper functions. Apply AFTER 002_embed_in_db.sql.
--
-- Prerequisites:
--   1. Apply sql/002_embed_in_db.sql (installs http extension + gemini_embed).
--   2. Store secrets in Supabase Vault once:
--        select vault.create_secret('<gemini_key>',   'gemini_api_key',
--                                   'Gemini API key for embedding');
--        select vault.create_secret('<service_role_key>', 'supabase_service_role_key',
--                                   'Service role key for sign_storage_url');
--   3. Confirm they're stored:
--        select name from vault.decrypted_secrets
--         where name in ('gemini_api_key','supabase_service_role_key');
--
-- After applying: use `gemini_embed_vault(text)` and `sign_storage_url(bucket, path)`
-- everywhere. No secrets appear in query text or logs.

-- ─────────────────────────────────────────────────────────────────────
-- Gemini embedding (Vault-based)
-- ─────────────────────────────────────────────────────────────────────
create or replace function public.gemini_embed_vault(in_text text)
returns extensions.vector(1536)
language plpgsql
security definer
set search_path = public, extensions, vault
as $fn$
declare
  k text;
begin
  select decrypted_secret into k
  from vault.decrypted_secrets
  where name = 'gemini_api_key' limit 1;
  if k is null then
    raise exception 'gemini_api_key secret not set in vault';
  end if;
  return public.gemini_embed(in_text, k);
end $fn$;

-- ─────────────────────────────────────────────────────────────────────
-- Signed URL generator for Storage objects
-- ─────────────────────────────────────────────────────────────────────
-- Edit `proj_url` if you deploy elsewhere.
create or replace function public.sign_storage_url(
  in_bucket text,
  in_path text,
  in_expires_seconds int default 3600
)
returns text
language plpgsql
security definer
set search_path = public, extensions, vault
as $fn$
declare
  k text;
  proj_url text := 'https://<YOUR_PROJECT_REF>.supabase.co';
  resp extensions.http_response;
  path_json jsonb;
begin
  select decrypted_secret into k
  from vault.decrypted_secrets
  where name = 'supabase_service_role_key' limit 1;
  if k is null then
    raise exception 'supabase_service_role_key secret not set in vault';
  end if;

  resp := extensions.http((
    'POST',
    proj_url || '/storage/v1/object/sign/' || in_bucket || '/' || in_path,
    array[
      extensions.http_header('Authorization', 'Bearer ' || k),
      extensions.http_header('Content-Type',  'application/json')
    ],
    'application/json',
    json_build_object('expiresIn', in_expires_seconds)::text
  )::extensions.http_request);

  if resp.status <> 200 then
    raise exception 'sign failed: status=% body=%', resp.status, left(resp.content, 300);
  end if;

  path_json := resp.content::jsonb;
  -- handles both "signedURL" and "signedUrl" field names across API versions
  return proj_url || '/storage/v1' ||
         coalesce(path_json->>'signedURL', path_json->>'signedUrl');
end $fn$;

-- ─────────────────────────────────────────────────────────────────────
-- match_proposals_with_url: wraps match_proposals + per-row signed URL
-- ─────────────────────────────────────────────────────────────────────
-- Rows whose storage_path is still a file:// placeholder (never uploaded)
-- return signed_url = null. All other rows get a fresh URL on each call.
create or replace function public.match_proposals_with_url(
  query_text       text,
  query_embedding  extensions.vector(1536),
  filter_year_min  int    default null,
  filter_industry  text   default null,
  filter_tags      text[] default null,
  match_count      int    default 10,
  kw_weight        float  default 0.4,
  vec_weight       float  default 0.6,
  url_expires_seconds int  default 3600
)
returns table (
  id bigint, title text, client_name text, project_year smallint,
  industry text, tags text[], storage_path text, abstract text,
  kw_score real, vec_score real, hybrid_score real, signed_url text
)
language plpgsql
stable
as $fn$
declare
  r record;
  u text;
begin
  for r in
    select * from public.match_proposals(
      query_text, query_embedding, filter_year_min, filter_industry,
      filter_tags, match_count, kw_weight, vec_weight
    )
  loop
    u := null;
    if r.storage_path is not null and r.storage_path not like 'file://%' then
      begin
        u := public.sign_storage_url('proposals', r.storage_path, url_expires_seconds);
      exception when others then
        u := null;  -- Storage object missing → just leave url null
      end;
    end if;
    id := r.id; title := r.title; client_name := r.client_name;
    project_year := r.project_year; industry := r.industry; tags := r.tags;
    storage_path := r.storage_path; abstract := r.abstract;
    kw_score := r.kw_score; vec_score := r.vec_score; hybrid_score := r.hybrid_score;
    signed_url := u;
    return next;
  end loop;
end $fn$;

grant execute on function public.gemini_embed_vault(text) to authenticated, service_role;
grant execute on function public.sign_storage_url(text, text, int) to authenticated, service_role;
grant execute on function public.match_proposals_with_url(
  text, extensions.vector, int, text, text[], int, float, float, int
) to authenticated, service_role;
