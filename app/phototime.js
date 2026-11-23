/* When photographers shoot here (measured): the share of a spot's photographers with a photo in morning or evening
   golden hour, from the Commons photo history (feed/spotphotos.json). A spot people shoot at sunset gets up to +15% in a
   sunset window; one nobody shoots then gets up to -20%. Scaled by evidence: 5 photographers carry half the effect,
   under 3 none. Baseline: the median spot with 5+ photographers has ~12% of them at each golden hour.
   Nov 23: Bonneville Fish Hatchery (0% golden) led Hood River sunrise; Haystack Rock (39% at sunset) sat 6th. */
"use strict";
const _fitQ = fitFor;
function photoTiming(s, w) {
  const f = fd("spotphotos"), v = f && f.spots && f.spots[s.id];
  if (!v || v[0] < 3 || !/sunrise|sunset|morning|evening/.test(w.kind || "")) return null;
  const am = /sunrise|morning/.test(w.kind), g = (am ? v[2] : v[3]) / 100;
  const raw = clamp(1 + 1.5 * (g - 0.12), 0.8, 1.15), wt = v[0] / (v[0] + 5);
  return { m: 1 + (raw - 1) * wt, g, am, who: v[0] };
}
fitFor = function (s, w) {
  const f = _fitQ(s, w);
  if (!f || SCORE_V !== 2 || w.kind === "night" || UI.group === "life") return f;
  const t = photoTiming(s, w); if (!t || Math.abs(t.m - 1) < 0.02) return f;
  const pct = Math.round(t.g * 100), when = t.am ? "sunrise" : "sunset";
  return { ...f, n: Math.round(clamp(f.n * t.m, 0, 100)), why: [...(f.why || []), t.m > 1 ? `${pct}% of its ${t.who} photographers shoot at ${when} (measured)` : `few photographers shoot here at ${when} (${pct}% of ${t.who}, measured)`] };
};
