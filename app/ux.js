/* Final presentation layer (loads last):
   - spot pages in a deliberate order: why go and how to shoot it first, then photos, getting there and light,
     then forecast detail and reference material; the long hour-by-hour odds table is folded away
   - "Scout pick:" research labels dropped from spot names
   - guidance for taking a useful conditions photo */
"use strict";
const SPOT_ORDER = [
  [/^How a pro would work it/, 10], [/^Best photos here|^Right now from people there/, 20], [/^Best months/, 25],
  [/^Getting there/, 30], [/^Light here today/, 35], [/^Wildlife here this week/, 40], [/^Seen here in the last/, 45],
  [/^Smoke and haze/, 55], [/^Odds next 18 hours/, 60], [/^Access/, 70], [/^Check before you go/, 72], [/^Conditions now/, 74],
  [/^Experimental ideas/, 90], [/^See others/, 92], [/^Sources/, 95]];
function blockTitle(el) {
  if (el.classList && el.classList.contains("photosbox")) return "Best photos here";
  if (el.tagName === "H3") return el.textContent.trim();
  if (el.tagName === "DETAILS") return (el.querySelector("summary") || el).textContent.trim();
  if (el.classList && el.classList.contains("label") && /^Best months/.test(el.textContent)) return "Best months";
  return null;
}
function orderSpotPage() {
  const b = $("#sheetBody"); if (!b || b._ordered) return;
  const kids = [...b.children], head = [], blocks = []; let cur = null;
  for (const el of kids) { const t = blockTitle(el);
    if (t) { const r = SPOT_ORDER.find(([re]) => re.test(t)); cur = { rank: r ? r[1] : 50, els: [el], t }; blocks.push(cur); }
    else (cur ? cur.els : head).push(el); }
  if (blocks.length < 3) return;
  // fold the hour-by-hour odds table: useful detail, but a wall of numbers on a phone
  const odds = blocks.find(x => /^Odds next 18 hours/.test(x.t));
  if (odds) { const d = document.createElement("details"); d.className = "oddsfold"; d.innerHTML = `<summary>Hour-by-hour odds: fog, clear sky, colour</summary>`;
    odds.els.forEach((el, i) => { if (i) d.appendChild(el); }); odds.els[0].remove(); odds.els = [d]; }
  blocks.sort((x, y) => x.rank - y.rank);
  const frag = document.createDocumentFragment();
  head.forEach(el => frag.appendChild(el)); blocks.forEach(x => x.els.forEach(el => frag.appendChild(el)));
  b.appendChild(frag); b._ordered = true;
}
{ const _o = openSpot; openSpot = function (id) { _o.apply(this, arguments); const b = $("#sheetBody"); if (!b) return;
  const again = () => { b._ordered = false; orderSpotPage(); };
  again();
  // sections that load a moment later get put in their place too (for the first few seconds)
  if (b._mo) b._mo.disconnect(); let tmr = null, busy = false;
  b._mo = new MutationObserver(() => { if (busy) return; clearTimeout(tmr); tmr = setTimeout(() => { busy = true; again(); setTimeout(() => busy = false, 0); }, 150); });
  b._mo.observe(b, { childList: true }); setTimeout(() => b._mo && b._mo.disconnect(), 8000); }; }

/* research labels like "Scout pick: …" read oddly as place names */
function tidyNames() { for (const s of SPOTS) if (/^Scout pick:\s*/i.test(s.name)) s.name = s.name.replace(/^Scout pick:\s*/i, ""); }
{ const _r = render; render = function () { tidyNames(); return _r.apply(this, arguments); }; }

/* what makes a conditions photo useful, shown in the report sheet */
const CAM_TIPS = `<details class="camtips"><summary>What makes a useful report photo</summary><ul class="plain">
  <li><b>One wide shot</b> at your widest lens, phone level, no zoom.</li>
  <li><b>Sky in the top half,</b> the view you came for in the bottom half.</li>
  <li><b>At sunrise or sunset, face the sun's side</b> of the sky: that's where colour shows.</li>
  <li><b>For fog,</b> include the valley or the river below you.</li>
  <li><b>Take it near the peak time</b> (within 15 minutes) and at the spot, so it's verified.</li></ul></details>`;
{ const _cr = typeof camRender === "function" ? camRender : null;
  if (_cr) camRender = function () { const r = _cr.apply(this, arguments); const el = $("#camSheet .sheetbody"); if (el && !el.querySelector(".camtips")) { const send = el.querySelector("#camSend"); (send || el.lastElementChild).insertAdjacentHTML("beforebegin", CAM_TIPS); } return r; }; }
