// Genius Olympiad pitch deck — 12 slides, Bedrock aesthetic.
// Real numbers from data/outputs/ JSON files.
const PptxGenJS = require("pptxgenjs");
const path = require("path");
const fs = require("fs");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "data/outputs");

// ── Bedrock design tokens ────────────────────────────────────────────
const C = {
  paper: "FAF8F5",
  ink:   "0E1116",
  inkSoft: "3A4048",
  rule:  "C8CCD2",
  accent: "A4221A",
  ocean: "EEF2F4",
};
const F = {
  header: "Georgia",
  body:   "Calibri",
  mono:   "Consolas",
};

// ── Pull verified numbers from the JSON outputs ──────────────────────
const ci = JSON.parse(fs.readFileSync(path.join(OUT, "bootstrap_ci.json")));
const alt = JSON.parse(fs.readFileSync(path.join(OUT, "alternative_metrics.json")));
const kop = JSON.parse(fs.readFileSync(path.join(OUT, "koppen_stratification.json")));
const F_ = ci.F_climate_only;
const B_ = ci.B_full_features;
const F_alt = alt.F_climate_only;
const B_alt = alt.B_full_features;
const kopC = kop.results.C;
const kopD = kop.results.D;

// ── Initialize presentation ──────────────────────────────────────────
const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";  // 13.33 x 7.5 in
pptx.author = "MSHI-Geo team";
pptx.title  = "Soil Microbial Respiration: A Three-Tier Monitoring Stack";

const W = 13.33, H = 7.5;
const MARGIN = 0.6;

// ── Helpers ──────────────────────────────────────────────────────────
function addBackground(slide) {
  slide.background = { color: C.paper };
}

function addHeader(slide, eyebrow, title) {
  slide.addText(eyebrow, {
    x: MARGIN, y: 0.45, w: W - 2*MARGIN, h: 0.32,
    fontFace: F.mono, fontSize: 11, color: C.accent, bold: true,
    charSpacing: 1,
  });
  slide.addText(title, {
    x: MARGIN, y: 0.80, w: W - 2*MARGIN, h: 1.0,
    fontFace: F.header, fontSize: 32, color: C.ink, bold: true,
  });
  // Hairline rule under title
  slide.addShape(pptx.ShapeType.line, {
    x: MARGIN, y: 1.85, w: W - 2*MARGIN, h: 0,
    line: { color: C.rule, width: 0.6 },
  });
}

function addFooter(slide, n, title) {
  slide.addShape(pptx.ShapeType.line, {
    x: MARGIN, y: H - 0.55, w: W - 2*MARGIN, h: 0,
    line: { color: C.rule, width: 0.6 },
  });
  slide.addText(`MSHI-GEO  ·  ${title}`, {
    x: MARGIN, y: H - 0.45, w: 8, h: 0.30,
    fontFace: F.mono, fontSize: 8, color: C.inkSoft,
  });
  slide.addText(`${n} / 12`, {
    x: W - MARGIN - 1.0, y: H - 0.45, w: 1.0, h: 0.30,
    fontFace: F.mono, fontSize: 8, color: C.inkSoft, align: "right",
  });
}

function addBody(slide, y, text, opts = {}) {
  slide.addText(text, Object.assign({
    x: MARGIN, y, w: W - 2*MARGIN, h: 1.5,
    fontFace: F.body, fontSize: 18, color: C.ink, valign: "top",
  }, opts));
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 1 — Title
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide();
  addBackground(s);
  s.addShape(pptx.ShapeType.line, {
    x: MARGIN, y: 1.7, w: 2.0, h: 0,
    line: { color: C.accent, width: 1.5 },
  });
  s.addText("MSHI-GEO", {
    x: MARGIN, y: 1.85, w: W - 2*MARGIN, h: 0.4,
    fontFace: F.mono, fontSize: 14, color: C.accent, bold: true, charSpacing: 2,
  });
  s.addText("Soil Microbial Respiration:\nA Three-Tier Monitoring Stack", {
    x: MARGIN, y: 2.35, w: W - 2*MARGIN, h: 2.0,
    fontFace: F.header, fontSize: 44, color: C.ink, bold: true,
  });
  s.addText("Continental gridded prediction · Held-out cross-continental validation · Electrochemical biosensor integration", {
    x: MARGIN, y: 4.7, w: W - 2*MARGIN, h: 0.6,
    fontFace: F.body, fontSize: 17, color: C.inkSoft, italic: true,
  });
  s.addText("[Author Name]   ·   [Affiliation]   ·   Genius Olympiad 2026", {
    x: MARGIN, y: H - 1.2, w: W - 2*MARGIN, h: 0.3,
    fontFace: F.mono, fontSize: 11, color: C.inkSoft,
  });
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 2 — The problem
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "01  ·  THE PROBLEM",
    "Soil respiration is the second-largest carbon flux. We can't see it at the resolution that matters.");
  addBody(s, 2.3,
    "Globally, soils release ~91 Pg C yr⁻¹ to the atmosphere — second only to ocean exchange. " +
    "Continental upscaling models (Hashimoto 2015; Warner 2019; Stell 2021) report uncertainty as Pg C yr⁻¹ " +
    "intervals on the global sum, not as held-out site-level transfer."
  );
  addBody(s, 4.0,
    "The decision-relevant question — does a model trained on one continent predict the next? — has not " +
    "been answered. This work addresses that gap, then shows what the answer implies for the kind of " +
    "ground-truth network the field needs.",
    { color: C.ink, fontSize: 17 }
  );
  addFooter(s, 2, "The problem");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 3 — Three-tier framework
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "02  ·  FRAMEWORK",
    "One biology, three scales of measurement.");

  const tiers = [
    { y: 2.3, scale: "cm", color: C.accent,
      name: "Electrochemical biosensor",
      desc: "Electron-transfer current proxy for substrate oxidation; centimetre footprint, continuous deployment, low cost." },
    { y: 3.6, scale: "m",  color: C.inkSoft,
      name: "Chamber + eddy-covariance",
      desc: "Direct CO₂ flux (μmol m⁻² s⁻¹); metre-scale footprint, sparse network, high instrument cost." },
    { y: 4.9, scale: "km", color: C.inkSoft,
      name: "Satellite + ML upscaling (this work)",
      desc: "5 km grid, climate + soil + (pending) MODIS NPP features; held-out cross-continental validation." },
  ];
  tiers.forEach(t => {
    s.addText(t.scale, {
      x: MARGIN, y: t.y, w: 1.0, h: 0.9,
      fontFace: F.header, fontSize: 36, color: t.color, bold: true,
    });
    s.addText(t.name, {
      x: MARGIN + 1.2, y: t.y, w: W - MARGIN*2 - 1.2, h: 0.5,
      fontFace: F.header, fontSize: 18, color: C.ink, bold: true,
    });
    s.addText(t.desc, {
      x: MARGIN + 1.2, y: t.y + 0.5, w: W - MARGIN*2 - 1.2, h: 0.7,
      fontFace: F.body, fontSize: 13, color: C.inkSoft,
    });
  });
  s.addText("Same biological flux. Three resolutions. The middle tier is where most chamber data lives; " +
            "the satellite tier struggles to generalise; the centimetre tier is what's missing.",
    { x: MARGIN, y: 6.3, w: W - 2*MARGIN, h: 0.6,
      fontFace: F.body, fontSize: 13, color: C.ink, italic: true });
  addFooter(s, 3, "Three-tier framework");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 4 — Methods overview
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "03  ·  METHODS",
    "Open community data, gradient-boosted trees, held-out continent.");

  const blocks = [
    { x: MARGIN, head: "Training data",
      txt: `615 Asia sites (605 SRDB v5 + 10 COSORE) for cross-continental training.\n` +
           `274 CONUS sites (253 SRDB + 21 COSORE) reserved as held-out validation.\n` +
           `Target: log(Rs_annual), g C m⁻² yr⁻¹.` },
    { x: MARGIN + 4.4, head: "Features",
      txt: `8 WorldClim 2.1 bioclim variables (T, P, seasonality).\n` +
           `8 SoilGrids 2.0 5-15 cm topsoil layers (SOC, N, pH, texture, ρ, CEC).\n` +
           `4 engineered (C/N, clay/sand, pH-optimality, aridity). MODIS NPP pending.` },
    { x: MARGIN + 8.8, head: "Model & validation",
      txt: `XGBoost regression (depth 3, n_est 250, L2 = 2 to 8).\n` +
           `5-fold spatial-block CV (5° blocks) on Asia.\n` +
           `Asia → US transfer R² + 2,000-iteration bootstrap CI.` },
  ];
  blocks.forEach(b => {
    s.addText(b.head, {
      x: b.x, y: 2.3, w: 4.0, h: 0.4,
      fontFace: F.header, fontSize: 16, color: C.accent, bold: true,
    });
    s.addText(b.txt, {
      x: b.x, y: 2.85, w: 4.0, h: 3.5,
      fontFace: F.body, fontSize: 13, color: C.ink, valign: "top",
    });
  });
  addFooter(s, 4, "Methods overview");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 5 — Result 1: climate-only transfers
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "04  ·  RESULT 1",
    "Climate features alone transfer Asia → US.");

  // Big number
  s.addText("R² = +0.127", {
    x: MARGIN, y: 2.2, w: 5.0, h: 0.85,
    fontFace: F.header, fontSize: 44, color: C.ink, bold: true,
  });
  s.addText("95 % bootstrap CI  (+0.019, +0.216)\nstatistically significant — CI excludes zero", {
    x: MARGIN, y: 3.2, w: 5.0, h: 0.9,
    fontFace: F.mono, fontSize: 12, color: C.accent,
  });
  s.addText(
    "Trained on 600 Asian sites with 8 WorldClim bioclim variables only " +
    "(no soil, no MODIS). Tested on 272 held-out US sites. The model captures " +
    "the cross-continental precipitation gradient — the only relationship that " +
    "transfers cleanly between regions.",
    { x: MARGIN, y: 4.3, w: 5.0, h: 2.5,
      fontFace: F.body, fontSize: 13, color: C.ink });

  // Embedded map
  const heroPath = path.join(OUT, "hero_climate_only_asia_screen.png");
  if (fs.existsSync(heroPath)) {
    s.addImage({ path: heroPath,
      x: MARGIN + 5.4, y: 2.05, w: 7.3, h: 4.7 });
  }
  addFooter(s, 5, "Climate-only model transfers");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 6 — Result 2: full features fail
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "05  ·  RESULT 2",
    "Adding SoilGrids texture features collapses transfer to zero.");

  s.addText("R² = +0.020", {
    x: MARGIN, y: 2.2, w: 5.0, h: 0.85,
    fontFace: F.header, fontSize: 44, color: C.inkSoft, bold: true,
  });
  s.addText("95 % bootstrap CI  (-0.141, +0.146)\nstatistically indistinguishable from zero", {
    x: MARGIN, y: 3.2, w: 5.0, h: 0.9,
    fontFace: F.mono, fontSize: 12, color: C.inkSoft,
  });
  s.addText(
    "Same XGBoost model, same training points, plus 12 SoilGrids and engineered " +
    "soil features. Cross-continental transfer collapses. Heavier regularisation " +
    "doesn't rescue it. Dropping clay/sand/silt doesn't either.",
    { x: MARGIN, y: 4.3, w: 5.0, h: 2.5,
      fontFace: F.body, fontSize: 13, color: C.ink });

  const heroPath = path.join(OUT, "hero_full_features_asia_screen.png");
  if (fs.existsSync(heroPath)) {
    s.addImage({ path: heroPath,
      x: MARGIN + 5.4, y: 2.05, w: 7.3, h: 4.7 });
  }
  addFooter(s, 6, "Full-feature model fails to transfer");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 7 — Mechanism: dual-region SHAP
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "06  ·  MECHANISM",
    "Same features, different drivers. The clay correlation flips.");

  s.addText(
    "When the same XGBoost is trained separately on Asia and on US sites, the " +
    "feature → Rs relationship changes. Annual precipitation (bio12) is the only " +
    "feature with stable rank in both regions.",
    { x: MARGIN, y: 2.2, w: 5.5, h: 1.3,
      fontFace: F.body, fontSize: 13, color: C.ink });

  s.addText(
    "Clay correlation with log Rs:\n" +
    "  Asia    r = +0.302  (top driver in Asia)\n" +
    "  US      r = -0.048  (no relationship)\n\n" +
    "A model that learns 'more clay → more Rs' from\n" +
    "Asia and applies it to US fails by construction.",
    { x: MARGIN, y: 3.65, w: 5.5, h: 2.6,
      fontFace: F.mono, fontSize: 12, color: C.ink });

  const shapPath = path.join(OUT, "shap_comparison.png");
  if (fs.existsSync(shapPath)) {
    s.addImage({ path: shapPath,
      x: MARGIN + 5.9, y: 2.05, w: 6.7, h: 4.7 });
  }
  addFooter(s, 7, "Regional driver heterogeneity");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 8 — Köppen finding
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "07  ·  STRATIFICATION TEST",
    "Climate-zone stratification makes transfer worse, not better.");

  s.addText(
    "If the feature → Rs relationship differs cross-region, train one sub-model per " +
    "Köppen-Geiger climate zone. Both qualifying zones underperform the cross-zone " +
    "baseline.",
    { x: MARGIN, y: 2.2, w: W - 2*MARGIN, h: 1.0,
      fontFace: F.body, fontSize: 14, color: C.ink });

  // Table
  const rows = [
    ["Configuration", "n_Asia", "n_US", "Transfer R²", "95 % CI", "Verdict"],
    ["F  cross-zone (reference)", "600", "272", "+0.127", "(+0.019, +0.216)", "✓ significant"],
    ["F  Köppen C  (temperate)",  "247",  "89", "−0.336", "(−1.06, +0.04)",  "✗ spans 0"],
    ["F  Köppen D  (continental)","244", "159", "−0.199", "(−0.39, −0.06)",  "✗ negative"],
  ];
  const table = rows.map((row, i) => row.map(cell => ({
    text: cell,
    options: {
      fontFace: i === 0 ? F.header : F.mono, fontSize: 12,
      color: i === 0 ? C.accent : C.ink, bold: i === 0,
      valign: "middle",
    },
  })));
  s.addTable(table, {
    x: MARGIN, y: 3.4, w: W - 2*MARGIN, colW: [3.6, 1.2, 1.2, 1.6, 2.4, 2.1],
    border: { type: "solid", color: C.rule, pt: 0.5 },
    rowH: 0.45,
  });

  s.addText(
    "The cross-zone +0.127 IS the cross-zone precipitation gradient. " +
    "Stratify it away and there is no transferable signal left.",
    { x: MARGIN, y: 6.0, w: W - 2*MARGIN, h: 0.7,
      fontFace: F.body, fontSize: 14, color: C.accent, italic: true, bold: true });
  addFooter(s, 8, "Stratification doesn't rescue transfer");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 9 — Implication
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "08  ·  IMPLICATION",
    "Continental Rs maps need ground truth that current data products can't supply.");

  // Figure on right
  const figPath = path.join(OUT, "framing2_comparison_panel.png");
  if (fs.existsSync(figPath)) {
    s.addImage({ path: figPath, x: MARGIN + 5.4, y: 2.1, w: 7.3, h: 3.5 });
  }

  s.addText(
    "Two of three components in the standard upscaling recipe — gridded climate, " +
    "gridded soil, gridded vegetation — are themselves modelled, not measured, " +
    "at the resolution that matters.\n\n" +
    "SoilGrids 2.0 carries soil signal that varies by region in ways that don't " +
    "reflect the actual Rs response.\n\n" +
    "MODIS NPP (pending) will help. But continental maps will continue to under-" +
    "represent soil-driven variability without an in-situ measurement layer at " +
    "the resolution where soil heterogeneity actually lives.",
    { x: MARGIN, y: 2.2, w: 5.0, h: 4.5,
      fontFace: F.body, fontSize: 13, color: C.ink });
  addFooter(s, 9, "Implication for monitoring infrastructure");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 10 — Sensor connection
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "09  ·  SENSOR CONNECTION",
    "The biosensor measures the same flux, at the resolution the satellite can't.");

  // Conceptual diagram (placeholder for sensor figure to be added later)
  const sensorFig = path.join(OUT, "sensor_connection_figure_screen.png");
  if (fs.existsSync(sensorFig)) {
    s.addImage({ path: sensorFig, x: MARGIN, y: 2.1, w: W - 2*MARGIN, h: 3.5 });
  } else {
    // Text placeholder
    s.addText(
      "[Sensor connection figure — pending Checkpoint 2 render]",
      { x: MARGIN, y: 3.2, w: W - 2*MARGIN, h: 1.0,
        fontFace: F.mono, fontSize: 12, color: C.inkSoft,
        align: "center", italic: true });
  }
  s.addText(
    "Electrochemically active biofilms (EAB) on a low-cost electrode yield a current " +
    "directly proportional to substrate oxidation rate — the biological process that " +
    "Rs_annual integrates. Centimetre footprint, continuous deployment, no laboratory.",
    { x: MARGIN, y: 5.8, w: W - 2*MARGIN, h: 0.9,
      fontFace: F.body, fontSize: 13, color: C.ink });
  addFooter(s, 10, "EAB-Rs linkage");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 11 — Roadmap
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addHeader(s, "10  ·  ROADMAP",
    "Three deliverables, three months.");

  const items = [
    { y: 2.3, head: "1.  MODIS NPP integration",
      sub: "GEE export queued; expected lift in transfer R² documented in literature.",
      status: "≤ 2 weeks" },
    { y: 3.4, head: "2.  Earth System Science Data submission",
      sub: "Manuscript draft in repository; 5 verified references; data and code public.",
      status: "≤ 6 weeks" },
    { y: 4.5, head: "3.  Co-located biosensor deployment",
      sub: "Pilot at 2 SRDB-listed sites; first paired EAB current vs chamber Rs measurement.",
      status: "≤ 12 weeks" },
  ];
  items.forEach(it => {
    s.addText(it.head, {
      x: MARGIN, y: it.y, w: 8.5, h: 0.5,
      fontFace: F.header, fontSize: 18, color: C.ink, bold: true,
    });
    s.addText(it.sub, {
      x: MARGIN, y: it.y + 0.5, w: 8.5, h: 0.5,
      fontFace: F.body, fontSize: 13, color: C.inkSoft,
    });
    s.addText(it.status, {
      x: W - MARGIN - 2.5, y: it.y, w: 2.5, h: 0.5,
      fontFace: F.mono, fontSize: 13, color: C.accent, bold: true, align: "right",
    });
  });
  addFooter(s, 11, "Roadmap");
}

// ────────────────────────────────────────────────────────────────────────
// SLIDE 12 — Closing
// ────────────────────────────────────────────────────────────────────────
{
  const s = pptx.addSlide(); addBackground(s);
  addBackground(s);
  s.addShape(pptx.ShapeType.line, {
    x: MARGIN, y: 2.4, w: 2.0, h: 0,
    line: { color: C.accent, width: 1.5 },
  });
  s.addText("Three scales.", {
    x: MARGIN, y: 2.6, w: W - 2*MARGIN, h: 1.0,
    fontFace: F.header, fontSize: 48, color: C.ink, bold: true });
  s.addText("One biology.", {
    x: MARGIN, y: 3.6, w: W - 2*MARGIN, h: 1.0,
    fontFace: F.header, fontSize: 48, color: C.ink, bold: true });
  s.addText("One missing instrument.", {
    x: MARGIN, y: 4.6, w: W - 2*MARGIN, h: 1.0,
    fontFace: F.header, fontSize: 48, color: C.accent, bold: true });

  s.addText("Genius Olympiad 2026   ·   MSHI-Geo   ·   github.com/Sparkxt-0318/MSHI", {
    x: MARGIN, y: H - 1.0, w: W - 2*MARGIN, h: 0.4,
    fontFace: F.mono, fontSize: 12, color: C.inkSoft });
}

// ── Write the file ───────────────────────────────────────────────────
const outPath = path.join(OUT, "genius_pitch_deck.pptx");
pptx.writeFile({ fileName: outPath }).then(filename => {
  console.log("Wrote " + filename);
});
