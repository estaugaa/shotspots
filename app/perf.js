/* Per-redraw memo of fitFor (load profile, Nov 18): one redraw scored the window on screen twice (day tabs and the
   list) and other sections scored it again; on a slow phone one window is ~1 s. During a single paint() nothing a score
   depends on can change (it runs without yielding), so each (spot, window) is scored once per paint and the memo is
   dropped when the paint ends. Outside paint() (background day-tab slices, tests, the spot page) fitFor runs as before.
   Loaded last, so it wraps the whole chain; it changes no score and is not a SCORE_LAYERS layer. */
"use strict";
let __fitMemo = null;
const _fitPerf = fitFor;
fitFor = function (s, w) {
  if (!__fitMemo || !s || !w || !w.start) return _fitPerf(s, w);
  const k = s.id + "|" + w.kind + "|" + w.start.getTime() + "|" + (w.end ? w.end.getTime() : "");
  let r = __fitMemo.get(k);
  if (r === undefined) { r = _fitPerf(s, w); __fitMemo.set(k, r); }
  return r;
};
const _paintPerf = paint;
paint = function () {
  const outer = !__fitMemo; if (outer) __fitMemo = new Map();
  try { return _paintPerf.apply(this, arguments); } finally { if (outer) __fitMemo = null; }
};
