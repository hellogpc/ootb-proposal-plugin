-- proposal-supabase-sync / 004_upload_via_vault.sql
--
-- Storage upload via the `upload-b64` Edge Function, called from inside the DB.
-- Requires:
--   1. Vault secret `supabase_service_role_key` (003_vault_helpers.sql)
--   2. Edge Function `upload-b64` deployed (edge-functions/upload-b64/index.ts)
--   3. http extension (already pulled in by 002_embed_in_db.sql)
--
-- After applying: Claude can ingest PDFs without any local SUPABASE_* env vars.
-- The base64 string travels through MCP `execute_sql`, the DB calls the Edge
-- Function, which decodes the bytes and writes to Storage using the service role.

create or replace function public.upload_pdf_via_vault(
  in_object_path text,
  in_pdf_b64     text,
  in_bucket      text default 'proposals'
) returns text
language plpgsql
security definer
set search_path = public, extensions, vault
as $fn$
declare
  k text;
  proj_url text := 'https://<YOUR_PROJECT_REF>.supabase.co';
  resp extensions.http_response;
begin
  select decrypted_secret into k
  from vault.decrypted_secrets
  where name = 'supabase_service_role_key' limit 1;
  if k is null then
    raise exception 'supabase_service_role_key secret not set in vault';
  end if;

  resp := extensions.http((
    'POST',
    proj_url || '/functions/v1/upload-b64',
    array[
      extensions.http_header('Authorization', 'Bearer ' || k)
    ],
    'application/json',
    json_build_object(
      'bucket', in_bucket,
      'path',   in_object_path,
      'b64',    in_pdf_b64
    )::text
  )::extensions.http_request);

  if resp.status >= 300 then
    raise exception 'upload failed: status=% body=%',
      resp.status, left(resp.content, 300);
  end if;

  return in_object_path;
end $fn$;

grant execute on function public.upload_pdf_via_vault(text, text, text)
  to authenticated, service_role;
