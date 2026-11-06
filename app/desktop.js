/* Desktop (>= 1100 px): keep the map rendered beside whatever view is open, fly to the spot when its page opens,
   and put a scrim behind centred dialogs. Phones are untouched. */
"use strict";
const DESK = matchMedia("(min-width:1100px)");
let SEL = null;
function deskMap() { if (!DESK.matches || !window.L) return; try { renderMap(); } catch (e) { } }
const _renderD = render;
render = function () { _renderD(); if (DESK.matches && UI.view !== "map") deskMap(); };
const _showD = show;
show = function (v) { if (DESK.matches && v === "map") v = "spots"; _showD(v); };
const _openD = openSpot;
openSpot = function (id) {
  _openD(id); const s = byId[id]; if (!DESK.matches || !s || !MAP) return;
  document.querySelectorAll(".item.sel,.lrow.sel").forEach(x => x.classList.remove("sel"));
  document.querySelectorAll(`[data-spot="${CSS.escape(id)}"]`).forEach(x => x.classList.add("sel"));
  const panel = $("#sheet").getBoundingClientRect().width || 0;
  const z = Math.max(MAP.getZoom(), 11);
  const pt = MAP.project([s.lat, s.lon], z).add([panel / 2, 0]);           // keep the spot clear of the docked panel
  MAP.flyTo(MAP.unproject(pt, z), z, { duration: matchMedia("(prefers-reduced-motion:reduce)").matches ? 0 : .6 });
  if (SEL) SEL.remove();
  SEL = L.circleMarker([s.lat, s.lon], { radius: 13, color: "#1E2628", weight: 2.5, fill: false, className: "pulse" }).addTo(MAP);
};
const _closeD = closeSheet;
closeSheet = function () { _closeD(); if (SEL) { SEL.remove(); SEL = null; } document.querySelectorAll(".sel").forEach(x => x.classList.remove("sel")); };
/* scrim behind centred dialogs (not the docked spot page) */
new MutationObserver(() => {
  if (!DESK.matches) return; const open = [...document.querySelectorAll(".sheet:not(#sheet)")].some(x => !x.hidden);
  let sc = $(".scrim"); if (open && !sc) { sc = document.createElement("div"); sc.className = "scrim"; document.body.appendChild(sc);
    sc.addEventListener("click", () => document.querySelectorAll(".sheet:not(#sheet)").forEach(x => x.hidden = true)); }
  else if (!open && sc) sc.remove();
}).observe(document.body, { subtree: true, attributes: true, attributeFilter: ["hidden"], childList: true });
document.addEventListener("keydown", e => { if (e.key === "Escape" && DESK.matches) document.querySelectorAll(".sheet:not(#sheet)").forEach(x => x.hidden = true); });
DESK.addEventListener("change", () => { if (UI.view === "map" && DESK.matches) show("spots"); setTimeout(() => MAP && MAP.invalidateSize(), 60); render(); });
window.addEventListener("resize", () => { clearTimeout(deskMap._t); deskMap._t = setTimeout(() => MAP && MAP.invalidateSize(), 120); });
(async () => { for (let i = 0; i < 80 && !window.L; i++) await new Promise(r => setTimeout(r, 100)); deskMap(); })();
