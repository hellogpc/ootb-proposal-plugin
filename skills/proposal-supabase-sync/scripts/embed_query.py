#!/usr/bin/env python3
"""
Embed a query string with Gemini and emit a pgvector literal.

Usage:
    python embed_query.py "복지로 SNS 전략"

Stdout (single line):
    [0.0123,-0.1340,0.0871,...]

Caller (typically Claude): paste the value into SQL as
    '<that>'::vector(1536)
and pass to `mcp__supabase__execute_sql`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
# ── ootb-proposal-automation: unified .env resolver ─────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_env as _ootb_load_env



def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("usage: embed_query.py \"<query text>\"", file=sys.stderr)
        return 2

    query = sys.argv[1]
    here = Path(__file__).resolve().parent
    _ootb_load_env(caller_script=Path(__file__))

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        return 2

    model = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
    dim = int(os.getenv("EMBED_DIM", "1536"))

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    result = client.models.embed_content(
        model=model,
        contents=query,
        config=types.EmbedContentConfig(output_dimensionality=dim),
    )
    values = list(result.embeddings[0].values)
    if len(values) != dim:
        print(f"ERROR: got {len(values)}-dim, expected {dim}", file=sys.stderr)
        return 3

    sys.stdout.write("[" + ",".join(f"{x:.6f}" for x in values) + "]\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
