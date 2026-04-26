#!/usr/bin/env python3
"""
Local-only PDF prep for the MCP-driven ingest flow.

What this does:
  1. Hash + extract text from the PDF (pdfplumber)
  2. (default) Upload the PDF to Supabase Storage via HTTP
  3. Emit JSON to stdout — Claude reads it, does structured extraction,
     and builds an upsert SQL that calls gemini_embed_vault() for embedding.

What this does NOT do:
  - Call Gemini (GEMINI_API_KEY not required)
  - Generate embeddings (handled by gemini_embed_vault() inside DB)
  - Extract structured metadata (handled by Claude)

Usage:
    python prep.py /abs/path/to/file.pdf               # upload PDF + stdout JSON
    python prep.py /abs/path/to/file.pdf -o out.json   # write JSON to file
    python prep.py /abs/path/to/file.pdf --no-upload   # skip Storage upload
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pdfplumber  # type: ignore
import requests

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_env as _ootb_load_env


# =========================================================================
# env (Supabase only — no Gemini needed)
# =========================================================================
def load_env() -> dict[str, Any]:
    _ootb_load_env(caller_script=Path(__file__))
    return {
        "SUPABASE_URL":             os.getenv("SUPABASE_URL", "").rstrip("/"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        "SUPABASE_BUCKET":          os.getenv("SUPABASE_BUCKET", "proposals"),
    }


# =========================================================================
# hashing / pdf
# =========================================================================
def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_pdf_text(p: Path) -> tuple[str, int]:
    with pdfplumber.open(str(p)) as pdf:
        parts = []
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if t:
                parts.append(t)
        return "\n\n".join(parts), len(pdf.pages)


# =========================================================================
# storage upload (direct HTTP — MCP can't stream binary)
# =========================================================================
def storage_upload(env: dict, local_path: Path, object_path: str) -> str:
    if not env["SUPABASE_URL"] or not env["SUPABASE_SERVICE_ROLE_KEY"]:
        raise RuntimeError(
            "Storage upload requested but SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set.")
    bucket = env["SUPABASE_BUCKET"]
    url = f"{env['SUPABASE_URL']}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {env['SUPABASE_SERVICE_ROLE_KEY']}",
        "Content-Type": "application/pdf",
        "x-upsert": "true",
    }
    with local_path.open("rb") as f:
        r = requests.post(url, headers=headers, data=f, timeout=300)
    if r.status_code >= 300:
        raise RuntimeError(f"Storage upload failed {r.status_code}: {r.text[:300]}")
    return object_path


# =========================================================================
# main
# =========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="Extract PDF text for MCP-driven upsert.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="Write JSON payload to this file (else stdout).")
    ap.add_argument("--no-upload", action="store_true",
                    help="Skip Supabase Storage upload; storage_path = file://...")
    ap.add_argument("--year-hint", type=int, default=None,
                    help="Year used in the Storage key path when project_year is unknown.")
    args = ap.parse_args()

    p = args.pdf.expanduser().resolve()
    if not p.exists() or p.suffix.lower() != ".pdf":
        print(f"ERROR: {p} is not an existing PDF", file=sys.stderr)
        return 2

    env = load_env()

    print(f"[1/3] hashing + extracting text from {p.name}", file=sys.stderr)
    fhash = sha256_file(p)
    full_text, page_count = extract_pdf_text(p)
    if not full_text.strip():
        print("ERROR: empty text (likely scanned PDF; OCR not included).", file=sys.stderr)
        return 3

    # Storage object key — ASCII only (Supabase Storage rejects Korean/spaces)
    year = str(args.year_hint or "unknown")
    stem_ascii = unicodedata.normalize("NFKD", p.stem).encode("ascii", "ignore").decode("ascii")
    stem_ascii = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem_ascii).strip("-._") or "proposal"
    object_key = f"{year}/{fhash[:12]}-{stem_ascii[:40]}.pdf"

    if args.no_upload or not env["SUPABASE_URL"]:
        print("[2/3] SKIP storage upload (--no-upload or env not set)", file=sys.stderr)
        storage_bucket = None
        storage_path = f"file://{p}"
    else:
        print(f"[2/3] uploading to Storage bucket={env['SUPABASE_BUCKET']} key={object_key}",
              file=sys.stderr)
        storage_upload(env, p, object_key)
        storage_bucket = env["SUPABASE_BUCKET"]
        storage_path = object_key

    print("[3/3] building output JSON", file=sys.stderr)
    payload = {
        "file_hash":      fhash,
        "file_name":      p.name,
        "file_size":      p.stat().st_size,
        "page_count":     page_count,
        "mime_type":      "application/pdf",
        "storage_bucket": storage_bucket,
        "storage_path":   storage_path,
        "full_text":      full_text,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
