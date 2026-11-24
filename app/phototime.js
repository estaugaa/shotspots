/* When photographers shoot here (measured): the share of a spot's photographers with a photo in morning or evening
   golden hour, from the Commons photo history (feed/spotphotos.json). A spot people shoot at sunset gets up to +15% in a
   sunset window; one nobody shoots then gets up to -20%. Scaled by evidence: 5 photographers carry half the effect,
   under 3 none. Baseline: per golden hour, from the feed (see photoTiming).
   Nov 23: Bonneville Fish Hatchery (0% golden) led Hood River sunrise; Haystack Rock (39% at sunset) sat 6th. */
"use strict";
const _fitQ = fitFor;
function photoTiming(s, w) {
  if (PHOTOQ_OFF) return null;
  const f = fd("spotphotos"), v = f && f.spots && f.spots[s.id];
  if (!v || v[0] < 3 || !/sunrise|sunset|morning|evening/.test(w.kind || "")) return null;
  // Nov 24: baseline per golden hour from the feed (median share among spots with 10+ photographers: sunrise 5%, sunset
  // 20% once camera times were read in the right time zone), not 12% for both; evidence weighed by shrinking the share
  // toward that baseline as if 10 more photographers had shot at the usual rate (1 of 14 no longer reads as "nobody
  // shoots sunrise here"; 0 of 100 still does). Effect x(1 + 0.25 (share / baseline - 1)), within x0.8..x1.15.
  const am = /sunrise|morning/.test(w.kind), g = (am ? v[2] : v[3]) / 100;
  const p0 = Math.max(0.02, ((f.base && (am ? f.base.am : f.base.pm)) || 12) / 100), A = 10;
  const post = (g * v[0] + A * p0) / (v[0] + A);
  return { m: clamp(1 + 0.25 * (post / p0 - 1), 0.8, 1.15), g, am, who: v[0] };
}
fitFor = function (s, w) {
  const f = _fitQ(s, w);
  if (!f || SCORE_V !== 2 || w.kind === "night" || UI.group === "life") return f;
  const t = photoTiming(s, w); if (!t || Math.abs(t.m - 1) < 0.02) return f;
  const pct = Math.round(t.g * 100), when = t.am ? "sunrise" : "sunset";
  return { ...f, n: Math.round(clamp(f.n * t.m, 0, 100)), why: [...(f.why || []), t.m > 1 ? `${pct}% of its ${t.who} photographers shoot at ${when} (measured)` : `few photographers shoot here at ${when} (${pct}% of ${t.who}, measured)`] };
};
