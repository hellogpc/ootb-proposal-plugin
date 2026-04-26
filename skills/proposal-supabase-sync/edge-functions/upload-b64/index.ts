// proposal-supabase-sync / Edge Function: upload-b64
//
// Accepts JSON body { bucket, path, b64 } and writes the decoded bytes to
// Supabase Storage using the service role key.
//
// Deployed via MCP `deploy_edge_function` with verify_jwt=true. Caller must
// pass a valid JWT (typically the service role key) in `Authorization`.
//
// Useful for pipelines where the upstream environment can't reach Storage
// directly but CAN reach the DB (e.g., restricted sandboxes): the DB calls
// this function via the `http` extension with the base64 body.
//
// Size caveat: works best for payloads up to a few MB. For large files the
// base64 string must be passed through in ONE request — if your upstream can
// only send small chunks, use `_upload_staging` table + `_upload_from_staging()`
// helper which concatenate in the DB before calling this function.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("use POST", { status: 405 });
  }
  let body: { bucket?: string; path?: string; b64?: string };
  try { body = await req.json(); }
  catch { return new Response("invalid json", { status: 400 }); }

  const { bucket, path, b64 } = body;
  if (!bucket || !path || !b64) {
    return new Response("need {bucket,path,b64}", { status: 400 });
  }

  // decode base64 → bytes
  let bytes: Uint8Array;
  try {
    const bin = atob(b64);
    bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  } catch (e) {
    return new Response("bad base64: " + String(e), { status: 400 });
  }

  const sb = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const { error } = await sb.storage.from(bucket).upload(path, bytes, {
    contentType: "application/pdf",
    upsert: true,
  });

  if (error) {
    return new Response("upload failed: " + error.message, { status: 500 });
  }

  return new Response(JSON.stringify({
    ok: true, bucket, path, size: bytes.length,
  }), { headers: { "Content-Type": "application/json" } });
});
