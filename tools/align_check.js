/* Check every stored alignment (app/data.js ALIGN) against the app's own ephemeris (app/astro.js):
   at the stored minute (±3 min) the sun or moon must sit within 0.5° of the target, as seen from the vantage,
   and within 0.05° of the stored miss. Prints a JSON report; exit 1 if any fail.
   node tools/align_check.js [repo root]                                        (Nov 2026 audit) */
const fs = require("fs"), vm = require("vm"), path = require("path");
const root = process.argv[2] || ".";
const ctx = { Intl, Date, Math, console }; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(root, "app/astro.js"), "utf8") +
  ";this.sunPos=sunPos;this.moonPos=moonPos;this.targetFrom=targetFrom;this.angDiff=angDiff;", ctx);
const t = fs.readFileSync(path.join(root, "app/data.js"), "utf8");
const D = JSON.parse(t.slice(t.indexOf("{"), t.lastIndexOf("}") + 1));
const bad = [];
for (const a of D.ALIGN) {
  const V = D.VANT[a.v], T = D.TARGETS[a.tk];
  if (!V || !T) { bad.push({ ...a, why: "missing vantage or target" }); continue; }
  const g = ctx.targetFrom(V, T), P = a.b === "sun" ? ctx.sunPos : ctx.moonPos, t0 = Date.parse(a.t);
  let best = 99;
  for (let k = -3; k <= 3; k++) {
    const p = P(new Date(t0 + k * 60000), V.lat, V.lon);
    best = Math.min(best, Math.hypot(ctx.angDiff(p.az, g.az) * Math.cos(g.alt * Math.PI / 180), p.app - g.alt));
  }
  if (best > 0.5 || best > a.miss + 0.05) bad.push({ v: a.v, tk: a.tk, b: a.b, t: a.t, stored_miss: a.miss, now_miss: +best.toFixed(3) });
}
console.log(JSON.stringify({ checked: D.ALIGN.length, failed: bad.length, bad: bad.slice(0, 30) }));
process.exit(bad.length ? 1 : 0);
