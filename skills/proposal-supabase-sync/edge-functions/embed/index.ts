// proposal-supabase-sync / Edge Function: embed
//
// Generates a 1536-dim Gemini text embedding. Reads GEMINI_API_KEY from the
// Edge Function's environment variables (Supabase Dashboard → Functions →
// Secrets) instead of Supabase Vault.
//
// Endpoint:
//   POST /functions/v1/embed
//   Authorization: Bearer <anon_key>
//   Content-Type: application/json
//   Body: { "text": "..." }
//
// Response:
//   200 { "embedding": [0.012, -0.134, ...] }   // length=1536
//   4xx/5xx with plain text on error
//
// Called from SQL (`public.gemini_embed_vault(text)`) via the http extension,
// and optionally from local Python prep scripts.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("use POST", { status: 405 });
  }

  let body: { text?: string };
  try {
    body = await req.json();
  } catch {
    return new Response("invalid json", { status: 400 });
  }
  const text = (body.text ?? "").trim();
  if (!text) {
    return new Response("missing or empty 'text'", { status: 400 });
  }

  const key = Deno.env.get("GEMINI_API_KEY");
  if (!key) {
    return new Response("GEMINI_API_KEY env var not set", { status: 500 });
  }

  const resp = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=${key}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: { parts: [{ text }] },
        outputDimensionality: 1536,
      }),
    },
  );

  if (!resp.ok) {
    const errBody = await resp.text();
    return new Response(
      `gemini failed (${resp.status}): ${errBody.slice(0, 300)}`,
      { status: 500 },
    );
  }

  const data = await resp.json();
  const values: number[] | undefined = data?.embedding?.values;
  if (!Array.isArray(values) || values.length !== 1536) {
    return new Response(
      `unexpected response shape: ${JSON.stringify(data).slice(0, 200)}`,
      { status: 500 },
    );
  }

  return new Response(JSON.stringify({ embedding: values }), {
    headers: { "Content-Type": "application/json" },
  });
});
