/* Scoring v2: score = conditions x spot quality (x access, applied in rankFor via drive time).
   Conditions: the light/weather fit from the rest of the model, with fame left out (0-100).
   Quality (0-1): fame for starter spots (Wikipedia links and views, photo counts, photographer stands); hand-researched spots 0.8.
   Multiplier 0.7 + 0.35q: an unknown spot keeps 70% of its light score, a typical curated spot ~98%, the most famous 105%.
   So an unknown spot in great light (90 -> 63) still beats a famous one in poor light (50 -> 53), and loses to it in fair light (60 -> 63).
   Night and the Wildlife filter keep v1: darkness and animals decide those. Settings key ss2:scorev = "1" switches back. */
let SCORE_V = 2;
try { if (localStorage.getItem("ss2:scorev") === "1") SCORE_V = 1; } catch (e) { }
function spotQuality(s) { return s.seed ? clamp((seedFame(s) + 2) / 12, 0, 1) : 0.8; }
const _fitV1 = fitFor;
fitFor = function (s, w) {
  const f = _fitV1(s, w);
  if (!f || SCORE_V !== 2 || w.kind === "night" || UI.group === "life") return f;
  const q = spotQuality(s);
  return { ...f, n: Math.round(clamp(f.n * (0.7 + 0.35 * q), 0, 100)), q };
};
