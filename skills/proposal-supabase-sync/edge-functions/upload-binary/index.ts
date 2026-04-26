// proposal-supabase-sync / Edge Function: upload-binary
//
// Receives the PDF binary directly via HTTP body and writes it to Supabase
// Storage using the service role key. No base64, no MCP — bypasses the
// `execute_sql` payload limit (~3.4 MB) entirely. Supabase Edge Function
// request body limit is ~50 MB.
//
// Endpoint:
//   POST /functions/v1/upload-binary?bucket=proposals&path=<object_path>
//   Authorization: Bearer <anon_key>
//   Content-Type: application/pdf
//   Body: <raw PDF bytes>
//
// Response:
//   200 { ok: true, bucket, path, size }
//   400/500 with text body on error
//
// Deploy via MCP `deploy_edge_function` with verify_jwt=true. Caller passes
// the project's anon (publishable) key — that's enough to invoke; the function
// itself uses SUPABASE_SERVICE_ROLE_KEY from Deno env to write to Storage.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("use POST", { status: 405 });
  }

  const url = new URL(req.url);
  const bucket = url.searchParams.get("bucket") || "proposals";
  const path = url.searchParams.get("path");
  if (!path) {
    return new Response("missing ?path= query parameter", { status: 400 });
  }

  const buf = await req.arrayBuffer();
  if (buf.byteLength === 0) {
    return new Response("empty body", { status: 400 });
  }
  const bytes = new Uint8Array(buf);

  const sb = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const contentType = req.headers.get("content-type") || "application/pdf";
  const { error } = await sb.storage.from(bucket).upload(path, bytes, {
    contentType,
    upsert: true,
  });

  if (error) {
    return new Response("upload failed: " + error.message, { status: 500 });
  }

  return new Response(
    JSON.stringify({ ok: true, bucket, path, size: bytes.length }),
    { headers: { "Content-Type": "application/json" } },
  );
});
