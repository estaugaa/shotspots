/* Scoring v2: score = conditions x spot quality (x access, applied in rankFor via drive time).
   Conditions: the light/weather fit from the rest of the model, with fame left out (0-100).
   Quality (0-1): fame from Wikipedia links and views, photo and sighting counts and photographer stands, for every spot alike.
   Multiplier 0.5 + 0.625q: an unknown spot keeps half its light score, the most famous 112%.
   So an unknown spot in great light (90 -> 45) beats a famous one in poor light (30 -> 34) but not in fair light (50 -> 56).
   Access: inside the chosen travel range distance is only a tie-breaker: rankFor orders by score x (1 - 0.1 x share of the range used).
   Night and the Wildlife filter keep v1: darkness and animals decide those. Settings key ss2:scorev = "1" switches back. */
let SCORE_V = 2;
try { if (localStorage.getItem("ss2:scorev") === "1") SCORE_V = 1; } catch (e) { }
// Quality is measured the same way for every spot, hand-researched or not (photo and sighting counts, Wikipedia, photographer
// stands): how much research a spot has had must not decide its rank. Hand spots get their counts from feed/handpop.json.
let HANDPOP = null;
fetch("feed/handpop.json").then(r => r.ok ? r.json() : null).then(j => { HANDPOP = j || {}; for (const s of SPOTS) { const p = HANDPOP[s.id]; if (p && !s.seed && s.pop == null) s.pop = p[0]; } if (typeof render === "function") render(); }).catch(() => { HANDPOP = {}; });
function spotQuality(s) {
  if (!s.seed && s.pop == null && HANDPOP && HANDPOP[s.id]) s.pop = HANDPOP[s.id][0];
  const q = clamp((seedFame(s) + 2) / 12, 0, 1);
  return /landmark|bridge/.test(s.kind || "") ? q * 0.75 : q;   // Wikipedia-famous buildings are not automatically photo spots
}
const _fitV1 = fitFor;
fitFor = function (s, w) {
  const f = _fitV1(s, w);
  if (!f || SCORE_V !== 2 || w.kind === "night" || UI.group === "life") return f;
  const q = spotQuality(s);
  return { ...f, n: Math.round(clamp(f.n * (0.5 + 0.625 * q), 0, 100)), q };
};
