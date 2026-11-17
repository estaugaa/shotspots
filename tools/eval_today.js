(async () => { const t0 = Date.now(); while (!(WX && WX.pts && WX.pts.length) && Date.now() - t0 < 60000) await new Promise(r => setTimeout(r, 500)); await new Promise(r => setTimeout(r, 4000));
  const ws = allWindows(LOC, PLAN_HOURS), today = laYMD(new Date()), now = Date.now();
  const out = { now: new Date().toString().slice(0, 21), windows: [] };
  for (const w of ws.filter(w => winDay(w) === today || (w.peak.getTime() > now && w.peak.getTime() - now < 20 * 36e5)).slice(0, 8)) {
    const R = rankFor(w).slice(0, 4), sk = skyAt(LOC, w);
    out.windows.push({ kind: w.kind, at: w.peak.toString().slice(16, 21), sky: sk && { q: sk.q, cc: sk.cc, low: sk.low, mid: sk.mid, high: sk.high, block: sk.block, canvas: sk.canvas, mode: sk.mode },
      top: R.map(x => `${x.f.n} (light ${x.f.light != null ? Math.round(x.f.light) : "-"}, spot ×${x.f.qm ? x.f.qm.toFixed(2) : "-"}) ${x.s.name.slice(0, 32)} | ${x.f.why.slice(0, 3).join("; ").slice(0, 160)}`) });
  }
  return out; })()
