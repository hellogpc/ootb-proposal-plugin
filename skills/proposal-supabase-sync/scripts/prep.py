#!/usr/bin/env python3
"""
Local PDF prep + direct HTTP upload to the `upload-binary` Edge Function.

Why this design:
  - MCP `execute_sql` has a ~3.4 MB payload cap, so we cannot send a base64-
    encoded PDF through SQL for anything but trivial files.
  - The Edge Function `upload-binary` accepts the raw PDF body via HTTP
    (Supabase EF body limit ~50 MB), uses its own service_role from Deno env
    to write to Storage, and only requires the project's anon key for auth.

Workflow:
  1. Hash + extract text from the PDF (pdfplumber)
  2. POST raw PDF bytes to <project_url>/functions/v1/upload-binary
     with Authorization: Bearer <anon_key>
  3. Emit JSON to stdout — Claude reads it, does structured extraction from
     `full_text`, and calls the proposals upsert with `gemini_embed_vault()`
     via MCP (no base64 in that SQL — payload stays small).

Usage:
    python prep.py /abs/path/to/file.pdf \
        --project-url https://<ref>.supabase.co \
        --anon-key <publishable-or-anon-key> \
        -o /tmp/prep.json

    # skip Storage upload (metadata only):
    python prep.py /abs/path/to/file.pdf --no-upload -o /tmp/prep.json

Both `--project-url` and `--anon-key` are public-safe values (the anon key is
designed for client-side use; security comes from RLS + the EF's service-role
isolation). Claude in Cowork can fetch them via MCP `get_project_url` /
`get_publishable_keys` and pass them as CLI args.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber  # type: ignore
import requests


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


def storage_object_key(p: Path, fhash: str, year_hint: int | None) -> str:
    """ASCII-only Storage path: {year}/{hash12}-{ascii_stem}.pdf"""
    year = str(year_hint or "unknown")
    stem_ascii = unicodedata.normalize("NFKD", p.stem).encode("ascii", "ignore").decode("ascii")
    stem_ascii = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem_ascii).strip("-._") or "proposal"
    return f"{year}/{fhash[:12]}-{stem_ascii[:40]}.pdf"


# =========================================================================
# HTTP upload to Edge Function
# =========================================================================
def upload_via_edge(local_path: Path, project_url: str, anon_key: str,
                    object_path: str, bucket: str = "proposals") -> int:
    url = f"{project_url.rstrip('/')}/functions/v1/upload-binary"
    headers = {
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/pdf",
    }
    params = {"bucket": bucket, "path": object_path}
    with local_path.open("rb") as f:
        r = requests.post(url, headers=headers, params=params, data=f, timeout=300)
    if r.status_code >= 300:
        raise RuntimeError(f"edge upload failed {r.status_code}: {r.text[:300]}")
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    return int(body.get("size") or local_path.stat().st_size)


# =========================================================================
# main
# =========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="Extract PDF + upload via Edge Function.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="Write JSON payload to this file (else stdout).")
    ap.add_argument("--project-url", default=None,
                    help="https://<ref>.supabase.co — required unless --no-upload.")
    ap.add_argument("--anon-key", default=None,
                    help="Publishable/anon API key — required unless --no-upload.")
    ap.add_argument("--bucket", default="proposals",
                    help="Storage bucket (default: proposals).")
    ap.add_argument("--no-upload", action="store_true",
                    help="Skip Storage upload; storage_path stays null.")
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

    if args.no_upload:
        print("[2/3] SKIP upload (--no-upload)", file=sys.stderr)
        storage_bucket = None
        storage_path = None
        uploaded_size = None
    else:
        if not args.project_url or not args.anon_key:
            print("ERROR: --project-url and --anon-key required (or use --no-upload)",
                  file=sys.stderr)
            return 4
        print(f"[2/3] uploading via Edge Function bucket={args.bucket} key={object_key}",
              file=sys.stderr)
        uploaded_size = upload_via_edge(
            p, args.project_url, args.anon_key, object_key, args.bucket)
        storage_bucket = args.bucket
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
        "uploaded_bytes": uploaded_size,
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
