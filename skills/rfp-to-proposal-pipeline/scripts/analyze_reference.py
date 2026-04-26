#!/usr/bin/env python3
"""
analyze_reference.py — 과거 유사 제안서 PDF(들)에서 스타일 토큰을 추출.

Input
-----
PDF 경로 또는 signed URL 하나 이상. 각각을 내려받아 상위 N개 페이지를 썸네일로
렌더한 뒤, K-means 로 지배 색상을 뽑고, OOTB 브랜드 토큰(navy_deep / navy /
blue / blue_bright / blue_light / bg_light)에 역할을 매핑해 저장한다.

Output
------
- reference_thumbnails/<hash>/page-NN.jpg   (Claude 시각 검토용)
- reference_palette.json                    (prepare_deck --reference-palette로 주입)

Usage
-----
    # 로컬 PDF
    python analyze_reference.py /abs/path/A.pdf /abs/path/B.pdf \
        -o /tmp/reference_palette.json -t /tmp/reference_thumbs/

    # signed URL
    python analyze_reference.py --url "https://...A.pdf" "https://...B.pdf" \
        -o /tmp/reference_palette.json

Heuristics
----------
* 각 PDF 당 최대 3 페이지 (cover · 중간 본문 · 색대비 파악용 1장).
* 픽셀 샘플링: 200×150 축소.
* 색 공간: RGB. 인접한 클러스터는 HSV 거리로 병합.
* 역할 매핑:
    navy_deep  = 가장 어둡고 채도 있는 색 (V<0.3, S>0.3)
    blue_bright= 가장 채도 높은 파랑 (H∈[180,240], S>0.6, V>0.5)
    blue       = blue_bright 보다 조금 어두운 파랑
    blue_light = 채도 낮은 밝은 파랑 (V>0.7, S∈[0.1,0.4])
    navy       = 어두운 파랑 중 중간 밝기 (V∈[0.15,0.35])
    bg_light   = 거의 흰색에 가깝지만 순백은 아닌 색 (V>0.85, S<0.1)
    text_dark  = 거의 검정 (V<0.15)
* 역할 매핑이 실패하면 해당 key 는 null. 주입할 때 null은 스킵한다.
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from PIL import Image
from sklearn.cluster import KMeans


# ---------- helpers ----------

def hash8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def fetch_pdf(src: str, cache_dir: Path) -> Path:
    """Download (if URL) or resolve a PDF path. Caches by URL hash."""
    if src.startswith(("http://", "https://")):
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / f"{hash8(src)}.pdf"
        if target.exists() and target.stat().st_size > 0:
            return target
        r = requests.get(src, timeout=90)
        r.raise_for_status()
        target.write_bytes(r.content)
        return target
    p = Path(src).expanduser().resolve()
    if not p.exists() or p.suffix.lower() != ".pdf":
        raise FileNotFoundError(f"{src} is not a readable PDF")
    return p


def pdf_to_thumbs(pdf: Path, out_dir: Path, max_pages: int = 3,
                  dpi: int = 60) -> list[Path]:
    """Render up to `max_pages` evenly-spaced pages to JPG."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # count pages
    res = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    n_pages = 1
    for line in (res.stdout or "").splitlines():
        if line.startswith("Pages:"):
            n_pages = int(line.split()[1]); break
    # pick page indices: first, middle, middle+1 (up to max)
    if n_pages <= max_pages:
        pages = list(range(1, n_pages + 1))
    else:
        pages = sorted({1, max(1, n_pages // 3), max(1, 2 * n_pages // 3), n_pages})[:max_pages]
    results: list[Path] = []
    for p in pages:
        out_prefix = out_dir / f"page-{p:02d}"
        subprocess.run(
            ["pdftoppm", "-jpeg", "-r", str(dpi), "-f", str(p), "-l", str(p),
             str(pdf), str(out_prefix)],
            check=True, capture_output=True,
        )
        # pdftoppm appends suffix based on page count; find the produced file
        candidates = sorted(out_dir.glob(f"page-{p:02d}*.jpg"))
        if candidates:
            results.append(candidates[-1])
    return results


# ---------- color analysis ----------

def collect_pixels(jpgs: list[Path], resize_to: tuple[int,int]=(200,150)) -> np.ndarray:
    parts = []
    for j in jpgs:
        img = Image.open(j).convert("RGB").resize(resize_to, Image.LANCZOS)
        parts.append(np.array(img).reshape(-1, 3))
    return np.concatenate(parts, axis=0) if parts else np.empty((0,3), dtype=np.uint8)


def cluster_colors(pixels: np.ndarray, k: int = 10) -> list[tuple[np.ndarray, int]]:
    """K-means cluster; return list of (center_rgb, count) sorted by count desc."""
    if len(pixels) < k * 10:
        return []
    km = KMeans(n_clusters=k, n_init=4, random_state=0)
    labels = km.fit_predict(pixels)
    centers = km.cluster_centers_.astype(np.float32)
    counts = np.bincount(labels, minlength=k)
    order = np.argsort(-counts)
    return [(centers[i], int(counts[i])) for i in order]


def rgb_to_hex(rgb: np.ndarray) -> str:
    r, g, b = (int(round(c)) for c in rgb)
    return f"{r:02X}{g:02X}{b:02X}"


def rgb_to_hsv(rgb: np.ndarray) -> tuple[float, float, float]:
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h, s, v


def role_match(clusters: list[tuple[np.ndarray,int]]) -> dict[str, Optional[str]]:
    """Map clusters to brand roles using HSV heuristics. Returns hex strings."""
    # Decorate each cluster with hsv
    decorated = []
    for rgb, n in clusters:
        h, s, v = rgb_to_hsv(rgb)
        decorated.append((rgb, n, h, s, v))

    def pick(cond, key):
        found = [(rgb, n, h, s, v) for (rgb, n, h, s, v) in decorated if cond(h, s, v)]
        if not found:
            return None
        # pick by highest count
        found.sort(key=key)
        return rgb_to_hex(found[0][0])

    # navy_deep: V<0.25, S>0.25
    navy_deep = pick(
        lambda h, s, v: v < 0.25 and s > 0.25,
        key=lambda x: (-x[1], x[4]),  # prefer frequent + darkest
    )
    # navy: V∈[0.15,0.45], S>0.25, H near blue (180°-260°) → 0.5-0.72
    navy = pick(
        lambda h, s, v: 0.15 <= v <= 0.45 and s > 0.25 and 0.5 <= h <= 0.72,
        key=lambda x: (-x[1],),
    )
    # blue_bright: saturated blue
    blue_bright = pick(
        lambda h, s, v: 0.5 <= h <= 0.66 and s > 0.6 and v > 0.5,
        key=lambda x: (-x[3], -x[1]),  # prefer highest sat
    )
    # blue: slightly darker saturated blue
    blue = pick(
        lambda h, s, v: 0.5 <= h <= 0.66 and 0.45 < s and 0.3 < v < 0.7,
        key=lambda x: (-x[1],),
    )
    # blue_light: pale blue
    blue_light = pick(
        lambda h, s, v: 0.5 <= h <= 0.66 and 0.08 < s < 0.55 and v > 0.75,
        key=lambda x: (-x[1],),
    )
    # bg_light: near-white (not pure white)
    bg_light = pick(
        lambda h, s, v: v > 0.85 and s < 0.10,
        key=lambda x: (-x[1], -x[4]),
    )
    # text_dark: near-black
    text_dark = pick(
        lambda h, s, v: v < 0.15,
        key=lambda x: (-x[1],),
    )

    return {
        "navy_deep":   navy_deep,
        "navy":        navy,
        "blue":        blue or blue_bright,
        "blue_bright": blue_bright or blue,
        "blue_light":  blue_light,
        "bg_light":    bg_light,
        "text_dark":   text_dark,
    }


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="Extract OOTB palette from past proposal PDFs.")
    ap.add_argument("refs", nargs="*", help="local PDF paths")
    ap.add_argument("--url", nargs="*", default=[], help="signed URLs")
    ap.add_argument("-o", "--out", type=Path, required=True,
                    help="reference_palette.json 출력 경로")
    ap.add_argument("-t", "--thumbs", type=Path, default=None,
                    help="썸네일 출력 루트 (기본: out 옆 /reference_thumbs)")
    ap.add_argument("--pages", type=int, default=3, help="각 PDF 당 페이지 수")
    ap.add_argument("--k", type=int, default=10, help="클러스터 수 per deck")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    sources = list(args.refs) + list(args.url)
    if not sources:
        print("no PDF/URL provided", file=sys.stderr); return 2

    thumbs_root = args.thumbs or args.out.parent / "reference_thumbs"
    thumbs_root.mkdir(parents=True, exist_ok=True)

    cache_dir = Path(tempfile.gettempdir()) / "ootb_ref_pdf_cache"

    # per-source clusters
    per_deck: list[dict] = []
    all_pixels: list[np.ndarray] = []

    for src in sources:
        try:
            pdf = fetch_pdf(src, cache_dir)
        except Exception as e:
            print(f"WARN fetch failed: {src} — {e}", file=sys.stderr)
            continue
        bucket = thumbs_root / hash8(src)
        jpgs = pdf_to_thumbs(pdf, bucket, max_pages=args.pages)
        if not jpgs:
            print(f"WARN no thumbnails for {src}", file=sys.stderr); continue
        px = collect_pixels(jpgs)
        all_pixels.append(px)
        clusters = cluster_colors(px, k=args.k)
        roles = role_match(clusters)
        per_deck.append({
            "source": src,
            "thumbnails": [str(j) for j in jpgs],
            "dominant": [{"hex": rgb_to_hex(c), "count": n} for c, n in clusters[:6]],
            "roles": roles,
        })
        if args.verbose:
            print(f"[{src}]")
            for r, hx in roles.items(): print(f"  {r:<12} {hx}")

    if not per_deck:
        print("ERROR: no decks analyzed", file=sys.stderr); return 3

    # cross-deck consensus — most common hex across decks per role
    from collections import Counter
    consensus: dict[str, Optional[str]] = {}
    for role in ["navy_deep","navy","blue","blue_bright","blue_light","bg_light","text_dark"]:
        vals = [d["roles"].get(role) for d in per_deck if d["roles"].get(role)]
        if not vals:
            consensus[role] = None; continue
        c = Counter(vals).most_common(1)[0][0]
        consensus[role] = c

    # pooled clustering as fallback
    pooled = np.concatenate(all_pixels, axis=0) if all_pixels else None
    pooled_clusters = cluster_colors(pooled, k=args.k) if pooled is not None else []

    result = {
        "schema_version": "1.0",
        "source_count":   len(per_deck),
        "per_deck":       per_deck,
        "consensus":      consensus,                    # role → hex (null OK)
        "pooled_dominant":[{"hex": rgb_to_hex(c), "count": n}
                           for c, n in pooled_clusters[:10]],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK  wrote {args.out}")
    print("consensus roles:")
    for k, v in consensus.items(): print(f"  {k:<12} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
