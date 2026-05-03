// Conference poster — 36 x 24 inch landscape, single-slide PPTX,
// converted to PDF via libreoffice in the bash wrapper.
const PptxGenJS = require("pptxgenjs");
const path = require("path");
const fs = require("fs");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "data/outputs");

const C = {
  paper: "FAF8F5", ink: "0E1116", inkSoft: "3A4048",
  rule: "C8CCD2", accent: "A4221A", ocean: "EEF2F4",
};
const F = { header: "Georgia", body: "Calibri", mono: "Consolas" };

const ci = JSON.parse(fs.readFileSync(path.join(OUT, "bootstrap_ci.json")));
const alt = JSON.parse(fs.readFileSync(path.join(OUT, "alternative_metrics.json")));
const kop = JSON.parse(fs.readFileSync(path.join(OUT, "koppen_stratification.json")));
const F_ = ci.F_climate_only;
const B_ = ci.B_full_features;

// Custom 36 x 24 inch landscape layout
const pptx = new PptxGenJS();
pptx.defineLayout({ name: "POSTER_36x24", width: 36, height: 24 });
pptx.layout = "POSTER_36x24";

const W = 36, H = 24;
const slide = pptx.addSlide();
slide.background = { color: C.paper };

// ── Header strip ────────────────────────────────────────────────────
const HEAD_H = 2.4;
slide.addShape(pptx.ShapeType.line, {
  x: 1.0, y: HEAD_H + 0.1, w: W - 2.0, h: 0,
  line: { color: C.accent, width: 2.0 },
});
slide.addText("MSHI-GEO", {
  x: 1.0, y: 0.55, w: 12.0, h: 0.6,
  fontFace: F.mono, fontSize: 24, color: C.accent, bold: true,
  charSpacing: 4,
});
slide.addText("Soil Microbial Respiration: A Three-Tier Monitoring Stack", {
  x: 1.0, y: 1.15, w: 24.0, h: 1.05,
  fontFace: F.header, fontSize: 44, color: C.ink, bold: true,
});
slide.addText("[Author Name]   ·   [School / Institution]   ·   Genius Olympiad 2026", {
  x: 1.0, y: 2.05, w: 24.0, h: 0.4,
  fontFace: F.mono, fontSize: 18, color: C.inkSoft,
});
slide.addText("github.com/Sparkxt-0318/MSHI", {
  x: W - 1.0 - 12.0, y: 1.55, w: 12.0, h: 0.5,
  fontFace: F.mono, fontSize: 18, color: C.inkSoft, align: "right",
});
slide.addText("Published EAB sensor work\nMSHI-Geo paper queued for ESSD", {
  x: W - 1.0 - 12.0, y: 0.55, w: 12.0, h: 0.95,
  fontFace: F.body, fontSize: 14, color: C.ink, align: "right", italic: true,
});

// ── Three-column row 1: Abstract / Methods / Three-tier framework ────
const ROW1_Y = HEAD_H + 0.45;
const ROW1_H = 5.5;
const COL_W = 11.0;
const COL_GAP = 0.5;

function colHeader(s, x, y, num, title) {
  s.addText(num, {
    x, y, w: COL_W, h: 0.42,
    fontFace: F.mono, fontSize: 14, color: C.accent, bold: true, charSpacing: 1,
  });
  s.addText(title, {
    x, y: y + 0.45, w: COL_W, h: 0.7,
    fontFace: F.header, fontSize: 22, color: C.ink, bold: true,
  });
  s.addShape(pptx.ShapeType.line, {
    x, y: y + 1.18, w: COL_W, h: 0,
    line: { color: C.rule, width: 0.8 },
  });
}

// Column 1 — Problem / abstract
{
  const x = 1.0;
  colHeader(slide, x, ROW1_Y, "01  ·  PROBLEM", "Soil respiration has no high-resolution validator.");
  slide.addText(
    "Soils release ~91 Pg C yr⁻¹ to the atmosphere, second only to ocean " +
    "exchange. Continental Rs upscaling models (Hashimoto 2015; Warner 2019; " +
    "Stell 2021) report uncertainty as Monte-Carlo confidence intervals on " +
    "the global sum, not as held-out site-level transfer.\n\n" +
    "We characterise the cross-continental transfer gap directly: train an " +
    "XGBoost model on Asian soil-respiration sites, test on a held-out US " +
    "subset, report transfer R² with 2 000-iteration bootstrap CIs and " +
    "ranked SHAP drivers per region. The result clarifies what the standard " +
    "feature stack can and cannot do at this scale, and where ground-truth " +
    "biosensor measurement is needed.",
    { x, y: ROW1_Y + 1.4, w: COL_W, h: ROW1_H - 1.4,
      fontFace: F.body, fontSize: 14, color: C.ink, valign: "top" });
}

// Column 2 — Methods
{
  const x = 1.0 + COL_W + COL_GAP;
  colHeader(slide, x, ROW1_Y, "02  ·  METHODS", "Open data, gradient-boosted trees, held-out continent.");

  const lines = [
    { head: "Training data", body:
        "615 Asia (605 SRDB v5 + 10 COSORE) — Jian 2021, Bond-Lamberty 2010, 2020.\n" +
        "274 CONUS (253 SRDB + 21 COSORE) reserved as held-out validation.\n" +
        "Target log(Rs_annual), g C m⁻² yr⁻¹." },
    { head: "Features (20)", body:
        "8 WorldClim 2.1 bioclim (T, P, seasonality) — Fick & Hijmans 2017.\n" +
        "8 SoilGrids 2.0 5-15 cm topsoil — Poggio 2021.\n" +
        "4 engineered (C/N, clay/sand, pH-optimality, aridity)." },
    { head: "Model & validation", body:
        "XGBoost depth=3, n_est=250, regularised. 5-fold spatial-block CV " +
        "(5° blocks). Asia → US transfer R² + 2 000-iteration bootstrap CI." },
  ];
  let y = ROW1_Y + 1.4;
  lines.forEach(l => {
    slide.addText(l.head, { x, y, w: COL_W, h: 0.4,
      fontFace: F.header, fontSize: 15, color: C.accent, bold: true });
    slide.addText(l.body, { x, y: y + 0.4, w: COL_W, h: 1.2,
      fontFace: F.body, fontSize: 12, color: C.ink, valign: "top" });
    y += 1.55;
  });
}

// Column 3 — Three-tier framework
{
  const x = 1.0 + 2 * (COL_W + COL_GAP);
  colHeader(slide, x, ROW1_Y, "03  ·  FRAMEWORK", "One biology, three scales of measurement.");

  const tiers = [
    { y: ROW1_Y + 1.5, scale: "cm", color: C.accent,
      name: "Electrochemical biosensor",
      desc: "Electron-transfer current ∝ substrate oxidation. Centimetre footprint, continuous, low cost." },
    { y: ROW1_Y + 2.85, scale: "m", color: C.inkSoft,
      name: "Chamber + eddy-covariance",
      desc: "Direct CO₂ flux measurement. Metre footprint, sparse, high instrument cost." },
    { y: ROW1_Y + 4.2, scale: "km", color: C.inkSoft,
      name: "Satellite + ML upscaling (this work)",
      desc: "5 km grid. Climate + soil features. Transfer-tested." },
  ];
  tiers.forEach(t => {
    slide.addText(t.scale, {
      x, y: t.y, w: 1.6, h: 1.0,
      fontFace: F.header, fontSize: 36, color: t.color, bold: true,
    });
    slide.addText(t.name, {
      x: x + 1.7, y: t.y, w: COL_W - 1.7, h: 0.45,
      fontFace: F.header, fontSize: 16, color: C.ink, bold: true,
    });
    slide.addText(t.desc, {
      x: x + 1.7, y: t.y + 0.45, w: COL_W - 1.7, h: 0.85,
      fontFace: F.body, fontSize: 11, color: C.inkSoft, valign: "top",
    });
  });
}

// ── Row 2: Hero map (left) + SHAP comparison (right) ──────────────────
const ROW2_Y = ROW1_Y + ROW1_H + 0.4;
const ROW2_H = 6.5;

// LEFT: Hero map
{
  const x = 1.0;
  const heroW = 16.0;
  slide.addText("04  ·  HERO MAP — climate-only model on Asia", {
    x, y: ROW2_Y, w: heroW, h: 0.4,
    fontFace: F.mono, fontSize: 12, color: C.accent, bold: true, charSpacing: 1,
  });
  const hero = path.join(OUT, "hero_climate_only_asia.png");
  if (fs.existsSync(hero)) {
    slide.addImage({ path: hero, x, y: ROW2_Y + 0.5, w: heroW, h: ROW2_H - 0.5 });
  }
}

// RIGHT: SHAP comparison
{
  const x = 1.0 + 16.0 + 0.5;
  const w = W - x - 1.0;
  slide.addText("05  ·  DRIVERS DIFFER BY REGION", {
    x, y: ROW2_Y, w, h: 0.4,
    fontFace: F.mono, fontSize: 12, color: C.accent, bold: true, charSpacing: 1,
  });
  const fig = path.join(OUT, "shap_comparison.png");
  if (fs.existsSync(fig)) {
    slide.addImage({ path: fig, x, y: ROW2_Y + 0.5, w, h: ROW2_H - 1.5 });
  }
  slide.addText(
    "Same XGBoost trained separately on Asia and US. Annual precipitation (bio12) is " +
    "the only feature with stable rank in both regions. Clay/sand-ratio (Asia rank 5) " +
    "drops out of the US top 8; nitrogen jumps to US rank 2. The clay correlation flips " +
    "sign cross-region (r_Asia = +0.302 vs r_US = −0.048). This is the mechanism " +
    "behind the transfer collapse.",
    { x, y: ROW2_Y + ROW2_H - 0.95, w, h: 0.95,
      fontFace: F.body, fontSize: 11, color: C.ink, valign: "top" });
}

// ── Row 3: Methodology evolution panel (full width) ────────────────────
const ROW3_Y = ROW2_Y + ROW2_H + 0.4;
const ROW3_H = 5.0;
{
  const x = 1.0; const w = W - 2.0;
  slide.addText("06  ·  METHODOLOGY EVOLUTION  —  what each model adds, where each one fails", {
    x, y: ROW3_Y, w, h: 0.4,
    fontFace: F.mono, fontSize: 12, color: C.accent, bold: true, charSpacing: 1,
  });
  const fig = path.join(OUT, "methodology_evolution_panel.png");
  if (fs.existsSync(fig)) {
    slide.addImage({ path: fig, x, y: ROW3_Y + 0.5, w, h: ROW3_H - 0.5 });
  }
}

// ── Row 4: three columns — Köppen / Sensor / Implications ──────────────
const ROW4_Y = ROW3_Y + ROW3_H + 0.4;
const ROW4_H = H - ROW4_Y - 1.2;

// Col 1 — Köppen finding
{
  const x = 1.0;
  colHeader(slide, x, ROW4_Y, "07  ·  KÖPPEN TEST", "Stratification doesn't help.");
  slide.addText(
    `Köppen C (temperate, n_us=89)   R² = ${kop.results.C.transfer_r2.toFixed(3)}   CI (${kop.results.C.ci_low.toFixed(2)}, ${kop.results.C.ci_high.toFixed(2)})\n` +
    `Köppen D (continental, n_us=159) R² = ${kop.results.D.transfer_r2.toFixed(3)}   CI (${kop.results.D.ci_low.toFixed(2)}, ${kop.results.D.ci_high.toFixed(2)})\n` +
    `Cross-zone reference              R² = ${F_.median.toFixed(3)}   CI (${F_.ci_low.toFixed(2)}, ${F_.ci_high.toFixed(2)})\n\n` +
    "Within-zone transfer is worse than the cross-zone baseline in both " +
    "qualifying zones. The cross-zone +0.127 R² IS the cross-zone " +
    "precipitation gradient; stratifying it away leaves no transferable " +
    "signal. Climate-zone stratification cannot rescue cross-continental Rs.",
    { x, y: ROW4_Y + 1.4, w: COL_W, h: ROW4_H - 1.4,
      fontFace: F.mono, fontSize: 11, color: C.ink, valign: "top", linespacing: 16 });
}

// Col 2 — Sensor connection figure embedded
{
  const x = 1.0 + COL_W + COL_GAP;
  colHeader(slide, x, ROW4_Y, "08  ·  SENSOR CONNECTION", "What the satellite cannot resolve.");
  const fig = path.join(OUT, "sensor_connection_figure.png");
  if (fs.existsSync(fig)) {
    slide.addImage({ path: fig, x, y: ROW4_Y + 1.3, w: COL_W, h: ROW4_H - 1.3 });
  }
}

// Col 3 — Implications + future + references
{
  const x = 1.0 + 2 * (COL_W + COL_GAP);
  colHeader(slide, x, ROW4_Y, "09  ·  IMPLICATIONS & ROADMAP", "Three deliverables, three months.");
  slide.addText(
    "•  Climate features transfer Asia → US (R² = +0.127, CI excl. 0).\n" +
    "•  Adding SoilGrids texture features collapses transfer to zero.\n" +
    "•  Climate-zone stratification does not rescue.\n\n" +
    "Roadmap:\n" +
    "  1.  MODIS NPP integration (≤ 2 weeks; GEE export queued)\n" +
    "  2.  ESSD manuscript submission (≤ 6 weeks)\n" +
    "  3.  Co-located biosensor pilot at SRDB site (≤ 12 weeks)\n\n" +
    "References:  Bond-Lamberty 2010, 2020 · Fick & Hijmans 2017 · " +
    "Hashimoto 2015 (10.5194/bg-12-4121-2015) · Jian 2021 (10.5194/essd-13-255-2021) · " +
    "Poggio 2021 · Stell 2021 (10.1111/gcb.15666) · Warner 2019 (10.1029/2019GB006264) · " +
    "Yao 2021 (10.1029/2020GB006918).",
    { x, y: ROW4_Y + 1.4, w: COL_W, h: ROW4_H - 1.4,
      fontFace: F.body, fontSize: 11, color: C.ink, valign: "top", linespacing: 14 });
}

// ── Footer ────────────────────────────────────────────────────────────
slide.addShape(pptx.ShapeType.line, {
  x: 1.0, y: H - 0.7, w: W - 2.0, h: 0,
  line: { color: C.rule, width: 0.6 },
});
slide.addText(
  "Code, data, paper draft, and this poster: github.com/Sparkxt-0318/MSHI " +
  "(branch claude/round-c-deliverables) · Genius Olympiad 2026.",
  { x: 1.0, y: H - 0.6, w: W - 2.0, h: 0.4,
    fontFace: F.mono, fontSize: 11, color: C.inkSoft, align: "center" });

const outPath = path.join(OUT, "genius_poster.pptx");
pptx.writeFile({ fileName: outPath }).then(filename => {
  console.log("Wrote " + filename);
});
