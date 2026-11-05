/* Getting there: seasonal gates and permits (researched rules), SNOTEL snow depth, forecast snow level vs. the spot. */
"use strict";
function ruleActive(r, d) {
  const md = laYMD(d).slice(5), day = laYMD(d);
  if (r.until && day >= r.until) return false; if (!r.from) return r.type === "info";
  const inside = r.from <= r.to ? (md >= r.from && md <= r.to) : (md >= r.from || md <= r.to);
  return r.type === "open_only" ? !inside : inside;
}
function accessRules(id) { const a = fd("access_rules"); return a ? a.rules.filter(r => r.spots.includes(id)) : []; }
function closedRule(id, d) { return accessRules(id).find(r => (r.type === "closed" || r.type === "open_only") && ruleActive(r, d)) || null; }
const MD = s => { const [m, d] = s.split("-").map(Number); return new Date(2000, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" }); };
function reopenText(r) { return r.until ? `expected to reopen ${new Date(r.until + "T12:00").toLocaleDateString("en-US", { month: "long", year: "numeric" })}` : r.type === "open_only" ? `usually open ${MD(r.from)}–${MD(r.to)}` : `usually reopens around ${MD(r.to)}`; }

const _fitAc = fitFor;
fitFor = function (s, w) {
  const f = _fitAc(s, w); if (!f) return f; const r = closedRule(s.id, w.peak); if (!r) return f;
  return { ...f, n: Math.min(f.n, 8), why: [`no car access now: ${r.type === "open_only" ? "outside its open season" : "road gated for the season"} (${reopenText(r)})`, ...f.why] };
};
const _openAc = openSpot;
openSpot = function (id) {
  _openAc(id); const s = byId[id]; if (!s) return;
  const rules = accessRules(id), sn = (fd("snow") || { spots: {} }).spots[id], el = spotElev(id), now = new Date();
  const hr = hrrrRow(id, new Date(Date.now() + 18 * 36e5)) || hrrrRow(id, now);
  if (!rules.length && !sn) return;
  let h = `<h3>Getting there</h3>`;
  const c = closedRule(id, now);
  if (c) h += `<div class="alertbox warn"><b>No car access right now.</b> ${esc(c.text)} <span class="muted">(${reopenText(c)})</span></div>`;
  for (const r of rules) { if (r === c) continue; const on = ruleActive(r, now);
    if (r.type === "permit" && !on) continue;
    if (r.type === "closed" || r.type === "open_only") { h += `<p style="font-size:15px"><b>Seasonal:</b> ${esc(r.text)}</p>`; continue; }
    h += `<p style="font-size:15px">${r.type === "permit" ? "<b>Permit now:</b> " : ""}${esc(r.text)}</p>`; }
  if (sn) { const ft = Math.round(sn.st_elev_m * 3.281);
    h += `<p style="font-size:15px">${sn.in > 0 ? `<b>${sn.in} in of snow</b>` : "No snow"} at ${esc(sn.station)} SNOTEL (${ft.toLocaleString()} ft, ${sn.km} km away, ${sn.delev_m >= 0 ? sn.delev_m + " m above" : -sn.delev_m + " m below"} this spot) on ${sn.date.slice(5).replace("-", "/")}. ${tag("snow")}${sn.in >= 6 ? " Expect snow on the road and trail; carry chains." : ""}</p>`; }
  if (hr && hr.snow_m != null && el != null && el > 300) { const below = hr.snow_m < el;
    h += `<p class="muted" style="font-size:14px">Forecast snow level about ${Math.round(hr.snow_m * 3.281).toLocaleString()} ft vs. ${Math.round(el * 3.281).toLocaleString()} ft here: ${below ? "any precipitation would fall as snow." : "precipitation would fall as rain."}</p>`; }
  const srcs = rules.flatMap(r => r.src || []); if (srcs.length) h += `<p class="muted" style="font-size:13px">Sources: ${[...new Map(srcs.map(x => [x[1], x])).values()].map(([t, u]) => `<a href="${u}" target="_blank" rel="noopener">${esc(t)}</a>`).join(" · ")}</p>`;
  const put = () => { const b = $("#sheetBody"); const fb = b && b.querySelector(".feedbox"); if (fb) { if (!fb.querySelector(".accessbox")) fb.insertAdjacentHTML("afterbegin", `<div class="accessbox">${h}</div>`); } else if ((put.n = (put.n || 0) + 1) < 40) setTimeout(put, 150); };
  put();
};
