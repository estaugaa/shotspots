/* Plain-language glossary: technical names (GOES-18, HRRR, Bortle, Kp…) get a dotted underline wherever they
   appear; tap or click one for a one-line explanation. Applied after each render, like kitify(). */
"use strict";
const GLOSS = [
  [/\bGOES(?:-1[6-9]|-West|-East)?\b/, "GOES-18", "NOAA's weather satellite that watches the West Coast from space. ShotSpots checks its pictures every 10–15 minutes to see where fog and low cloud are right now."],
  [/\bHRRR\b/, "HRRR", "NOAA's High-Resolution Rapid Refresh: a detailed weather forecast (3 km grid) that updates every hour, out to 48 hours. It drives the fog, cloud and sunset-colour odds."],
  [/\bOpen-Meteo\b/, "Open-Meteo", "A free weather service ShotSpots uses for hourly forecasts, and for days 3–5 beyond the HRRR's reach."],
  [/\bSNOTEL\b/, "SNOTEL", "Automatic snow stations run by the US Department of Agriculture in the mountains. They report snow depth daily, which tells you whether a road or trail is snowed in."],
  [/\bSentinel-2\b/, "Sentinel-2", "A European satellite that photographs the ground every few days. ShotSpots uses it to see how far along fall colour is."],
  [/\bBortle(?: \d)?\b/, "Bortle", "A 1–9 scale of how dark the night sky is: 1 is a remote dark site where the Milky Way casts shadows, 9 is a city centre where you see only a few stars."],
  [/\bKp(?: ?\d(?:\.\d)?)?\b/, "Kp", "A 0–9 measure of how stirred up Earth's magnetic field is. In the Northwest, northern lights become possible from about Kp 6 and likely at 7 or more."],
  [/\bVIIRS\b/, "VIIRS", "A satellite sensor that measures light at night. ShotSpots uses it to estimate how dark the sky is at each spot."],
  [/\bSQM\b/, "SQM", "A Sky Quality Meter reading: sky brightness in magnitudes per square arcsecond. Higher is darker; 21.5 or more is a properly dark sky."],
  [/\baerosol optical depth\b|\bAOD\b/i, "Aerosol optical depth", "How much haze or smoke is in the air overhead. Under 0.1 is crisp; above 0.5 the sky looks milky and distant mountains vanish."],
  [/\bGBIF\b/, "GBIF", "The Global Biodiversity Information Facility: a worldwide database of wildlife sightings. ShotSpots uses it to tell when a species usually shows up at a spot."],
  [/\binversion\b/, "Inversion", "Warm air sitting on top of cold air. It traps fog and smoke in valleys, which is what gives you a sea of fog from a high viewpoint."],
  [/\bblue hour\b/i, "Blue hour", "The 20–40 minutes before sunrise and after sunset when the sky is deep blue and city lights balance with it."],
  [/\bgolden hour\b/i, "Golden hour", "Roughly the first and last hour of sunlight, when the sun is low and the light is warm and soft."],
  [/\bBrier\b/, "Brier score", "A score for how good probability forecasts were: 0 is perfect, 0.25 is no better than a coin toss. Lower is better."],
  [/\bclimatology\b/, "Climatology", "What usually happens on this date, from years of records. A forecast with skill beats it."],
  [/\bterminator\b/, "Terminator", "The line between day and night on the moon. Craters near it show the most relief."],
];
const GLOSS_SKIP = "button,a,input,select,option,textarea,svg,script,style,.term,#glossPop,.figsvg,label";
function glossify(root) {
  if (!root) return;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: n => n.nodeValue.trim().length > 2 && n.parentElement && !n.parentElement.closest(GLOSS_SKIP) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT });
  const nodes = []; while (w.nextNode()) nodes.push(w.currentNode);
  for (const n of nodes) {
    const blk = n.parentElement.closest("p,li,div,small,h3,figcaption,span") || root; blk._gl = blk._gl || new Set();
    for (let gi = 0; gi < GLOSS.length; gi++) { const [re] = GLOSS[gi]; if (blk._gl.has(gi)) continue;
      const m = n.nodeValue.match(re); if (!m) continue;
      const after = n.splitText(m.index); after.nodeValue = after.nodeValue.slice(m[0].length);
      const b = document.createElement("span"); b.className = "term"; b.tabIndex = 0; b.setAttribute("role", "button"); b.dataset.term = gi; b.textContent = m[0];
      n.parentNode.insertBefore(b, after); blk._gl.add(gi); break; }   // one term per text node per pass is plenty
  }
}
function glossShow(el) {
  const [, title, txt] = GLOSS[+el.dataset.term]; let p = $("#glossPop");
  if (!p) { document.body.insertAdjacentHTML("beforeend", `<div id="glossPop" role="tooltip" hidden></div>`); p = $("#glossPop"); }
  if (!p.hidden && p._for === el) { p.hidden = true; return; }
  p.innerHTML = `<b>${esc(title)}</b> ${esc(txt)}`; p.hidden = false; p._for = el;
  const r = el.getBoundingClientRect(), W = Math.min(320, innerWidth - 24); p.style.width = W + "px";
  let x = Math.min(Math.max(12, r.left + r.width / 2 - W / 2), innerWidth - W - 12), y = r.bottom + 8;
  p.style.left = x + "px"; p.style.top = y + "px";
  const ph = p.offsetHeight; if (y + ph > innerHeight - 12) p.style.top = Math.max(12, r.top - ph - 8) + "px";
}
document.addEventListener("click", e => { const t = e.target.closest(".term"); const p = $("#glossPop");
  if (t) { e.preventDefault(); e.stopPropagation(); return glossShow(t); } if (p && !p.hidden && !e.target.closest("#glossPop")) p.hidden = true; }, true);
document.addEventListener("keydown", e => { const t = e.target.closest && e.target.closest(".term"); if (t && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); glossShow(t); } if (e.key === "Escape") { const p = $("#glossPop"); if (p) p.hidden = true; } });
addEventListener("scroll", () => { const p = $("#glossPop"); if (p) p.hidden = true; }, true);
{ const _rG = render; render = function () { const r = _rG.apply(this, arguments); glossify($("#main")); return r; }; }
{ const _oG = openSpot; openSpot = function (id) { _oG(id); const b = $("#sheetBody"); glossify(b); setTimeout(() => glossify(b), 900); }; }
{ const _sG = renderSettings; renderSettings = function () { const r = _sG.apply(this, arguments); const b = $("#setBody"); setTimeout(() => glossify(b), 450); if (r && r.then) r.then(() => setTimeout(() => glossify(b), 50)); return r; }; }
{ const _mG = renderMap; renderMap = function () { const r = _mG.apply(this, arguments); glossify($("#mapLegend")); return r; }; }
