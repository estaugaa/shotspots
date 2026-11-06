/* Shot list (specific images, not places) and outing logs that feed the verification loop. */
"use strict";
let SHOTS = store.get("shots", []);
const SH_LIGHT = [["blueAM", "AM blue"], ["sunrise", "Sunrise"], ["morning", "Morning"], ["midday", "Midday"], ["afternoon", "Afternoon"], ["sunset", "Sunset"], ["bluePM", "PM blue"], ["night", "Night"]];
const SH_COND = [["any", "Any"], ["fog", "Fog"], ["clear", "Clear"], ["color", "Colour sky"], ["overcast", "Overcast"], ["calm", "Calm"], ["snow", "Snow"], ["rain", "Rain"]];
const SH_TARGET = [["", "None"], ["moon", "Moon"], ["sun", "Sun"], ["mwcore", "Milky Way core"], ["orion", "Orion"], ["pleiades", "Pleiades"], ["cygnus", "Cygnus"]];

/* ---------- probability model ----------
   P(shot in a window) = P(light window exists at the right time) x P(condition) x P(species) x P(target alignment), treated as independent.
   Within 48 h, condition odds come from HRRR (modeled); beyond that from 10-year ASOS climatology (measured history). */
function pCondForecast(c, s, w) {
  const h = hrrrRow(s.id, w.peak); if (!h) return null; const el = spotElev(s.id) || 0;
  return { any: 1, fog: h.p_fog / 100, clear: h.p_clear / 100, color: h.p_color / 100, overcast: h.tcc >= 80 ? 0.8 : h.tcc >= 60 ? 0.45 : 0.12,
    calm: h.wind <= 4 ? 0.75 : h.wind <= 8 ? 0.4 : 0.1, snow: h.snow_m != null && h.snow_m < el + 100 && h.tcc >= 80 ? 0.5 : 0.04, rain: h.tcc >= 90 && h.rh >= 90 ? 0.6 : 0.1 }[c];
}
function pCondClimo(c, s, t) {
  const k = climoFor(s, t); if (!k) return null; const mo = +laYMD(t).slice(5, 7), el = spotElev(s.id) || 0;
  return { any: 1, fog: k.fog / 100, clear: k.clear * 0.75 / 100, color: 0.3 * (1 - k.lowovc / 100), overcast: k.lowovc / 100 + 0.15, calm: 0.45,
    snow: [12, 1, 2].includes(mo) ? (el > 900 ? 0.4 : el > 300 ? 0.12 : 0.04) : 0.02, rain: 0.25 + 0.2 * k.lowovc / 100 }[c];
}
function pSpecies(sh, s, t) {
  if (!sh.species) return { p: 1 }; const w = wildlifeFor(s.id); if (!w) return { p: null };
  const x = w.species.find(z => z.sp.toLowerCase() === sh.species.toLowerCase()); if (!x) return { p: 0.02 };
  let p = w.kind.startsWith("eBird") ? x.wk[weekIdx(t)] / 100 : (x.rel ? x.rel[weekIdx(t)] * 0.6 : x.wk[weekIdx(t)] / 100); if (x.hr) { const tot = x.hr.reduce((a, b) => a + b, 0); const hb = Math.floor(+t.toLocaleString("en-US", { timeZone: TZ, hour: "numeric", hourCycle: "h23" }) / 3); p *= Math.min(1.6, Math.max(0.3, x.hr[hb] / tot * 8)); }
  return { p: Math.min(1, p), kind: w.kind };
}
function windowsForDate(s, ymd) {
  const e = dayEvents(s, ymd); if (!e.sunrise) return [];
  const civD = e.civilDawn || addMin(e.sunrise, -32), civK = e.civilDusk || addMin(e.sunset, 32);
  return [["blueAM", civD], ["sunrise", e.sunrise], ["morning", laDate(ymd, 9 * 60 + 30)], ["midday", laDate(ymd, 13 * 60)], ["afternoon", laDate(ymd, 15 * 60 + 30)],
    ["sunset", e.sunset], ["bluePM", civK], ["night", e.astroDusk ? addMin(e.astroDusk, 90) : addMin(civK, 150)]];
}
const __predMemo = {};
function predictShot(sh) {
  const mk = JSON.stringify(sh) + Math.floor(Date.now() / 6e5) + (FEED.m ? FEED.m.gen : "");
  if (__predMemo[mk]) return __predMemo[mk];
  return (__predMemo[mk] = predictShot2(sh));
}
function predictShot2(sh) {
  const s = byId[sh.spot]; if (!s) return null; const res = { next: null, best: null };
  const okMonth = t => !sh.months || !sh.months.length || sh.months.includes(+laYMD(t).slice(5, 7));
  // 1) forecast horizon: the windows in the next 40 h
  for (const w of allWindows(s, 40)) {
    if (!sh.light.includes(w.kind) || !okMonth(w.peak)) continue;
    let pc = 1, srcC = null;
    for (const c of sh.cond) { const v = pCondForecast(c, s, w); if (v == null) { pc = null; break; } pc *= v; }
    if (pc == null) { pc = sh.cond.reduce((a, c) => a * (pCondClimo(c, s, w.peak) ?? 0.3), 1); srcC = "climatology"; } else srcC = "HRRR";
    const ps = pSpecies(sh, s, w.peak);
    let pt = 1; if (sh.target) { const pl = fd("planner"); const ev = pl && (pl.events[s.id] || []).find(e => e.obj === sh.target && (!sh.landmark || e.lm === sh.landmark) && e.t * 60000 >= w.start - 40 * 60000 && e.t * 60000 <= w.end.getTime() + 40 * 60000); pt = ev ? 1 : 0; }
    const p = pc * (ps.p ?? 0.5) * pt;
    if (!res.next || p > res.next.p) res.next = { w, p, parts: { cond: pc, condSrc: srcC, species: ps.p, target: pt } };
  }
  // 2) beyond: seasonal odds for the next 365 days
  const today = laYMD(new Date());
  const cand = [];
  if (sh.target) {
    const pl = fd("planner"); for (const e of (pl && pl.events[s.id]) || []) { if (e.obj !== sh.target || (sh.landmark && e.lm !== sh.landmark)) continue; const t = minToDate(e.t); if (t - Date.now() < 40 * 36e5 || !okMonth(t)) continue;
      const pc = sh.cond.reduce((a, c) => a * (pCondClimo(c === "any" ? "clear" : c, s, t) ?? 0.3), 1); const ps = pSpecies(sh, s, t); cand.push({ t, kind: e.obj, p: pc * (ps.p ?? 0.5), ev: e }); }
  } else {
    for (let k = 2; k < 365; k += k < 120 ? 2 : 7) { const ymd = addDays(today, k); const mid = laDate(ymd, 12 * 60); if (!okMonth(mid)) continue;
      for (const [kind, t] of windowsForDate(s, ymd)) { if (!sh.light.includes(kind)) continue; const pc = sh.cond.reduce((a, c) => a * (pCondClimo(c, s, t) ?? 0.3), 1); const ps = pSpecies(sh, s, t); cand.push({ t, kind, p: pc * (ps.p ?? 0.5) }); } }
  }
  if (cand.length) { const maxP = Math.max(...cand.map(c => c.p)); res.best = cand.find(c => c.p >= maxP * 0.85) || cand[0]; res.firstGood = cand.find(c => c.p >= Math.max(0.15, maxP * 0.5)); }
  return res;
}
function pct(p) { return p == null ? "–" : p >= 0.995 ? ">99%" : p < 0.005 ? "<1%" : Math.round(p * 100) + "%"; }

/* ---------- Spots tab: shot list ---------- */
function shotsHtml() {
  let h = `<div class="sect shotlist"><h3>My shot list <button class="chip" id="addShot" style="float:right">+ Add a shot</button></h3>`;
  if (!SHOTS.length) return h + `<p class="muted">Add the specific images you want: a subject, the light, the conditions and the season. ShotSpots then tells you when each one next becomes possible and how likely it is.</p></div>`;
  h += SHOTS.map((sh, i) => { const s = byId[sh.spot], P = predictShot(sh); if (!s || !P) return "";
    const nx = P.next, be = P.firstGood || P.best;
    return `<div class="item shot"><b role="button" tabindex="0" data-spot="${s.id}">${esc(sh.subject || s.name)}</b><small class="muted">${esc(s.name)} · ${sh.light.map(k => KSHORT[k]).join("/")} · ${sh.cond.filter(c => c !== "any").join(" + ") || "any conditions"}${sh.species ? " · " + esc(sh.species) : ""}${sh.target ? " · " + esc(OBJN[sh.target]) + (sh.landmark ? " over " + esc(sh.landmark) : "") : ""}</small>
      <p>${nx ? `<b>${pct(nx.p)}</b> ${esc(wTitle(nx.w))} ${fmtT(GOLDK.has(nx.w.kind) ? nx.w.peak : nx.w.start)} <span class="muted">(conditions ${pct(nx.parts.cond)} ${nx.parts.condSrc}${sh.species ? `, ${esc(sh.species)} ${pct(nx.parts.species)}` : ""}${sh.target ? `, alignment ${nx.parts.target ? "yes" : "no"}` : ""})</span>` : `<span class="muted">Not possible in the next 40 hours.</span>`}
      ${be ? `<br>Next good chance: <b>${pct(be.p)}</b> ${fmtDate(be.t)} ${KNAME[be.kind] ? KNAME[be.kind].toLowerCase() : OBJN[be.kind] || ""} ${fmtT(be.t)} <span class="muted">(seasonal odds from 10-yr records${be.ev ? `, ${be.ev.fl} mm` : ""})</span>` : ""}</p>
      <button class="chip" data-delshot="${i}">Remove</button></div>`; }).join("");
  return h + `<p class="muted" style="font-size:13px">Odds multiply the condition, wildlife and alignment chances as if independent; check them against your logged outings in ⚙ › Forecast check.</p></div>`;
}
const _renderSpotsShots = renderSpots;
renderSpots = function () { _renderSpotsShots(); $("#v-spots").insertAdjacentHTML("beforeend", shotsHtml()); };   // below the list, so the filters stay on top

/* ---------- add-shot sheet ---------- */
function ensureSheet(id, title) {
  let el = document.getElementById(id); if (el) return el;
  el = document.createElement("div"); el.className = "sheet"; el.id = id; el.hidden = true; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true");
  el.innerHTML = `<div class="sheetbar"><b>${title}</b><button class="iconbtn" data-close="${id}" aria-label="Close">✕</button></div><div class="sheetbody"></div>`;
  document.body.appendChild(el); return el;
}
function chipGroup(name, opts, sel, multi) { return `<div class="chips" data-group-name="${name}" data-multi="${multi ? 1 : 0}">${opts.map(([v, l]) => `<button type="button" class="chip" data-opt="${v}" aria-pressed="${sel.includes(v)}">${l}</button>`).join("")}</div>`; }
function openAddShot(spotId) {
  const el = ensureSheet("shotSheet", "Add a shot"), s = spotId ? byId[spotId] : null;
  const opts = SPOTS.slice().sort((a, b) => a.name.localeCompare(b.name)).map(x => `<option value="${x.id}"${x.id === spotId ? " selected" : ""}>${esc(x.name)}</option>`).join("");
  el.querySelector(".sheetbody").innerHTML = `<form id="shotForm" class="stack">
    <label>Spot<select name="spot" id="shotSpot">${opts}</select></label>
    <label>Subject<input name="subject" placeholder="e.g. Heron in fog with backlit cottonwoods" required></label>
    <p class="label">Light</p>${chipGroup("light", SH_LIGHT, s ? (s.light === "sunset" ? ["sunset"] : ["sunrise"]) : ["sunrise"], true)}
    <p class="label">Conditions (all must happen)</p>${chipGroup("cond", SH_COND, ["any"], true)}
    <p class="label">Months</p>${chipGroup("months", "JFMAMJJASOND".split("").map((m, i) => [String(i + 1), m]), (s && s.months ? s.months : []).map(String), true)}
    <label>Wildlife (optional)<input name="species" id="shotSpecies" list="speciesList" placeholder="e.g. Great Blue Heron"><datalist id="speciesList"></datalist></label>
    <label>Sky alignment (optional)<select name="target">${SH_TARGET.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select></label>
    <label>Over landmark (optional)<select name="landmark"><option value="">Any</option>${["Mt. Hood", "Mt. Adams", "Mt. St. Helens", "Mt. Rainier", "Mt. Jefferson", "Beacon Rock", "Vista House (Crown Point)", "Rooster Rock", "Larch Mountain", "Angel's Rest", "Silver Star Mountain", "Downtown Portland towers", "I-205 Glenn Jackson Bridge", "Bridge of the Gods"].map(x => `<option>${esc(x)}</option>`).join("")}</select></label>
    <button class="btn primary wide" type="submit">Save shot</button></form>`;
  const fillSpecies = () => { const w = wildlifeFor($("#shotSpot").value); $("#speciesList").innerHTML = w ? w.species.map(x => `<option value="${esc(x.sp)}">`).join("") : ""; };
  feedGet("wildlife").then(fillSpecies); $("#shotSpot").addEventListener("change", fillSpecies);
  feedGet("planner"); el.hidden = false;
}
function readChips(form, name) { return [...form.querySelectorAll(`[data-group-name="${name}"] [aria-pressed="true"]`)].map(b => b.dataset.opt); }

/* ---------- outing log (verification) ---------- */
function predBundle(s, t) {
  const w = allWindows(s, 40).find(x => x.start <= t && x.end >= t) || allWindows(s, 40)[0]; const f = w ? fitFor(s, w) : null; const h = hrrrRow(s.id, t);
  const H = fd("hrrr"); const sp = {}; topSpecies(s.id, t, 6).forEach(x => sp[x.sp] = x.p);
  return { kind: w && w.kind, score: f ? f.n : null, p_clear: h ? h.p_clear : null, p_fog: h ? h.p_fog : null, p_color: h ? h.p_color : null,
    hrrr_run: H ? H.run : null, lead_h: H ? Math.round((t - new Date(H.run)) / 36e5) : null, p_species: sp, sqm_pred: typeof spotSqm === "function" ? +spotSqm(s).toFixed(2) : null };
}
function openOutcome(spotId) {
  const s = byId[spotId], el = ensureSheet("outSheet", "Log this outing"); const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  el.querySelector(".sheetbody").innerHTML = `<form id="outForm" class="stack" data-spot="${s.id}"><p><b>${esc(s.name)}</b></p>
    <label>When<input type="datetime-local" name="when" value="${local}"></label>
    <label>Keepers<input type="number" name="keepers" min="0" inputmode="numeric" value="0"></label>
    <p class="label">How good was it?</p>${chipGroup("rating", [["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]], [], false)}
    <p class="label">Sky</p>${chipGroup("sky", [["clear", "Clear"], ["partly", "Partly"], ["overcast", "Overcast"], ["rain", "Rain"]], [], false)}
    <p class="label">Fog</p>${chipGroup("fog", [["yes", "Yes"], ["no", "No"]], [], false)}
    <p class="label">Colour in the sky</p>${chipGroup("color", [["none", "None"], ["some", "Some"], ["strong", "Strong"]], [], false)}
    <label>Wildlife seen (comma-separated)<input name="species" placeholder="Great Blue Heron, Bald Eagle"></label>
    <label>eBird checklist ID (optional)<input name="ebird" placeholder="S123456789"></label>
    <label>Sky meter reading, mag/arcsec² (optional)<input name="sqm" type="number" step="0.01" inputmode="decimal"></label>
    <label>Notes<textarea name="notes" rows="2"></textarea></label>
    <button class="btn primary wide" type="submit">Save and send for checking</button>
    <p class="muted" style="font-size:13px">The app saves what it predicted for this time and place. The pipeline then checks your outing against GOES-18, the nearest airport station, same-day Flickr photos, your eBird checklist and your meter reading.</p></form>`;
  el.hidden = false;
}
let OUTQ = store.get("outq", []);
async function flushOutcomes() {
  const keep = [];
  for (const o of OUTQ) { try { const r = await fetch("/", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ "form-name": "outcome", ...o }).toString() }); if (!r.ok) throw 0; } catch (e) { keep.push(o); } }
  OUTQ = keep; store.set("outq", OUTQ); return keep.length;
}

/* ---------- events ---------- */
document.addEventListener("click", e => {
  const t = e.target.closest("#addShot,[data-delshot],[data-close],[data-opt],#outcomeBtn,[data-addshot]"); if (!t) return;
  if (t.id === "addShot") return openAddShot();
  if (t.dataset.addshot) return openAddShot(t.dataset.addshot);
  if (t.dataset.delshot != null) { SHOTS.splice(+t.dataset.delshot, 1); store.set("shots", SHOTS); return renderSpots(); }
  if (t.dataset.close) { document.getElementById(t.dataset.close).hidden = true; return; }
  if (t.id === "outcomeBtn") return openOutcome(t.dataset.id);
  if (t.dataset.opt != null) { const g = t.closest("[data-group-name]"); if (g.dataset.multi !== "1") g.querySelectorAll(".chip").forEach(b => b.setAttribute("aria-pressed", "false"));
    t.setAttribute("aria-pressed", t.getAttribute("aria-pressed") === "true" && g.dataset.multi === "1" ? "false" : "true");
    if (g.dataset.groupName === "cond") { const any = g.querySelector('[data-opt="any"]'); if (t.dataset.opt === "any") g.querySelectorAll(".chip").forEach(b => b !== any && b.setAttribute("aria-pressed", "false")); else any.setAttribute("aria-pressed", "false"); } }
});
document.addEventListener("submit", async e => {
  if (e.target.id === "shotForm") { e.preventDefault(); const f = e.target, fdx = new FormData(f);
    const sh = { spot: fdx.get("spot"), subject: fdx.get("subject").trim(), light: readChips(f, "light"), cond: readChips(f, "cond"), months: readChips(f, "months").map(Number),
      species: (fdx.get("species") || "").trim() || null, target: fdx.get("target") || null, landmark: fdx.get("landmark") || null };
    if (!sh.light.length) sh.light = ["sunrise", "sunset"]; if (!sh.cond.length) sh.cond = ["any"];
    SHOTS.push(sh); store.set("shots", SHOTS); $("#shotSheet").hidden = true; toast("Shot saved"); if (UI.view === "spots") renderSpots(); return; }
  if (e.target.id === "outForm") { e.preventDefault(); const f = e.target, fdx = new FormData(f), s = byId[f.dataset.spot]; const t = new Date(fdx.get("when"));
    const o = { spot: s.id, t: String(t.getTime()), kind: "", rating: readChips(f, "rating")[0] || "", keepers: fdx.get("keepers") || "0", sky: readChips(f, "sky")[0] || "", fog: readChips(f, "fog")[0] || "",
      color: readChips(f, "color")[0] || "", species: fdx.get("species") || "", ebird: fdx.get("ebird") || "", sqm: fdx.get("sqm") || "", notes: fdx.get("notes") || "" };
    const pred = predBundle(s, t); o.kind = pred.kind || ""; o.pred = JSON.stringify(pred);
    LOG.unshift({ id: s.id, t: t.getTime(), c: `${o.keepers} keepers${o.rating ? ", " + o.rating + "/5" : ""}` }); store.set("log", LOG.slice(0, 300));
    OUTQ.push(o); store.set("outq", OUTQ); const left = await flushOutcomes(); $("#outSheet").hidden = true; toast(left ? "Saved; will send when online" : "Logged and sent for checking"); }
});
window.addEventListener("online", flushOutcomes);
if (OUTQ.length) flushOutcomes();
