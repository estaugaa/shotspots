(async () => { await new Promise(r => setTimeout(r, 15000));
  const ws = allWindows(LOC, PLAN_HOURS).filter(w => w.kind !== "night").slice(0, 6), S = SPOTS.filter(s => !tooFar(s));
  const layers = [["app", _fitFor], ["live", _fitSky], ["sky", _fitFeed], ["feed", _fitAl], ["alerts", _fitAc], ["access", _fitExtras], ["extras", _fitHours], ["hours", _fitNC], ["nowcast", _fitV1], ["score2", fitFor]];
  const out = {}; let prev = 0;
  for (const [k, fn] of layers) { if (typeof __skyMemoAt !== "undefined") __skyMemoAt = -1; const t = performance.now(); for (const w of ws) for (const s of S) fn(s, w); const ms = performance.now() - t; out[k] = { cum: Math.round(ms), own: Math.round(ms - prev) }; prev = ms; }
  return { spots: S.length, windows: ws.length, perLayer: out, allWindows: allWindows(LOC, PLAN_HOURS).length };
})()
