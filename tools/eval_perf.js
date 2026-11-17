(async () => { await new Promise(r => setTimeout(r, 15000));
  const names = ["hourAt", "obsFor", "fitFor", "medianQuality", "spotQuality", "terrainLightDay", "seedFame", "viewFame", "skyAt", "calibLow", "hrrrAt", "lightDay", "rankFor", "nearestPt"];
  const stat = {};
  for (const n of names) { let f; try { f = eval(n); } catch (e) { continue; } if (typeof f !== "function") continue;
    stat[n] = { calls: 0, ms: 0 }; const w = function () { const t = performance.now(); try { return f.apply(this, arguments); } finally { stat[n].calls++; stat[n].ms += performance.now() - t; } };
    try { eval(n + " = w"); } catch (e) { delete stat[n]; } }
  if (typeof __skyMemoAt !== "undefined") __skyMemoAt = -1; if (typeof __topsKey !== "undefined") __topsKey = "";
  const t0 = performance.now(); paint(); const total = performance.now() - t0;
  for (const k in stat) { stat[k].ms = Math.round(stat[k].ms); }
  return { renderMs: Math.round(total), spots: SPOTS.length, obs: OBSNOW ? OBSNOW.length : null, stat };
})()
