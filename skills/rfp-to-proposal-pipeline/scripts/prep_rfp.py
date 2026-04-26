#!/usr/bin/env python3
"""
RFP prep: extract text from a Korean 제안요청서 / 과업지시서 / 공고 PDF.

What this does:
  1. Extract text from the PDF (pdfplumber)
  2. Emit JSON — Claude reads it, does structured extraction, builds query_text,
     and searches with gemini_embed_vault() inline in SQL via MCP.

What this does NOT do:
  - Call Gemini (GEMINI_API_KEY not required)
  - Generate embeddings (handled by gemini_embed_vault() inside DB)
  - Extract structured metadata (handled by Claude)

Usage:
    python prep_rfp.py /abs/path/to/RFP.pdf -o /tmp/rfp.json

Output JSON shape:
    {
      "rfp_full_text": "원문 (정제 후)",
      "page_count":    42,
      "file_name":     "RFP.pdf"
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pdfplumber  # type: ignore


# =========================================================================
# helpers
# =========================================================================
def extract_pdf_text(p: Path) -> tuple[str, int]:
    parts: list[str] = []
    with pdfplumber.open(str(p)) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if t:
                parts.append(t)
        return "\n\n".join(parts), len(pdf.pages)


# =========================================================================
# main
# =========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="Extract RFP PDF text for Claude to process.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    p = args.pdf.expanduser().resolve()
    if not p.exists() or p.suffix.lower() != ".pdf":
        print(f"ERROR: {p} is not a PDF", file=sys.stderr)
        return 2

    print("[1/1] extracting text", file=sys.stderr)
    full_text, page_count = extract_pdf_text(p)
    if not full_text.strip():
        print("ERROR: empty text (scanned PDF — OCR not included)", file=sys.stderr)
        return 3

    payload = {
        "rfp_full_text": full_text,
        "page_count":    page_count,
        "file_name":     p.name,
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
