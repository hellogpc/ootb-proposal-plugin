#!/usr/bin/env python3
"""
Local-only PDF prep for the MCP-driven ingest flow.

What this does:
  1. Hash + extract text from the PDF (pdfplumber)
  2. Base64-encode the PDF bytes (for MCP-driven Storage upload)
  3. Emit JSON to stdout — Claude reads it and:
     - extracts structured metadata from full_text
     - calls upload_pdf_via_vault(path, pdf_b64) via MCP
     - calls the proposals upsert with gemini_embed_vault() via MCP

What this does NOT do:
  - Call Gemini (no GEMINI_API_KEY required)
  - Call Supabase HTTP directly (no SUPABASE_URL / SERVICE_ROLE_KEY required)
  - Generate embeddings (handled by gemini_embed_vault() inside DB)
  - Extract structured metadata (handled by Claude)

The plugin runs **env-free** — all credentials live in Supabase Vault.

Usage:
    python prep.py /abs/path/to/file.pdf               # stdout JSON
    python prep.py /abs/path/to/file.pdf -o out.json   # write JSON to file
    python prep.py /abs/path/to/file.pdf --no-b64      # skip base64 (no Storage upload)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path


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
    import pdfplumber  # type: ignore
    with pdfplumber.open(str(p)) as pdf:
        parts = []
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if t:
                parts.append(t)
        return "\n\n".join(parts), len(pdf.pages)


def storage_object_key(p: Path, fhash: str, year_hint: int | None) -> str:
    """ASCII-only Storage path: {year}/{hash12}-{ascii_stem}.pdf"""
    year = str(year_hint or "unknown")
    stem_ascii = unicodedata.normalize("NFKD", p.stem).encode("ascii", "ignore").decode("ascii")
    stem_ascii = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem_ascii).strip("-._") or "proposal"
    return f"{year}/{fhash[:12]}-{stem_ascii[:40]}.pdf"


# =========================================================================
# main
# =========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="Extract PDF for MCP-driven ingest (env-free).")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="Write JSON payload to this file (else stdout).")
    ap.add_argument("--no-b64", action="store_true",
                    help="Omit pdf_b64 (skips Storage upload entirely; storage_path stays null).")
    ap.add_argument("--year-hint", type=int, default=None,
                    help="Year used in the Storage key path when project_year is unknown.")
    args = ap.parse_args()

    p = args.pdf.expanduser().resolve()
    if not p.exists() or p.suffix.lower() != ".pdf":
        print(f"ERROR: {p} is not an existing PDF", file=sys.stderr)
        return 2

    print(f"[1/3] hashing + extracting text from {p.name}", file=sys.stderr)
    fhash = sha256_file(p)
    full_text, page_count = extract_pdf_text(p)
    if not full_text.strip():
        print("ERROR: empty text (likely scanned PDF; OCR not included).", file=sys.stderr)
        return 3

    object_key = storage_object_key(p, fhash, args.year_hint)

    if args.no_b64:
        print("[2/3] SKIP base64 (--no-b64); Storage upload disabled", file=sys.stderr)
        pdf_b64 = None
    else:
        print(f"[2/3] base64-encoding PDF ({p.stat().st_size} bytes)", file=sys.stderr)
        pdf_b64 = base64.b64encode(p.read_bytes()).decode("ascii")

    print("[3/3] building output JSON", file=sys.stderr)
    payload = {
        "file_hash":      fhash,
        "file_name":      p.name,
        "file_size":      p.stat().st_size,
        "page_count":     page_count,
        "mime_type":      "application/pdf",
        "storage_bucket": "proposals" if pdf_b64 else None,
        "storage_path":   object_key if pdf_b64 else None,
        "full_text":      full_text,
        "pdf_b64":        pdf_b64,  # null when --no-b64
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
