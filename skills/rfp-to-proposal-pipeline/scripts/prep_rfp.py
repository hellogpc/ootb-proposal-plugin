#!/usr/bin/env python3
"""
RFP prep: read a Korean 제안요청서 / 과업지시서 / 공고 PDF and produce the JSON
needed to query the `proposals` table and later synthesize an outline.yaml.

Usage:
    python prep_rfp.py /abs/path/to/RFP.pdf -o /tmp/rfp.json

Output JSON shape:
    {
      "rfp_meta":        {...structured fields...},
      "rfp_summary":     "3~5 문장 요약",
      "rfp_full_text":   "원문 (정제 후)",
      "query_text":      "검색용 키워드 문자열",
      "query_embedding": "[0.012,-0.134,...]"   # pgvector literal (1536-d)
    }
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pdfplumber  # type: ignore
from dotenv import load_dotenv
# ── ootb-proposal-automation: unified .env resolver ─────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_env as _ootb_load_env



# =========================================================================
# RFP extraction schema (different from 제안서 schema — RFP-side fields)
# =========================================================================
RFP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_title":      {"type": "string",
                                "description": "공고/과업의 공식 사업명"},
        "issuing_org":        {"type": "string", "nullable": True,
                                "description": "발주기관"},
        "industry":           {"type": "string", "nullable": True,
                                "description": "분야 (복지/수산/환경/관광 등)"},
        "scope_of_work":      {"type": "array",  "items": {"type": "string"},
                                "description": "과업범위 주요 항목 5~12개"},
        "target_audience":    {"type": "string", "nullable": True,
                                "description": "주요 타깃 (일반국민/MZ/청년/어촌 등)"},
        "budget_krw":         {"type": "integer", "nullable": True,
                                "description": "예산(원). 없으면 null"},
        "duration":           {"type": "string", "nullable": True,
                                "description": "사업기간 (예: 2026.04.~2026.12.)"},
        "deadline":           {"type": "string", "nullable": True,
                                "description": "제안서 제출 마감 YYYY-MM-DD"},
        "evaluation_criteria":{"type": "array",  "items": {"type": "string"},
                                "description": "평가항목/배점 등"},
        "required_deliverables":{"type": "array","items": {"type": "string"},
                                  "description": "필수 산출물 리스트"},
        "keywords":           {"type": "array",  "items": {"type": "string"},
                                "description": "검색에 쓸 핵심 키워드 6~15개"},
        "summary":            {"type": "string",
                                "description": "3~5 문장의 과업 요약"},
    },
    "required": ["project_title", "scope_of_work", "keywords", "summary"],
}

RFP_SYSTEM = (
    "당신은 공공/민간 공고문(RFP, 제안요청서, 과업지시서)에서 핵심 정보를 "
    "JSON 스키마에 맞춰 추출하는 추출기입니다. 표지/총칙/과업내용/예산/일정/"
    "평가기준을 읽어 구조화하세요. 확실하지 않은 필드는 null로 두세요."
)


# =========================================================================
# env
# =========================================================================
def load_env() -> dict[str, Any]:
    here = Path(__file__).resolve().parent
    # Unified resolver: user config → $CLAUDE_PLUGIN_ROOT → sibling skill → here
    _ootb_load_env(caller_script=Path(__file__))

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("ERROR: GEMINI_API_KEY not found in .env (tried this skill's "
              "scripts/.env and proposal-supabase-sync/scripts/.env)",
              file=sys.stderr)
        sys.exit(2)
    return {
        "GEMINI_API_KEY":     key,
        "GEMINI_CHAT_MODEL":  os.getenv("GEMINI_CHAT_MODEL",  "gemini-2.5-flash"),
        "GEMINI_EMBED_MODEL": os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001"),
        "EMBED_DIM":          int(os.getenv("EMBED_DIM", "1536")),
    }


# =========================================================================
# helpers
# =========================================================================
def extract_pdf_text(p: Path) -> str:
    parts: list[str] = []
    with pdfplumber.open(str(p)) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if t:
                parts.append(t)
    return "\n\n".join(parts)


def gemini_extract(env, text: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=env["GEMINI_API_KEY"])
    clipped = text[:120_000]
    response = client.models.generate_content(
        model=env["GEMINI_CHAT_MODEL"],
        contents=[{"role": "user",
                   "parts": [{"text": f"{RFP_SYSTEM}\n\n--- RFP 원문 ---\n{clipped}"}]}],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RFP_SCHEMA,
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
    values = list(result.embeddings[0].values)
    if len(values) != env["EMBED_DIM"]:
        raise RuntimeError(
            f"expected {env['EMBED_DIM']}-d embedding, got {len(values)}.")
    return values


# =========================================================================
# main
# =========================================================================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    if not args.pdf.exists() or args.pdf.suffix.lower() != ".pdf":
        print(f"ERROR: {args.pdf} is not a PDF", file=sys.stderr)
        return 2

    env = load_env()

    print("[1/3] extracting text", file=sys.stderr)
    full_text = extract_pdf_text(args.pdf)
    if not full_text.strip():
        print("ERROR: empty text (scanned PDF — OCR not included)", file=sys.stderr)
        return 3

    print(f"[2/3] Gemini structured extraction ({env['GEMINI_CHAT_MODEL']})",
          file=sys.stderr)
    rfp = gemini_extract(env, full_text)

    # Build query text (for tsvector) and embed input (for vector search)
    keywords = rfp.get("keywords") or []
    scope    = rfp.get("scope_of_work") or []
    query_text = " ".join([rfp.get("project_title","")] + keywords + scope[:5])

    embed_input = "\n\n".join([
        f"TITLE: {rfp.get('project_title','')}",
        f"INDUSTRY: {rfp.get('industry','')}",
        f"SUMMARY: {rfp.get('summary','')}",
        "SCOPE: " + " / ".join(scope),
        "KEYWORDS: " + ", ".join(keywords),
        f"TARGET: {rfp.get('target_audience','')}",
    ])

    print(f"[3/3] Gemini embedding ({env['GEMINI_EMBED_MODEL']}, "
          f"{env['EMBED_DIM']}-d)", file=sys.stderr)
    vec = gemini_embed(env, embed_input)
    vec_literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

    payload = {
        "rfp_meta":        rfp,
        "rfp_summary":     rfp.get("summary"),
        "rfp_full_text":   full_text,
        "query_text":      query_text,
        "query_embedding": vec_literal,
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
