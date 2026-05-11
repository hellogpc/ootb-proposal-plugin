-- proposal-supabase-sync / 006_edge_secrets.sql
--
-- Vault 대신 Edge Function의 환경변수(SERVICE_ROLE_KEY, GEMINI_API_KEY)를
-- 사용하도록 helper 함수를 교체.
--
-- 변경점:
--   - public.gemini_embed_vault(text) → POST /functions/v1/embed 호출
--   - public.sign_storage_url(...)    → POST /functions/v1/sign-url 호출
--   - vault.decrypted_secrets 의존 제거
--
-- 둘 다 anon 키로 인증 (publicly safe). proj_url + anon_key를 함수에 하드코딩.
-- Edge Function 측이 실제 시크릿을 보유하므로 SQL 로그에 시크릿 노출 없음.

create extension if not exists http with schema extensions;

-- ─────────────────────────────────────────────────────────────────────
-- Gemini embedding (Edge Function-backed)
-- ─────────────────────────────────────────────────────────────────────
create or replace function public.gemini_embed_vault(in_text text)
returns extensions.vector(1536)
language plpgsql
security definer
set search_path = public, extensions
as $fn$
declare
  resp extensions.http_response;
  vals jsonb;
  result_vec extensions.vector(1536);
  proj_url text := 'https://aqswaavcxdmuinylvxcb.supabase.co';
  anon_key text := 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFxc3dhYXZjeGRtdWlueWx2eGNiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg0OTU0NTEsImV4cCI6MjA5NDA3MTQ1MX0.cDeyApEg-vyLwDUjPfmXuM07ck9U_CAfhK9bT75HeUI';
begin
  resp := extensions.http((
    'POST',
    proj_url || '/functions/v1/embed',
    array[
      extensions.http_header('Authorization', 'Bearer ' || anon_key),
      extensions.http_header('Content-Type',  'application/json')
    ],
    'application/json',
    json_build_object('text', in_text)::text
  )::extensions.http_request);

  if resp.status <> 200 then
    raise exception 'embed function failed: status=% body=%',
      resp.status, left(resp.content, 300);
  end if;

  vals := resp.content::jsonb -> 'embedding';

  select ('[' || string_agg(v::text, ',' order by o) || ']')::extensions.vector(1536)
  into result_vec
  from jsonb_array_elements(vals) with ordinality as t(v, o);

  return result_vec;
end $fn$;

-- ─────────────────────────────────────────────────────────────────────
-- Signed URL (Edge Function-backed)
-- ─────────────────────────────────────────────────────────────────────
create or replace function public.sign_storage_url(
  in_bucket text,
  in_path text,
  in_expires_seconds int default 3600
)
returns text
language plpgsql
security definer
set search_path = public, extensions
as $fn$
declare
  resp extensions.http_response;
  proj_url text := 'https://aqswaavcxdmuinylvxcb.supabase.co';
  anon_key text := 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFxc3dhYXZjeGRtdWlueWx2eGNiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg0OTU0NTEsImV4cCI6MjA5NDA3MTQ1MX0.cDeyApEg-vyLwDUjPfmXuM07ck9U_CAfhK9bT75HeUI';
begin
  resp := extensions.http((
    'POST',
    proj_url || '/functions/v1/sign-url',
    array[
      extensions.http_header('Authorization', 'Bearer ' || anon_key),
      extensions.http_header('Content-Type',  'application/json')
    ],
    'application/json',
    json_build_object(
      'bucket',  in_bucket,
      'path',    in_path,
      'expires', in_expires_seconds
    )::text
  )::extensions.http_request);

  if resp.status <> 200 then
    raise exception 'sign-url function failed: status=% body=%',
      resp.status, left(resp.content, 300);
  end if;

  return (resp.content::jsonb ->> 'signed_url');
end $fn$;

grant execute on function public.gemini_embed_vault(text)              to authenticated, service_role;
grant execute on function public.sign_storage_url(text, text, int)     to authenticated, service_role;
