// Evaluate the phone app's own ephemeris (app/astro.js + planet code in app/sky.js) for verify.py.
const fs = require("fs"), path = require("path"), vm = require("vm");
const app = path.join(__dirname, "..", "app");
let src = fs.readFileSync(path.join(app, "astro.js"), "utf8").replace(/^let TZ/m, "var TZ");
const sky = fs.readFileSync(path.join(app, "sky.js"), "utf8");
src += "\n" + sky.split("/* ---------- 7Timer")[0].replace('"use strict";', "");
src = src.replace(/^const /gm, "var ").replace(/^let /gm, "var ");
const ctx = { console, Intl, Date, Math, JSON };
vm.createContext(ctx); vm.runInContext(src, ctx);
const a = JSON.parse(process.argv[2]);
if (a.dayEvents) {
  const e = ctx.dayEvents({ lat: a.lat, lon: a.lon }, a.dayEvents), out = {};
  const f = d => d ? new Intl.DateTimeFormat("en-GB", { timeZone: "America/Los_Angeles", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(d) : null;
  for (const k of ["sunrise", "sunset", "civilDawn", "civilDusk", "moonrise", "moonset"]) out[k] = f(e[k]);
  console.log(JSON.stringify(out));
} else {
  const out = {};
  for (const b of a.bodies) out[b] = a.times.map(ms => { const t = new Date(ms);
    if (b === "sun") { const p = ctx.sunPos(t, a.lat, a.lon); return [p.alt, p.az]; }
    if (b === "moon") { const p = ctx.moonPos(t, a.lat, a.lon); return [p.alt, p.az]; }
    const n = b[0].toUpperCase() + b.slice(1); const p = ctx.planetPos(n, t, a.lat, a.lon); return [p.alt, p.az]; });
  console.log(JSON.stringify(out));
}
