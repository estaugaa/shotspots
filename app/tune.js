/* Tuning panel for testing the scoring weights: open the app with #tune. Sliders change TUNE (app.js) on this device
   only; the list re-scores live. "Reset" returns to the defaults. */
"use strict";
const TUNE_INFO = {
  clearLight: ["Clear golden light on the land", 30, 90, 1, "value of a clear sunrise/sunset for landscapes (sky plain, light warm)"],
  alpenglow: ["Alpenglow bonus (mountains)", 0, 20, 1, "extra for peaks in clear golden light"],
  canvasFloor: ["Bare-sky colour floor", 0.1, 0.6, 0.02, "sky colour factor when there are no clouds to catch colour"],
  lowBroken: ["Broken low cloud (45–75%)", 0.3, 1, 0.05, "multiplier on sky colour; fair-weather cumulus"],
  lowDeck: ["Solid low deck (75%+)", 0.1, 0.8, 0.05, "multiplier on sky colour"],
  qMin: ["Spot quality: least photographed", 0.2, 1, 0.05, "multiplier for spots with the least record"],
  qMax: ["Spot quality: most photographed", 0.8, 1.5, 0.02, "multiplier for the best-known spots"],
  wildlifeOutside: ["Wildlife spots outside Wildlife", 0.5, 1, 0.05, "multiplier for refuges and birding spots"],
  sunLow: ["Daytime, sun below 12°", 0.5, 1, 0.02, "multiplier: low, warm, raking light"],
  sunMid: ["Daytime, sun 12–25°", 0.4, 1, 0.02, "multiplier: a winter midday"],
  sunHigh: ["Daytime, sun 25–40°", 0.4, 1, 0.02, "multiplier"],
  sunOverhead: ["Daytime, sun above 40°", 0.3, 1, 0.02, "multiplier: a summer midday, harsh"],
  faceAway: ["Faces away from the golden-hour sun", 0.4, 1, 0.01, "multiplier (measured x0.90 from photo history, Nov 20)"],
  blocked: ["Terrain 6°+ toward the low sun", 0.4, 1, 0.01, "multiplier (measured x0.75 from photo history, Nov 20)"],
  distance: ["Distance tie-break", 0, 0.4, 0.02, "most taken off at the edge of your travel range"],
};
function tuneHtml() {
  return `<div id="tunePanel" style="position:fixed;inset:auto 8px 8px 8px;max-height:62vh;overflow:auto;z-index:9999;background:var(--bg,#fff);color:inherit;border-radius:14px;box-shadow:0 6px 30px rgba(0,0,0,.35);padding:12px 14px">
    <div style="display:flex;justify-content:space-between;align-items:center"><b>Scoring weights (testing, this device)</b><span><button class="chip" data-tune-reset>Reset</button> <button class="chip" data-tune-close>Close</button></span></div>
    ${Object.entries(TUNE_INFO).map(([k, [lbl, lo, hi, st, help]]) => `<label style="display:block;margin:8px 0 2px;font-size:13px">${lbl}: <b data-tv="${k}">${TUNE[k]}</b> <small class="muted">(default ${TUNE_DEFAULT[k]})</small>
      <input type="range" min="${lo}" max="${hi}" step="${st}" value="${TUNE[k]}" data-tune="${k}" style="width:100%"><small class="muted">${help}</small></label>`).join("")}</div>`;
}
function openTune() { if (document.getElementById("tunePanel")) return; document.body.insertAdjacentHTML("beforeend", tuneHtml()); }
function tuneChanged() {
  const diff = {}; for (const k in TUNE) if (TUNE[k] !== TUNE_DEFAULT[k]) diff[k] = TUNE[k];
  try { localStorage.setItem("ss2:tune", JSON.stringify(diff)); } catch (e) { }
  if (typeof __skyMemoAt !== "undefined") __skyMemoAt = -1; if (typeof __topsKey !== "undefined") __topsKey = "";
  clearTimeout(tuneChanged.t); tuneChanged.t = setTimeout(() => typeof render === "function" && render(), 250);
}
document.addEventListener("input", e => { const el = e.target.closest("[data-tune]"); if (!el) return; const k = el.dataset.tune; TUNE[k] = +el.value;
  const b = document.querySelector(`[data-tv="${k}"]`); if (b) b.textContent = el.value; tuneChanged(); });
document.addEventListener("click", e => {
  if (e.target.closest("[data-tune-close]")) { document.getElementById("tunePanel")?.remove(); return; }
  if (e.target.closest("[data-tune-reset]")) { TUNE = { ...TUNE_DEFAULT }; document.getElementById("tunePanel")?.remove(); openTune(); tuneChanged(); }
});
if (/#tune\b/.test(location.hash)) { history.replaceState(null, "", location.pathname); setTimeout(openTune, 1200); }
window.addEventListener("hashchange", () => { if (/#tune\b/.test(location.hash)) { history.replaceState(null, "", location.pathname); openTune(); } });
