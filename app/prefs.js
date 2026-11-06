/* Settings → Your setup: starting point, how you travel and how far, units.
   The travel limit drops spots that are too far from Plan and the weekend picks, greys them on the map,
   and hides them (with a "show" link) on the Spots list. */
"use strict";
let SETHOME = false;
const DRIVE_OPTS = [30, 45, 60, 90, 120, 180, 240], WALK_OPTS = [10, 15, 20, 30, 45, 60, 90];
function travelHtml() {
  const opts = PREFS.travel === "walk" ? WALK_OPTS : DRIVE_OPTS, cur = maxTravel();
  return `<p class="label">Getting there</p>
    <div class="chips" style="margin-bottom:8px"><button class="chip" data-travel="drive" aria-pressed="${PREFS.travel !== "walk"}">🚗 Driving</button><button class="chip" data-travel="walk" aria-pressed="${PREFS.travel === "walk"}">🚶 Walking</button></div>
    <label class="sortrow" style="justify-content:flex-start;gap:8px">Only suggest spots up to <select id="maxTravel">${opts.map(m => `<option value="${m}" ${m === cur ? "selected" : ""}>${fmtDur(m)}</option>`).join("")}</select> ${PREFS.travel === "walk" ? "on foot" : "away"}</label>
    <p class="muted" style="font-size:13px;margin-top:4px">${PREFS.travel === "walk" ? "Walking times are estimated from distance at an easy pace, plus the walk in from the road." : "Drive times come from road routing where available, plus the walk in from parking."}</p>`;
}
function setupHtml() {
  return `<div class="sect setup" id="setupBox"><h3>Your setup</h3>
    <p class="label">Starting point</p>
    <p style="font-size:15px;margin:2px 0 8px">Home: <b>${esc(HOME.label.replace(/ \(home\)$/, ""))}</b>${LOC.src !== "home" && km(LOC, HOME) > 1.5 ? `<br><span class="muted">Planning from ${esc(LOC.label)} right now</span>` : ""}</p>
    <div class="chips" style="margin-bottom:8px">
      <button class="chip" id="homeGps">Use my location as home</button>
      <button class="chip" id="homeSearch">Search for a place</button>
      ${LOC.src !== "home" && LOC.src !== "gps" && km(LOC, HOME) > 1.5 ? `<button class="chip" id="homeHere">Make ${esc(LOC.label)} home</button>` : ""}</div>
    <p style="font-size:15px;margin:8px 0 4px">When the app opens, plan from</p>
    <div class="chips"><button class="chip" data-start="gps" aria-pressed="${PREFS.start !== "home"}">Where I am</button><button class="chip" data-start="home" aria-pressed="${PREFS.start === "home"}">Home</button></div>
    ${travelHtml()}
    <p class="label">Units</p>
    <div class="chips"><button class="chip" data-units="us" aria-pressed="${!METRIC()}">Miles, °F</button><button class="chip" data-units="metric" aria-pressed="${METRIC()}">Kilometres, °C</button></div></div>`;
}
function prefsChanged(msg) { savePrefs(); __topsKey = ""; fbar(); render(); if ($("#setSheet") && !$("#setSheet").hidden) renderSettings();
  const ts = $("#travelSheet"); if (ts && !ts.hidden) ts.querySelector(".sheetbody").innerHTML = travelHtml(); if (msg) toast(msg); }
function setHome(l) { HOME = { lat: l.lat, lon: l.lon, label: (l.label || "Home").replace(/ \(home\)$/, "") + " (home)", src: "home" };
  try { localStorage.setItem("ss2:home", JSON.stringify(HOME)); } catch (e) { } DRIVES = {}; store.set("drives", {}); }
const _renderSettingsP = renderSettings;
renderSettings = function () { const r = _renderSettingsP.apply(this, arguments);
  const put = () => { const b = $("#setBody"); if (!b) return; if (!b.querySelector("#setupBox")) b.insertAdjacentHTML("afterbegin", setupHtml());
    const k = b.querySelector(".kitbox"), u = b.querySelector("#setupBox"); if (k) b.prepend(k); b.prepend(u);   // your setup and camera first, live data after
    if (!b.querySelector(".livehead")) { const nx = (k || u).nextElementSibling; if (nx) nx.insertAdjacentHTML("beforebegin", `<h3 class="livehead" style="margin-top:22px">Live data</h3>`); } };
  put(); if (r && r.then) r.then(put); setTimeout(put, 400); return r; };
document.addEventListener("click", async e => {
  const t = e.target.closest("[data-travel],[data-units],[data-start],#homeGps,#homeSearch,#homeHere,#travelChip,#showFar"); if (!t) return;
  if (t.id === "showFar") { UI.showFar = true; return renderSpots(); }
  if (t.id === "travelChip") { const el = ensureSheet("travelSheet", "How far you'll go"); el.querySelector(".sheetbody").innerHTML = travelHtml() + `<p class="muted" style="font-size:13px">More options (home, units) are in Settings ⚙.</p>`; el.hidden = false; return; }
  if (t.dataset.travel) { PREFS.travel = t.dataset.travel; return prefsChanged(PREFS.travel === "walk" ? `Walking: spots within ${fmtDur(maxTravel())}` : `Driving: spots within ${fmtDur(maxTravel())}`); }
  if (t.dataset.units) { PREFS.units = t.dataset.units; return prefsChanged(); }
  if (t.dataset.start) { PREFS.start = t.dataset.start; return prefsChanged(PREFS.start === "home" ? `The app will open planning from ${HOME.label.replace(/ \(home\)$/, "")}` : "The app will open planning from where you are"); }
  if (t.id === "homeHere") { setHome(LOC); return prefsChanged(`Home set to ${LOC.label}`); }
  if (t.id === "homeGps") { toast("Finding you…"); const ok = await gps(12000); if (ok) { setHome({ ...LOC, label: LOC.label === "Here" ? "My place" : LOC.label }); prefsChanged(`Home set to ${HOME.label.replace(/ \(home\)$/, "")}`); } else toast("Couldn't get your location. Allow location, or search instead."); return; }
  if (t.id === "homeSearch") { SETHOME = true; $("#setSheet").hidden = true; $("#locBtn").click(); setTimeout(() => { const m = $("#locMsg"); if (m) m.textContent = "Pick your home"; }, 50); return; }
}, true);
/* when choosing a home from the location search, the picked place becomes home as well */
document.addEventListener("click", e => { const h = e.target.closest("[data-hit]"); if (!h || !SETHOME) return; const x = $("#locHits")._list[+h.dataset.hit];
  SETHOME = false; setHome({ lat: x.lat, lon: x.lon, label: x.label }); setTimeout(() => toast(`Home set to ${x.label}`), 600); }, true);
document.addEventListener("click", e => { if (e.target.closest("#locClose")) SETHOME = false; }, true);
document.addEventListener("change", e => { if (e.target.id === "maxTravel") { PREFS[PREFS.travel === "walk" ? "maxWalk" : "maxDrive"] = +e.target.value; prefsChanged(); } });
