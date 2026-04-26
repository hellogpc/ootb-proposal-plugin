#!/usr/bin/env python3
"""
Upload-only helper. Puts PDF originals into Supabase Storage and patches the
`proposals` row's `storage_bucket` / `storage_path`.

Does NOT call Gemini — embeddings/summaries are untouched. Use this when:
  - The row already exists (e.g., ingested earlier without Storage access), or
  - You want to re-sync Storage paths without paying for re-embedding.

Usage:
    python upload_storage.py /abs/path/to/*.pdf

Idempotent: matches rows by SHA-256 `file_hash`, uploads with `x-upsert: true`.
Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env. No Gemini key needed.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv
# ── ootb-proposal-automation: unified .env resolver ─────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_env as _ootb_load_env



def safe_object_key(year: str, file_hash: str, stem: str) -> str:
    """Build an ASCII-only Storage object key.

    Supabase Storage rejects most non-ASCII chars (Korean, spaces, many
    punctuation). We keep the human name information in the `file_name`
    column of the DB; the key itself uses:
        {year}/{hash_12}-{ascii_stem}.pdf

    `ascii_stem` is transliterated down to [a-zA-Z0-9._-], truncated to 40 chars.
    Collision-safe via the 12-char hash prefix.
    """
    stem_nfkd = unicodedata.normalize("NFKD", stem)
    stem_ascii = stem_nfkd.encode("ascii", "ignore").decode("ascii")
    stem_ascii = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem_ascii).strip("-._")
    stem_ascii = (stem_ascii or "proposal")[:40]
    return f"{year}/{file_hash[:12]}-{stem_ascii}.pdf"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_env() -> dict[str, str]:
    here = Path(__file__).resolve().parent
    _ootb_load_env(caller_script=Path(__file__))
    missing = [k for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY") if not os.getenv(k)]
    if missing:
        print(f"ERROR: missing env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)
    return {
        "SUPABASE_URL":              os.environ["SUPABASE_URL"].rstrip("/"),
        "SUPABASE_SERVICE_ROLE_KEY": os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        "SUPABASE_BUCKET":           os.getenv("SUPABASE_BUCKET", "proposals"),
    }


def pg_select_row(env: dict[str, str], file_hash: str) -> dict | None:
    """Fetch {id, project_year} for the row with matching file_hash via PostgREST."""
    r = requests.get(
        f"{env['SUPABASE_URL']}/rest/v1/proposals",
        params={"file_hash": f"eq.{file_hash}", "select": "id,project_year,file_name,storage_path"},
        headers={
            "apikey":        env["SUPABASE_SERVICE_ROLE_KEY"],
            "Authorization": f"Bearer {env['SUPABASE_SERVICE_ROLE_KEY']}",
        },
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def storage_upload(env: dict[str, str], local: Path, object_path: str) -> None:
    url = f"{env['SUPABASE_URL']}/storage/v1/object/{env['SUPABASE_BUCKET']}/{object_path}"
    with local.open("rb") as f:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {env['SUPABASE_SERVICE_ROLE_KEY']}",
                "Content-Type": "application/pdf",
                "x-upsert": "true",
            },
            data=f,
            timeout=600,
        )
    if r.status_code >= 300:
        raise RuntimeError(f"upload failed {r.status_code}: {r.text[:300]}")


def pg_patch_row(env: dict[str, str], row_id: int, object_path: str) -> None:
    r = requests.patch(
        f"{env['SUPABASE_URL']}/rest/v1/proposals",
        params={"id": f"eq.{row_id}"},
        headers={
            "apikey":        env["SUPABASE_SERVICE_ROLE_KEY"],
            "Authorization": f"Bearer {env['SUPABASE_SERVICE_ROLE_KEY']}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",
        },
        json={"storage_bucket": env["SUPABASE_BUCKET"], "storage_path": object_path},
        timeout=30,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"patch failed {r.status_code}: {r.text[:300]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="PDF files")
    args = ap.parse_args()
    env = load_env()

    pdfs = []
    for p in args.paths:
        path = Path(p).expanduser().resolve()
        if path.exists() and path.suffix.lower() == ".pdf":
            pdfs.append(path)
        else:
            print(f"WARN skip: {p}", file=sys.stderr)

    if not pdfs:
        print("no PDFs")
        return 1

    for p in pdfs:
        fhash = sha256_file(p)
        row = pg_select_row(env, fhash)
        if not row:
            print(f"SKIP  no DB row for {p.name} (hash={fhash[:12]}…). "
                  f"Run prep.py/ingest first.")
            continue
        year = str(row.get("project_year") or "unknown")
        # Korean / spaces / special chars are rejected by Supabase Storage.
        # Use an ASCII-only key derived from hash + transliterated stem.
        object_path = safe_object_key(year, fhash, p.stem)
        print(f"[1/2] uploading {p.name}\n        → {env['SUPABASE_BUCKET']}/{object_path}")
        storage_upload(env, p, object_path)
        print(f"[2/2] patching row id={row['id']}")
        pg_patch_row(env, row["id"], object_path)
        print(f"OK    id={row['id']}  {object_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
