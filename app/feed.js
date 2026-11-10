/* ShotSpots feed: reads the data the GitHub Actions pipeline publishes at /feed/ and folds it into scoring and the UI.
   Every number shown from the feed carries its provenance (MEASURED / MODELED / ESTIMATED). */
"use strict";
const FEED = { m: null, d: {}, loading: {} };
const EAGER = ["spots_extra", "research_status", "alerts", "goes", "hrrr", "light", "climo", "flow", "sounding", "sentinel", "darksky", "access", "calibration", "phenology", "snow", "access_rules", "weekend", "trails", "reports", "photos", "obs", "birds", "fogabove", "photostats", "verify_obs", "nwsfog", "goes_grid", "darkgrid"];
const LAZY = ["planner", "wildlife", "originality", "report", "verify_positions", "solves", "outcomes_public"];
async function feedGet(name) {
  if (FEED.d[name]) return FEED.d[name];
  if (FEED.loading[name]) return FEED.loading[name];
  FEED.loading[name] = fetch(`feed/${name}.json`, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).catch(() => null).then(j => { if (j) FEED.d[name] = j; delete FEED.loading[name]; return j; });
  return FEED.loading[name];
}
async function loadFeed() {
  FEED.m = await fetch("feed/manifest.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!FEED.m) return false;
  for (const k of [...EAGER, ...LAZY]) delete FEED.d[k];
  await Promise.all(EAGER.filter(n => FEED.m.files.includes(n + ".json")).map(feedGet));
  return true;
}
const fd = n => FEED.d[n] || null;
const ST = n => (FEED.m && FEED.m.status && FEED.m.status[n]) || null;
const KIND_TAG = { MEASURED: "measured", MODELED: "modeled", ESTIMATED: "estimate" };
function tag(src) { const s = ST(src); return s ? `<span class="prov p-${(s.kind || "").toLowerCase()}" title="${esc(s.note || "")}">${KIND_TAG[s.kind] || s.kind}</span>` : ""; }
const minToDate = m => new Date(m * 60000);
const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");

/* common names as birders use them in the US (the global taxonomy names some species differently) */
const SPN = { "Hen Harrier": "Northern Harrier", "Great Blue/Cocoi Heron": "Great Blue Heron", "Common Gull": "Short-billed Gull", "Barn Swallow": "Barn Swallow", "Mew Gull": "Short-billed Gull", "Common Merganser": "Common Merganser", "Eurasian Wigeon": "Eurasian Wigeon", "Rock Dove": "Rock Pigeon", "Northern Goshawk": "American Goshawk" };
function dayWordYMD(d) { if (!d) return ""; const t = laYMD(new Date()), y = laYMD(new Date(Date.now() - 864e5)); if (d === t) return "today"; if (d === y) return "yesterday"; const x = new Date(d + "T12:00:00"); return x.toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
function spName(n) { return SPN[n] || n; }
/* ---------- lookups ---------- */
function hrrrRow(id, t) {
  const h = fd("hrrr"); if (!h || !h.spots[id]) return null; const tm = t.getTime() / 60000; let bi = -1, bd = 1e9;
  h.t.forEach((x, i) => { const d = Math.abs(x - tm); if (d < bd) { bd = d; bi = i; } });
  if (bi < 0 || bd > 100) return null; const row = h.spots[id][bi]; const o = {}; h.cols.forEach((c, i) => o[c] = row[i]); o.dt = bd; return o;
}
function lightDay(id, t) {
  const L = fd("light"); if (!L || !L.spots[id]) return null; const ymd = laYMD(t); const i = L.days.indexOf(ymd); return i >= 0 ? L.spots[id][i] : null;
}
function litDuring(id, w) {
  const d = lightDay(id, w.peak); if (!d) return null; const a = w.start.getTime() / 60000, b = w.end.getTime() / 60000;
  return d.lit.some(([s, e]) => e >= a && s <= b);
}
function spotElev(id) { const L = fd("light"); return L && L.elev ? L.elev[id] : null; }
function soundingTop() { const s = fd("sounding"); const o = s && s.obs && s.obs[0]; return o && o.inv_c >= 2 ? o : null; }
const __climoSt = {};
function climoFor(s, t) {
  const c = fd("climo"); if (!c) return null; let best = __climoSt[s.id], bd = 1e9;
  if (best === undefined) { for (const [k, v] of Object.entries(c.stations)) { const d = km(s, v); if (d < bd) { bd = d; best = [k, v]; } } if (bd > 80) best = null; __climoSt[s.id] = best; }
  if (!best) return null; const mo = +laYMD(t).slice(5, 7) - 1, hr = +t.toLocaleString("en-US", { timeZone: TZ, hour: "numeric", hourCycle: "h23" });
  const v = best[1]; return { station: best[0], fog: v.fog[mo][hr], clear: v.clear12k[mo][hr], lowovc: v.lowovc[mo][hr] };
}
function weekIdx(t) { const d = new Date(laYMD(t) + "T12:00:00"); const start = new Date(d.getFullYear(), 0, 1); return Math.min(51, Math.floor((d - start) / 864e5 / 7)); }
function wildlifeFor(id) { const w = fd("wildlife"); return w && w.spots ? w.spots[id] : null; }
function topSpecies(id, t, n) {
  const w = wildlifeFor(id); if (!w) return []; const wk = weekIdx(t), hb = Math.floor(+t.toLocaleString("en-US", { timeZone: TZ, hour: "numeric", hourCycle: "h23" }) / 3);
  return w.species.map(x => { const tot = x.hr ? x.hr.reduce((a, b) => a + b, 0) : 0; const hf = x.hr && tot ? x.hr[hb] / tot * 8 : 1;
    return { sp: x.sp, p: x.wk[wk], best: x.hr ? x.hr.indexOf(Math.max(...x.hr)) * 3 : null, hf }; }).filter(x => x.p > 0).sort((a, b) => b.p - a.p).slice(0, n || 6);
}

/* ---------- scoring hooks ---------- */
const _fitFeed = fitFor;
fitFor = function (s, w) {
  const f = _fitFeed(s, w); if (!f) return f; let n = f.n; const why = f.why.slice();
  const dk = fd("darksky"); if (w.kind === "night" && dk && dk.spots[s.id] && f.sqm != null) { /* sky.js already scored darkness; VIIRS value replaces the model below */ }
  const hr = hrrrRow(s.id, w.peak);
  if (hr && w.kind !== "night") {
    if (GOLDK.has(w.kind) && hr.p_color != null && s.cats.some(c => SKY.includes(c))) { const adj = (hr.p_color - 40) * 0.15; n += adj; why.push(`${hr.p_color}% chance of colour (HRRR)`); }
    if (hr.p_fog >= 40 && (s.cats.includes("waterfall") || s.cats.includes("fallcolor") || LIFE.some(c => s.cats.includes(c)))) why.push(`${hr.p_fog}% chance of fog here`);
  }
  // above the fog: low spots fogged + this spot above the measured inversion top
  const top = soundingTop(), el = spotElev(s.id);
  if (top && el != null && AMK.has(w.kind) && FOG_ABOVE.includes(s.id)) {
    const low = hrrrRow("steigerwald", w.peak) || hrrrRow("washougal-waterfront", w.peak);
    if (low && low.p_fog >= 40) { if (el > top.top_m + 50) { n = Math.max(n, 85 * (KCAP[w.kind] || 1)); why.unshift(`${low.p_fog}% fog below; you're at ${Math.round(el)} m, inversion top ~${Math.round(top.top_m)} m`); } else { n -= 20; why.unshift(`likely inside the fog (inversion top ~${Math.round(top.top_m)} m)`); } }
  }
  // terrain: is the scene actually in sun during this golden window?
  if (GOLDK.has(w.kind)) { const lit = litDuring(s.id, w); const d = lightDay(s.id, w.peak);
    if (lit === false && s.cats.some(c => ["fallcolor", "mountain", "reflection", "wildflowers", "geology"].includes(c))) { n -= 10; why.push(`terrain blocks the ${w.kind === "sunrise" ? "rising" : "setting"} sun here`); }
    else if (d && w.kind === "sunrise" && d.tr && d.or && d.tr - d.or >= 15) why.push(`sun clears the ridge at ${fmtT(minToDate(d.tr))}`);
    else if (d && w.kind === "sunset" && d.ts && d.os && d.os - d.ts >= 15) why.push(`sun drops behind terrain at ${fmtT(minToDate(d.ts))}`); }
  // satellite colour stage
  const se = fd("sentinel"), sv = se && se.spots[s.id];
  if (sv && sv.stage && s.cats.includes("fallcolor") && !NIGHT.includes(w.kind)) { const adj = { "near peak": 10, turning: 4, green: -8, "past (leaves dropping)": -12 }[sv.stage] || 0; n += adj; why.push(`satellite: ${sv.stage} (${sv.date.slice(5)})`); }
  // wildlife encounter rates
  if (LIFE.some(c => s.cats.includes(c))) { const W = wildlifeFor(s.id), ts = topSpecies(s.id, w.peak, 3);
    if (ts.length && W.kind.startsWith("eBird")) { const p = ts[0].p; n += Math.min(10, (p - 30) / 6); why.push(`${ts[0].sp} on ${p}% of checklists this week`); }
    else if (ts.length && ts[0].p >= 15) why.push(`lots of ${ts[0].sp} reported here this week`); }
  // access
  const ac = fd("access"), av = ac && ac.spots[s.id]; if (av && av.alerts && av.alerts.length) why.push("forest alert: check access");
  return { ...f, n: Math.round(clamp(n, 0, 100)), why };
};
if (typeof spotSqm === "function") { const _sq = spotSqm; spotSqm = function (s) { const dk = fd("darksky"); return dk && dk.spots[s.id] && dk.spots[s.id].sqm ? dk.spots[s.id].sqm : _sq(s); }; }

/* ---------- spot sheet ---------- */
const CMP8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
function roseSvg(g) {
  const max = Math.max(...g, 1); let p = "";
  g.forEach((v, i) => { const a = (i * 22.5 - 90) * D2R, a0 = a - 0.19, a1 = a + 0.19, rr = 8 + 30 * v / max;
    p += `<path d="M40 40 L${40 + rr * Math.cos(a0)} ${40 + rr * Math.sin(a0)} A${rr} ${rr} 0 0 1 ${40 + rr * Math.cos(a1)} ${40 + rr * Math.sin(a1)} Z" fill="var(--gold)" opacity="${0.35 + 0.65 * v / max}"/>`; });
  return `<svg viewBox="0 0 80 80" width="88" height="88" aria-label="Sky glow by direction">${p}<text x="40" y="9" text-anchor="middle" class="lbl">N</text><text x="76" y="43" text-anchor="end" class="lbl">E</text><text x="40" y="78" text-anchor="middle" class="lbl">S</text><text x="4" y="43" class="lbl">W</text></svg>`;
}
const FIELDCRAFT = {
  birds: "Approach on a slow diagonal, never straight at the bird, and stop when it looks up. Car windows make great blinds at refuges with auto tours. Never flush roosting or nesting birds for a flight shot.",
  wildlife: "Give large mammals at least 25 yards (100 for elk in rut and bears). Use the 70–300 and the 1.4x crop instead of closing distance. Stay on trails and never bait or call.",
  heron: "Herons nest in colonies from February to July: shoot only from the designated viewing areas.",
};
async function sheetFeed(s) {
  if (!FEED.m) return; await Promise.all(["wildlife", "planner", "originality"].map(feedGet));
  const body = $("#sheetBody"); if (!body || body.querySelector(".feedbox")) return; let h = "";
  const d = lightDay(s.id, new Date()), d2 = lightDay(s.id, new Date(Date.now() + 864e5)), el = spotElev(s.id);
  if (d) {
    const lit = d.lit.map(([a, b]) => `${fmtT(minToDate(a))}–${fmtT(minToDate(b))}`).join(", ");
    h += `<h3>Light here today ${tag("light")}</h3><div class="kv">
      <span>Sunrise</span><span>${d.or ? fmtT(minToDate(d.or)) : "–"} open horizon${d.tr && d.tr !== d.or ? `; over terrain ${fmtT(minToDate(d.tr))}` : ""}</span>
      <span>Sunset</span><span>${d.os ? fmtT(minToDate(d.os)) : "–"} open horizon${d.ts && d.ts !== d.os ? `; behind terrain ${fmtT(minToDate(d.ts))}` : ""}</span>
      <span>Direct sun</span><span>${lit || "none today (terrain shade)"}</span>
      ${d.saz[0] != null ? `<span>Sun direction</span><span>rises ${cmp(d.saz[0])} (${Math.round(d.saz[0])}°), sets ${cmp(d.saz[1])} (${Math.round(d.saz[1])}°)</span>` : ""}
      ${d.mr || d.ms ? `<span>Moon</span><span>${d.mi}% lit${d.mr ? ", rises over terrain " + fmtT(minToDate(d.mr)) : ""}${d.ms ? ", sets " + fmtT(minToDate(d.ms)) : ""}</span>` : ""}
      ${d.core && d.core.length ? `<span>Milky Way core</span><span>above terrain in darkness ${d.core.map(([a, b]) => fmtT(minToDate(a)) + "–" + fmtT(minToDate(b))).join(", ")}</span>` : ""}
      ${el != null ? `<span>Elevation</span><span>${Math.round(el)} m (${Math.round(el * 3.281)} ft)</span>` : ""}</div>`;
    const pv = (D.PEAKVIS || {})[(D.PEAK_OF || {})[s.id] || s.id], L = fd("light");
    if (pv && L && L.alpen) { const i = L.days.indexOf(laYMD(new Date())); const rows = pv.filter(r => r[3] >= 0.3).map(r => { const nm = r[0] === "Hood" ? "Mt. Hood" : r[0] === "Adams" ? "Mt. Adams" : r[0] === "St. Helens" ? "Mt. St. Helens" : "Mt. " + r[0]; const a = L.alpen[nm] && L.alpen[nm][i]; return a ? `${nm}: morning glow ${a[0] ? fmtT(minToDate(a[0])) + "–" + fmtT(minToDate(a[1])) : "–"}, evening glow ${a[2] ? fmtT(minToDate(a[2])) + "–" + fmtT(minToDate(a[3])) : "–"}` : null; }).filter(Boolean);
      if (rows.length) h += `<p class="muted" style="font-size:14px;margin-top:4px">Alpenglow (sun within 2° of the summit's horizon): ${rows.join("; ")}.</p>`; }
    h += `<p class="muted" style="font-size:13px">From USGS 3DEP bare-earth terrain: trees and buildings can delay sun further.</p>`;
  }
  const hr = hrrrRow(s.id, new Date(Date.now() + 36e5));
  const H = fd("hrrr");
  if (H && H.spots[s.id]) { const now = Date.now() / 60000; const rows = H.t.map((t, i) => [t, H.spots[s.id][i]]).filter(([t]) => t >= now - 30).slice(0, 18);
    h += `<h3>Odds next 18 hours ${tag("hrrr")}</h3><div class="hours odds">${rows.map(([t, r]) => `<div><small>${minToDate(t).toLocaleTimeString("en-US", { timeZone: TZ, hour: "numeric" }).replace(" ", "").toLowerCase()}</small><span title="fog">🌫${r[0] ?? "–"}</span><span title="clear">✦${r[2] ?? "–"}</span><span title="colour">🎨${r[3] ?? "–"}</span>${r[6] >= 12 ? `<span title="smoke µg/m³">🔥${Math.round(r[6])}</span>` : r[7] >= 0.15 ? `<span title="smoke haze (aerosol optical depth)">haze ${r[7].toFixed(1)}</span>` : ""}</div>`).join("")}</div>
      <p class="muted" style="font-size:13px">% chance of fog, clear sky and sunset/sunrise colour from HRRR (${esc(H.method)}). Snow level ${hr && hr.snow_m ? Math.round(hr.snow_m) + " m" : "–"}${hr && hr.inv_c != null ? `; ${hr.inv_c > 0 ? "inversion " + hr.inv_c.toFixed(1) + " °C" : "no inversion"}` : ""}.</p>`; }
  const g = fd("goes"), gv = g && g.spots[s.id];
  if (gv) h += `<p><b>Right now from GOES-18</b> ${tag("goes")}: ${gv[0]}% cloud, ${gv[1]}% low cloud/fog${gv[2] ? `, tops ~${gv[2]} m` : ""} <span class="muted">(${fmtT(new Date(g.obs))})</span></p>`;
  const fl = fd("flow"), gid = (D.GAUGES || {})[s.id], fv = fl && gid && fl.gauges[gid];
  if (fv && fv.pct != null) h += `<p><b>River</b> ${tag("flow")}: ${fv.cfs ? Math.round(fv.cfs).toLocaleString() + " cfs, " : ""}${typeof fv.pct === "number" ? ordinal(fv.pct) : fv.pct} percentile for this date${fv.median_today ? ` (median ${Math.round(fv.median_today).toLocaleString()} cfs)` : ""}.</p>`;
  const se = fd("sentinel"), sv = se && se.spots[s.id];
  if (sv && (sv.stage || sv.snow >= 10)) h += `<p><b>Satellite (${sv.date})</b> ${tag("sentinel")}: ${sv.stage ? `foliage ${sv.stage}` : ""}${sv.snow >= 10 ? `${sv.stage ? "; " : ""}${sv.snow}% snow cover` : ""}.</p>`;
  // wildlife
  const wl = wildlifeFor(s.id);
  if (wl) { const ts = topSpecies(s.id, new Date(), 8); const wkind = wl.kind.startsWith("eBird") ? "eBird checklists within 2 km (effort-corrected)" : "share of GBIF/iNaturalist records (presence-only, not effort-corrected)";
    const sp = sunPos(new Date(), s.lat, s.lon); const w0 = allWindows(s, 40).find(x => GOLDK.has(x.kind) || x.kind === "morning"), spw = w0 ? sunPos(w0.peak, s.lat, s.lon) : sp;
    const hr = h0 => { const d = new Date(); d.setHours(h0, 0, 0, 0); return fmtT(d).replace(":00", ""); };
    h += `<h3>Wildlife here this week ${tag("wildlife")}</h3>${ts.length ? `<p class="muted" style="font-size:14px;margin-bottom:4px">Most-reported species, as a share of all sightings here:</p><ul class="plain">${ts.map(x => `<li><b>${esc(spName(x.sp))}</b> ${x.p}%${x.best != null ? ` · mostly seen ${hr(x.best)}–${hr(x.best + 3)}` : ""}</li>`).join("")}</ul>` : `<p class="muted">Few sightings logged here for this time of year.</p>`}
      <p class="muted" style="font-size:13px">${wkind}.</p>
      ${w0 ? `<p><b>Where to stand:</b> ${esc(wTitle(w0))} the sun comes from the ${cmp(spw.az)}. Keep it at your back (shoot toward the ${cmp((spw.az + 180) % 360)}) for evenly lit animals, shoot toward it for glowing rim-lit silhouettes, or across it (toward the ${cmp((spw.az + 90) % 360)} or ${cmp((spw.az + 270) % 360)}) for side light that shows texture.</p>` : ""}
      <p class="muted" style="font-size:14px">${s.id === "maddax-heronry" ? FIELDCRAFT.heron : s.cats.includes("birds") ? FIELDCRAFT.birds : FIELDCRAFT.wildlife}</p>`; }
  const wlf = fd("wildlife"); if (wlf && wlf.fish && /bonneville|oxbow/.test(s.id) && wlf.fish.last14 && wlf.fish.last14.length) { const last = wlf.fish.last14[wlf.fish.last14.length - 1];
    h += `<p><b>Bonneville ladder, latest day</b> (DART): ${Object.entries(last).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(", ")}.</p>`; }
  // dark sky
  const dk = fd("darksky"), dv = dk && dk.spots[s.id];
  if (dv && (nightEligible(s) || s.cats.includes("city"))) h += `<h3>Sky darkness ${tag("darksky")}</h3><div style="display:flex;gap:12px;align-items:center">${roseSvg(dv.glow16)}<p style="margin:0">SQM ≈ <b>${dv.sqm}</b> (${bortleLabel(dv.sqm)}). Glow is worst toward the ${cmp(dv.brightest)}; shoot toward the ${cmp(dv.darkest)} for the darkest sky. <span class="muted">VIIRS satellite radiance, calibrated on ${dk.calibration.n} readings (${esc(dk.calibration.source)}, ±${dk.calibration.rmse_mag} mag).</span></p></div>`;
  // planner
  const pl = await feedGet("planner"); const ev = pl && pl.events[s.id] ? pl.events[s.id].filter(e => e.t * 60000 > Date.now()).slice(0, 6) : [];
  if (ev.length) h += `<h3>Planned alignments ${tag("planner")}</h3><ul class="plain">${ev.map(e => `<li>${fmtDate(minToDate(e.t))} ${fmtT(minToDate(e.t))}: ${esc(OBJN[e.obj] || e.obj)} ${e.obj === "sun" || e.obj === "moon" ? (e.alt > e.lalt + 0.4 ? "just above" : "on") : "above"} ${esc(e.lm)}${e.illum ? ` (${e.illum}% moon)` : ""} · about ${e.fl} mm${e.fl > 50 ? " (70–300)" : e.fl > 27 ? " (16–50)" : " (16–50 wide)"}</li>`).join("")}</ul>`;
  // originality
  const og = await feedGet("originality"), ov = og && og.spots[s.id];
  if (ov && ov.share) h += `<h3>How others shoot it ${tag("originality")}</h3><p>${ov.n} Flickr photos within 400 m: ${ov.share.golden}% golden hour, ${ov.share.blue}% blue hour, ${ov.share.night}% night, ${ov.share.day}% daytime. ${ov.top_share >= 25 ? `${ov.top_share}% were taken from one 40 m spot (<a href="https://maps.apple.com/?ll=${ov.stand[0].lat},${ov.stand[0].lon}&q=Most%20photographed%20spot" target="_blank" rel="noopener">here</a>).` : ""}</p>
    ${ov.under.length || ov.quiet_months.length ? `<p><b>Under-photographed:</b> ${[ov.under.length ? ov.under.map(k => ({ blue: "blue hour", night: "night", golden: "golden hour" }[k])).join(", ") : "", ov.quiet_months.length ? "in-season months " + ov.quiet_months.map(m => "JFMAMJJASOND"[m - 1]).join(" ") : ""].filter(Boolean).join("; ")}.</p>` : ""}`;
  // access
  const ac = fd("access"), av = ac && ac.spots[s.id];
  if (av) h += `<h3>Access ${tag("access")}</h3><p>${av.land && av.land.manager ? `${esc(av.land.unit || "")} (${esc(av.land.manager)})${av.land.access ? ", public access: " + esc(av.land.access) : ""}.` : av.land && !av.land.error ? "" : ""}${!av.land ? "<b>Not inside a mapped public-land boundary</b> (PAD-US, within 150 m). It may be a roadside pull-off or private land: check where to park." : ""}</p>${av.alerts ? `<ul class="plain">${av.alerts.map(a => `<li><a href="${a.url}" target="_blank" rel="noopener">${esc(a.title)}</a></li>`).join("")}</ul>` : ""}`;
  if (!h) return;
  const box = document.createElement("div"); box.className = "live feedbox"; box.innerHTML = h;
  const anchor = body.querySelector("details"); anchor ? body.insertBefore(box, anchor) : body.appendChild(box);
}
const OBJN = { sun: "Sun", moon: "Moon", mwcore: "Milky Way core", orion: "Orion", pleiades: "Pleiades", cygnus: "Cygnus Milky Way" };
const _openFeed = openSpot;
openSpot = function (id) { _openFeed(id); const s = byId[id]; if (!s) return; const b = $("#shotBtn"); if (b) { b.id = "outcomeBtn"; b.textContent = "📷 Log outing"; } sheetFeed(s); };

/* ---------- Now: GOES card + map overlay ---------- */
/* airport weather reports near you: what the ground sees (visibility, fog or mist, cloud base) */
function obsHtml() {
  const o = fd("obs"); if (!o || !o.stations) return "";
  const st = o.stations.filter(x => x.lat && km(LOC, x) < 70 && Date.now() - new Date(x.t) < 3 * 36e5).sort((a, b) => km(LOC, a) - km(LOC, b)).slice(0, 4); if (!st.length) return "";
  const ft = f => METRIC() ? Math.round(f * 0.3048 / 10) * 10 + " m" : f.toLocaleString() + " ft";
  const WX = { RA: "rain", DZ: "drizzle", SN: "snow", FG: "fog", BR: "mist", HZ: "haze", FU: "smoke", TS: "thunderstorm" };
  const line = x => { const w = [...new Set((x.wx.match(/FG|BR|RA|DZ|SN|HZ|FU|TS/g) || []).map(k => WX[k]))].join(", ");
    const vis = x.vis_mi == null ? "" : METRIC() ? `${Math.round(x.vis_mi * 1.609)} km visibility` : `${x.vis_mi >= 10 ? "10+" : x.vis_mi} mi visibility`;
    return `<li><b>${esc(x.name.replace(/ (Intl|International|Regional|Municipal|Airport|Arpt|Arfld|Arpk|Field|Fld|Muni).*$/i, ""))}</b>: ${[x.fog ? "<b>fog</b>" : "", vis, w && !x.fog ? w : "", x.base_ft != null ? `cloud base ${ft(x.base_ft)}` : "no low ceiling"].filter(Boolean).join(", ")}</li>`; };
  const low = st.filter(x => x.base_ft != null && x.base_ft <= 1500).length;
  return `<p class="label" style="margin-top:8px">Ground reports (airport weather stations)</p><ul class="plain" style="font-size:14.5px">${st.map(line).join("")}</ul>${st.some(x => x.fog) ? `<p style="font-size:14.5px">Fog reported on the ground.</p>` : low ? `<p style="font-size:14.5px">Cloud base is low, so hills and viewpoints above about ${ft(Math.min(...st.filter(x => x.base_ft != null).map(x => x.base_ft)))} are likely in the cloud.</p>` : ""}`;
}
const _specFeed = specialsHtml;
specialsHtml = function () {
  let base = _specFeed(); const g = fd("goes"); if (!g || (typeof outsideCoverage === "function" && outsideCoverage())) return base;
  const near = SPOTS.filter(s => g.spots[s.id] && km(LOC, s) < 60);
  const fogged = near.filter(s => g.spots[s.id][1] >= 50), clearAbove = near.filter(s => FOG_ABOVE.includes(s.id) && g.spots[s.id][0] <= 30);
  const ageMin = Math.round((Date.now() - new Date(g.obs)) / 60000);
  // a deck of higher cloud (tops above ~3 km) over most spots hides anything lower from the satellite
  const blind = near.filter(s => g.spots[s.id][0] >= 90 && g.spots[s.id][1] < 50 && g.spots[s.id][2] > 3000), blindMost = near.length && blind.length / near.length >= 0.6;
  const sat = fogged.length ? `Fog or low cloud over ${fogged.length} nearby spots${fogged.length <= 4 ? ": " + fogged.map(s => esc(s.name.split("(")[0])).join(", ") : ""}. ${clearAbove.length ? `Clear above it at ${clearAbove.slice(0, 3).map(s => esc(s.name.split("(")[0].replace("Scout pick: ", ""))).join(", ")}.` : ""}`
    : blindMost ? `Thick higher cloud overhead (tops around ${Math.round(blind.reduce((a, s) => a + g.spots[s.id][2], 0) / blind.length / 1000)} km), so the satellite can't see whether there's fog or low cloud underneath. The ground reports below can.`
    : "No fog or low cloud near you. ";
  const item = `<div class="item"><b>🛰 Right now (GOES-18, ${ageMin} min ago) ${tag("goes")}</b><p>${sat} The Map tab shows the satellite fog layer.</p>${obsHtml()}</div>`;
  const bd = fd("birds"), bn = bd && km(LOC, { lat: 45.6, lon: -122.3 }) < 120 ? (bd.notables || []).filter(n => n.lat == null || !tooFar({ id: "_b", lat: n.lat, lon: n.lon })).slice(0, 5) : [];
  const birdItem = bn.length ? `<div class="item"><b>🐦 Notable birds nearby (last 4 days)</b><ul class="plain birdlist">${bn.map(n => `<li>${n.photo ? `<img src="${n.photo}" alt="" loading="lazy" width="44" height="44">` : ""}<span><a href="${n.url}" target="_blank" rel="noopener"><b>${n.target ? "🎯 " : ""}${esc(n.species)}</b></a> · ${esc((n.place || "").replace(/\s*\([-\d.,\s]+\)\s*$/, "").replace(/,? US-[A-Z]{2}\b/, "").replace(/, (OR|WA), US$/, ""))} · ${esc(dayWordYMD(n.date))}<br><small>${esc(n.why.replace(/^./, c => c.toUpperCase()))}${n.src === "eBird" ? "" : ` (${esc(n.src)})`}</small></span></li>`).join("")}</ul></div>` : "";
  // actionable things first (alignments, events, ideas), then birds, then the satellite and airport details
  if (!base) return `<div class="sect"><h3>Also worth knowing</h3>${birdItem}${item}</div>`;
  const cut = base.lastIndexOf("</div>");
  return base.slice(0, cut) + birdItem + `<details class="item satdetails"><summary><b>🛰 Fog and cloud right now</b> <span class="muted">${esc(item.includes("Fog or low cloud over") ? "fog reported near you" : item.includes("can't see") ? "high cloud hides the view" : "no fog near you")}</span></summary>${item}</details>` + base.slice(cut);
};
let GOES_LAYER = null;
const _renderMapFeed = renderMap;
renderMap = function () { _renderMapFeed(); const g = fd("goes"); if (!g || !window.L || !MAP) return; if (GOES_LAYER) GOES_LAYER.remove();
  const b = g.overlay.bbox; GOES_LAYER = L.imageOverlay(`feed/${g.overlay.png}?t=${encodeURIComponent(g.obs)}`, [[b[1], b[0]], [b[3], b[2]]], { opacity: 0.75 }).addTo(MAP);
  $("#mapLegend").innerHTML += `<br>White: fog/low cloud now (GOES-18, ${fmtT(new Date(g.obs))})`; };

/* ---------- settings: feed status + forecast check ---------- */
const _renderSettingsFeed = renderSettings;
renderSettings = async function () {
  _renderSettingsFeed(); if (!FEED.m) { $("#setBody").insertAdjacentHTML("afterbegin", `<div class="pipebox"><p class="muted">Pipeline feed not published yet.</p></div>`); return; }
  const st = FEED.m.status || {}, age = t => { const m = Math.round((Date.now() - new Date(t)) / 60000); return m < 120 ? m + " min" : m < 2880 ? Math.round(m / 60) + " h" : Math.round(m / 1440) + " d"; };
  let h = `<p class="label">Pipeline (GitHub Actions)</p><ul class="plain status">${Object.entries(st).map(([k, v]) => `<li class="${v.ok ? "ok" : "bad"}">${v.ok ? "✓" : "✗"} ${esc(k)} <span class="prov p-${(v.kind || "").toLowerCase()}">${KIND_TAG[v.kind] || ""}</span> <span class="muted">${age(v.at)} ago</span><br><small class="muted">${esc(v.note || "")}</small></li>`).join("")}</ul>`;
  const rep = await feedGet("report"), vp = await feedGet("verify_positions"), sol = await feedGet("solves");
  h += `<p class="label">Forecast check</p>`;
  if (rep) { h += `<p>${rep.outings} outings logged.</p><ul class="plain">${Object.entries(rep.events || {}).filter(([, v]) => v).map(([k, v]) => `<li><b>${esc(k)}</b>: Brier ${v.brier}, skill vs climatology ${v.skill_vs_climatology} (n=${v.n})</li>`).join("") || "<li>Not enough outings yet. Log each one with 📷 Log outing.</li>"}</ul>${Object.values(rep.events || {}).some(v => v) ? `<img src="feed/reliability.png?t=${Date.now()}" alt="Reliability chart" style="width:100%;max-width:360px">` : ""}${rep.sqm && rep.sqm.n ? `<p>SQM: model bias ${rep.sqm.bias} mag, RMSE ${rep.sqm.rmse} (n=${rep.sqm.n}).</p>` : ""}`; }
  if (vp) h += `<p><b>Sun/moon/planet positions vs JPL Horizons:</b> ${Object.entries(vp.bodies).map(([b, v]) => v.app_max_arcmin != null ? `${b} app ≤${v.app_max_arcmin}′, pipeline ≤${v.pipeline_max_arcmin}′` : `${b}: ${v.error ? "error" : "–"}`).join("; ")}.${vp.usno_vs_app_minutes && !vp.usno_vs_app_minutes.error ? ` Rise/set vs USNO: ${Object.entries(vp.usno_vs_app_minutes).map(([k, v]) => `${k} ${v >= 0 ? "+" : ""}${v} min`).join(", ")}.` : ""}</p>`;
  if (sol && sol.rows.length) h += `<p><b>Plate-solved frames:</b></p><ul class="plain">${sol.rows.slice(0, 5).map(x => `<li>${esc(x.file)}: ${x.solved ? `centre az ${x.center_az ?? "?"}°, alt ${x.center_alt ?? "?"}°${x.mwcore_pred ? `; Milky Way core predicted az ${x.mwcore_pred.az}°, alt ${x.mwcore_pred.alt}° (${x.mwcore_pred.in_frame ? "in frame ✓" : "outside frame"})` : ""}` : "not solved"}</li>`).join("")}</ul>`;
  h += `<p class="muted" style="font-size:13px">Drop night photos into the repo's inbox/frames folder (GitHub app → Add file → Upload) to have them plate-solved. Start the file name with the spot id if the photo has no GPS.</p>`;
  $("#setBody").insertAdjacentHTML("afterbegin", `<div class="pipebox">${h}</div>`);
};

/* ---------- boot ---------- */
loadFeed().then(ok => { if (ok) { render(); Promise.all(["wildlife", "planner"].map(feedGet)).then(render); } });
document.addEventListener("visibilitychange", () => { if (!document.hidden && FEED.m && Date.now() - new Date(FEED.m.gen) > 20 * 60000) loadFeed().then(ok => ok && render()); });
