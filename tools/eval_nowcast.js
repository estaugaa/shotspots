(async () => { const t0 = Date.now(); while (!(WX && OBSNOW && OBSNOW.length) && Date.now() - t0 < 40000) await new Promise(r => setTimeout(r, 500));
  const pt = nearestPt(LOC, 60), now = new Date(), c = hourAt(pt, now), raw = _hourAtNC(pt, now);

  return { stations: OBSNOW.length, near: obsFor(pt), forecast: raw && { cc: raw.cc, low: raw.low, mid: raw.mid, high: raw.high }, nowcast: c && { cc: c.cc, low: c.low, mid: c.mid, high: c.high, nc: c.nc } };
})()
