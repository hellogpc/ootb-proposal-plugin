#!/usr/bin/env python3
"""
prepare_deck.py — OOTB Lab 제안서 *데이터 추출/정규화* 단계.

입력:
  - outline.yaml              (사용자/Claude가 작성한 슬라이드 아우트라인)
  - brand/brand.json          (브랜드 토큰 — 팔레트/폰트/사이즈)
  - brand/blueprints.md       (참고용, 이 스크립트는 읽지 않음)

출력:
  - deck_plan.json            (렌더링 엔진에 그대로 넘길 수 있는 구조화된 스펙)

이 스크립트는 PPT 파일을 만들지 않는다. 실제 렌더링은 `anthropic-skills:pptx`
스킬(pptxgenjs 가이드)를 따라 `scripts/render_deck.js` 로 수행.

Usage:
    python prepare_deck.py outline.yaml -o deck_plan.json [--validate]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


VALID_TYPES = {
    "cover", "toc", "section_divider", "hero",
    "content", "content_image", "closing",
}

REQUIRED_FIELDS = {
    "cover":            [],
    "toc":              ["items"],
    "section_divider":  ["title"],
    "hero":             ["headline"],
    "content":          ["title", "body"],
    "content_image":    ["title"],
    "closing":          [],
}


def load_brand(here: Path) -> dict:
    """Load brand.json. Tries skill-local brand/brand.json first."""
    brand_path = here.parent / "brand" / "brand.json"
    if not brand_path.exists():
        sys.exit(f"ERROR: brand/brand.json not found at {brand_path}")
    return json.loads(brand_path.read_text(encoding="utf-8"))


def resolve_assets_dir(outline_path: Path) -> Path:
    """Look for assets/ next to the outline, then at the skill root."""
    cand = [outline_path.parent / "assets",
            outline_path.parent.parent / "assets"]
    for p in cand:
        if p.exists():
            return p.resolve()
    return (outline_path.parent / "assets").resolve()  # non-existent but fine


def validate_outline(outline: dict) -> list[str]:
    """Return list of errors (empty = OK)."""
    errs: list[str] = []
    slides = outline.get("slides")
    if not isinstance(slides, list):
        return ["outline missing top-level `slides:` list"]

    nums_seen: list[str] = []
    toc_count = 0

    for i, sl in enumerate(slides):
        t = sl.get("type")
        if t not in VALID_TYPES:
            errs.append(f"slide#{i}: unknown type {t!r}; valid={sorted(VALID_TYPES)}")
            continue
        for req in REQUIRED_FIELDS[t]:
            if req not in sl:
                errs.append(f"slide#{i} ({t}): missing required field `{req}`")

        if t == "section_divider":
            num = str(sl.get("number") or "")
            nums_seen.append(num)
        if t == "toc":
            toc_count = len(sl.get("items") or [])
        if t == "content":
            body = sl.get("body") or []
            if not (2 <= len(body) <= 4):
                errs.append(
                    f"slide#{i} (content): body length={len(body)}; must be 2~4. "
                    "Split into multiple slides if too many."
                )
            for j, b in enumerate(body):
                txt = (b or {}).get("text") or ""
                if len(txt) > 120:
                    errs.append(
                        f"slide#{i} (content) body#{j}: text length {len(txt)} > 120; "
                        "consider shortening."
                    )

    if toc_count and nums_seen and toc_count != len(nums_seen):
        errs.append(
            f"TOC items ({toc_count}) != section_divider count ({len(nums_seen)})"
        )
    # warn if numbering non-consecutive (roman I-IV or arabic 01-NN)
    if nums_seen and all(n.isdigit() for n in nums_seen):
        ints = [int(n) for n in nums_seen]
        if ints != list(range(ints[0], ints[0] + len(ints))):
            errs.append(f"section_divider numbers not consecutive: {nums_seen}")

    hero_count = sum(1 for s in slides if s.get("type") == "hero")
    if hero_count > 2:
        errs.append(f"hero slides = {hero_count} (recommended max 2)")

    return errs


def build_deck_plan(outline: dict, brand: dict, assets_dir: Path) -> dict:
    """Produce a fully-resolved deck plan for the renderer.

    The renderer receives:
      - brand tokens (flat, already resolved)
      - per-slide `fields` (just the content, no layout math)
      - `blueprint` key pointing to which blueprint to apply
    """
    project = outline.get("project") or {}
    brand_merged = dict(brand)
    # Allow outline.brand overrides
    for k, v in (outline.get("brand") or {}).items():
        brand_merged[k] = v
    # Expose assets_dir absolute path if it exists
    brand_merged["assets_dir"] = str(assets_dir) if assets_dir.exists() else None

    resolved_slides: list[dict] = []
    for sl in outline.get("slides", []):
        t = sl["type"]
        fields = {k: v for k, v in sl.items() if k != "type"}
        # Fill defaults from project/brand where blueprint expects
        if t == "cover":
            fields.setdefault("title",   project.get("title", ""))
            fields.setdefault("date",    project.get("date",  ""))
            fields.setdefault("company", brand_merged.get("company_name", ""))
        if t == "closing":
            fields.setdefault("message", "감사합니다")
            fields.setdefault("tagline", f"{brand_merged.get('company_name','')}과 함께하겠습니다")
        resolved_slides.append({"type": t, "blueprint": t, "fields": fields})

    return {
        "schema_version": "1.0",
        "brand":   brand_merged,
        "project": project,
        "slides":  resolved_slides,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="OOTB 제안서 outline.yaml → deck_plan.json")
    ap.add_argument("outline", type=Path, help="outline.yaml 경로")
    ap.add_argument("-o", "--output", type=Path, default=None,
                    help="deck_plan.json 경로 (기본: outline 옆 deck_plan.json)")
    ap.add_argument("--validate", action="store_true",
                    help="구조 검증만 수행 (출력 파일 생성 안 함)")
    ap.add_argument("--reference-palette", type=Path, default=None,
                    help="analyze_reference.py 결과 JSON. 지정되면 consensus roles를 "
                         "brand.palette 위에 덮어씀 (null 값은 스킵).")
    args = ap.parse_args()

    if not args.outline.exists():
        print(f"ERROR: {args.outline} not found", file=sys.stderr)
        return 2

    here = Path(__file__).resolve().parent
    brand = load_brand(here)

    outline = yaml.safe_load(args.outline.read_text(encoding="utf-8"))
    errs = validate_outline(outline)
    if errs:
        print("VALIDATION ERRORS:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        if args.validate:
            return 3
        print("\n(continuing despite errors; fix before rendering)", file=sys.stderr)

    if args.validate:
        print(f"OK  {args.outline} passes validation "
              f"(slides={len(outline.get('slides', []))})")
        return 0

    assets_dir = resolve_assets_dir(args.outline)

    # Optional: merge reference palette on top of brand tokens
    if args.reference_palette:
        if not args.reference_palette.exists():
            print(f"ERROR: {args.reference_palette} not found", file=sys.stderr)
            return 2
        ref = json.loads(args.reference_palette.read_text(encoding="utf-8"))
        consensus = (ref.get("consensus") or {})
        pal = brand.setdefault("palette", {})
        overridden: list[str] = []
        for role, hexval in consensus.items():
            if not hexval:
                continue
            before = pal.get(role)
            if before != hexval:
                pal[role] = hexval
                overridden.append(f"{role}: {before} → {hexval}")
        # stash provenance so the renderer / user can see what happened
        brand["_reference_palette_source"] = str(args.reference_palette)
        brand["_reference_overrides"] = overridden
        if overridden:
            print(f"reference palette applied ({len(overridden)} role(s)):")
            for line in overridden:
                print(f"  - {line}")
        else:
            print("reference palette: no overrides "
                  "(consensus roles already match brand or all null)")

    plan = build_deck_plan(outline, brand, assets_dir)

    out = args.output or (args.outline.parent / "deck_plan.json")
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK  wrote {out}  (slides={len(plan['slides'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
