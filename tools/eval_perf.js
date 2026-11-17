(async () => { await new Promise(r => setTimeout(r, 15000));
  const t = []; for (let i = 0; i < 3; i++) { if (typeof __skyMemoAt !== "undefined") __skyMemoAt = -1; __topsKey = ""; const t0 = performance.now(); paint(); t.push(Math.round(performance.now() - t0)); }
  return { redrawMs: t, spots: SPOTS.length, windows: allWindows(LOC, PLAN_HOURS).length };
})()
