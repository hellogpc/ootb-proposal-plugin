#!/usr/bin/env node
/**
 * render_deck.js — deck_plan.json → .pptx via pptxgenjs.
 *
 * 이 스크립트는 `anthropic-skills:pptx`의 pptxgenjs 가이드를 따라 작성된
 * 참조 구현이다. `ootb-proposal-pptx/brand/blueprints.md` 의 레시피를 그대로
 * 구현해 OOTB Lab 브랜드 포맷으로 렌더링한다.
 *
 * Usage:
 *   node render_deck.js deck_plan.json -o output.pptx
 */
"use strict";

const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

// ---------- CLI ----------
function parseArgs() {
  const argv = process.argv.slice(2);
  if (argv.length === 0) {
    console.error("usage: node render_deck.js deck_plan.json [-o output.pptx]");
    process.exit(2);
  }
  const planPath = argv[0];
  let outPath = null;
  for (let i = 1; i < argv.length; i++) {
    if ((argv[i] === "-o" || argv[i] === "--output") && argv[i + 1]) {
      outPath = argv[i + 1];
      i++;
    }
  }
  return { planPath, outPath };
}

// ---------- Helpers ----------
// hex(): palette 값을 6자리 HEX로 정규화. 값이 없으면 경고 + 검은색 fallback.
// key를 함께 넘기면 어떤 키가 빠졌는지 stderr에 로그됨.
function hex(c, key) {
  if (c === undefined || c === null) {
    if (key) console.warn(`[WARN] palette.${key} 미정의 → #000000 fallback`);
    return "000000";
  }
  return String(c).replace(/^#/, "");
}

// sz(): sizes_pt 값을 안전하게 읽기. 없으면 fallback + 경고.
function sz(brand, key, fallback) {
  const v = brand.sizes_pt && brand.sizes_pt[key];
  if (v === undefined || v === null) {
    console.warn(`[WARN] sizes_pt.${key} 미정의 → ${fallback}pt fallback`);
    return fallback;
  }
  return v;
}

function assetPath(brand, filename) {
  if (!brand.assets_dir) return null;
  const p = path.join(brand.assets_dir, filename);
  return fs.existsSync(p) ? p : null;
}

// Apply Korean EA font to pptxgenjs text options.
// pptxgenjs has no direct `eastAsiaFontFace`, so we emit the Latin fontFace
// (for non-Hangul) and rely on the viewer to pick an EA font. As a safety net
// we also output `lang: "ko-KR"` to hint at Korean.
function koText(brand, base) {
  return {
    fontFace: brand.fonts.latin,
    lang: "ko-KR",
    ...base,
  };
}

// Add a text run that declares both Latin and EA fonts via a workaround:
// pptxgenjs supports `charSpacing: 0` + rich runs, but to force the EA font
// we post-process the XML after writing. For runtime simplicity we just set
// the fontFace and rely on presentation defaults — PowerPoint will still
// substitute a Korean font for Hangul characters if the declared font lacks
// CJK glyphs.

// ---------- Blueprints ----------
const W = 13.333;  // LAYOUT_WIDE inches
const H = 7.5;

function addCover(slide, f, brand) {
  const P = brand.palette;
  slide.background = { color: hex(P.navy_deep, "navy_deep") };

  const bg = (f.background)
    ? (path.isAbsolute(f.background) ? f.background
       : path.join(brand.assets_dir || "", f.background))
    : assetPath(brand, "cover_bg.jpg");
  if (bg && fs.existsSync(bg)) {
    slide.addImage({ path: bg, x: 0, y: 0, w: W, h: H });
  }

  // Accent parallelogram bar
  slide.addShape("parallelogram", {
    x: -1.0, y: 1.2, w: 7.0, h: 0.12,
    fill: { color: hex(P.blue, "blue") },
    line: { type: "none" },
  });

  slide.addText(f.title || "", koText(brand, {
    x: 1.2, y: 2.4, w: 11.0, h: 2.4,
    fontSize: sz(brand, "cover_title", 48),
    bold: true, color: hex(P.white, "white"),
    align: "center", valign: "middle", margin: 0,
  }));

  if (f.date) {
    slide.addText(f.date, koText(brand, {
      x: 1.2, y: 5.8, w: 11.0, h: 0.4,
      fontSize: sz(brand, "cover_date", 14),
      color: hex(P.white, "white"), align: "center", margin: 0,
    }));
  }

  if (f.company) {
    slide.addText(f.company, koText(brand, {
      x: 1.2, y: 6.3, w: 11.0, h: 0.4,
      fontSize: sz(brand, "cover_company", 14),
      bold: true, color: hex(P.blue_light, "blue_light"), align: "center", margin: 0,
    }));
  }

  const mascot = assetPath(brand, "mascot.png");
  if (mascot) slide.addImage({ path: mascot, x: 0.5, y: 4.5, w: 2.6, h: 2.6 });
}

function addTOC(slide, f, brand) {
  const P = brand.palette;
  slide.background = { color: hex(P.bg_light, "bg_light") };

  slide.addText("Index", koText(brand, {
    x: 1.5, y: 1.2, w: 3.5, h: 1.2,
    fontSize: sz(brand, "toc_label", 48),
    bold: true, color: hex(P.blue, "blue"),
    align: "center", valign: "middle", margin: 0,
  }));

  const items = f.items || [];
  const N = items.length;
  const GAP = 0.15;
  const ROW_H = N <= 4 ? 0.95 : Math.max(0.7, (4.5 - GAP * (N - 1)) / N);
  const START_Y = 1.4;
  for (let i = 0; i < N; i++) {
    const y = START_Y + (ROW_H + GAP) * i;
    slide.addShape("roundRect", {
      x: 5.8, y, w: 0.9, h: ROW_H,
      fill: { color: hex(P.blue, "blue") }, line: { type: "none" },
      rectRadius: 0.15,
    });
    slide.addText(String(i + 1).padStart(2, "0"), koText(brand, {
      x: 5.8, y, w: 0.9, h: ROW_H,
      fontSize: sz(brand, "toc_num", 18),
      bold: true, color: hex(P.white, "white"),
      align: "center", valign: "middle", margin: 0,
    }));
    slide.addText(items[i], koText(brand, {
      x: 7.2, y, w: 5.5, h: ROW_H,
      fontSize: sz(brand, "toc_item", 22),
      bold: true, color: hex(P.navy_deep, "navy_deep"),
      align: "left", valign: "middle", margin: 0,
    }));
  }

  addCompanyTopRight(slide, brand, /*on_dark=*/false);
}

function addSectionDivider(slide, f, brand) {
  const P = brand.palette;
  slide.background = { color: hex(P.navy_deep, "navy_deep") };

  const bg = assetPath(brand, "section_bg.jpg");
  if (bg) slide.addImage({ path: bg, x: 0, y: 0, w: W, h: H });

  if (f.number) {
    slide.addText(String(f.number), koText(brand, {
      x: 0, y: 2.3, w: W, h: 1.5,
      fontSize: sz(brand, "section_num", 54),
      bold: true, color: hex(P.blue_light, "blue_light"),
      align: "center", valign: "middle", margin: 0,
    }));
  }

  slide.addShape("rect", {
    x: (W - 0.6) / 2, y: 3.5, w: 0.6, h: 0.04,
    fill: { color: hex(P.blue, "blue") }, line: { type: "none" },
  });

  slide.addText(f.title || "", koText(brand, {
    x: 0, y: 3.6, w: W, h: 1.5,
    fontSize: sz(brand, "section_title", 44),
    bold: true, color: hex(P.white, "white"),
    align: "center", valign: "middle", margin: 0,
  }));
}

function addHero(slide, f, brand) {
  const P = brand.palette;
  slide.background = { color: hex(P.blue_bright, "blue_bright") };

  if (f.eyebrow) {
    slide.addText(f.eyebrow, koText(brand, {
      x: 1.0, y: 1.8, w: 11.3, h: 0.5,
      fontSize: sz(brand, "hero_eyebrow", 16),
      color: hex(P.blue_light, "blue_light"), align: "center", margin: 0,
    }));
  }

  slide.addText(f.headline || "", koText(brand, {
    x: 1.0, y: 2.4, w: 11.3, h: 1.9,
    fontSize: sz(brand, "hero_headline", 72),
    bold: true, color: hex(P.white, "white"),
    align: "center", valign: "middle", margin: 0,
  }));

  if (f.subheadline) {
    const sub = f.subheadline;
    const hl = f.highlight;
    let runs;
    if (hl && sub.includes(hl)) {
      const [before, after] = sub.split(hl);
      runs = [
        { text: before, options: { color: hex(P.white, "white") } },
        { text: hl,     options: { color: hex(P.navy_deep, "navy_deep"), highlight: hex(P.white, "white") } },
        { text: after,  options: { color: hex(P.white, "white") } },
      ].filter(r => r.text && r.text.length > 0);
    } else {
      runs = [{ text: sub, options: { color: hex(P.white, "white") } }];
    }
    runs.forEach(r => { r.options = koText(brand, {
      fontSize: sz(brand, "hero_sub", 24), bold: true, ...r.options,
    }); });
    slide.addText(runs, {
      x: 1.0, y: 4.9, w: 11.3, h: 1.2,
      align: "center", valign: "top", margin: 0,
    });
  }
}

function addContent(slide, f, brand) {
  const P = brand.palette, M = brand.slide.margin;
  slide.background = { color: hex(P.bg_light, "bg_light") };

  if (f.breadcrumb) {
    slide.addText(f.breadcrumb, koText(brand, {
      x: M.left, y: 0.3, w: 8.0, h: 0.3,
      fontSize: sz(brand, "breadcrumb", 10),
      color: hex(P.text_muted, "text_muted"), align: "left", margin: 0,
    }));
  }

  slide.addText(f.title || "", koText(brand, {
    x: M.left, y: 0.9, w: W - M.left - M.right, h: 1.4,
    fontSize: sz(brand, "content_title", 26),
    bold: true, color: hex(P.navy_deep, "navy_deep"),
    align: "left", valign: "top", margin: 0,
  }));

  // Dark container
  const contX = M.left, contY = 2.6;
  const contW = W - M.left - M.right, contH = 4.2;
  slide.addShape("rect", {
    x: contX, y: contY, w: contW, h: contH,
    fill: { color: hex(P.navy_deep, "navy_deep") }, line: { type: "none" },
  });
  slide.addShape("rect", {
    x: contX, y: contY + contH - 0.05, w: contW, h: 0.05,
    fill: { color: hex(P.blue, "blue") }, line: { type: "none" },
  });

  const body = (f.body || []).slice(0, 4);
  const n = Math.max(1, body.length);
  const colW = contW / n;
  const CIRCLE_D = 2.0, TOP_PAD = 0.6;

  for (let i = 0; i < n; i++) {
    const blk = body[i] || {};
    const cx = contX + colW * i + (colW - CIRCLE_D) / 2;
    const cy = contY + TOP_PAD;

    const outerColor = (i % 2 === 1) ? P.blue : P.navy;
    const innerColor = (i % 2 === 1) ? P.white : P.navy_soft;
    const headingColor = (i % 2 === 1) ? P.navy_deep : P.blue_light;

    slide.addShape("ellipse", {
      x: cx, y: cy, w: CIRCLE_D, h: CIRCLE_D,
      fill: { color: hex(outerColor) }, line: { type: "none" },
    });
    slide.addShape("ellipse", {
      x: cx + 0.15, y: cy + 0.15, w: CIRCLE_D - 0.3, h: CIRCLE_D - 0.3,
      fill: { color: hex(innerColor) }, line: { type: "none" },
    });

    slide.addText(`[${blk.heading || ""}]`, koText(brand, {
      x: cx, y: cy + CIRCLE_D * 0.32, w: CIRCLE_D, h: 0.45,
      fontSize: sz(brand, "flow_heading", 16),
      bold: true, color: hex(headingColor),
      align: "center", valign: "middle", margin: 0,
    }));

    slide.addText(blk.text || "", koText(brand, {
      x: contX + colW * i + 0.1, y: cy + CIRCLE_D + 0.1,
      w: colW - 0.2, h: 1.3,
      fontSize: sz(brand, "flow_body", 12),
      bold: true, color: hex(P.white, "white"),
      align: "center", valign: "top", margin: 0,
    }));

    if (i < n - 1) {
      const ax1 = cx + CIRCLE_D + 0.05;
      const ax2 = contX + colW * (i + 1) + (colW - CIRCLE_D) / 2 - 0.05;
      slide.addShape("line", {
        x: ax1, y: cy + CIRCLE_D / 2, w: ax2 - ax1, h: 0,
        line: { color: hex(P.blue_light, "blue_light"), width: 2 },
      });
    }
  }

  addCompanyTopRight(slide, brand, /*on_dark=*/false);
}

function addContentImage(slide, f, brand) {
  const P = brand.palette, M = brand.slide.margin;
  slide.background = { color: hex(P.bg_light, "bg_light") };

  if (f.breadcrumb) {
    slide.addText(f.breadcrumb, koText(brand, {
      x: M.left, y: 0.3, w: 8.0, h: 0.3,
      fontSize: sz(brand, "breadcrumb", 10),
      color: hex(P.text_muted, "text_muted"), align: "left", margin: 0,
    }));
  }

  slide.addText(f.title || "", koText(brand, {
    x: M.left, y: 0.9, w: W - M.left - M.right, h: 1.4,
    fontSize: sz(brand, "content_title", 26),
    bold: true, color: hex(P.navy_deep, "navy_deep"),
    align: "left", valign: "top", margin: 0,
  }));

  const pos = (f.image_position || "right").toLowerCase();
  const colW = (W - M.left - M.right - 0.5) / 2;
  const top = 2.7, h = 3.8;
  const imgX = pos === "right" ? W - M.right - colW : M.left;
  const txtX = pos === "right" ? M.left : M.left + colW + 0.5;

  let img = null;
  if (f.image) {
    const p = path.isAbsolute(f.image) ? f.image
      : path.join(brand.assets_dir || "", f.image);
    if (fs.existsSync(p)) img = p;
  }
  if (img) {
    slide.addImage({ path: img, x: imgX, y: top, w: colW, h, sizing: { type: "contain", w: colW, h } });
  } else {
    slide.addShape("roundRect", {
      x: imgX, y: top, w: colW, h,
      fill: { color: hex(P.blue_light, "blue_light") }, line: { type: "none" },
      rectRadius: 0.15,
    });
    slide.addText("(image)", koText(brand, {
      x: imgX, y: top, w: colW, h,
      fontSize: 14, color: hex(P.navy, "navy"),
      align: "center", valign: "middle", margin: 0,
    }));
  }

  // Body text — preserve newlines as separate runs
  const lines = String(f.text || "").split(/\r?\n/);
  const runs = lines.map((ln, i) => ({
    text: ln,
    options: koText(brand, {
      fontSize: sz(brand, "img_body", 14),
      color: hex(P.text_dark, "text_dark"),
      breakLine: i < lines.length - 1,
    }),
  }));
  slide.addText(runs, {
    x: txtX, y: top, w: colW, h,
    align: "left", valign: "top", margin: 0,
  });

  addCompanyTopRight(slide, brand, /*on_dark=*/false);
}

function addClosing(slide, f, brand) {
  const P = brand.palette;
  slide.background = { color: hex(P.navy_deep, "navy_deep") };

  slide.addText(f.message || "감사합니다", koText(brand, {
    x: 0, y: 2.8, w: W, h: 1.5,
    fontSize: sz(brand, "closing", 56),
    bold: true, color: hex(P.white, "white"),
    align: "center", valign: "middle", margin: 0,
  }));

  if (f.tagline) {
    slide.addText(f.tagline, koText(brand, {
      x: 0, y: 4.4, w: W, h: 0.8,
      fontSize: sz(brand, "closing_tagline", 16),
      color: hex(P.blue_light, "blue_light"), align: "center", margin: 0,
    }));
  }

  const mascot = assetPath(brand, "mascot.png");
  if (mascot) slide.addImage({ path: mascot, x: 0.5, y: 3.0, w: 2.8, h: 2.8 });
}

function addCompanyTopRight(slide, brand, on_dark) {
  const P = brand.palette;
  const name = brand.company_name || "OOTB LAB";
  slide.addText(name, koText(brand, {
    x: W - 2.7, y: 0.3, w: 2.2, h: 0.4,
    fontSize: 11,
    bold: true,
    color: on_dark ? hex(P.white, "white") : hex(P.navy_deep, "navy_deep"),
    align: "right", margin: 0,
  }));
}

const DISPATCH = {
  cover:            addCover,
  toc:              addTOC,
  section_divider:  addSectionDivider,
  hero:             addHero,
  content:          addContent,
  content_image:    addContentImage,
  closing:          addClosing,
};

// ---------- Main ----------
function main() {
  const { planPath, outPath } = parseArgs();
  if (!fs.existsSync(planPath)) {
    console.error(`ERROR: ${planPath} not found`);
    process.exit(2);
  }
  const plan = JSON.parse(fs.readFileSync(planPath, "utf-8"));
  const brand = plan.brand;
  const pres = new pptxgen();
  pres.defineLayout({ name: "OOTB_WIDE", width: W, height: H });
  pres.layout = "OOTB_WIDE";
  pres.title = (plan.project && plan.project.title) || "OOTB Proposal";
  pres.author = brand.company_name || "OOTB Lab";

  for (const s of plan.slides) {
    const fn = DISPATCH[s.blueprint];
    if (!fn) {
      console.error(`WARN: unknown blueprint ${s.blueprint}, skipping`);
      continue;
    }
    const slide = pres.addSlide();
    fn(slide, s.fields || {}, brand);
  }

  const out = outPath || path.join(
    path.dirname(planPath),
    `${path.basename(planPath, ".json")}.pptx`
  );
  pres.writeFile({ fileName: out }).then(fn => {
    console.log(`OK  wrote ${fn}`);
  }).catch(err => {
    console.error("ERROR writing pptx:", err);
    process.exit(1);
  });
}

main();
