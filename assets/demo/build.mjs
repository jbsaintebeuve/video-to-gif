#!/usr/bin/env node
// Génère assets/demo.svg, la démo animée en haut du README.
//
//   node assets/demo/build.mjs            écrit assets/demo.svg
//   node assets/demo/build.mjs --at 9.5   affiche l'image figée à 9,5 s
//   node assets/demo/build.mjs --check    échoue si assets/demo.svg n'est pas à jour
//
// Uniquement des keyframes CSS, sans script : GitHub retire le JavaScript des SVG.
// Chaque ligne utilise textLength, pour que les colonnes restent alignées quelle
// que soit la police monospace du lecteur. Les sorties viennent de ./scenario.sh,
// qui lance le vrai vid2gif (et de vid2gif/desktop.py pour `vid2gif setup`).
// Même moteur que la démo de https://github.com/jbsaintebeuve/wt.

import { readFileSync, writeFileSync } from "node:fs";

const FONT = 14.5;
const CW = 8.7; // avance forcée par caractère
const LH = 25;
const W = 860;
const PAD = 20; // marge autour de la fenêtre, pour l'ombre
const BAR = 40; // hauteur de la barre de titre
const X0 = 46; // première colonne de texte
const Y0 = BAR + 34; // ligne de base de la première rangée
const ROWS = 12;
const H = BAR + 34 + (ROWS - 1) * LH + 26;

const C = {
  bg: "#0f1117", bar: "#161922", border: "#262b36",
  text: "#d5dae4", dim: "#7b8496", path: "#7aa2f7", sigil: "#4f5872",
  cmd: "#7dcfff", tool: "#34d399", red: "#ff7a90", green: "#9ece6a",
  yellow: "#e8b86b", cursor: "#34d399", brand: "#059669",
};

const HOME = "~";
const X_URL = "https://x.com/weirdnotwild/status/2114199180243857583";
const X_GIF = "weirdnotwild_2114199158982606849.gif";

// --- timeline ---------------------------------------------------------------

const screens = [];
let t = 0;
let scr;

function screen(caption, build) {
  scr = { caption, start: t, rows: [], toasts: [] };
  t += 0.35;
  build();
  t += 2.3; // garde l'état final à l'écran
  scr.end = t;
  screens.push(scr);
}

function row(segs, extra = {}) {
  const r = { segs, at: t, ...extra };
  scr.rows.push(r);
  return r;
}

const prompt = (dir) => [[dir, "path"], [" $ ", "sigil"]];

function cmd(dir, text, extra = {}) {
  const [head, ...rest] = text.split(" ");
  const segs = [...prompt(dir), [head, head === "vid2gif" ? "tool" : "cmd"]];
  if (rest.length) segs.push([" " + rest.join(" "), "text"]);
  const r = row(segs, extra);
  r.col = dir.length + 3;
  r.typeStart = t + 0.45;
  r.typeEnd = r.typeStart + text.length * 0.04;
  r.n = text.length;
  r.enter = r.typeEnd + 0.22;
  t = r.enter + 0.2;
  return r;
}

function out(segs, extra = {}, gap = 0.07) {
  const r = row(typeof segs === "string" ? [[segs, "text"]] : segs, extra);
  t += gap;
  return r;
}

function idle(dir) {
  const r = row(prompt(dir));
  r.col = dir.length + 3;
  r.idle = true;
}

const ok = (text, cls = "text") => [["✓", "green b"], [" " + text, cls]];

screen("vid2gif setup : le clic droit et le raccourci ⌃⌥⌘G en une commande", () => {
  cmd(HOME, "vid2gif setup");
  t += 0.3;
  out(ok("Quick Action « Convertir en GIF »"), {}, 0.18);
  out(ok("Quick Action « Lien vidéo en GIF »"), {}, 0.18);
  out(ok("Quick Action « GIF depuis le lien copié »"), {}, 0.18);
  out(ok("Raccourci ⌃⌥⌘G → « GIF depuis le lien copié »"), { badge: "ok", hl: ["green", 0, 47] }, 0.3);
  out("");
  out([["C'est prêt :", "text b"]]);
  out([["  • Finder : clic droit sur une vidéo → ", "dim"], ["Actions rapides → Convertir en GIF", "text"]],
    { hl: ["violet", 40, 74] });
  out([["  • Lien vidéo copié → ", "dim"], ["⌃⌥⌘G", "tool"]], { hl: ["violet", 23, 27] });
  out([["Le GIF est copié : collez-le avec ⌘V.", "dim"]]);
  idle(HOME);
});

screen("Un lien X → un GIF déjà dans le presse-papiers", () => {
  cmd(HOME, `vid2gif ${X_URL} --copy`);
  out([["↓ ", "cmd"], [X_URL, "dim"]], {}, 1.3); // téléchargement
  out([["→ ", "cmd"], [`~/Downloads/${X_GIF}`, "path"]], {}, 1.6); // conversion
  out(ok("5.0 Mo (480px, 15 i/s)", "green b"), { badge: "ok", hl: ["green", 0, 24] });
  scr.toasts.push(t + 0.25);
  t += 0.6;
  idle(HOME);
  t += 1.2;
});

screen("Une vidéo locale : un extrait, allégé automatiquement", () => {
  cmd(HOME, "vid2gif Movies/vacances.mov -s 12 -t 4 --max-mb 3");
  out([["→ ", "cmd"], ["~/Movies/vacances.gif", "path"]], {}, 1.3);
  out([["  5.0 Mo > limite 3.0 Mo, nouvel essai plus léger…", "yellow"]], { hl: ["yellow", 2, 51] }, 1.2);
  out(ok("2.9 Mo (372px, 15 i/s)", "green b"), { badge: "ok", hl: ["green", 0, 24] });
  idle(HOME);
});

const T = +t.toFixed(2);

// --- rendering --------------------------------------------------------------

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const pct = (s) => `${Math.min(100, Math.max(0, (s / T) * 100)).toFixed(3)}%`;
const len = (segs) => segs.reduce((n, [s]) => n + [...s].length, 0);

let css = "";
let k = 0;

// Déclare des keyframes à partir d'étapes [temps, déclarations, timing?] ; renvoie une classe.
function anim(stops, extra = "") {
  const name = `k${k++}`;
  const all = [[0, stops[0][1]], ...stops, [T, stops[stops.length - 1][1]]];
  css += `@keyframes ${name}{${all
    .map(([s, d, fn]) => `${pct(s)}{${d}${fn ? `;animation-timing-function:${fn}` : ""}}`)
    .join("")}}\n.${name}{animation:${name} ${T}s linear infinite${extra}}\n`;
  return name;
}

const show = (at, fade = 0.12) => anim([[at, "opacity:0"], [at + fade, "opacity:1"]]);
const span = (a, b, fade = 0.3) =>
  anim([[a, "opacity:0"], [a + fade, "opacity:1"], [b - fade, "opacity:1"], [b, "opacity:0"]]);

function text(segs, x, y) {
  const body = segs.map(([s, cls]) => `<tspan class="${cls}">${esc(s)}</tspan>`).join("");
  return `<text xml:space="preserve" x="${x}" y="${y}" textLength="${(len(segs) * CW).toFixed(1)}" lengthAdjust="spacing">${body}</text>`;
}

const HL = {
  red: "rgba(255,122,144,.13)", green: "rgba(158,206,106,.14)",
  violet: "rgba(52,211,153,.11)", yellow: "rgba(232,184,107,.12)",
};

function badge(kind, y, at) {
  const pop = anim([
    [at, "transform:scale(0)", "cubic-bezier(.3,1.6,.6,1)"],
    [at + 0.28, "transform:scale(1)"],
  ]);
  const color = kind === "ok" ? C.green : C.red;
  const mark = kind === "ok"
    ? `<path d="M-3.4 0.2 L-1 2.6 L3.6 -2.4" />`
    : `<path d="M-2.6 -2.6 L2.6 2.6 M2.6 -2.6 L-2.6 2.6" />`;
  return `<g transform="translate(24 ${y - 4.5})"><g class="${pop}">` +
    `<circle r="8" fill="${color}" fill-opacity=".16" stroke="${color}" stroke-width="1.2"/>` +
    `<g fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${mark}</g></g></g>`;
}

function highlight([color, from, to], y, at) {
  const sweep = anim([
    [at, "transform:scaleX(0)", "cubic-bezier(.2,.8,.2,1)"],
    [at + 0.45, "transform:scaleX(1)"],
  ]);
  return `<g transform="translate(${X0 + from * CW - 5} ${y - 17})"><rect class="${sweep}" ` +
    `width="${((to - from) * CW + 10).toFixed(1)}" height="23" rx="5" fill="${HL[color]}"/></g>`;
}

// Notification macOS « GIF prêt » qui glisse depuis la droite, comme celle de vid2gif --notify.
function toast(at) {
  const TW = 384;
  const TH = 80;
  const x = W - TW - 18;
  const y = Y0 + 5 * LH - 6;
  const slide = anim([
    [at, "transform:translateX(420px)", "cubic-bezier(.16,1,.3,1)"],
    [at + 0.55, "transform:translateX(0)"],
  ]);
  return `<g transform="translate(${x} ${y})"><g class="${slide}">` +
    `<rect width="${TW}" height="${TH}" rx="13" fill="#1d2130" stroke="#323848" filter="url(#toastShadow)"/>` +
    `<rect x="14" y="21" width="38" height="38" rx="9" fill="${C.brand}"/>` +
    `<text class="icon" x="33" y="45" text-anchor="middle">VT</text>` +
    `<text class="tt" x="64" y="28">GIF prêt</text>` +
    `<g transform="translate(131 23.5)"><circle r="6.5" fill="${C.green}" fill-opacity=".18" stroke="${C.green}" stroke-width="1"/>` +
    `<path d="M-2.8 0.2 L-0.8 2.2 L3 -2" fill="none" stroke="${C.green}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></g>` +
    `<text class="tb" x="64" y="47">${esc(X_GIF)} — 5.0 Mo</text>` +
    `<text class="tm" x="${TW - 14}" y="28" text-anchor="end">maintenant</text>` +
    `<text class="tk" x="64" y="65">copié, prêt à coller <tspan class="key">⌘V</tspan></text>` +
    `</g></g>`;
}

function renderRow(r, i) {
  const y = Y0 + i * LH;
  let g = "";
  if (r.hl) g += highlight(r.hl, y, r.at + 0.1);
  g += text(r.segs, X0, y);
  if (r.n) g += typing(r, y);
  if (r.idle) {
    g += `<g class="${anim([[r.at, "opacity:1"]])}"><rect class="blink" x="${X0 + r.col * CW}" ` +
      `y="${y - 14}" width="${CW}" height="18" rx="1.5" fill="${C.cursor}"/></g>`;
  }
  if (r.badge) g += badge(r.badge, y, r.at + 0.08);
  return `<g class="${show(r.at)}">${g}</g>`;
}

// Un curseur suivi d'un masque couleur de fond glisse d'un caractère par étape,
// révélant la commande comme si elle était tapée.
function typing(r, y) {
  const slide = anim([
    [r.typeStart, "transform:translateX(0)", `steps(${r.n},end)`],
    [r.typeEnd, `transform:translateX(${(r.n * CW).toFixed(1)}px)`],
  ]);
  const caret = anim([[r.enter, "opacity:1"], [r.enter + 0.01, "opacity:0"]]);
  return `<g transform="translate(${X0 + r.col * CW} 0)"><g class="${slide}">` +
    `<rect x="${CW}" y="${y - 17}" width="${W}" height="23" fill="${C.bg}"/>` +
    `<rect class="${caret}" y="${y - 14}" width="${CW}" height="18" rx="1.5" fill="${C.cursor}"/></g></g>`;
}

function render() {
  const body = screens.map((s) =>
    `<g class="${span(s.start, s.end)}">${s.rows.map((r, i) => renderRow(r, i)).join("")}${s.toasts.map(toast).join("")}</g>`).join("\n");

  const captions = screens.map((s) =>
    `<text class="cap ${span(s.start, s.end)}" x="${W / 2}" y="${BAR / 2 + 4.5}" text-anchor="middle">${esc(s.caption)}</text>`).join("");

  const dots = screens.map((s, i) => {
    const x = W - 64 + i * 16;
    return `<circle cx="${x}" cy="${BAR / 2}" r="3.5" fill="${C.border}"/>` +
      `<circle class="${span(s.start, s.end, 0.2)}" cx="${x}" cy="${BAR / 2}" r="3.5" fill="${C.tool}"/>`;
  }).join("");

  const progress = anim([[0, "transform:scaleX(0)"], [T, "transform:scaleX(1)"]]);

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W + 2 * PAD} ${H + 2 * PAD}" width="${W + 2 * PAD}" height="${H + 2 * PAD}" xml:space="preserve" role="img" aria-label="Démo de vid2gif : vid2gif setup installe les actions rapides et le raccourci ⌃⌥⌘G ; un lien X devient un GIF copié dans le presse-papiers, avec une notification ; une vidéo locale est découpée et allégée automatiquement sous 3 Mo.">
<style>
${css}text{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;font-size:${FONT}px;fill:${C.text};white-space:pre;font-variant-ligatures:none}
.cap,.tt,.tb,.tm,.tk,.icon{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
.cap{font-size:12.5px;fill:#8d96a8;letter-spacing:.01em}
.tt{font-size:13px;font-weight:600;fill:#eef1f6}.tb{font-size:12px;fill:#b4bccb}.tm{font-size:11px;fill:#7b8496}
.tk{font-size:11.5px;fill:${C.green}}.key{font-weight:700}.icon{font-size:14px;font-weight:600;fill:#fff}
.path{fill:${C.path}}.sigil{fill:${C.sigil}}.cmd{fill:${C.cmd}}.tool{fill:${C.tool};font-weight:700}
.text{fill:${C.text}}.dim{fill:${C.dim}}.red{fill:${C.red}}.green{fill:${C.green}}.yellow{fill:${C.yellow}}.b{font-weight:700}
.blink{animation:blink 1.05s steps(1) infinite}@keyframes blink{50%{opacity:0}}
</style>
<defs>
<filter id="shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#000" flood-opacity=".35"/></filter>
<filter id="toastShadow" x="-10%" y="-20%" width="120%" height="160%"><feDropShadow dx="0" dy="5" stdDeviation="7" flood-color="#000" flood-opacity=".45"/></filter>
<clipPath id="win"><rect width="${W}" height="${H}" rx="11"/></clipPath>
</defs>
<g transform="translate(${PAD} ${PAD})">
<rect width="${W}" height="${H}" rx="11" fill="${C.bg}" filter="url(#shadow)"/>
<g clip-path="url(#win)">
<rect width="${W}" height="${H}" fill="${C.bg}"/>
<rect width="${W}" height="${BAR}" fill="${C.bar}"/>
<rect y="${BAR}" width="${W}" height="1" fill="${C.border}"/>
<circle cx="22" cy="${BAR / 2}" r="6" fill="#ff5f57"/><circle cx="42" cy="${BAR / 2}" r="6" fill="#febc2e"/><circle cx="62" cy="${BAR / 2}" r="6" fill="#28c840"/>
${captions}
${dots}
${body}
<rect class="${progress}" y="${H - 2}" width="${W}" height="2" fill="${C.tool}" fill-opacity=".55"/>
</g>
<rect x=".5" y=".5" width="${W - 1}" height="${H - 1}" rx="10.5" fill="none" stroke="${C.border}"/>
</g>
</svg>
`;
}

let svg = render();
const file = new URL("../demo.svg", import.meta.url);
const at = process.argv.indexOf("--at");
if (at !== -1) {
  const s = Number(process.argv[at + 1]);
  svg = svg.replace("</style>", `*{animation-play-state:paused!important;animation-delay:-${s}s!important}\n</style>`);
  process.stdout.write(svg);
} else if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = readFileSync(file, "utf8");
  } catch {}
  if (current !== svg) {
    console.error("assets/demo.svg n'est pas à jour : lancez node assets/demo/build.mjs");
    process.exit(1);
  }
} else {
  writeFileSync(file, svg);
  console.error(`assets/demo.svg écrit : boucle de ${T}s, ${svg.length} octets`);
}
