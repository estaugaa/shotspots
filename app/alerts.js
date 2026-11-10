/* Alerts: heads-up card on Now, an alerts sheet (bell), Web Push sign-up, alert settings, and smoke-aware scoring. */
"use strict";
const VAPID_PUBLIC = "BOt5ek966SAcZdZOxtvjB5B_x1W_i22n-mRrep97SA5N_3nNNJH3hi74XfqzVpbpuDKpZ_UCl8yiGnDc9IzZzmQ";
const RULE_NAMES = { fog_above: "Sea of fog from high viewpoints", color: "Colourful sunrise or sunset", alignment: "Sun or moon behind a landmark", dark: "Clear, dark night", aurora: "Aurora (northern lights)", weekend: "Weekend plan (Friday afternoon)", smoke: "Heavy smoke" };
const IS_IOS = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const STANDALONE = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const PUSH_OK = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

/* ---------- smoke in scoring ---------- */
const _fitAl = fitFor;
fitFor = function (s, w) {
  const f = _fitAl(s, w); if (!f || w.kind === "night") return f; const hr = hrrrRow(s.id, w.peak); if (!hr) return f;
  const aod = hr.smoke_aod || 0, pm = hr.smoke_ugm3 || 0; let n = f.n; const why = f.why.slice();
  const H = fd("hrrr"); if (GOLDK.has(w.kind) && H && H.rays && H.rays[s.id] && s.cats.some(c => SKY.includes(c))) {
    const tm = w.peak.getTime() / 60000; let bi = 0; H.t.forEach((x, i) => { if (Math.abs(x - tm) < Math.abs(H.t[bi] - tm)) bi = i; });
    const op = Math.abs(H.t[bi] - tm) <= 100 && H.rays[s.id][bi] ? H.rays[s.id][bi][w.kind === "sunrise" ? 0 : 1] : null;
    if (op != null && op < 40) { n -= 12; why.push(`low cloud deck toward the ${w.kind === "sunrise" ? "rising" : "setting"} sun (path ${op}% open)`); }
    else if (op != null && op < 70) { n -= 5; why.push(`path toward the sun only ${op}% open`); }
    else if (op != null) why.push(`clear path toward the sun (${op}% open)`); }
  const far = s.cats.some(c => ["mountain", "vista", "alignment"].includes(c));
  if (aod >= 1 || pm >= 35) { n -= far ? 20 : 10; why.unshift(`heavy smoke forecast (AOD ${aod.toFixed(1)}): muted light${far ? ", distant peaks hidden" : ""}`); }
  else if (aod >= 0.4) { n -= far ? 8 : 3; why.push(`smoky (AOD ${aod.toFixed(2)}): red sun${far ? ", far peaks faint" : ""}`); }
  else if (aod >= 0.15 && GOLDK.has(w.kind)) { n += 3; why.push(`light smoke haze (AOD ${aod.toFixed(2)}) can deepen reds`); }
  return { ...f, n: Math.round(clamp(n, 0, 100)), why };
};

/* ---------- smoke on the spot sheet ---------- */
const _openAl = openSpot;
openSpot = function (id) {
  _openAl(id); const s = byId[id]; const h = fd("hrrr"); if (!s || !h || !h.spots[id]) return;
  const now = Date.now() / 60000, rows = h.t.map((t, i) => [t, h.spots[id][i]]).filter(([t]) => t >= now - 60 && t <= now + 48 * 60);
  const ci = h.cols.indexOf("smoke_aod"), pi = h.cols.indexOf("smoke_ugm3"); if (ci < 0 || !rows.length) return;
  const mx = rows.reduce((a, [t, r]) => (r[ci] || 0) > (a[1][ci] || 0) ? [t, r] : a, rows[0]);
  const aod = mx[1][ci] || 0, pm = mx[1][pi] || 0;
  const txt = aod >= 1 || pm >= 35 ? `Heavy smoke expected around ${fmtT(minToDate(mx[0]))} (AOD ${aod.toFixed(1)}, ${Math.round(pm)} µg/m³ at ground level). Skip distant-peak shots; a red sun and close-up work can still be good.`
    : aod >= 0.4 ? `Smoky at times (AOD up to ${aod.toFixed(2)}): expect a red sun and faint far peaks.`
    : aod >= 0.15 ? `Light smoke haze at times (AOD up to ${aod.toFixed(2)}): can deepen sunrise and sunset reds.`
    : `Clean air: no smoke in the next 48 hours (AOD under 0.15).`;
  const box = `<h3>Smoke and haze ${tag("hrrr")}</h3><p style="font-size:15px">${txt}</p>`;
  const wait = () => { const b = $("#sheetBody"); const fb = b && b.querySelector(".feedbox"); if (fb) { if (!fb.querySelector(".smokebox")) fb.insertAdjacentHTML("beforeend", `<div class="smokebox">${box}</div>`); } else if ((wait.n = (wait.n || 0) + 1) < 40) setTimeout(wait, 150); };
  wait();
};

/* ---------- heads-up card on Now ---------- */
function upcoming() { const a = fd("alerts"); if (!a) return []; const now = Date.now(); // alerts are worked out for the home area: only show ones whose spots you can actually reach from here
  const near = x => { const sp = (x.spots || []).map(id => byId[id]).filter(Boolean); return sp.length ? sp.some(s => km(LOC, s) < 150 && !tooFar(s)) : km(LOC, HOME) < 60; };
  return a.alerts.filter(x => new Date(x.at).getTime() > now - 20 * 60000 && near(x)); }
function alertRow(a) {
  const sp = (a.spots || [])[0];
  return `<button class="lrow alertrow r-${a.rule}" ${sp && byId[sp] ? `data-spot="${sp}"` : `data-openalerts="1"`}><span><b>${esc(a.title)}</b><small>${esc(a.body)}</small></span><span class="pct">${a.rule === "smoke" ? "!" : a.p + "%"}</span></button>`;
}
const _renderNowAl = renderNow;
renderNow = function () {
  _renderNowAl(); const u = upcoming(); const v = $("#v-now"); if (!u.length || !v || (typeof outsideCoverage === "function" && outsideCoverage())) return;
  const a = u[0];
  v.insertAdjacentHTML("afterbegin", `<button class="alertline r-${a.rule}" data-openalerts="1"><i class="adot"></i><span><b>${esc(a.title)}</b></span>${a.rule === "smoke" ? "" : `<b class="ap">${a.p}%</b>`}${u.length > 1 ? `<small>+${u.length - 1}</small>` : ""}<span class="chev" aria-hidden="true">›</span></button>`);
};

/* ---------- alerts sheet ---------- */
async function pushState() {
  if (!PUSH_OK) return { can: false, why: IS_IOS && !STANDALONE ? "ios-home" : "unsupported" };
  if (IS_IOS && !STANDALONE) return { can: false, why: "ios-home" };
  const reg = await navigator.serviceWorker.getRegistration(); const sub = reg && await reg.pushManager.getSubscription().catch(() => null);
  return { can: true, on: !!sub && Notification.permission === "granted", denied: Notification.permission === "denied", sub };
}
function goNowHtml(ps) {
  const k = store.get("goKinds", ["color", "dark"]), box = (id, t) => `<label class="chk"><input type="checkbox" data-gokind="${id}"${k.includes(id) ? " checked" : ""}> ${t}</label>`;
  return `<div class="sect"><p><b>Go-now alerts, wherever you are.</b> ${km(LOC, HOME) < 60 ? "Away from home, alerts" : "Alerts"} are worked out for where you are and your travel limit (${maxTravel()} min ${PREFS.travel === "walk" ? "on foot" : "by car"}): a strong sunrise or sunset 45–120 minutes ahead, checked against the latest satellite scan, and clear dark nights by late afternoon. At most two a week. Your location is sent rounded to about 5 km.</p>
    ${box("color", "Strong sunrise or sunset")} ${box("dark", "Clear, dark night")}</div>`;
}
document.addEventListener("change", e => { const t = e.target.closest("[data-gokind]"); if (!t) return;
  const k = [...document.querySelectorAll("[data-gokind]")].filter(x => x.checked).map(x => x.dataset.gokind); store.set("goKinds", k); store.set("pushLoc", null); pushMoved().catch(() => { }); toast("Saved"); });
async function openAlerts() {
  const el = ensureSheet("alSheet", "Alerts"); const a = fd("alerts"); const st = (a && a.settings) || {}; const ps = await pushState();
  const u = upcoming(), nm = a ? a.near_misses.filter(x => new Date(x.at || x.t * 60000) > Date.now()) : [];
  let notif;
  if (ps.why === "ios-home") notif = `<p>To get alerts on your iPhone, add ShotSpots to your Home Screen first: tap <b>Share</b>, then <b>Add to Home Screen</b>, and open it from there. iPhones only allow notifications from web apps opened that way.</p>`;
  else if (!ps.can) notif = `<p class="muted">This browser can't receive notifications. Alerts still show on the Now tab.</p>`;
  else if (ps.denied) notif = `<p>Notifications are blocked for ShotSpots. Turn them on in your device's settings for this app, then come back here.</p>`;
  else notif = ps.on ? `<p>Notifications are <b>on</b> for this device.</p><div class="chips"><button class="chip" id="pushOff">Turn off on this device</button></div>`
    : `<p>Get a notification when a shot lines up, usually the evening before.</p><button class="btn primary wide" id="pushOn">Turn on notifications</button>`;
  const rules = st.rules || Object.keys(RULE_NAMES), push = st.push_rules || ["fog_above", "color", "alignment", "dark", "aurora", "weekend"];
  el.querySelector(".sheetbody").innerHTML = `
    <div class="sect">${u.length ? u.map(alertRow).join("") : `<p class="muted">Nothing lined up in the next three days at ${st.min_prob || 60}% or better. ${nm.length ? "Closest calls are below." : ""}</p>`}</div>
    ${nm.length ? `<h3 style="margin-top:22px">Close calls (under your ${st.min_prob || 60}% bar)</h3><div class="sect nearmiss">${nm.slice(0, 4).map(alertRow).join("")}</div>` : ""}
    ${weekendHtml(true)}
    <h3>Notifications</h3>${notif}${goNowHtml(ps)}
    ${!isOwner() ? `<p class="muted" style="font-size:14px">Alerts are tuned for the Washougal, Portland and Columbia Gorge area: fog, colourful skies, sun or moon alignments, dark skies and aurora within about 150 km.</p>` : `<h3>Alert settings</h3>
    <form id="alForm" class="stack">
      <label>Only alert at this chance or better (%)<input type="number" name="min_prob" min="20" max="95" step="5" value="${st.min_prob || 60}"></label>
      <p class="label">Notify me about</p>
      ${Object.entries(RULE_NAMES).map(([k, v]) => `<label><input type="checkbox" name="push_${k}" ${push.includes(k) ? "checked" : ""} style="display:inline;width:auto"> ${v}</label>`).join("")}
      <label>Only spots within this distance of home (km)<input type="number" name="max_km" min="20" max="1000" step="10" value="${st.max_km || 150}"></label>
      <label>For dark-sky trips, within (km)<input type="number" name="max_km_dark" min="20" max="1000" step="10" value="${st.max_km_dark || 300}"></label>
      <label>Aurora: alert at Kp (5 = camera only, 7 = likely visible to the eye)<input type="number" name="aurora_kp" min="4" max="9" value="${st.aurora_kp || 6}"></label>
      <label>Most notifications per day<input type="number" name="max_per_day" min="1" max="10" value="${st.max_per_day || 3}"></label>
      <label>Quiet from (hour, 0–23)<input type="number" name="quiet_start" min="0" max="23" value="${st.quiet_start ?? 22}"></label>
      <label>Quiet until (hour, 0–23)<input type="number" name="quiet_end" min="0" max="23" value="${st.quiet_end ?? 6}"></label>
      <button class="btn primary wide" type="submit">Save alert settings</button>
      <p class="muted" style="font-size:13px">Alerts are checked every 3 hours with each new forecast. Odds are raw model probabilities for now; logging your outings lets ShotSpots calibrate them.</p>
    </form>`}`;
  el.querySelector(".sheetbody")._rules = rules; el.hidden = false;
}
function b64u(s) { const p = "=".repeat((4 - s.length % 4) % 4); const b = atob((s + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(b, c => c.charCodeAt(0)); }
async function pushOn() {
  try {
    const perm = await Notification.requestPermission(); if (perm !== "granted") { toast("Notifications weren't allowed"); return openAlerts(); }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64u(VAPID_PUBLIC) });
    const ok = await postForm("push_sub", { action: "subscribe", sub: JSON.stringify(sub), device: (IS_IOS ? "iPhone" : navigator.platform || "device") + " " + new Date().toISOString().slice(0, 10), ...pushWhere() });
    store.set("pushLoc", { lat: LOC.lat, lon: LOC.lon });
    store.set("pushOn", true);
    reg.showNotification("ShotSpots", { body: "Notifications work on this device. Alerts start with the next forecast (within 3 hours).", icon: "icon-192.png", tag: "local-test" });
    toast(ok ? "Notifications on" : "Turned on here, but couldn't reach the server. Try again when online.");
  } catch (e) { toast("Couldn't turn on notifications: " + (e.message || e)); }
  openAlerts();
}
// 'Go now' alerts are worked out for where you are: send a rough location (about 5 km), travel limit and time zone
function pushWhere() { const r = v => (Math.round(v * 20) / 20).toFixed(2);
  return { lat: r(LOC.lat), lon: r(LOC.lon), travel: PREFS.travel, limit: String(maxTravel()), kinds: store.get("goKinds", ["color", "dark"]).join(","), tzoff: String(-new Date().getTimezoneOffset() * 60) }; }
async function pushMoved() {   // you've moved more than ~20 km (a trip): update the subscription so alerts follow you
  if (!store.get("pushOn", false) || !("serviceWorker" in navigator)) return; const last = store.get("pushLoc", null);
  if (last && km(last, LOC) < 20) return;
  const reg = await navigator.serviceWorker.getRegistration(); const sub = reg && await reg.pushManager.getSubscription().catch(() => null); if (!sub) return;
  if (await postForm("push_sub", { action: "update", sub: JSON.stringify(sub), ...pushWhere() })) store.set("pushLoc", { lat: LOC.lat, lon: LOC.lon });
}
setTimeout(() => { pushMoved().catch(() => { }); }, 8000);
async function pushOff() {
  const reg = await navigator.serviceWorker.getRegistration(); const sub = reg && await reg.pushManager.getSubscription();
  if (sub) { await postForm("push_sub", { action: "unsubscribe", sub: JSON.stringify(sub) }); await sub.unsubscribe().catch(() => { }); }
  store.set("pushOn", false); toast("Notifications off on this device"); openAlerts();
}
document.addEventListener("click", e => {
  const t = e.target.closest("[data-openalerts],#pushOn,#pushOff,#alertBtn"); if (!t) return;
  if (t.id === "pushOn") return pushOn(); if (t.id === "pushOff") return pushOff(); openAlerts();
});
document.addEventListener("submit", async e => {
  if (e.target.id !== "alForm") return; e.preventDefault(); const f = new FormData(e.target);
  const push = Object.keys(RULE_NAMES).filter(k => f.get("push_" + k));
  const rules = [...new Set([...(e.target.closest(".sheetbody")._rules || Object.keys(RULE_NAMES)), ...push])].filter(k => k !== "weekend");
  const ok = await postForm("alert_settings", { enabled: "true", min_prob: f.get("min_prob"), max_per_day: f.get("max_per_day"), max_km: f.get("max_km"), max_km_dark: f.get("max_km_dark"), aurora_kp: f.get("aurora_kp"), quiet_start: f.get("quiet_start"), quiet_end: f.get("quiet_end"), rules: rules.join(","), push_rules: push.join(",") });
  $("#alSheet").hidden = true; toast(ok ? "Saved. Applies from the next forecast check." : "Couldn't send. Try again when online.");
});
/* bell in the header + deep links from notifications */
(function () {
  const top = document.querySelector(".topr"); if (top && !$("#alertBtn")) top.insertAdjacentHTML("afterbegin", `<button class="iconbtn" id="alertBtn" aria-label="Alerts" title="Alerts"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg></button>`);
  const go = () => { if (/^#alert/.test(location.hash)) { history.replaceState(null, "", location.pathname); openAlerts(); } };
  window.addEventListener("hashchange", go);
  (async () => { for (let i = 0; i < 60 && !FEED.m; i++) await new Promise(r => setTimeout(r, 250)); await feedGet("alerts"); if (UI.view === "now") renderNow(); go(); })();
  if (navigator.serviceWorker) navigator.serviceWorker.addEventListener("message", ev => { if (!ev.data || ev.data.open !== "alerts") return; const m = /#spot=([\w-]+)/.exec(ev.data.url || ""); if (m) location.hash = "spot=" + m[1]; else openAlerts(); });
})();

/* ---------- weekend plan (Thu-Sun) ---------- */
const wkPass = p => !(p.spots || []).length || p.spots.some(id => !byId[id] || (inGroup(byId[id]) && !tooFar(byId[id])));
/* picks without odds (seasonal wildlife, fall colour, alignments) get an icon saying why they're here */
const WHY_IC = {
  wildlife: ["Peak season", '<path d="M3 13c3-1 5-4 9-4 3 0 5 2 9 1-2 3-5 4-8 4l-2 4-1-4c-3 0-5-1-7-1z"/><circle cx="15.5" cy="10.5" r=".6" fill="currentColor"/>'],
  birds: ["Peak season", '<path d="M3 13c3-1 5-4 9-4 3 0 5 2 9 1-2 3-5 4-8 4l-2 4-1-4c-3 0-5-1-7-1z"/><circle cx="15.5" cy="10.5" r=".6" fill="currentColor"/>'],
  fallcolor: ["Near peak", '<path d="M12 21v-6M12 15c-5 0-8-4-8-9 3 0 6 1 8 4 2-3 5-4 8-4 0 5-3 9-8 9z"/>'],
  night: ["Dark sky", '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M18.5 15l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>'],
  alignment: ["Alignment", '<circle cx="12" cy="9" r="3.5"/><path d="M3 20l6-7 3 3 3-4 6 8z"/>'],
  land: ["Landscape", '<path d="M2 20l7-11 4 6 3-4 6 9z"/><circle cx="17" cy="6" r="2"/>'],
  water: ["Waterfall", '<path d="M5 4h14M8 4v9M12 4v12M16 4v9M5 20c2-2 4-2 7-2s5 0 7 2"/>'] };
function whyIcon(p, sp) { const s = byId[sp], cats = s ? s.cats : [];
  const k = WHY_IC[p.rule] ? p.rule : p.rule === "dark" || p.rule === "aurora" ? "night" : cats.includes("waterfall") ? "water" : cats.some(c => LIFE.includes(c)) ? "wildlife" : "land";
  const [label, path] = WHY_IC[k];
  return `<span class="whyic" title="${label}"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true">${path}</svg><small>${label}</small></span>`; }
function weekendHtml(inSheet) {
  const w = fd("weekend"); if (!w || !w.picks || !w.picks.length) return ""; const end = new Date(w.sun + "T23:59:00"); if (end < new Date()) return "";
  const d = x => new Date(x + "T12:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `<div class="sect weekend"><h3>This weekend <span class="muted" style="font-size:15px;font-weight:400">${d(w.sat)}–${d(w.sun)}</span></h3>
    ${w.picks.filter(wkPass).map(p => { const sp = (p.spots || []).find(id => byId[id] && inGroup(byId[id]) && !tooFar(byId[id])) || (p.spots || [])[0];
      return `<button class="lrow alertrow r-${p.rule}" ${sp && byId[sp] ? `data-spot="${sp}"` : ""}><span><b>${esc(p.title)}</b><small>${esc(p.body)}${p.lens ? `<br><i>Lens:</i> ${esc(typeof kitText === "function" ? kitText(p.lens) : p.lens)}` : ""}</small></span>${p.p != null ? `<span class="pct">${p.p}%</span>` : whyIcon(p, sp)}</button>`; }).join("") || `<p class="muted">Nothing this weekend for the filter you've set.</p>`}
    <p class="muted" style="font-size:13px">${esc(w.note || "")}</p></div>`;
}
const _renderNowWk = renderNow;
renderNow = function () { _renderNowWk(); const v = $("#v-now"); if (!v) return; const ex = seasonalHtml(); if (ex) { const n = v.querySelector(".scorenote"); (n || v).insertAdjacentHTML(n ? "afterend" : "beforeend", ex); } };
/* seasonal picks (birds at peak, fall colour) don't have odds: show them as "in season" notes, not scored rows */
function seasonalHtml() {
  if (typeof outsideCoverage === "function" && outsideCoverage()) return "";
  const w = fd("weekend"); const ex = ((w && w.picks) || []).filter(p => (p.rule === "wildlife" || p.rule === "fallcolor") && wkPass(p)); if (!ex.length) return "";
  return `<div class="sect inseason"><h3>In season now</h3>${ex.map(p => { const sp = (p.spots || [])[0];
    return `<button class="lrow" ${sp && byId[sp] ? `data-spot="${sp}"` : ""}><span><b>${esc(p.title)}</b><small>${esc(p.body)}</small></span>${whyIcon(p, sp)}</button>`; }).join("")}</div>`;
}
(async () => { for (let i = 0; i < 60 && !FEED.m; i++) await new Promise(r => setTimeout(r, 250)); if (FEED.m && FEED.m.files.includes("weekend.json")) { await feedGet("weekend"); if (UI.view === "now") renderNow(); } })();
