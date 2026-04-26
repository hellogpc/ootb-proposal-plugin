#!/usr/bin/env python3
"""
Convert a built .pptx to per-slide JPGs via LibreOffice + pdftoppm so we can
visually inspect the output. Prints absolute paths of the generated images.

Usage:
    python quickcheck.py path/to/output.pptx
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], **kw) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx", type=Path)
    ap.add_argument("--dpi", type=int, default=120)
    args = ap.parse_args()

    if not args.pptx.exists():
        print(f"ERROR: {args.pptx} not found", file=sys.stderr)
        return 2

    out_dir = args.pptx.parent / (args.pptx.stem + "_slides")
    out_dir.mkdir(exist_ok=True)

    # Clean old slides
    for old in out_dir.glob("slide-*.jpg"):
        old.unlink(missing_ok=True)

    if shutil.which("soffice") is None:
        print("ERROR: `soffice` (LibreOffice) not found on PATH.\n"
              "Install it or open the pptx manually.", file=sys.stderr)
        return 3
    if shutil.which("pdftoppm") is None:
        print("ERROR: `pdftoppm` (poppler) not found on PATH.", file=sys.stderr)
        return 3

    # 1) pptx -> pdf
    run(["soffice", "--headless",
         "--convert-to", "pdf",
         "--outdir", str(out_dir),
         str(args.pptx)])
    pdf = out_dir / (args.pptx.stem + ".pdf")
    if not pdf.exists():
        print(f"ERROR: PDF not produced at {pdf}", file=sys.stderr)
        return 4

    # 2) pdf -> jpgs
    run(["pdftoppm", "-jpeg", "-r", str(args.dpi), str(pdf),
         str(out_dir / "slide")])

    jpgs = sorted(out_dir.glob("slide-*.jpg"))
    for j in jpgs:
        print(j.resolve())
    print(f"\nWrote {len(jpgs)} image(s) to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
