-- proposal-supabase-sync / 002_embed_in_db.sql
--
-- OPTIONAL migration. Apply this only when you need Claude to run the
-- Gemini embedding call from INSIDE the database (e.g., when the local
-- Python environment cannot reach generativelanguage.googleapis.com).
--
-- Normal flow (preferred): prep.py calls Gemini locally, ships a SQL
-- statement with the precomputed vector literal. The DB does no external I/O.
--
-- Workaround flow (this file): a SQL function `public.gemini_embed(text, key)`
-- performs an HTTP POST to Gemini via the `http` extension and returns a
-- vector(1536). Useful when the sandbox/CI is network-restricted but Supabase
-- has open egress.
--
-- ╔══════════════════════════════════════════════════════════════════╗
-- ║ ⚠  SECURITY                                                       ║
-- ║                                                                  ║
-- ║  This function accepts the Gemini API key as a parameter. Every  ║
-- ║  call leaks the key into pg_stat_statements, CloudWatch-like     ║
-- ║  log streams, and Supabase migration history.                    ║
-- ║                                                                  ║
-- ║  If you apply this migration, ROTATE the Gemini key after use,   ║
-- ║  OR switch the implementation to read the key from Supabase      ║
-- ║  Vault (see commented alternative at the bottom of this file).   ║
-- ║                                                                  ║
-- ║  Prefer prep.py from a local machine if possible — it keeps the  ║
-- ║  key in client-side .env only.                                   ║
-- ╚══════════════════════════════════════════════════════════════════╝

create extension if not exists http with schema extensions;

create or replace function public.gemini_embed(in_text text, in_key text)
returns extensions.vector(1536)
language plpgsql
as $$
declare
  resp       extensions.http_response;
  vals       jsonb;
  result_vec extensions.vector(1536);
begin
  resp := extensions.http((
    'POST',
    'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=' || in_key,
    array[extensions.http_header('Content-Type','application/json')],
    'application/json',
    json_build_object(
      'content', json_build_object('parts', json_build_array(json_build_object('text', in_text))),
      'outputDimensionality', 1536
    )::text
  )::extensions.http_request);

  if resp.status <> 200 then
    raise exception 'Gemini embed failed: status=% body=%', resp.status, left(resp.content, 500);
  end if;

  vals := resp.content::jsonb #> '{embedding,values}';

  select ('[' || string_agg(v::text, ',' order by o) || ']')::extensions.vector(1536)
  into result_vec
  from jsonb_array_elements(vals) with ordinality as t(v, o);

  return result_vec;
end $$;

-- ---------------------------------------------------------------------------
-- OPTIONAL: Vault-based variant (no key in logs)
-- ---------------------------------------------------------------------------
-- 1. Store the key once:
--      select vault.create_secret('AIza...', 'gemini_api_key');
-- 2. Replace the function body to read the key:
--
--   create or replace function public.gemini_embed_vault(in_text text)
--   returns extensions.vector(1536)
--   language plpgsql
--   security definer   -- needed to read vault.decrypted_secrets
--   as $fn$
--   declare
--     k text;
--   begin
--     select decrypted_secret into k
--     from vault.decrypted_secrets
--     where name = 'gemini_api_key' limit 1;
--     if k is null then
--       raise exception 'gemini_api_key secret not set in vault';
--     end if;
--     return public.gemini_embed(in_text, k);
--   end $fn$;
--
-- Then call gemini_embed_vault(...) everywhere — no key in queries.
