/* Camera kit: what you shoot with, and lens advice translated to it.
   Spot notes, sky targets and alerts were written for a Fujifilm X-T5 with the 16-50, 27 and 70-300 (APS-C, 1.5x).
   kitify() rewrites those references for the chosen kit, by 35 mm-equivalent focal length. */
"use strict";
const KITS = {
  iphone_pro: { name: "iPhone Pro", note: "0.5×, 1×, 2×, 5×", phone: true, lenses: [{ l: "0.5×", a: 13, b: 13 }, { l: "1×", a: 24, b: 24 }, { l: "2×", a: 48, b: 48 }, { l: "5×", a: 120, b: 120 }] },
  iphone: { name: "iPhone", note: "0.5×, 1×, 2×", phone: true, lenses: [{ l: "0.5×", a: 13, b: 13 }, { l: "1×", a: 26, b: 26 }, { l: "2×", a: 52, b: 52 }] },
  android: { name: "Android phone", note: "ultra-wide, main, 3× tele", phone: true, lenses: [{ l: "ultra-wide", a: 14, b: 14 }, { l: "main camera", a: 24, b: 24 }, { l: "3× tele", a: 70, b: 70 }] },
  fuji_xt5: { name: "Fujifilm X-T5", note: "XF 16-50, 27, 70-300", crop: 1.5, lenses: [{ l: "16-50", a: 24, b: 75 }, { l: "27", a: 40, b: 40 }, { l: "70-300", a: 105, b: 450 }] },
  custom: { name: "My own kit", note: "", custom: true, lenses: [] },
};
function kitId() { return store.get("kit", isOwner() ? "fuji_xt5" : "iphone_pro"); }
function kit() {
  const id = kitId(); if (id !== "custom") return { id, ...KITS[id] };
  const c = store.get("kitCustom", { name: "My camera", crop: 1, lenses: "24-70, 70-200" });
  const lenses = String(c.lenses).split(/[,;]+/).map(x => x.trim()).filter(Boolean).map(x => { const m = x.match(/(\d+)(?:\s*[-–]\s*(\d+))?/); if (!m) return null;
    const a = +m[1], b = +(m[2] || m[1]); return { l: x.replace(/\s*mm$/i, "") + (/mm/i.test(x) ? "" : " mm"), a: a * c.crop, b: b * c.crop, raw: [a, b] }; }).filter(Boolean);
  return { id, name: c.name || "My camera", crop: +c.crop || 1, lenses, custom: true };
}
/* best lens in the kit for a 35 mm-equivalent range [lo, hi] */
function lensFor(lo, hi) {
  const k = kit(); if (!k.lenses.length) return { txt: `about ${Math.round(lo)}${hi > lo ? "–" + Math.round(hi) : ""} mm (full-frame equivalent)` };
  const want = Math.sqrt(lo * hi);
  let best = null, bd = 1e9;
  for (const L of k.lenses) { const d = want < L.a ? L.a / want : want > L.b ? want / L.b : 1; if (d < bd) { bd = d; best = L; } }
  const at = (L) => { if (L.a === L.b) return ""; const f = Math.min(Math.max(want, L.a), L.b) / (k.crop || 1); return ` at about ${Math.round(f)} mm`; };
  if (want > best.b * 1.25) return { txt: k.phone ? `the ${best.l} (then crop in)` : `your ${best.l} at the long end (then crop)`, short: true };
  if (want < best.a / 1.25) return { txt: k.phone ? `the ${best.l} (or step back)` : `your ${best.l} at the wide end (or step back / panorama)` };
  return { txt: k.phone ? `the ${best.l}` : `your ${best.l}${at(best)}` };
}
const FUJI = { "16-50": [24, 36], "27": [40, 40], "70-300": [105, 450] };   // bare "16-50" is used for its wide end
const LENS_RE = /(?:\b(?:the|your)\s+)?\b(16[-–]50|70[-–]300|27(?=\s?mm\b|\s+(?:for|at|f\/)|\s*\(|\s*,|\s+or\b))(?:\s?mm)?(?:\s+at\s+(?:about\s+|~)?(\d+)(?:\s?[-–]\s?(\d+))?\s?mm)?/g;
function kitText(str) {
  if (!str || kitId() === "fuji_xt5") return str;
  return String(str).replace(LENS_RE, (m, lens, f1, f2) => {
    const key = lens.replace("–", "-"); const [a, b] = FUJI[key] || [24, 75];
    const lo = f1 ? +f1 * 1.5 : a, hi = f2 ? +f2 * 1.5 : f1 ? +f1 * 1.5 : b;
    return lensFor(lo, hi).txt;
  }).replace(/X-T5(?:'s)?/g, kit().name).replace(/\bthe 1\.4x crop\b|\bthe 1\.5x crop\b/g, "cropping")
    .replace(kit().phone ? /\s+at\s+f\/\d+(?:\.\d+)?/g : /$^/g, "")
    .replace(kit().phone ? /,?\s*\bf\/\d+(?:\.\d+)?|,?\s*\bISO \d+(?:[–-]\d+)?/g : /$^/g, "");
}
/* rewrite rendered text in place (spot sheets, sky targets, alerts) */
function kitify(el) {
  if (!el || kitId() === "fuji_xt5") return;
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const nodes = []; while (w.nextNode()) nodes.push(w.currentNode);
  for (const n of nodes) { const t = kitText(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; }
}
/* phone-specific night help replaces the X-T5 NPF box */
const _nightHelpK = nightHelp;
nightHelp = function (s) {
  const k = kit(); if (!k.phone) { const h = _nightHelpK(s); return k.id === "fuji_xt5" ? h : h.replace(/Night settings for your X-T5/, `Night settings for your ${esc(k.name)}`).replace(/Pinpoint stars:[^<]*/, `Pinpoint stars: keep exposures under about ${Math.round(500 / ((k.lenses[0] || { a: 24 }).a))} s at your widest lens (500 rule). ISO 3200–6400.`); }
  const e = dayEvents(s, laYMD(new Date())), m = moonPos(new Date(), s.lat, s.lon), nw = nightWindow(s);
  return `<details open><summary>Night shots with your ${esc(k.name)}</summary><ul class="plain">
    <li>Moon ${Math.round(m.illum * 100)}% lit${e.moonrise ? ", rises " + fmtT(e.moonrise) : ""}${e.moonset ? ", sets " + fmtT(e.moonset) : ""}.${nw && nw.dark ? ` Moon-free dark ${fmtT(nw.dark.s)}–${fmtT(nw.dark.e)}.` : ""}</li>
    <li>Use the 1× (main) camera: it has the biggest sensor. Put the phone on a tripod or a steady rock; Night mode then allows exposures up to about 30 s (tap the moon icon and drag to Max).</li>
    <li>Turn the flash off, tap to focus on a bright star or distant light, and use the self-timer or a Bluetooth remote so you don't shake it.</li>
    <li>For more control, a manual camera app with long exposures and RAW (such as ProCamera or NightCap) helps with stars and light trails.</li></ul></details>`;
};
/* hook rendering so every view speaks the chosen kit */
const _openK = openSpot; openSpot = function (id) { _openK(id); const b = $("#sheetBody"); kitify(b); setTimeout(() => kitify(b), 700); };
const _renderK = render; render = function () { _renderK(); kitify($("#main") || document.body); };
document.addEventListener("click", () => setTimeout(() => document.querySelectorAll(".sheet:not([hidden])").forEach(kitify), 50), true);

/* settings: pick a kit */
function kitSettingsHtml() {
  const id = kitId(), c = store.get("kitCustom", { name: "My camera", crop: 1, lenses: "24-70, 70-200" });
  return `<p class="label">Your camera</p><p class="muted" style="font-size:15px">Lens advice across the app is written for this.</p>
    <div class="chips" id="kitChips">${Object.entries(KITS).map(([k, v]) => `<button class="chip" data-kit="${k}" aria-pressed="${k === id}">${v.name}</button>`).join("")}</div>
    ${id === "custom" ? `<form id="kitForm" class="stack" style="margin-top:8px">
      <label>Camera name<input name="name" value="${esc(c.name)}"></label>
      <label>Lenses (focal lengths as printed, comma-separated)<input name="lenses" value="${esc(c.lenses)}" placeholder="14, 24-70, 70-200"></label>
      <label>Sensor<select name="crop">${[[1, "Full frame"], [1.5, "APS-C (Fuji, Sony, Nikon)"], [1.6, "APS-C (Canon)"], [2, "Micro Four Thirds"], [2.7, "1-inch"]].map(([v, l]) => `<option value="${v}" ${+c.crop === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <button class="btn" type="submit">Save kit</button></form>` : `<p class="muted" style="font-size:14px">${esc(KITS[id].note)}</p>`}`;
}
const _renderSettingsK = renderSettings;
renderSettings = function () { _renderSettingsK(); const b = $("#setBody"); if (b && !b.querySelector("#kitChips")) b.insertAdjacentHTML("afterbegin", kitSettingsHtml()); };
document.addEventListener("click", e => { const t = e.target.closest("[data-kit]"); if (!t) return; store.set("kit", t.dataset.kit); renderSettings(); render(); toast(`Lens advice now for: ${KITS[t.dataset.kit].name}`); });
document.addEventListener("submit", e => { if (e.target.id !== "kitForm") return; e.preventDefault(); const f = new FormData(e.target);
  store.set("kitCustom", { name: f.get("name") || "My camera", lenses: f.get("lenses") || "", crop: +f.get("crop") || 1 }); renderSettings(); render(); toast("Kit saved"); });

/* Plan tab: Light / Night sky / Calendar switch at the top of each of the three views */
function planSeg() {
  const v = UI.view; if (!PLAN_VIEWS.includes(v)) return; const el = $("#v-" + v); if (!el || el.querySelector(".planseg")) return;
  el.insertAdjacentHTML("afterbegin", `<div class="planseg" role="tablist" aria-label="Plan views">${[["now", "Light"], ["sky", "Night sky"], ["cal", "Calendar"]].map(([k, l]) =>
    `<button role="tab" data-v="${k}" aria-selected="${k === v}">${l}</button>`).join("")}</div>`);
}
const _renderSeg = render; render = function () { _renderSeg(); planSeg(); };
new MutationObserver(() => planSeg()).observe(document.getElementById("main") || document.body, { childList: true, subtree: true });
