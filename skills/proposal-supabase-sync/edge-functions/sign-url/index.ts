// proposal-supabase-sync / Edge Function: sign-url
//
// Generates a Supabase Storage signed URL. Reads SERVICE_ROLE_KEY from the
// Edge Function's environment variables instead of Supabase Vault.
//
// Endpoint:
//   POST /functions/v1/sign-url
//   Authorization: Bearer <anon_key>
//   Content-Type: application/json
//   Body: { "bucket": "proposals", "path": "<object_path>", "expires": 3600 }
//
// Response:
//   200 { "signed_url": "https://..." }
//   4xx/5xx with plain text on error

import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("use POST", { status: 405 });
  }

  let body: { bucket?: string; path?: string; expires?: number };
  try {
    body = await req.json();
  } catch {
    return new Response("invalid json", { status: 400 });
  }
  const bucket = body.bucket ?? "proposals";
  const path = body.path;
  const expires = body.expires ?? 3600;
  if (!path) {
    return new Response("missing 'path'", { status: 400 });
  }

  // Prefer user-defined SERVICE_ROLE_KEY; fall back to Supabase auto-injected.
  const key = Deno.env.get("SERVICE_ROLE_KEY") ??
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const url = Deno.env.get("SUPABASE_URL");
  if (!key || !url) {
    return new Response(
      "SERVICE_ROLE_KEY or SUPABASE_URL env var not set",
      { status: 500 },
    );
  }

  const sb = createClient(url, key);
  const { data, error } = await sb.storage.from(bucket).createSignedUrl(
    path,
    expires,
  );
  if (error) {
    return new Response("sign failed: " + error.message, { status: 500 });
  }

  return new Response(JSON.stringify({ signed_url: data.signedUrl }), {
    headers: { "Content-Type": "application/json" },
  });
});
