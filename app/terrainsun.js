/* Sun over terrain for spots researched nationwide (pipeline/deepnat.py). Hand-researched and test-region spots get
   these times from the pipeline (feed/light.json); the rest carry a compact horizon profile (s.hzp: 360 values, tenths
   of a degree) and the times are worked out here, the same way: open-horizon sunrise/sunset, the moment the sun's disc
   clears the terrain, the last moment it is above it, and when direct light reaches the spot. Moon and Milky Way are
   left to the pipeline. MODELED: bare-earth terrain, trees not modeled. */
"use strict";
const __tsMemo = {};
function terrainLightDay(s, t) {
  if (!s || !s.hzp) return null;
  const ymd = laYMD(t), key = s.id + "|" + ymd; if (__tsMemo[key] !== undefined) return __tsMemo[key];
  const [y, m, d] = ymd.split("-").map(Number), t0 = Date.UTC(y, m - 1, d, 8), step = 2;   // ~local midnight on the West Coast; a day of 2-minute steps
  let or = null, os = null, tr = null, ts = null, saz = [null, null]; const lit = []; let run = null;
  for (let k = 0; k <= 24 * 60 / step; k++) {
    const tm = new Date(t0 + k * step * 60e3), p = sunPos(tm, s.lat, s.lon), hz = s.hzp[((Math.round(p.az) % 360) + 360) % 360] / 10, min = Math.floor(tm.getTime() / 60e3);
    if (p.app > -0.833) { if (or == null) { or = min; saz[0] = Math.round(p.az * 10) / 10; } os = min; saz[1] = Math.round(p.az * 10) / 10; }
    if (p.app + 0.27 > hz) { if (tr == null) tr = min; ts = min; }
    if (p.app > hz) { if (!run) run = [min, min]; else run[1] = min; } else if (run) { if (run[1] - run[0] >= 2) lit.push(run); run = null; }
  }
  if (run && run[1] - run[0] >= 2) lit.push(run);
  return (__tsMemo[key] = { or, os, tr, ts, lit, mr: null, ms: null, core: [], saz, est: true });
}
const _lightDayTS = lightDay;
lightDay = function (id, t) { return _lightDayTS(id, t) || terrainLightDay(byId[id], t); };
