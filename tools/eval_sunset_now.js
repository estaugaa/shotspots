(async () => { const t0 = Date.now(); while (!WX && Date.now() - t0 < 30000) await new Promise(r => setTimeout(r, 500));
  const today = laYMD(new Date()), w = allWindows(LOC, PLAN_HOURS).find(x => winDay(x) === today && x.kind === "sunset");
  if (!w) return "no sunset window today";
  const pick = (id) => SPOTS.find(s => s.id === id);
  const sky = (s) => { const k = skyAt(s, w); return k ? { q: Math.round(k.q), cc: k.cc, low: k.cl, mid: k.cm, high: k.ch, block: k.block, canvas: k.canvas, wind: k.wind, rain: k.pp, mode: k.mode } : null; };
  const list = rankFor(w).slice(0, 6).map(x => { const v1 = _fitV1(x.s, w); return { name: x.s.name, score: x.f.n, conditions: v1 ? v1.n : null, quality: x.f.q != null ? +x.f.q.toFixed(2) : null, why: x.f.why.slice(0, 6) }; });
  const views = ["cape-horn-lookout", "crown-point", "washougal-waterfront", "steigerwald", "silver-star", "pittock"].map(pick).filter(Boolean)
    .map(s => { const f = fitFor(s, w); return { name: s.name, light: s.light, score: f ? f.n : null, why: f ? f.why.slice(0, 5) : [], sky: sky(s) }; });
  return { window: w.label || w.kind, peak: w.peak && w.peak.toString().slice(0, 21), headline: (document.querySelector('#v-now h2, #v-now .head, #v-now .headline') || {}).textContent, top: list, views };
})()
