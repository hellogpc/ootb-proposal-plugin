#!/usr/bin/env python3
"""
Local-only PDF prep for the MCP-driven ingest flow.

What this does:
  1. Hash + extract text from the PDF (pdfplumber)
  2. Gemini structured extraction (strict JSON schema)
  3. Gemini embedding (1536-dim via Matryoshka)
  4. (default) Upload the PDF to Supabase Storage via HTTP
  5. Emit a JSON payload to stdout (or -o <file>) that includes a pre-built
     `sql_upsert` statement — Claude forwards it to `mcp__supabase__execute_sql`.

What this deliberately does NOT do:
  - Call the Supabase DB directly (that's Claude's job via MCP).

Usage:
    python prep.py /abs/path/to/file.pdf               # upload PDF + stdout JSON
    python prep.py /abs/path/to/file.pdf -o out.json   # write JSON to file
    python prep.py /abs/path/to/file.pdf --no-upload   # skip Storage; storage_path = file://...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pdfplumber  # type: ignore
import requests
from dotenv import load_dotenv
# ── ootb-proposal-automation: unified .env resolver ─────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_env as _ootb_load_env



# =========================================================================
# env
# =========================================================================
def load_env() -> dict[str, Any]:
    here = Path(__file__).resolve().parent
    # Prefer user-writable location (configure-env writes here)
    _ootb_load_env(caller_script=Path(__file__))

    gkey = os.getenv("GEMINI_API_KEY")
    if not gkey:
        print("ERROR: GEMINI_API_KEY not set. See scripts/.env.example.",
              file=sys.stderr)
        sys.exit(2)

    return {
        "GEMINI_API_KEY":      gkey,
        "GEMINI_CHAT_MODEL":   os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash"),
        "GEMINI_EMBED_MODEL":  os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001"),
        "EMBED_DIM":           int(os.getenv("EMBED_DIM", "1536")),
        "SUPABASE_URL":        os.getenv("SUPABASE_URL", "").rstrip("/"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        "SUPABASE_BUCKET":     os.getenv("SUPABASE_BUCKET", "proposals"),
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


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def extract_pdf_text(p: Path) -> tuple[str, int]:
    with pdfplumber.open(str(p)) as pdf:
        pages = pdf.pages
        parts = []
        for pg in pages:
            t = pg.extract_text() or ""
            if t:
                parts.append(t)
        return "\n\n".join(parts), len(pages)


# =========================================================================
# gemini
# =========================================================================
PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title":            {"type": "string"},
        "project_year":     {"type": "integer", "nullable": True},
        "client_name":      {"type": "string",  "nullable": True},
        "client_type":      {"type": "string",  "nullable": True,
                              "enum": ["공공","민간","지자체","기타"]},
        "industry":         {"type": "string",  "nullable": True},
        "service_category": {"type": "array",   "items": {"type": "string"}},
        "budget_krw":       {"type": "integer", "nullable": True},
        "contract_start":   {"type": "string",  "nullable": True},
        "contract_end":     {"type": "string",  "nullable": True},
        "submitted_at":     {"type": "string",  "nullable": True},
        "abstract":         {"type": "string"},
        "key_points":       {"type": "array",   "items": {"type": "string"}},
        "objectives":       {"type": "string",  "nullable": True},
        "strategy":         {"type": "string",  "nullable": True},
        "deliverables":     {"type": "array",   "items": {"type": "string"}},
        "tags":             {"type": "array",   "items": {"type": "string"}},
    },
    "required": ["title","abstract","key_points","tags",
                 "service_category","deliverables"],
}

EXTRACT_SYSTEM = (
    "당신은 한국어 제안서(RFP 응찰 제안)의 메타데이터를 구조화하는 추출기입니다. "
    "표지/목차/본문/부록을 고려해 핵심 정보를 JSON으로 산출하세요. "
    "확실하지 않은 필드는 null로 두고, 추측하지 마세요. "
    "tags는 검색에 유용한 핵심 키워드 5~12개로 구성합니다."
)


def gemini_extract(env, full_text: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=env["GEMINI_API_KEY"])
    clipped = full_text[:120_000]
    response = client.models.generate_content(
        model=env["GEMINI_CHAT_MODEL"],
        contents=[{"role": "user",
                   "parts": [{"text": f"{EXTRACT_SYSTEM}\n\n--- 제안서 원문 ---\n{clipped}"}]}],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PROPOSAL_SCHEMA,
            temperature=0.1,
        ),
    )
    return json.loads(response.text)


def gemini_embed(env, text: str) -> list[float]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=env["GEMINI_API_KEY"])
    result = client.models.embed_content(
        model=env["GEMINI_EMBED_MODEL"],
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=env["EMBED_DIM"]),
    )
    values = result.embeddings[0].values
    if len(values) != env["EMBED_DIM"]:
        raise RuntimeError(
            f"Expected {env['EMBED_DIM']}-dim embedding, got {len(values)}. "
            f"Check GEMINI_EMBED_MODEL supports output_dimensionality."
        )
    return list(values)


# =========================================================================
# storage upload (direct HTTP — MCP can't do binary)
# =========================================================================
def storage_upload(env, local_path: Path, object_path: str) -> str:
    """
    PUT /storage/v1/object/{bucket}/{path}
    Returns storage path ('<bucket>/<object_path>' style).
    """
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
# sql building
# =========================================================================
def sql_str(v: Any) -> str:
    """Quote a scalar for SQL. Single-quote escape by doubling."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def sql_array(arr: list[str] | None, el_cast: str = "text") -> str:
    if not arr:
        return "'{}'"
    parts = ",".join(s.replace('"', '\\"') for s in arr)
    # Use array constructor so unicode escapes stay safe
    elements = ",".join(sql_str(x) for x in arr)
    return f"array[{elements}]::{el_cast}[]"


def sql_daterange(start: str | None, end: str | None) -> str:
    if not start and not end:
        return "null"
    lo = start or ""
    hi = end or ""
    return f"'[{lo},{hi}]'::daterange"


def build_upsert_sql(row: dict[str, Any], embedding: list[float] | None,
                     embed_input: str | None = None) -> str:
    """Build INSERT ... ON CONFLICT statement.

    If `embedding` is given, inlines it as a vector literal.
    If `embedding` is None, inlines a call to public.gemini_embed(<input>, <key>)
    where <input> is `embed_input` and <key> is the placeholder
    `'<GEMINI_API_KEY>'` that the caller must substitute before execute.
    """
    if embedding is not None:
        vec_expr = "'[" + ",".join(f"{x:.6f}" for x in embedding) + "]'::vector(1536)"
    else:
        if not embed_input:
            raise ValueError("embed_input required when embedding is None")
        safe = embed_input.replace("'", "''")
        vec_expr = f"public.gemini_embed('{safe}', '<GEMINI_API_KEY>')"
    cols_vals = {
        "storage_bucket":   sql_str(row["storage_bucket"]),
        "storage_path":     sql_str(row["storage_path"]),
        "file_name":        sql_str(row["file_name"]),
        "file_hash":        sql_str(row["file_hash"]),
        "file_size":        sql_str(row["file_size"]),
        "page_count":       sql_str(row["page_count"]),
        "mime_type":        sql_str(row.get("mime_type","application/pdf")),

        "doc_type":         sql_str(row.get("doc_type","제안서")),
        "title":            sql_str(row["title"]),
        "project_year":     sql_str(row.get("project_year")),
        "client_name":      sql_str(row.get("client_name")),
        "client_type":      sql_str(row.get("client_type")),
        "industry":         sql_str(row.get("industry")),
        "service_category": sql_array(row.get("service_category") or []),
        "budget_krw":       sql_str(row.get("budget_krw")),
        "contract_period":  sql_daterange(row.get("contract_start"), row.get("contract_end")),
        "submitted_at":     sql_str(row.get("submitted_at")),

        "abstract":         sql_str(row.get("abstract")),
        "key_points":       sql_array(row.get("key_points") or []),
        "objectives":       sql_str(row.get("objectives")),
        "strategy":         sql_str(row.get("strategy")),
        "deliverables":     sql_array(row.get("deliverables") or []),
        "tags":             sql_array(row.get("tags") or []),

        "full_text":        sql_str(row.get("full_text","")),

        "embedding":        vec_expr,
        "embedding_model":  sql_str(row.get("embedding_model")),
        "embedding_input_hash": sql_str(row.get("embedding_input_hash")),
    }
    cols = ",".join(cols_vals.keys())
    vals = ",".join(cols_vals.values())
    update = ",".join(f"{k}=excluded.{k}" for k in cols_vals.keys()
                      if k not in ("file_hash",))
    return (
        f"insert into public.proposals ({cols}) values ({vals}) "
        f"on conflict (file_hash) do update set {update} "
        "returning id, title, project_year;"
    )


# =========================================================================
# main
# =========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="Prep a PDF for MCP-driven upsert.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="Write JSON payload to this file (else stdout).")
    ap.add_argument("--no-upload", action="store_true",
                    help="Skip Supabase Storage upload; storage_path = file://...")
    ap.add_argument("--skip-embed", action="store_true",
                    help="Skip Gemini embedding. The output SQL will call "
                         "public.gemini_embed(input_text, <your key>) inline "
                         "instead (requires sql/002_embed_in_db.sql applied). "
                         "Use this when local Gemini API is blocked.")
    ap.add_argument("--year-hint", type=int, default=None,
                    help="Year used in the Storage key path if project_year is null.")
    args = ap.parse_args()

    p = args.pdf.expanduser().resolve()
    if not p.exists() or p.suffix.lower() != ".pdf":
        print(f"ERROR: {p} is not an existing PDF", file=sys.stderr)
        return 2

    env = load_env()

    print(f"[1/5] hashing + extracting text from {p.name}", file=sys.stderr)
    fhash = sha256_file(p)
    full_text, page_count = extract_pdf_text(p)
    if not full_text.strip():
        print("ERROR: empty text (likely scanned PDF; OCR not included).",
              file=sys.stderr)
        return 3

    print(f"[2/5] gemini structured extraction ({env['GEMINI_CHAT_MODEL']})",
          file=sys.stderr)
    meta = gemini_extract(env, full_text)

    embed_input = "\n\n".join([
        f"TITLE: {meta.get('title','')}",
        f"ABSTRACT: {meta.get('abstract','')}",
        "KEY_POINTS: " + " / ".join(meta.get("key_points") or []),
        "TAGS: " + ", ".join(meta.get("tags") or []),
    ])
    emb_hash = sha256_str(embed_input)
    if args.skip_embed:
        print("[3/5] SKIP embedding (--skip-embed). SQL will call "
              "public.gemini_embed() inline.", file=sys.stderr)
        embedding = None
    else:
        print(f"[3/5] gemini embedding ({env['GEMINI_EMBED_MODEL']}, "
              f"{env['EMBED_DIM']}-d)", file=sys.stderr)
        embedding = gemini_embed(env, embed_input)

    # Storage path — must be ASCII-only. Supabase Storage rejects Korean/spaces
    # in object keys. Use {year}/{hash12}-{ascii_stem}.pdf so different files
    # don't collide and the original filename is still in `file_name` column.
    import re
    year = str(meta.get("project_year") or args.year_hint or "unknown")
    stem_ascii = unicodedata.normalize("NFKD", p.stem).encode("ascii","ignore").decode("ascii")
    stem_ascii = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem_ascii).strip("-._") or "proposal"
    object_key = f"{year}/{fhash[:12]}-{stem_ascii[:40]}.pdf"

    if args.no_upload or not env["SUPABASE_URL"]:
        print("[4/5] SKIP storage upload (--no-upload or env not set)",
              file=sys.stderr)
        storage_bucket = None
        storage_path = f"file://{p}"
    else:
        print(f"[4/5] uploading to Storage bucket={env['SUPABASE_BUCKET']} "
              f"key={object_key}", file=sys.stderr)
        storage_upload(env, p, object_key)
        storage_bucket = env["SUPABASE_BUCKET"]
        storage_path = object_key

    # Build row dict
    row = {
        "storage_bucket":   storage_bucket,
        "storage_path":     storage_path,
        "file_name":        p.name,
        "file_hash":        fhash,
        "file_size":        p.stat().st_size,
        "page_count":       page_count,
        "mime_type":        "application/pdf",

        "doc_type":         "제안서",
        "title":            meta.get("title") or p.stem,
        "project_year":     meta.get("project_year"),
        "client_name":      meta.get("client_name"),
        "client_type":      meta.get("client_type"),
        "industry":         meta.get("industry"),
        "service_category": meta.get("service_category") or [],
        "budget_krw":       meta.get("budget_krw"),
        "contract_start":   meta.get("contract_start"),
        "contract_end":     meta.get("contract_end"),
        "submitted_at":     meta.get("submitted_at"),

        "abstract":         meta.get("abstract"),
        "key_points":       meta.get("key_points") or [],
        "objectives":       meta.get("objectives"),
        "strategy":         meta.get("strategy"),
        "deliverables":     meta.get("deliverables") or [],
        "tags":             meta.get("tags") or [],

        "full_text":        full_text,

        "embedding_model":      env["GEMINI_EMBED_MODEL"],
        "embedding_input_hash": emb_hash,
    }

    print("[5/5] building SQL upsert", file=sys.stderr)
    sql = build_upsert_sql(row, embedding, embed_input=embed_input)

    payload = {
        "file_hash": fhash,
        "storage_path": storage_path,
        "title": row["title"],
        "project_year": row["project_year"],
        "tags": row["tags"],
        "page_count": page_count,
        "embedding_dim": len(embedding),
        "sql_upsert": sql,
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
