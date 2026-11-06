/* Where form data goes: the Cloudflare forms Worker (URL from endpoints.json, written by the Cloudflare workflow).
   Also: moving your on-device data (saved spots, shot list, log, votes...) between addresses. */
"use strict";
const FORMS_DEFAULT = "https://shotspots-forms.shotspots-eric.workers.dev";
let FORMS_URL = store.get("formsUrl", FORMS_DEFAULT);
fetch("endpoints.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null).then(j => { if (j && j.forms) { FORMS_URL = j.forms; store.set("formsUrl", j.forms); } }).catch(() => { });
async function sendForm(name, data) {
  try {
    const r = await fetch(`${FORMS_URL}/f/${name}`, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams(data).toString() });
    return r.ok;
  } catch (e) { return false; }
}
postForm = sendForm;   // research.js, alerts.js, photolog.js all go through postForm
flushOutcomes = async function () {
  const keep = [];
  for (const o of OUTQ) { if (!(await sendForm("outcome", o))) keep.push(o); }
  OUTQ = keep; store.set("outq", OUTQ); return keep.length;
};

/* ---- carry on-device data to a new address: export as a link/code, import from #import=... ---- */
const MOVE_KEYS = ["saved", "shots", "log", "votes", "hiddenSpots", "reviewedSpots", "seenResearched", "loc", "drives", "ebirdKey", "outq"];
function exportData() { const o = {}; MOVE_KEYS.forEach(k => { const v = store.get(k, undefined); if (v !== undefined) o[k] = v; });
  return btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
function importData(code) {
  const o = JSON.parse(decodeURIComponent(escape(atob(code.replace(/-/g, "+").replace(/_/g, "/")))));
  let n = 0;
  for (const k of MOVE_KEYS) { if (!(k in o)) continue; const cur = store.get(k, undefined);
    if (Array.isArray(o[k]) && Array.isArray(cur)) { const seen = new Set(cur.map(x => JSON.stringify(x))); store.set(k, cur.concat(o[k].filter(x => !seen.has(JSON.stringify(x))))); }
    else if (o[k] && typeof o[k] === "object" && cur && typeof cur === "object" && !Array.isArray(cur)) store.set(k, { ...o[k], ...cur });
    else if (cur === undefined) store.set(k, o[k]);
    n++; }
  return n;
}
(function () {
  const m = location.hash.match(/^#import=([A-Za-z0-9_-]+)/); if (!m) return;
  try { const n = importData(m[1]); history.replaceState(null, "", location.pathname); store.set("importedAt", Date.now()); location.reload(); }
  catch (e) { history.replaceState(null, "", location.pathname); setTimeout(() => toast("Couldn't import that data link"), 800); }
})();
function openMove() {
  const el = ensureSheet("moveSheet", "Move my data");
  const link = `${location.origin}${location.pathname}#import=${exportData()}`;
  el.querySelector(".sheetbody").innerHTML = `
    <p>Saved spots, your shot list, outing log, votes and settings live on this device for this web address. To bring them to another device or address, open this link there:</p>
    <textarea readonly rows="4" style="width:100%;font-size:12px" id="moveLink">${esc(link)}</textarea>
    <div class="chips"><button class="chip" id="moveCopy">Copy link</button>${navigator.share ? `<button class="chip" id="moveShare">Share…</button>` : ""}</div>
    <p class="label">Or paste a link or code from another device</p>
    <textarea rows="3" style="width:100%;font-size:12px" id="moveIn" placeholder="…#import=…"></textarea>
    <button class="btn primary wide" id="moveImport">Import</button>`;
  el.hidden = false;
}
document.addEventListener("click", async e => {
  const t = e.target.closest("#moveOpen,#moveCopy,#moveShare,#moveImport"); if (!t) return;
  if (t.id === "moveOpen") return openMove();
  const link = $("#moveLink") && $("#moveLink").value;
  if (t.id === "moveCopy") { try { await navigator.clipboard.writeText(link); toast("Copied"); } catch (er) { $("#moveLink").select(); } }
  if (t.id === "moveShare") navigator.share({ title: "ShotSpots data", url: link }).catch(() => { });
  if (t.id === "moveImport") { const v = ($("#moveIn").value || "").trim(); const code = (v.match(/#import=([A-Za-z0-9_-]+)/) || [])[1] || v;
    try { const n = importData(code); toast(`Imported ${n} kinds of data`); setTimeout(() => location.reload(), 900); } catch (er) { toast("That doesn't look like a ShotSpots data link"); } }
});
