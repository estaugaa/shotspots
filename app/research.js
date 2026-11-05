/* Nightly research: ask for a place to be researched, set limits, see what the research found. */
"use strict";
let HIDDEN = store.get("hiddenSpots", {}), REVIEWED = store.get("reviewedSpots", {});

/* ---------- merge researched spots into the app ---------- */
function mergeResearched() {
  const x = fd("spots_extra"); if (!x) return 0; let n = 0;
  for (const s of x.spots) {
    if (byId[s.id] || HIDDEN[s.id]) continue;
    s.src = (s.sources || []).map((src, i) => { const k = `rs:${s.id}:${i}`; D.SRC[k] = src; return k; });
    s.drive = null; s.researched = s.researched || true;
    SPOTS.push(s); byId[s.id] = s; n++;
  }
  return n;
}
const _loadFeedR = loadFeed;
loadFeed = async function () { const ok = await _loadFeedR(); if (ok && FEED.m.files.includes("spots_extra.json")) { await feedGet("spots_extra"); await feedGet("research_status"); if (mergeResearched()) render(); } return ok; };

/* ---------- spot sheet: researched banner ---------- */
const _openR = openSpot;
openSpot = function (id) {
  _openR(id); const s = byId[id]; if (!s || !s.id.startsWith("r-")) return;
  const b = $("#sheetBody"); const rev = REVIEWED[s.id];
  b.querySelector(".sub")?.insertAdjacentHTML("afterend", `<div class="alertbox research"><b>Found by nightly research</b> (${esc(s.researched || "")}, ${esc(s.confidence || "medium")} confidence). ${rev ? "You've reviewed it." : "Not reviewed yet: check the pin and sources before driving out."}
    <div class="chips" style="margin-top:6px">${rev ? "" : `<button class="chip" data-review="${s.id}">Looks right</button>`}<button class="chip" data-hide="${s.id}">Hide this spot</button></div></div>`);
};

/* ---------- your take: thumbs on every spot (steers nightly research and alerts) ---------- */
let VOTES = store.get("votes", {});
function voteHtml(id) { const v = VOTES[id];
  return `<div class="votes" data-voteid="${id}"><span class="muted" style="font-size:14px">Your take:</span>
    <button class="chip" data-vote="up" aria-pressed="${v === "up"}">More like this</button><button class="chip" data-vote="down" aria-pressed="${v === "down"}">Not for me</button></div>`; }
const _openV = openSpot;
openSpot = function (id) { _openV(id); const b = $("#sheetBody"); if (!b || b.querySelector(".votes")) return; const anchor = b.querySelector(".alertbox.research") || b.querySelector(".sub"); anchor?.insertAdjacentHTML("afterend", voteHtml(id)); };
document.addEventListener("click", async e => {
  const t = e.target.closest("[data-vote]"); if (!t) return; const id = t.closest("[data-voteid]").dataset.voteid, s = byId[id]; if (!s) return;
  const vote = VOTES[id] === t.dataset.vote ? "clear" : t.dataset.vote; let note = "";
  if (vote !== "clear") note = prompt(vote === "up" ? "What do you like about it? (optional, helps research find more like it)" : "What's not right about it? (optional)") || "";
  if (vote === "clear") delete VOTES[id]; else VOTES[id] = vote; store.set("votes", VOTES);
  t.parentElement.outerHTML = voteHtml(id);
  const ok = await postForm("spot_feedback", { id, vote, name: s.name, cats: (s.cats || []).join(","), note });
  toast(vote === "clear" ? "Cleared" : ok ? (vote === "up" ? "Noted: research will look for more like this" : "Noted: research will skip spots like this, and alerts won't suggest it") : "Saved here; couldn't reach the server");
});

/* ---------- Spots tab: explore section ---------- */
function researchHtml() {
  const st = fd("research_status"); const cfg = st ? st.settings : null;
  let h = `<div class="sect explore"><h3>Explore new areas <button class="chip" id="resLimits" style="float:right">Limits</button></h3>
    <p class="muted">Each night, Claude researches spots the way the Gorge list was built: guides, photo sites, agency pages, map checks. It starts with places you ask for, then works outward from home to the nearest area with more to find.</p>
    <button class="btn primary" id="resAdd">Research a place</button>`;
  if (st) {
    const q = st.requests.filter(r => r.status !== "done");
    if (q.length) h += `<p class="label">Queued</p><ul class="plain">${q.map(r => `<li>${esc(r.label)} (${r.radius_km} km)${r.status === "in_progress" ? " · in progress" : ""}</li>`).join("")}</ul>`;
    if (st.runs.length) h += `<p class="label">Recent nights</p><ul class="plain">${st.runs.slice(-5).reverse().map(r => `<li>${esc(r.at.slice(0, 10))}: ${esc(r.target)}: ${r.added.length} new${r.rejected && r.rejected.length ? `, ${r.rejected.length} skipped` : ""}${r.searches ? ` · ${r.searches} searches` : ""}</li>`).join("")}</ul>`;
    h += `<p class="muted" style="font-size:13px">${st.totals.researched_spots} researched spots so far; ${st.totals.cells_saturated} areas finished. ${cfg && !cfg.enabled ? "<b>Research is paused.</b>" : `Limits: ${cfg.regions_per_night} area and up to ${cfg.max_new_spots_per_night} new spots a night.`}</p>`;
  } else h += `<p class="muted" style="font-size:13px">No research has run yet.</p>`;
  return h + `</div>`;
}
const _renderSpotsR = renderSpots;
renderSpots = function () { _renderSpotsR(); const sl = $("#v-spots .shotlist"); (sl || $("#v-spots")).insertAdjacentHTML(sl ? "afterend" : "afterbegin", researchHtml()); };

/* ---------- sheets ---------- */
function openResearchAdd() {
  const el = ensureSheet("resSheet", "Research a place");
  el.querySelector(".sheetbody").innerHTML = `<form id="resSearch" class="search"><input id="resQ" type="search" placeholder="Town, park, region…" autocomplete="off"><button type="submit">Search</button></form>
    <div id="resHits"></div>
    <form id="resForm" class="stack" hidden><p id="resPicked"></p>
      <p class="label">How far around it</p>${chipGroup("radius", [["10", "10 km"], ["25", "25 km"], ["50", "50 km"], ["100", "100 km"]], ["25"], false)}
      <label>Focus (optional)<input name="focus" placeholder="e.g. waterfalls and birds, night sky"></label>
      <button class="btn primary wide" type="submit">Queue research</button>
      <p class="muted" style="font-size:13px">Requests go first, ahead of the automatic expansion. A request is finished when two nights in a row find almost nothing new.</p></form>`;
  el.hidden = false; setTimeout(() => $("#resQ").focus(), 150);
}
async function resSearch(q) {
  const box = $("#resHits"); box.innerHTML = `<p class="muted">Searching…</p>`;
  try { const j = await (await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&q=${encodeURIComponent(q)}`)).json();
    box._list = j.map(x => ({ label: x.name || x.display_name.split(",")[0], sub: x.display_name.split(",").slice(1, 4).join(","), lat: +x.lat, lon: +x.lon }));
    box.innerHTML = box._list.length ? box._list.map((x, i) => `<button class="lrow" data-reshit="${i}"><span><b>${esc(x.label)}</b><small>${esc(x.sub)}</small></span><span class="muted">${Math.round(km(HOME, x))} km</span></button>`).join("") : `<p class="muted">No match. Try a larger town or park name.</p>`;
  } catch (e) { box.innerHTML = `<p class="muted">Search needs a connection.</p>`; }
}
function openLimits() {
  const st = fd("research_status"), c = (st && st.settings) || { enabled: true, regions_per_night: 1, max_new_spots_per_night: 8, max_web_searches_per_night: 40, max_minutes_per_night: 45, auto_expand: true, max_km_from_home: 250 };
  const el = ensureSheet("limSheet", "Research limits");
  el.querySelector(".sheetbody").innerHTML = `<form id="limForm" class="stack">
    <label><input type="checkbox" name="enabled" ${c.enabled ? "checked" : ""} style="display:inline;width:auto"> Research each night</label>
    <label>Areas per night<input type="number" name="regions_per_night" min="1" max="3" value="${c.regions_per_night}"></label>
    <label>New spots per night (most)<input type="number" name="max_new_spots_per_night" min="1" max="30" value="${c.max_new_spots_per_night}"></label>
    <label>Web searches per night (most)<input type="number" name="max_web_searches_per_night" min="5" max="150" value="${c.max_web_searches_per_night}"></label>
    <label>Minutes per night (most)<input type="number" name="max_minutes_per_night" min="10" max="120" value="${c.max_minutes_per_night}"></label>
    <label><input type="checkbox" name="auto_expand" ${c.auto_expand ? "checked" : ""} style="display:inline;width:auto"> Expand outward automatically when nothing is queued</label>
    <label>Stay within this distance of home (km)<input type="number" name="max_km_from_home" min="20" max="2000" value="${c.max_km_from_home}"></label>
    <button class="btn primary wide" type="submit">Save limits</button>
    <p class="muted" style="font-size:13px">Research runs on your Claude plan as a scheduled task, so these limits cap how much of your plan's usage it takes each night. Searches and minutes are counted by the research task itself, so treat them as approximate. Changes apply from the next night.</p></form>`;
  el.hidden = false;
}
async function postForm(name, data) {
  const body = new URLSearchParams({ "form-name": name, ...data }).toString();
  try { const r = await fetch("/", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body }); return r.ok; } catch (e) { return false; }
}
document.addEventListener("click", async e => {
  const t = e.target.closest("#resAdd,#resLimits,[data-reshit],[data-review],[data-hide]"); if (!t) return;
  if (t.id === "resAdd") return openResearchAdd();
  if (t.id === "resLimits") return openLimits();
  if (t.dataset.reshit != null) { const x = $("#resHits")._list[+t.dataset.reshit]; const f = $("#resForm"); f._place = x; f.hidden = false; $("#resPicked").innerHTML = `<b>${esc(x.label)}</b> <span class="muted">${esc(x.sub)}</span>`; $("#resHits").innerHTML = ""; return; }
  if (t.dataset.review) { REVIEWED[t.dataset.review] = Date.now(); store.set("reviewedSpots", REVIEWED); toast("Marked as reviewed"); t.remove(); return; }
  if (t.dataset.hide) { HIDDEN[t.dataset.hide] = Date.now(); store.set("hiddenSpots", HIDDEN); const i = SPOTS.findIndex(s => s.id === t.dataset.hide); if (i >= 0) SPOTS.splice(i, 1); delete byId[t.dataset.hide]; history.back(); toast("Hidden on this device"); render(); }
});
document.addEventListener("submit", async e => {
  if (e.target.id === "resSearch") { e.preventDefault(); return resSearch($("#resQ").value.trim()); }
  if (e.target.id === "resForm") { e.preventDefault(); const f = e.target, x = f._place; if (!x) return;
    const ok = await postForm("research", { label: x.label + (x.sub ? ", " + x.sub.split(",")[0].trim() : ""), lat: x.lat.toFixed(5), lon: x.lon.toFixed(5), radius_km: readChips(f, "radius")[0] || "25", focus: new FormData(f).get("focus") || "" });
    $("#resSheet").hidden = true; toast(ok ? `Queued: ${x.label}. Research runs overnight.` : "Couldn't send. Try again when online."); return; }
  if (e.target.id === "limForm") { e.preventDefault(); const fd_ = new FormData(e.target), d = {};
    for (const k of ["regions_per_night", "max_new_spots_per_night", "max_web_searches_per_night", "max_minutes_per_night", "max_km_from_home"]) d[k] = fd_.get(k);
    d.enabled = fd_.get("enabled") ? "true" : "false"; d.auto_expand = fd_.get("auto_expand") ? "true" : "false";
    const ok = await postForm("research_settings", d); $("#limSheet").hidden = true; toast(ok ? "Limits saved; they apply from the next night" : "Couldn't send. Try again when online."); }
});
// first load: feed.js may have finished loading before this file wrapped loadFeed
(async () => { for (let i = 0; i < 60 && !FEED.m; i++) await new Promise(r => setTimeout(r, 250)); if (FEED.m && FEED.m.files.includes("spots_extra.json")) { await feedGet("spots_extra"); await feedGet("research_status"); if (mergeResearched()) render(); } })();
