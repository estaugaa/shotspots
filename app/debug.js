/* Problem reports: keeps the last errors and taps in memory, and Settings › "Send a problem report" posts them
   with the app version and screen state, so issues on a real phone can be seen without guessing. */
"use strict";
const DBG = { errs: [], taps: [] };
addEventListener("error", e => { DBG.errs.push(`${new Date().toISOString().slice(11, 19)} ${e.message} @${(e.filename || "").split("/").pop()}:${e.lineno}`); DBG.errs = DBG.errs.slice(-15); });
addEventListener("unhandledrejection", e => { DBG.errs.push(`${new Date().toISOString().slice(11, 19)} promise: ${String(e.reason && e.reason.message || e.reason).slice(0, 200)}`); DBG.errs = DBG.errs.slice(-15); });
document.addEventListener("click", e => { const t = e.target.closest("[data-day],[data-win],[data-group],[data-cam],button,a") || e.target;
  const tag = t.dataset && (t.dataset.day || t.dataset.win || t.dataset.group) ? JSON.stringify(t.dataset) : (t.id || t.className || t.tagName);
  DBG.taps.push(`${new Date().toISOString().slice(11, 19)} ${String(tag).slice(0, 80)} -> day=${typeof UI !== "undefined" ? UI.day : "?"}`); DBG.taps = DBG.taps.slice(-20); }, true);
async function appVersion() { try { return (await caches.keys()).filter(k => /^ss2-v/.test(k)).join(",") || "no cache"; } catch (e) { return "?"; } }
async function sendDebug() {
  const later = (DBG.taps.slice(-1)[0] || "");
  const d = { v: await appVersion(), sw: navigator.serviceWorker && navigator.serviceWorker.controller ? "controlled" : "none",
    ua: navigator.userAgent.slice(0, 200), standalone: String(matchMedia("(display-mode: standalone)").matches || !!navigator.standalone),
    view: `${innerWidth}x${innerHeight} scroll=${Math.round(scrollY)}`, ui: typeof UI !== "undefined" ? JSON.stringify({ view: UI.view, day: UI.day, focus: UI.focus, group: UI.group }) : "",
    errs: DBG.errs.join("\n"), taps: DBG.taps.join("\n"), stick: getComputedStyle(document.documentElement).getPropertyValue("--stick"), at: new Date().toISOString() };
  const ok = await postForm("debug", d); toast(ok ? "Problem report sent. Thanks!" : "Couldn't send the report; check your connection."); return later;
}
{ const _rs = renderSettings; renderSettings = function () { const r = _rs.apply(this, arguments);
    const put = async () => { const b = $("#setBody"); if (!b || b.querySelector(".dbgbox")) return;
      b.insertAdjacentHTML("beforeend", `<div class="dbgbox" style="margin-top:18px"><p class="muted" style="font-size:13px">App version: ${esc(await appVersion())}</p><button class="btn wide" id="dbgSend">Send a problem report</button><p class="muted" style="font-size:13px">If something isn't working, try it once more, then tap this. It sends the app version, recent errors and your last taps (no photos or location).</p></div>`); };
    put(); setTimeout(put, 600); return r; }; }
document.addEventListener("click", e => { if (e.target.id === "dbgSend") sendDebug(); });
