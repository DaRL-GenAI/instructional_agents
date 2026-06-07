#!/usr/bin/env node
/**
 * LaTeX Beamer → PPTX Builder (pptxgenjs)
 *
 * Reads JSON frame data from stdin, produces a .pptx file.
 *
 * Follows the PPTX skill guidelines strictly:
 *   - pptxgenjs LAYOUT_WIDE (13.3" × 7.5")
 *   - Midnight Executive palette (navy dominant, ice-blue secondary, orange accent)
 *   - Georgia / Calibri / Consolas font stack
 *   - Dark/light sandwich: first & last slides dark, content slides light
 *   - NEVER accent lines under titles (use whitespace instead)
 *   - bullet: true (never unicode bullets)
 *   - breakLine: true between items, omitted on last item
 *   - Fresh option objects per call (never reuse)
 *   - Every slide gets a visual element (decorative shape/icon circle)
 *   - Varied layouts per content type
 *   - 0.5" minimum margins, 0.3–0.5" between content blocks
 *   - Titles 36pt+, body 14–16pt, captions 10–12pt
 */

const pptxgen = require("pptxgenjs");

// ─── Icons (react-icons → PNG → base64) ────────────────────────────────────
// Skill: "Icons in small colored circles next to section headers"

let React, ReactDOMServer, sharp, iconSets;
let iconsAvailable = false;

try {
  React = require("react");
  ReactDOMServer = require("react-dom/server");
  sharp = require("sharp");
  iconSets = {
    fa: require("react-icons/fa"),
    md: require("react-icons/md"),
  };
  iconsAvailable = true;
} catch (e) {
  // Icons optional — fall back to colored circles
}

function renderIconSvg(IconComponent, color, size) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
}

async function iconToBase64Png(IconComponent, color, size) {
  const svg = renderIconSvg(IconComponent, color || "#FFFFFF", size || 256);
  const pngBuf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + pngBuf.toString("base64");
}

// Map content keywords to icons for intelligent icon selection
const ICON_MAP = [
  { kw: ["code", "program", "software", "algorithm", "implement"], icon: "FaCode" },
  { kw: ["data", "database", "storage", "dataset"], icon: "FaDatabase" },
  { kw: ["learn", "education", "study", "course", "train"], icon: "FaGraduationCap" },
  { kw: ["network", "connect", "internet", "web"], icon: "FaNetworkWired" },
  { kw: ["security", "safe", "protect", "privacy"], icon: "FaShieldAlt" },
  { kw: ["chart", "graph", "statistic", "metric", "performance"], icon: "FaChartLine" },
  { kw: ["check", "success", "correct", "result"], icon: "FaCheckCircle" },
  { kw: ["search", "find", "query", "retriev"], icon: "FaSearch" },
  { kw: ["brain", "intelligen", "cogniti", "think", "reason"], icon: "FaBrain" },
  { kw: ["robot", "agent", "automat", "bot"], icon: "FaRobot" },
  { kw: ["tool", "utility", "function"], icon: "FaTools" },
  { kw: ["book", "document", "text", "read", "paper"], icon: "FaBook" },
  { kw: ["warning", "alert", "danger", "risk", "error"], icon: "FaExclamationTriangle" },
  { kw: ["setting", "config", "parameter", "option"], icon: "FaCog" },
  { kw: ["user", "human", "person", "people"], icon: "FaUser" },
  { kw: ["list", "item", "categor", "classif", "taxonom"], icon: "FaListUl" },
  { kw: ["example", "case", "scenario", "illustr"], icon: "FaLightbulb" },
  { kw: ["model", "architecture", "framework", "system", "design"], icon: "FaCubes" },
  { kw: ["language", "nlp", "llm", "gpt", "natural"], icon: "FaLanguage" },
  { kw: ["memory", "remember", "recall", "context"], icon: "FaMemory" },
];

function pickIconName(title) {
  if (!title) return "FaCubes";
  const lc = title.toLowerCase();
  for (const entry of ICON_MAP) {
    if (entry.kw.some(k => lc.includes(k))) return entry.icon;
  }
  return "FaCubes"; // default
}

function getIconComponent(name) {
  if (!iconsAvailable) return null;
  return iconSets.fa[name] || iconSets.md[name] || iconSets.fa.FaCubes;
}

// Pre-render icon cache (filled during main)
const iconCache = {};

async function getIconBase64(name, color) {
  const key = name + ":" + color;
  if (iconCache[key]) return iconCache[key];
  const comp = getIconComponent(name);
  if (!comp) return null;
  const data = await iconToBase64Png(comp, color, 256);
  iconCache[key] = data;
  return data;
}

// ─── Design tokens ──────────────────────────────────────────────────────────

const PAL = {
  navy:       "1E2761",
  iceBlue:    "CADCFC",
  accent:     "E67E22",
  textDark:   "242424",
  textMuted:  "646F82",
  green:      "27AE60",
  red:        "C0392B",
  codeBg:     "282C34",
  codeFg:     "ABB2BF",
  white:      "FFFFFF",
  offWhite:   "F8F9FC",
  mathBg:     "F0EDFF",
  blockBlue:  "E8EDF8",
  blockRed:   "FDF0EB",
  blockGreen: "E8F6EE",
  tikzBg:     "F0F0F6",
};

const FONT = { heading: "Georgia", body: "Calibri", code: "Consolas" };

// Slide dimensions for LAYOUT_WIDE
const SW = 13.33;
const SH = 7.5;

const L = {
  titleH:   1.1,            // title bar height
  cX:       0.7,            // content left margin
  cY:       1.5,            // content top (below title bar)
  cW:       11.93,          // content width (SW - 2 * 0.7)
  gap:      0.35,           // gap between content blocks (≥0.3)
  maxY:     6.8,            // stop adding content
};

// Visual motif (sidebar accent, decorative circles) is now in Slide Masters.
// addIconCircle is kept for per-slide icon placement.

function addIconCircle(slide, y, color) {
  slide.addShape("ellipse", {
    x: 0.7, y: y + 0.05, w: 0.22, h: 0.22,
    fill: { color: color || PAL.accent },
  });
}

// ─── Height estimation ──────────────────────────────────────────────────────

function estH(text, w, pt) {
  if (!text) return 0.4;
  const cpl = Math.max(1, Math.floor(w * (pt <= 12 ? 7 : 5)));
  const lines = Math.max(1, Math.ceil(text.length / cpl));
  return lines * (pt / 55) + 0.15;
}

// ─── Rough element height estimator (for vertical centering) ────────────────

function estimateElemH(el) {
  if (!el) return 0;
  switch (el.type) {
    case "text": return estH(el.content, L.cW, 16) + L.gap;
    case "itemize":
    case "enumerate": {
      let n = (el.items || []).length;
      (el.items || []).forEach(it => { n += (it.subitems || []).length; });
      return n * 0.35 + L.gap;
    }
    case "block":
    case "alertblock":
    case "exampleblock": {
      let lines = el.title ? 1 : 0;
      (el.children || []).forEach(c => { lines += c.type === "text" ? 1 : (c.items || []).length || 1; });
      return lines * 0.3 + 0.5 + L.gap;
    }
    case "code": return Math.min((el.content || "").split("\n").length * 0.25 + 0.5, 3.5) + L.gap;
    case "math": return 0.6 + L.gap;
    case "tikz": return 1.2 + L.gap;
    case "image": return 3.2 + L.gap;
    case "columns": return 2.0 + L.gap;
    default: return 0.5;
  }
}

// ─── Flatten block children ─────────────────────────────────────────────────

function flattenElem(el, lvl) {
  lvl = lvl || 0;
  const out = [];
  if (el.type === "text") {
    if (el.content) out.push({ kind: lvl > 0 ? "sub" : "text", text: el.content });
  } else if (el.type === "itemize" || el.type === "enumerate") {
    (el.items || []).forEach((it, i) => {
      const pfx = el.type === "enumerate" ? `${i + 1}. ` : "";
      if (it.text) out.push({ kind: lvl > 0 ? "sub" : "bullet", text: pfx + it.text });
      (it.subitems || []).forEach(s => {
        if (s.text) out.push({ kind: "sub", text: s.text });
      });
    });
  } else if (["block", "alertblock", "exampleblock"].includes(el.type)) {
    if (el.title) out.push({ kind: "title", text: el.title });
    (el.children || []).forEach(c => out.push(...flattenElem(c, lvl + 1)));
  } else if (el.type === "code") {
    out.push({ kind: "text", text: el.language ? `[Code: ${el.language}]` : "[Code]" });
  } else if (el.type === "math") {
    out.push({ kind: "text", text: `[LaTeX] ${el.content}` });
  } else if (el.type === "tikz") {
    out.push({ kind: "text", text: "[TikZ Diagram]" });
  }
  return out;
}

// ─── Title bar (no accent line underneath!) ─────────────────────────────────

// Title bar shape is in the Slide Master; this just adds the title text.
function addTitleText(slide, title) {
  if (!title) return;
  const fs = title.length > 45 ? 28 : title.length > 35 ? 32 : 36;
  slide.addText(title, {
    x: 0.7, y: 0, w: 12.2, h: L.titleH,
    fontFace: FONT.heading, fontSize: fs, bold: true,
    color: PAL.white, valign: "middle", margin: 0,
    shrinkText: true,
  });
}

// ─── Element renderers ──────────────────────────────────────────────────────

function addText(slide, text, x, y, w) {
  if (!text) return y;
  const h = estH(text, w, 16);
  slide.addText(text, {
    x, y, w, h,
    fontFace: FONT.body, fontSize: 16, color: PAL.textDark,
    valign: "top", paraSpaceAfter: 6, margin: 0,
  });
  return y + h + L.gap;
}

function addList(slide, items, x, y, w, numbered) {
  if (!items || !items.length) return y;

  const rows = [];
  let numCounter = 0;
  items.forEach((it, i) => {
    numCounter++;
    const itemText = numbered ? `${numCounter}. ${it.text || ""}` : (it.text || "");
    rows.push({
      text: itemText,
      options: {
        ...(numbered
          ? { breakLine: true }
          : { bullet: true, breakLine: true }),
        fontFace: FONT.body, fontSize: 16, color: PAL.textDark,
        paraSpaceAfter: 6,
      },
    });
    (it.subitems || []).forEach(s => {
      rows.push({
        text: s.text || "",
        options: {
          bullet: true, indentLevel: 1, breakLine: true,
          fontFace: FONT.body, fontSize: 14, color: PAL.textMuted,
          paraSpaceAfter: 4,
        },
      });
    });
  });
  if (rows.length) delete rows[rows.length - 1].options.breakLine;

  let chars = 0;
  rows.forEach(r => { chars += (r.text || "").length + 20; });
  const h = Math.min(estH("x".repeat(chars), w, 16), 5.5);

  slide.addText(rows, { x, y, w, h, valign: "top", margin: 0 });
  return y + h + L.gap;
}

function addBlock(slide, elem, x, y, w) {
  let bgColor, acColor, ttColor;
  if (elem.type === "alertblock") {
    bgColor = PAL.blockRed; acColor = PAL.accent; ttColor = PAL.red;
  } else if (elem.type === "exampleblock") {
    bgColor = PAL.blockGreen; acColor = PAL.green; ttColor = PAL.green;
  } else {
    bgColor = PAL.blockBlue; acColor = PAL.navy; ttColor = PAL.navy;
  }

  const lines = [];
  if (elem.title) lines.push({ kind: "title", text: elem.title });
  (elem.children || []).forEach(c => lines.push(...flattenElem(c, 0)));

  const rows = [];
  lines.forEach((ln, i) => {
    const last = i === lines.length - 1;
    if (ln.kind === "title") {
      rows.push({ text: ln.text, options: {
        breakLine: !last, fontFace: FONT.heading, fontSize: 18,
        bold: true, color: ttColor, paraSpaceAfter: 8,
      }});
    } else if (ln.kind === "bullet") {
      rows.push({ text: ln.text, options: {
        bullet: true, breakLine: !last,
        fontFace: FONT.body, fontSize: 14, color: PAL.textDark,
        paraSpaceAfter: 4,
      }});
    } else if (ln.kind === "sub") {
      rows.push({ text: ln.text, options: {
        bullet: true, indentLevel: 1, breakLine: !last,
        fontFace: FONT.body, fontSize: 13, color: PAL.textMuted,
        paraSpaceAfter: 3,
      }});
    } else {
      rows.push({ text: ln.text, options: {
        breakLine: !last, fontFace: FONT.body, fontSize: 14,
        color: PAL.textDark, paraSpaceAfter: 4,
      }});
    }
  });

  let chars = 0;
  lines.forEach(l => { chars += (l.text || "").length + 20; });
  const effW = w - 0.5;
  const h = Math.min(estH("x".repeat(chars), effW, 14) + 0.35, 5.5);

  // Left accent stripe
  slide.addShape("rect", {
    x, y, w: 0.06, h,
    fill: { color: acColor },
  });
  // Content with fill + shadow (skill: visual polish)
  slide.addText(rows, {
    x: x + 0.06, y, w: w - 0.06, h,
    fill: { color: bgColor },
    shadow: { type: "outer", color: "000000", blur: 6, offset: 3, angle: 135, opacity: 0.2 },
    valign: "top", margin: [6, 10, 6, 14],
  });

  return y + h + L.gap;
}

function addCode(slide, elem, x, y, w) {
  const code = elem.content || "";
  const codeLines = code.split("\n");
  const h = Math.min(codeLines.length * 0.25 + 0.5, 3.5);

  // Dark rounded rect background with shadow
  slide.addShape("roundRect", {
    x, y, w, h,
    fill: { color: PAL.codeBg },
    rectRadius: 0.08,
    shadow: { type: "outer", color: "000000", blur: 8, offset: 3, angle: 135, opacity: 0.25 },
  });

  // Language label (top-right, caption size)
  if (elem.language) {
    slide.addText(elem.language, {
      x: x + w - 1.5, y: y + 0.06, w: 1.4, h: 0.25,
      fontFace: FONT.code, fontSize: 10, color: PAL.textMuted,
      align: "right", margin: 0,
    });
  }

  // Code lines
  const rows = codeLines.map((ln, i) => ({
    text: ln,
    options: {
      breakLine: i < codeLines.length - 1,
      fontFace: FONT.code, fontSize: 11, color: PAL.codeFg,
      paraSpaceAfter: 1,
    },
  }));
  slide.addText(rows, {
    x: x + 0.2, y: y + 0.15, w: w - 0.4, h: h - 0.3,
    valign: "top", margin: 0,
  });

  return y + h + L.gap;
}

function addMath(slide, elem, x, y, w) {
  const latex = elem.content || "";
  const h = estH(latex, w, 14) + 0.15;
  slide.addText([
    { text: "LaTeX  ", options: { fontFace: FONT.code, fontSize: 10, color: PAL.textMuted, italic: true } },
    { text: latex,     options: { fontFace: FONT.code, fontSize: 14, color: PAL.navy } },
  ], {
    x, y, w, h,
    fill: { color: PAL.mathBg },
    valign: "top", margin: [4, 8, 4, 8],
  });
  return y + h + L.gap;
}

function addPicture(slide, elem, x, y, w) {
  // \includegraphics — embed a real image file (PNG/JPG) on the slide.
  // The Python side has already resolved elem.content to an absolute
  // path. We sanity-check the file exists and constrain the rendered
  // box so the image never bleeds past the slide's bottom margin.
  const fs = require("fs");
  const path = elem.content;
  if (!path || !fs.existsSync(path)) {
    slide.addShape("roundRect", {
      x, y, w, h: 1.0,
      fill: { color: PAL.tikzBg },
      line: { color: PAL.textMuted, width: 1 },
      rectRadius: 0.08,
    });
    slide.addText(`Image not found: ${path || "(no path)"}`, {
      x: x + 0.1, y: y + 0.3, w: w - 0.2, h: 0.4,
      fontSize: 11, color: PAL.textMuted, italic: true, align: "center",
    });
    return y + 1.0 + L.gap;
  }
  // Constrain height so the image always fits inside the slide.
  // L.maxY is the bottom of the usable content area; leave a small
  // buffer so the image doesn't visually crowd it. Cap at 3.2" so
  // multiple stacked elements stay sane on dense slides.
  const buffer = 0.25;
  const remaining = Math.max(0.8, L.maxY - y - buffer);
  const boxH = Math.min(3.2, remaining);
  const boxW = w;
  // Read PNG dimensions from header so we can pre-fit instead of relying on
  // pptxgenjs's sizing:"contain" (which LibreOffice doesn't always honour).
  let imgW = boxW, imgH = boxH;
  try {
    const buf = fs.readFileSync(path);
    // PNG: width = bytes 16-19 BE, height = bytes 20-23 BE
    if (buf.length >= 24 && buf[1] === 0x50 && buf[2] === 0x4E) {
      const nw = buf.readUInt32BE(16);
      const nh = buf.readUInt32BE(20);
      if (nw > 0 && nh > 0) {
        const aspect = nw / nh;          // native aspect (w/h)
        const boxAspect = boxW / boxH;
        if (aspect >= boxAspect) {
          // wider than box → fit by width
          imgW = boxW;
          imgH = boxW / aspect;
        } else {
          // taller than box → fit by height
          imgH = boxH;
          imgW = boxH * aspect;
        }
      }
    }
  } catch (e) { /* fall back to box dims */ }
  // Centre horizontally inside the box for a tidy layout.
  const drawX = x + (boxW - imgW) / 2;
  slide.addImage({ path, x: drawX, y, w: imgW, h: imgH });
  return y + imgH + L.gap;
}

function addTikz(slide, x, y, w) {
  const h = 1.2;
  slide.addShape("roundRect", {
    x, y, w, h,
    fill: { color: PAL.tikzBg },
    line: { color: PAL.textMuted, width: 1 },
    rectRadius: 0.08,
  });
  slide.addText("TikZ Diagram \u2014 see PDF version", {
    x, y, w, h,
    fontFace: FONT.body, fontSize: 14, italic: true,
    color: PAL.textMuted, align: "center", valign: "middle", margin: 0,
  });
  return y + h + L.gap;
}

function addColumns(slide, elem, x, y, w) {
  const cols = elem.children || [];
  if (!cols.length) return y;
  const colGap = 0.3;
  const colW = (w - colGap * (cols.length - 1)) / cols.length;
  let maxBot = y;
  cols.forEach((col, i) => {
    const cx = x + i * (colW + colGap);
    let cy = y;
    (col.children || []).forEach(child => { cy = renderElem(slide, child, cx, cy, colW); });
    maxBot = Math.max(maxBot, cy);
  });
  return maxBot + L.gap * 0.5;
}

function renderElem(slide, elem, x, y, w) {
  if (y > L.maxY) return y;
  switch (elem.type) {
    case "text":        return addText(slide, elem.content, x, y, w);
    case "itemize":     return addList(slide, elem.items, x, y, w, false);
    case "enumerate":   return addList(slide, elem.items, x, y, w, true);
    case "block":
    case "alertblock":
    case "exampleblock": return addBlock(slide, elem, x, y, w);
    case "code":        return addCode(slide, elem, x, y, w);
    case "math":        return addMath(slide, elem, x, y, w);
    case "tikz":        return addTikz(slide, x, y, w);
    case "columns":     return addColumns(slide, elem, x, y, w);
    case "image":       return addPicture(slide, elem, x, y, w);
    default:            return y;
  }
}

// ─── Layout selection ───────────────────────────────────────────────────────
// Skill: "Don't repeat the same layout — vary columns, cards, callouts."
// We detect the content structure and pick from several layout strategies.

function classifyFrame(frame) {
  const elems = frame.elements || [];
  if (elems.length === 0) return "empty";
  if (elems.length === 1 && elems[0].type === "text") return "single-text";
  if (elems.every(e => ["itemize", "enumerate"].includes(e.type))) return "list-only";
  if (elems.some(e => ["block", "alertblock", "exampleblock"].includes(e.type))) return "blocks";
  if (elems.some(e => e.type === "code")) return "code";
  if (elems.some(e => e.type === "columns")) return "columns";
  return "mixed";
}

// ─── Slide renderers by layout ──────────────────────────────────────────────

function renderStandard(slide, frame) {
  // Title bar and sidebar accent come from CONTENT_MASTER
  addTitleText(slide, frame.title);

  // Estimate total content height to center vertically if sparse
  const elems = frame.elements || [];
  let estTotal = 0;
  for (const e of elems) estTotal += estimateElemH(e);
  const availH = L.maxY - L.cY;
  const startY = estTotal < availH * 0.5 ? L.cY + (availH - estTotal) * 0.3 : L.cY;

  let y = startY;
  for (const elem of elems) {
    y = renderElem(slide, elem, L.cX, y, L.cW - 0.3);
  }
}

function renderSingleText(slide, frame) {
  addTitleText(slide, frame.title);

  const text = (frame.elements[0] || {}).content || "";
  // Use larger font for single-text slides, vertically centered
  const fs = text.length > 300 ? 16 : text.length > 150 ? 18 : 22;
  slide.addText(text, {
    x: L.cX, y: L.cY, w: L.cW - 0.3, h: SH - L.cY - 0.5,
    fontFace: FONT.body, fontSize: fs, color: PAL.textDark,
    valign: "middle", margin: [0, 0, 0, 0], paraSpaceAfter: 8,
  });
}

function renderListOnly(slide, frame) {
  addTitleText(slide, frame.title);

  const elems = frame.elements || [];
  let estTotal = 0;
  for (const e of elems) estTotal += estimateElemH(e);
  const availH = L.maxY - L.cY;
  const startY = estTotal < availH * 0.5 ? L.cY + (availH - estTotal) * 0.3 : L.cY;

  let y = startY;
  for (const elem of elems) {
    y = renderElem(slide, elem, L.cX, y, L.cW - 0.3);
  }
}

function renderBlocks(slide, frame) {
  addTitleText(slide, frame.title);

  const elems = frame.elements || [];
  let estTotal = 0;
  for (const e of elems) estTotal += estimateElemH(e);
  const availH = L.maxY - L.cY;
  const startY = estTotal < availH * 0.5 ? L.cY + (availH - estTotal) * 0.3 : L.cY;

  let y = startY;
  for (const elem of elems) {
    y = renderElem(slide, elem, L.cX, y, L.cW - 0.3);
  }
}

function renderCodeSlide(slide, frame) {
  // Title bar and bottom bar come from CONTENT_CODE master
  addTitleText(slide, frame.title);

  const elems = frame.elements || [];
  let estTotal = 0;
  for (const e of elems) estTotal += estimateElemH(e);
  const availH = L.maxY - L.cY;
  const startY = estTotal < availH * 0.5 ? L.cY + (availH - estTotal) * 0.3 : L.cY;

  let y = startY;
  for (const elem of elems) {
    y = renderElem(slide, elem, L.cX, y, L.cW);
  }
}

function renderDarkSlide(slide, frame) {
  // Background comes from DARK_MASTER; decorative circles added here
  // (pptxgenjs masters don't support ellipse in objects array)
  slide.addShape("ellipse", {
    x: SW - 1.8, y: SH - 1.8, w: 2.2, h: 2.2,
    fill: { color: "1A2255" },
  });
  slide.addShape("ellipse", {
    x: SW - 1.3, y: SH - 1.3, w: 1.5, h: 1.5,
    fill: { color: PAL.accent }, transparency: 85,
  });

  // Title — positioned at top, scaled for long titles
  if (frame.title) {
    const tLen = frame.title.length;
    const fs = tLen > 50 ? 26 : tLen > 40 ? 30 : tLen > 30 ? 34 : 38;
    slide.addText(frame.title, {
      x: 0.7, y: 0.6, w: 11.9, h: 1.2,
      fontFace: FONT.heading, fontSize: fs, bold: true,
      color: PAL.white, valign: "middle", align: "left", margin: 0,
      shrinkText: true,
    });
    // No accent line under title (skill: NEVER use accent lines under titles)
  }

  // Flatten ALL elements into text rows for light-on-dark rendering
  const allLines = [];
  for (const elem of (frame.elements || [])) {
    allLines.push(...flattenElem(elem, 0));
  }
  if (!allLines.length) return;

  const rows = [];
  allLines.forEach((ln, i) => {
    const last = i === allLines.length - 1;
    if (ln.kind === "title") {
      rows.push({ text: ln.text, options: {
        breakLine: !last, fontFace: FONT.heading, fontSize: 18,
        bold: true, color: PAL.white, paraSpaceAfter: 8,
      }});
    } else if (ln.kind === "bullet") {
      rows.push({ text: ln.text, options: {
        bullet: true, breakLine: !last,
        fontFace: FONT.body, fontSize: 16, color: PAL.iceBlue,
        paraSpaceAfter: 6,
      }});
    } else if (ln.kind === "sub") {
      rows.push({ text: ln.text, options: {
        bullet: true, indentLevel: 1, breakLine: !last,
        fontFace: FONT.body, fontSize: 14, color: PAL.iceBlue,
        paraSpaceAfter: 4,
      }});
    } else {
      rows.push({ text: ln.text, options: {
        breakLine: !last, fontFace: FONT.body, fontSize: 16,
        color: PAL.iceBlue, paraSpaceAfter: 6,
      }});
    }
  });

  // Place content in the area below title, spanning most of the slide
  slide.addText(rows, {
    x: 0.7, y: 2.2, w: 11.0, h: 4.8,
    valign: "top", margin: 0,
  });
}

// ─── Main ───────────────────────────────────────────────────────────────────

async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  const { outputPath, frames } = input;

  if (!outputPath || !frames) {
    console.error("Error: JSON must contain outputPath and frames");
    process.exit(1);
  }

  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.author = "Instructional Agents";
  pres.title = "Course Slides";

  // ── Slide Masters (skill: use defineSlideMaster for consistent layouts) ──
  pres.defineSlideMaster({
    title: "CONTENT_MASTER",
    background: { color: PAL.offWhite },
    objects: [
      // Navy title bar
      { rect: { x: 0, y: 0, w: "100%", h: L.titleH, fill: { color: PAL.navy } } },
      // Right sidebar accent (visual motif)
      { rect: { x: SW - 0.18, y: L.titleH, w: 0.18, h: SH - L.titleH,
                fill: { color: PAL.navy }, transparency: 70 } },
    ],
  });

  pres.defineSlideMaster({
    title: "CONTENT_CODE",
    background: { color: PAL.offWhite },
    objects: [
      // Navy title bar
      { rect: { x: 0, y: 0, w: "100%", h: L.titleH, fill: { color: PAL.navy } } },
      // Bottom bar instead of sidebar (more horizontal space for code)
      { rect: { x: 0, y: SH - 0.08, w: "100%", h: 0.08, fill: { color: PAL.iceBlue } } },
    ],
  });

  // DARK_MASTER: only background (pptxgenjs masters don't support ellipse shapes)
  // Decorative circles are added in renderDarkSlide() instead.
  pres.defineSlideMaster({
    title: "DARK_MASTER",
    background: { color: PAL.navy },
    objects: [],
  });

  const total = frames.length;

  for (let i = 0; i < total; i++) {
    const frame = frames[i];

    // Dark/light sandwich: first and last slides are dark
    const isFirst = i === 0;
    const isLast  = i === total - 1;
    const titleLc = (frame.title || "").toLowerCase();
    const isConclusion = titleLc.includes("conclusion") || titleLc.includes("summary")
                      || titleLc.includes("key points") || titleLc.includes("takeaway");

    if (isFirst || isLast || (isConclusion && !isFirst)) {
      const slide = pres.addSlide({ masterName: "DARK_MASTER" });
      renderDarkSlide(slide, frame);
      // Icon in title area for dark slides
      if (iconsAvailable) {
        const iconName = pickIconName(frame.title);
        const iconData = await getIconBase64(iconName, "#" + PAL.iceBlue);
        if (iconData) {
          // Icon in colored circle, top-right area
          slide.addShape("ellipse", {
            x: SW - 1.6, y: 0.35, w: 0.6, h: 0.6,
            fill: { color: PAL.accent }, transparency: 30,
          });
          slide.addImage({ data: iconData, x: SW - 1.45, y: 0.5, w: 0.3, h: 0.3 });
        }
      }
    } else {
      const kind = classifyFrame(frame);
      const masterName = kind === "code" ? "CONTENT_CODE" : "CONTENT_MASTER";
      const slide = pres.addSlide({ masterName });
      switch (kind) {
        case "single-text": renderSingleText(slide, frame); break;
        case "list-only":   renderListOnly(slide, frame);   break;
        case "blocks":      renderBlocks(slide, frame);     break;
        case "code":        renderCodeSlide(slide, frame);  break;
        default:            renderStandard(slide, frame);   break;
      }
      // Icon in title bar for content slides (skill: "Icons in small colored circles")
      if (iconsAvailable) {
        const iconName = pickIconName(frame.title);
        const iconData = await getIconBase64(iconName, "#FFFFFF");
        if (iconData) {
          // Small icon circle at right end of title bar
          slide.addShape("ellipse", {
            x: SW - 1.2, y: (L.titleH - 0.5) / 2, w: 0.5, h: 0.5,
            fill: { color: PAL.accent },
          });
          slide.addImage({
            data: iconData,
            x: SW - 1.08, y: (L.titleH - 0.26) / 2, w: 0.26, h: 0.26,
          });
        }
      }
    }
  }

  await pres.writeFile({ fileName: outputPath });
  console.log(`Generated: ${outputPath} (${total} slides)`);
}

main().catch(err => {
  console.error("Error:", err.message);
  process.exit(1);
});
