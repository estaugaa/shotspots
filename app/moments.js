/* Moments near you (roadmap 1.4): heads-ups for every place, worked out in the app from the same ranking the lists use,
   so they cover wherever you plan from, not just the pipeline's home area. A moment is a window in the next 48 h where
   a well-scoring spot you can reach has an event reason: rainbow chance, above the fog, fresh snow on a peak, the moon
   rising or setting near the horizon, an aurora watch. One per kind (the soonest window, its best-scoring spot with it),
   at most 4. Alpenglow is left out: it comes with most clear evenings at peaks (3 of 4 Grand Canyon moments, Nov 24). MODELED, like the reasons they come from; graded later (roadmap 4.1).
   Recomputed only when the data or the place changes, not on every redraw. */
"use strict";
const MOMENT_KINDS = [
  ["rainbow", /rainbow/i, "Rainbow chance"],
  ["fogabove", /above the fog/i, "Above the fog"],
  ["snow", /fresh snow on/i, "Fresh snow"],
  ["moon", /moon (rises|sets)/i, "Moon on the horizon"],
  ["aurora", /aurora watch/i, "Aurora watch"],
];
// Updates: at once when the place, filter or travel limit changes (and with the first list); otherwise recomputed 3 s
// after redraws settle, at most every 15 s. Some inputs behind the reasons have no version to key on (a cached list
// missed a rainbow at Multnomah Falls, Nov 24). A late update may change what an alert line says but doesn't add or
// remove the line by itself (that moved the list down), so the next redraw shows it.
let __mom = { k: "", list: [], at: -1e9, t: 0 };
function momentsNow() {
  if (typeof __listOk !== "undefined" && !__listOk) return __mom.list;   // not while the first list is held
  if (!LOC || !WX || typeof rankFor !== "function") return [];
  const k = [locKey(), UI.group, PREFS.travel, maxTravel()].join("|");
  if (__mom.k !== k) { __mom = { k, list: computeMoments(), at: performance.now(), t: 0 }; return __mom.list; }
  clearTimeout(__mom.t);
  const later = () => {
    const wait = 15000 - (performance.now() - __mom.at);
    if (wait > 0) { __mom.t = setTimeout(later, wait); return; }   // too soon after the last update: try again then
    const n = computeMoments(), had = __mom.list.length, same = n.map(x => x.key).join() === __mom.list.map(x => x.key).join();
    __mom.list = n; __mom.at = performance.now();
    if (!same && had && n.length) render();
  };
  __mom.t = setTimeout(later, 3000);
  return __mom.list;
}
function computeMoments() {
  const now = Date.now(), out = [], had = new Set();
  try {
    for (const w of allWindows(LOC, PLAN_HOURS)) {
      if (w.end.getTime() < now || w.start.getTime() - now > 48 * 36e5) continue;
      const R = rankFor(w).slice(0, 25); if (!R.length) continue;
      const floor = Math.max(35, 0.7 * R[0].f.n);
      for (const [kind, re, label] of MOMENT_KINDS) {
        if (had.has(kind)) continue;
        const x = R.find(y => y.f.n >= floor && (y.f.why || []).some(t => re.test(t)));
        if (!x) continue;
        const reason = x.f.why.find(t => re.test(t)); had.add(kind);
        out.push({ rule: "m-" + kind, key: `m:${kind}:${x.s.id}:${w.peak.getTime()}`, at: w.peak.toISOString(), p: null, spots: [x.s.id],
                   title: `${label}: ${x.s.name}`, body: `${wTitle(w)}, ${dayWord(w.peak)} ${fmtT(w.peak)}. ${reason} (modeled)`, moment: true });
      }
    }
  } catch (e) { noteErr("moments", e); }
  out.sort((a, b) => new Date(a.at) - new Date(b.at));
  return out.slice(0, 4);
}
