/* ShotSpots Sky: light pollution (Bortle), planets, constellations, deep-sky targets, seeing,
   a monthly field guide, live cams and trip-report links. Runs entirely on the phone. */
"use strict";

/* ---------- light pollution model ----------
   Walker's-law sky glow from towns (population in thousands), calibrated to World Atlas / lightpollutionmap
   readings at home (19.66), Cape Horn uplands (21.21), Washougal River Rd (21.56) and Larch Mtn (21.53). */
const LP = { C: 0.7943, k: 2.0, ext: 150, cities: [[45.52,-122.68,300],[45.52,-122.58,200],[45.58,-122.7,90],[45.47,-122.7,60],[45.63,-122.67,110],[45.64,-122.55,110],[45.7,-122.66,60],[45.5,-122.43,115],[45.54,-122.4,35],[45.59,-122.42,27],[45.58,-122.35,17],[45.49,-122.8,100],[45.52,-122.93,110],[45.42,-122.77,110],[45.38,-122.65,110],[45.43,-122.55,100],[45.78,-122.53,22],[45.81,-122.74,12],[45.4,-122.26,13],[45.26,-122.69,18],[44.94,-123.03,215],[45.14,-122.86,26],[46.14,-122.94,50],[45.86,-122.83,20],[45.71,-121.52,9],[45.73,-121.49,4],[45.6,-121.18,16],[45.69,-121.88,3],[45.82,-120.82,3.5],[46.6,-120.51,130],[47.25,-122.44,600],[47.04,-122.9,150],[44.06,-121.31,100],[45.21,-123.2,34],[45.3,-122.97,25],[45.52,-123.11,26],[46.19,-123.83,10],[46.0,-123.92,7],[45.46,-123.84,5],[44.96,-124.0,9],[46.23,-119.15,300],[45.84,-119.29,19],[47.42,-120.31,70],[47.0,-120.55,20],[44.27,-121.17,35],[44.05,-123.09,270],[44.6,-123.15,110],[46.7,-122.95,25],[45.3,-121.75,0.4],[45.67,-121.89,1.2],[45.29,-122.33,4],[45.15,-122.58,10],[45.9,-122.74,6],[45.86,-122.41,2],[44.3,-120.84,10],[45.89,-123.96,1.7],[45.36,-120.21,0.7],[45.6,-120.2,0.4]] };
const SQM_MEASURED = { "scout-cape-horn-uplands": 21.21, "scout-dark-washougal": 21.56, "larch-mtn": 21.53 };
const __sqmCache = {};
function sqmKnown(lat, lon) { let m = 1e9; for (const [la, lo] of LP.cities) { const d = Math.hypot((lat - la) * 111.2, (lon - lo) * 111.2 * Math.cos(lat * D2R)); if (d < m) m = d; } return m < 250; }
function sqmAt(lat, lon) {
  const k = lat.toFixed(3) + "," + lon.toFixed(3); if (__sqmCache[k]) return __sqmCache[k];
  if (!sqmKnown(lat, lon)) return (__sqmCache[k] = 20.0);   // light-pollution model only covers the Northwest: assume suburban
  let a = 0; for (const [la, lo, p] of LP.cities) { const d = Math.hypot((lat - la) * 111.2, (lon - lo) * 111.2 * Math.cos(lat * D2R)); a += p * Math.pow(Math.max(d, 2), -LP.k) * Math.exp(-d / LP.ext); }
  return (__sqmCache[k] = Math.min(21.95, 22.0 - 2.5 * Math.log10(1 + LP.C * a)));
}
function spotSqm(s) { return SQM_MEASURED[s.id] || sqmAt(s.lat, s.lon); }
function bortle(q) { return q >= 21.95 ? 1 : q >= 21.85 ? 2 : q >= 21.65 ? 3 : q >= 21.0 ? 4 : q >= 20.4 ? 4.5 : q >= 19.5 ? 5 : q >= 18.94 ? 6 : q >= 18.38 ? 7 : 8; }
const BORTLE_TXT = { 1: "Excellent dark sky: zodiacal light, airglow, Milky Way casts shadows", 2: "Truly dark: Milky Way structure obvious, M33 naked-eye", 3: "Rural: Milky Way detailed overhead, some glow on the horizon", 4: "Rural/suburban transition: Milky Way clear overhead, washed out low toward towns", 4.5: "Suburban edge: Milky Way visible but faint; long exposures pick up glow", 5: "Suburban: Milky Way faint or invisible to the eye; camera still catches it overhead", 6: "Bright suburban: no Milky Way to the eye; constellations and planets only", 7: "Suburban/urban: bright planets, the moon and city-light scenes", 8: "City: planets, the moon, star trails over lights" };
function bortleLabel(q) { const b = bortle(q); return `Bortle ${b === 4.5 ? "4–5" : b}`; }
function skyF(q) { return q >= 21.8 ? 1 : q >= 21.5 ? 0.92 : q >= 21.2 ? 0.82 : q >= 20.8 ? 0.68 : q >= 20.3 ? 0.52 : q >= 19.7 ? 0.38 : q >= 19 ? 0.25 : 0.15; }

/* ---------- planets (Schlyter low-precision elements, ~1-2 arcmin) ---------- */
const PEL = {
  Mercury: d => ({ N: 48.3313 + 3.24587e-5 * d, i: 7.0047 + 5e-8 * d, w: 29.1241 + 1.01444e-5 * d, a: 0.387098, e: 0.205635 + 5.59e-10 * d, M: 168.6562 + 4.0923344368 * d }),
  Venus: d => ({ N: 76.6799 + 2.4659e-5 * d, i: 3.3946 + 2.75e-8 * d, w: 54.891 + 1.38374e-5 * d, a: 0.72333, e: 0.006773 - 1.302e-9 * d, M: 48.0052 + 1.6021302244 * d }),
  Mars: d => ({ N: 49.5574 + 2.11081e-5 * d, i: 1.8497 - 1.78e-8 * d, w: 286.5016 + 2.92961e-5 * d, a: 1.523688, e: 0.093405 + 2.516e-9 * d, M: 18.6021 + 0.5240207766 * d }),
  Jupiter: d => ({ N: 100.4542 + 2.76854e-5 * d, i: 1.303 - 1.557e-7 * d, w: 273.8777 + 1.64505e-5 * d, a: 5.20256, e: 0.048498 + 4.469e-9 * d, M: 19.895 + 0.0830853001 * d }),
  Saturn: d => ({ N: 113.6634 + 2.3898e-5 * d, i: 2.4886 - 1.081e-7 * d, w: 339.3939 + 2.97661e-5 * d, a: 9.55475, e: 0.055546 - 9.499e-9 * d, M: 316.967 + 0.0334442282 * d }),
};
const PMAG = { Mercury: [-0.36, 0.027, 2.2e-13, 6], Venus: [-4.34, 0.013, 4.2e-7, 3], Mars: [-1.51, 0.016, 0, 1], Jupiter: [-9.25, 0.014, 0, 1], Saturn: [-9.0, 0.044, 0, 1] };
function helio(el) {
  const M = rev(el.M); let E = M + R2D * el.e * sind(M) * (1 + el.e * cosd(M));
  for (let k = 0; k < 6; k++) E = E - (E - R2D * el.e * sind(E) - M) / (1 - el.e * cosd(E));
  const xv = el.a * (cosd(E) - el.e), yv = el.a * Math.sqrt(1 - el.e * el.e) * sind(E), v = atan2d(yv, xv), r = Math.hypot(xv, yv);
  const x = r * (cosd(el.N) * cosd(v + el.w) - sind(el.N) * sind(v + el.w) * cosd(el.i)), y = r * (sind(el.N) * cosd(v + el.w) + cosd(el.N) * sind(v + el.w) * cosd(el.i)), z = r * sind(v + el.w) * sind(el.i);
  return { x, y, z, r, M };
}
function planetPos(name, date, lat, lon) {
  const d = dS(date); let h = helio(PEL[name](d));
  if (name === "Jupiter" || name === "Saturn") {
    const Mj = rev(19.895 + 0.0830853001 * d), Ms = rev(316.967 + 0.0334442282 * d);
    let L = atan2d(h.y, h.x), B = atan2d(h.z, Math.hypot(h.x, h.y));
    if (name === "Jupiter") L += -0.332 * sind(2 * Mj - 5 * Ms - 67.6) - 0.056 * sind(2 * Mj - 2 * Ms + 21) + 0.042 * sind(3 * Mj - 5 * Ms + 21) - 0.036 * sind(Mj - 2 * Ms) + 0.022 * cosd(Mj - Ms) + 0.023 * sind(2 * Mj - 3 * Ms + 52) - 0.016 * sind(Mj - 5 * Ms - 69);
    else { L += 0.812 * sind(2 * Mj - 5 * Ms - 67.6) - 0.229 * cosd(2 * Mj - 4 * Ms - 2) + 0.119 * sind(Mj - 2 * Ms - 3) + 0.046 * sind(2 * Mj - 6 * Ms - 69) + 0.014 * sind(Mj - 3 * Ms + 32); B += -0.02 * cosd(2 * Mj - 4 * Ms - 2) + 0.018 * sind(2 * Mj - 6 * Ms - 49); }
    h = { ...h, x: h.r * cosd(B) * cosd(L), y: h.r * cosd(B) * sind(L), z: h.r * sind(B) };
  }
  const s = sunEcl(d), xs = s.r * cosd(s.lon), ys = s.r * sind(s.lon);
  const xg = h.x + xs, yg = h.y + ys, zg = h.z, R = Math.hypot(xg, yg, zg);
  const elon = rev(atan2d(yg, xg)), elat = atan2d(zg, Math.hypot(xg, yg)), q = eclToEq(elon, elat, R, d), p = horiz(q.ra, q.dec, date, lat, lon);
  const FV = Math.acos(Math.max(-1, Math.min(1, (h.r * h.r + R * R - s.r * s.r) / (2 * h.r * R)))) * R2D, pm = PMAG[name];
  const mag = pm[0] + 5 * Math.log10(h.r * R) + pm[1] * FV + pm[2] * Math.pow(FV, pm[3]);
  const sunElong = Math.acos(Math.max(-1, Math.min(1, (s.r * s.r + R * R - h.r * h.r) / (2 * s.r * R)))) * R2D;
  return { alt: p.alt, az: p.az, mag, elon, ra: q.ra, dec: q.dec, elong: sunElong, R };
}
const ZOD = [[29.1, "Pisces"], [53.5, "Aries"], [90.4, "Taurus"], [118.3, "Gemini"], [138.2, "Cancer"], [174.2, "Leo"], [218.0, "Virgo"], [241.0, "Libra"], [247.7, "Scorpius"], [266.3, "Ophiuchus"], [299.7, "Sagittarius"], [327.5, "Capricornus"], [351.6, "Aquarius"], [360, "Pisces"]];
function zodiac(lon) { lon = rev(lon); for (const [b, n] of ZOD) if (lon < b) return n; return "Pisces"; }

/* ---------- constellations & targets ---------- */
const CONST = [["Orion", 83, 5, "Betelgeuse, Rigel and the belt; the Orion Nebula below the belt"], ["Taurus", 68, 16, "Aldebaran and the Pleiades"], ["Gemini", 107, 24, "Castor and Pollux"], ["Canis Major", 104, -22, "Sirius, the brightest star"], ["Auriga", 87, 42, "Capella"], ["Perseus", 52, 45, "the Double Cluster; Perseids radiant"], ["Cassiopeia", 15, 61, "the W; a great star-trail anchor"], ["Andromeda", 12, 38, "the Andromeda Galaxy"], ["Pegasus", 343, 20, "the Great Square"], ["Cygnus", 307, 42, "the Northern Cross on the Milky Way"], ["Lyra", 284, 36, "Vega"], ["Aquila", 297, 5, "Altair"], ["Sagittarius", 285, -28, "the Teapot and the Milky Way core"], ["Scorpius", 253, -30, "red Antares and the curling tail"], ["Ursa Major", 165, 55, "the Big Dipper"], ["Ursa Minor", 225, 78, "Polaris: aim here for circular star trails"], ["Leo", 158, 15, "Regulus and the Sickle"], ["Boötes", 215, 30, "orange Arcturus"], ["Virgo", 195, -3, "Spica"], ["Hercules", 255, 30, "the Keystone and the M13 cluster"], ["Cepheus", 330, 70, "Garnet Star"], ["Canis Minor", 115, 6, "Procyon"], ["Cancer", 130, 20, "the Beehive cluster"], ["Aquarius", 335, -10, ""], ["Capricornus", 315, -18, ""], ["Pisces", 10, 12, ""], ["Aries", 40, 20, ""], ["Triangulum", 30, 32, "the Triangulum Galaxy"], ["Cetus", 25, -10, "Mira"], ["Piscis Austrinus", 335, -30, "Fomalhaut, low in the south"], ["Corvus", 186, -18, ""], ["Ophiuchus", 257, -5, ""], ["Corona Borealis", 235, 30, "the Northern Crown"], ["Draco", 260, 65, ""], ["Lepus", 84, -19, ""], ["Monoceros", 105, -3, "the Rosette Nebula region"]];
const PL_TIPS = { Venus: "Brightest point in the sky: frame it over a ridge in twilight with the 70–300, or shoot it reflected in still water.", Jupiter: "At 300 mm, 1/60–1/125 s and ISO 400 shows the disc and up to four moons in a row.", Saturn: "A bright gold point. At 300 mm the rings are only a tiny elongation; better as part of a wide frame.", Mars: "Orange-red; strongest near opposition. Pairs well with the moon or bright stars.", Mercury: "Only low in bright twilight for a few days at a time: shoot it over a clear horizon 30–45 min after sunset or before sunrise." };
const DSO = [
  { n: "Milky Way core", ra: 266.4, dec: -29, minAlt: 8, lens: "16 mm at f/2.8, 12 s, ISO 3200–6400; stack 10–20 frames to cut noise", note: "Best Apr–Sep. Needs a dark south horizon (Bortle 4 or better)." },
  { n: "Cygnus Milky Way (Northern Cross)", ra: 307, dec: 40, minAlt: 30, lens: "16 mm, 12 s, ISO 3200–6400. Dark rift and the North America Nebula area show in stacks", note: "Overhead on summer and early-fall evenings." },
  { n: "Winter Milky Way (Auriga–Gemini–Monoceros)", ra: 95, dec: 22, minAlt: 35, lens: "16 mm, 12 s, ISO 6400; it is faint, so this needs Bortle 3–4", note: "Dec–Mar evenings, with Orion alongside." },
  { n: "Andromeda Galaxy (M31)", ra: 10.7, dec: 41.3, minAlt: 30, lens: "70–300 at about 150 mm f/5, 1.5 s, ISO 6400; stack 100+ frames", note: "A faint smudge to the eye; stacking brings out the core and dust lanes." },
  { n: "Pleiades (M45)", ra: 56.75, dec: 24.1, minAlt: 30, lens: "70–300 at 200 mm f/5.6, 1 s, ISO 6400; stack 100+ frames", note: "Bright blue cluster; long stacks reveal the reflection nebula." },
  { n: "Orion Nebula (M42)", ra: 83.8, dec: -5.4, minAlt: 25, lens: "70–300 at 300 mm f/5.6, 0.8 s, ISO 6400; stack 150+ frames", note: "The easiest nebula: pink and teal show in even a short stack." },
  { n: "Double Cluster", ra: 34.8, dec: 57.1, minAlt: 30, lens: "70–300 at 200–300 mm, 1 s, ISO 6400", note: "Two rich clusters side by side; red giant stars sprinkled through." },
  { n: "Beehive Cluster (M44)", ra: 130.1, dec: 19.7, minAlt: 30, lens: "70–300 at 150 mm, 1.5 s, ISO 3200", note: "Wide, bright cluster; nice framed with Jupiter or the moon when they pass." },
  { n: "Hercules Cluster (M13)", ra: 250.4, dec: 36.5, minAlt: 35, lens: "70–300 at 300 mm, 0.8 s, ISO 6400; stack", note: "A tight ball of 300,000 stars; small at 300 mm, so crop." },
  { n: "Triangulum Galaxy (M33)", ra: 23.5, dec: 30.7, minAlt: 35, lens: "70–300 at 150 mm, 1.5 s, ISO 6400; deep stack and dark site only", note: "Very faint; a Bortle 3–4 test target." },
];
function polarisTip() { return "Star trails: aim north at Polaris (altitude ≈ your latitude, 45.6°). 16 mm, f/4, ISO 800, 30 s frames for 45–90 min; blend in StarStaX or Sequator."; }

/* ---------- night data ---------- */
const cap = x => x[0].toUpperCase() + x.slice(1);
function nightOf(p) { const ws = allWindows(p, 40).filter(w => w.kind === "night"); return ws[0] || null; }
function sampleNight(p, fn, w, step) { const out = []; const s = addMin(w.start, -50), e = addMin(w.end, 50); for (let t = s.getTime(); t <= e.getTime(); t += (step || 15) * 60000) out.push(fn(new Date(t))); return out; }
function tonightPlanets(p, w) {
  const res = [];
  for (const name of Object.keys(PEL)) {
    const s = addMin(w.start, -75), e = addMin(w.end, 75); let best = null, first = null, last = null, mag = 0, con = "";
    for (let t = s.getTime(); t <= e.getTime(); t += 10 * 60000) {
      const d = new Date(t), sun = sunPos(d, p.lat, p.lon); if (sun.alt > -6) continue;
      const pp = planetPos(name, d, p.lat, p.lon); if (pp.alt < 8) continue;
      if (!first) first = d; last = d; if (!best || pp.alt > best.alt) { best = { ...pp, t: d }; mag = pp.mag; con = zodiac(pp.elon); }
    }
    if (best && best.mag < 6.5) res.push({ name, first, last, best, mag, con });
  }
  return res.sort((a, b) => a.mag - b.mag);
}
function whereNow(ra, dec, t, p) { const h = horiz(ra, dec, t, p.lat, p.lon); return h; }
function dirTxt(az, alt) { return alt >= 72 ? "overhead" : cmp(az) + " " + Math.round(alt) + "° up"; }
function bestDuringDark(ra, dec, w, p, minAlt) {
  let best = null, first = null, last = null; const s = w.start, e = w.end;
  for (let t = s.getTime(); t <= e.getTime(); t += 15 * 60000) { const d = new Date(t), h = horiz(ra, dec, d, p.lat, p.lon); if (h.alt < minAlt) continue; if (!first) first = d; last = d; if (!best || h.alt > best.alt) best = { ...h, t: d }; }
  return best ? { best, first, last } : null;
}
function zodiacalLight(month) { return [2, 3, 4].includes(month) ? "Zodiacal light: a faint cone in the west 80–110 min after sunset, best on moonless nights from a dark site." : [9, 10, 11].includes(month) ? "Zodiacal light: a faint cone in the east before dawn twilight, best on moonless mornings from a dark site." : ""; }

/* ---------- 7Timer astro (seeing/transparency) ---------- */
let SEVEN = store.get("seven", null);
async function loadSeven() {
  if (SEVEN && Date.now() - SEVEN.at < 3 * 36e5 && SEVEN.key === locKey()) return;
  try {
    const r = await fetch(`https://www.7timer.info/bin/astro.php?lon=${LOC.lon.toFixed(2)}&lat=${LOC.lat.toFixed(2)}&ac=0&unit=metric&output=json&tzshift=0`);
    const j = await r.json(); const i = j.init, t0 = Date.UTC(+i.slice(0, 4), +i.slice(4, 6) - 1, +i.slice(6, 8), +i.slice(8, 10));
    SEVEN = { at: Date.now(), key: locKey(), rows: j.dataseries.map(x => ({ t: t0 + x.timepoint * 36e5, cc: x.cloudcover, see: x.seeing, tr: x.transparency })) };
    store.set("seven", SEVEN); LIVE.status.seven = { ok: true, note: "seeing & transparency loaded" };
  } catch (e) { LIVE.status.seven = { ok: false, note: "7Timer not reachable from the phone" }; }
}
const SEE = ["", "excellent", "excellent", "good", "good", "average", "average", "poor", "poor"];
function sevenAt(t) { if (!SEVEN) return null; let b = null, bd = 1e12; for (const r of SEVEN.rows) { const d = Math.abs(r.t - t); if (d < bd) { bd = d; b = r; } } return bd <= 2 * 36e5 ? b : null; }

/* ---------- night scoring ---------- */
function nightEligible(s) {
  if (s.cats.some(c => NIGHT.includes(c))) return true;
  if (!["road", "short"].includes(s.effort)) return false;
  return s.cats.some(c => ["mountain", "vista", "reflection", "coast", "geology"].includes(c)) && spotSqm(s) >= 20.8;
}
function nightCloud(s, w) {
  const pt = nearestPt(s, 60); if (!pt) return null; const span = w.dark && w.dark.e > Date.now() ? w.dark : { s: w.start, e: w.end }; let sum = 0, n = 0, pop = 0;
  for (let t = Math.max(span.s.getTime(), Date.now() - 30 * 60000); t <= span.e.getTime(); t += 36e5) { const c = hourAt(pt, new Date(t)); if (c) { sum += c.cc; n++; pop = Math.max(pop, c.pop); } }
  return n ? { cc: sum / n, pop } : null;
}
const _fitSky = fitFor;
fitFor = function (s, w) {
  if (w.kind !== "night") return _fitSky(s, w);
  if (s.closed) return null; const road = roadStatus(s, w.peak); if (road && road.level === "closed") return null;
  const city = s.cats.includes("city"); if (!city && !nightEligible(s)) return null;
  const why = [], c = nightCloud(s, w), q = spotSqm(s), b = bortle(q);
  const clearF = !c ? 0.5 : c.cc <= 10 ? 1 : c.cc <= 30 ? 0.8 : c.cc <= 50 ? 0.5 : c.cc <= 70 ? 0.25 : 0.06;
  let n;
  if (city) { n = 50 + (c && c.pop >= 50 ? 8 : 0); why.push(c && c.pop >= 50 ? "wet night: reflections of the lights" : "city lights at night"); }
  else {
    const hrs = w.dark ? (w.dark.e - w.dark.s) / 36e5 : 0, moonF = hrs >= 3 ? 1 : hrs >= 1 ? 0.8 : w.illum >= 0.7 ? 0.5 : 0.7;
    n = 100 * clearF * skyF(q) * moonF;
    why.push(c ? (c.cc <= 15 ? "clear" : c.cc <= 40 ? `some cloud (${Math.round(c.cc)}%)` : `cloudy (${Math.round(c.cc)}%)`) : (typeof wxMiss === "function" ? wxMiss() : "forecast loading"));
    why.push(`${bortleLabel(q)} sky`);
    if (w.dark) why.push(`moon-free ${fmtT(w.dark.s)}–${fmtT(w.dark.e)}`); else why.push(`${Math.round(w.illum * 100)}% moon up`);
    if (!w.dark && w.illum >= 0.6 && clearF >= 0.8 && s.cats.some(k => ["mountain", "waterfall", "vista", "coast", "reflection"].includes(k))) { const v = 58 * clearF * (0.75 + 0.25 * skyF(q)); if (v > n) { n = v; why.unshift("bright moon: moonlit landscape with stars"); } }
    const kp = Math.max((LIVE.kpNow && Date.now() - LIVE.kpNow.at < 3 * 36e5) ? LIVE.kpNow.kp : 0, KP && KP.max || 0);
    if (kp >= 5 && s.cats.includes("aurora") && clearF >= 0.5) { n = Math.max(n, 60 + (kp - 5) * 15); why.unshift(`aurora watch: Kp ${kp.toFixed(1)}`); }
    const sev = sevenAt(w.peak.getTime()); if (sev && sev.tr <= 3 && clearF >= 0.8) { n += 4; why.push("good transparency"); }
  }
  if (road) { n -= 10; why.push(road.short || road.title); }
  n *= KCAP.night || 0.95;
  return { n: Math.round(clamp(n, 0, 100)), why, sk: null, sqm: q };
};

/* ---------- Sky tab ---------- */
UI.skyT = UI.skyT || 0;
function skyTimes(w) {
  const now = new Date(), list = [];
  if (now >= w.start && now <= w.end) list.push(["Now", now]);
  list.push(["Evening", addMin(w.start, 60)], ["Midnight", laDate(addDays(laYMD(w.start), 1), 0)], ["Pre-dawn", addMin(w.end, -60)]);
  return list.filter(([, t]) => t >= addMin(w.start, -1) && t <= w.end);
}
function cloudStrip(p, w) {
  const pt = nearestPt(p, 60); if (!pt) return "";
  const s = new Date(Math.floor(addMin(w.start, -90).getTime() / 36e5) * 36e5); let cells = "";
  for (let k = 0; k < 15; k++) { const t = new Date(s.getTime() + k * 36e5); if (t > addMin(w.end, 60)) break; const c = hourAt(pt, t); if (!c) continue; const sv = sevenAt(t.getTime());
    const shade = c.cc <= 15 ? "var(--moss)" : c.cc <= 40 ? "var(--gold)" : c.cc <= 70 ? "var(--muted)" : "var(--line)";
    cells += `<div><small>${t.toLocaleTimeString("en-US", { timeZone: TZ, hour: "numeric" }).replace(" ", "").toLowerCase()}</small><span class="cc" style="background:${shade}">${Math.round(c.cc)}</span>${sv ? `<small title="seeing / transparency">${SEE[sv.see][0].toUpperCase()}·${SEE[sv.tr][0].toUpperCase()}</small>` : ""}</div>`; }
  return `<div class="hours nightcc" aria-label="Cloud cover by hour tonight">${cells}</div><p class="muted" style="font-size:13px;margin:2px 0 0">Cloud % by hour${SEVEN ? "; letters are seeing · transparency (E excellent, G good, A average, P poor)" : ""}.</p>`;
}
function renderSky() {
  const el = $("#v-sky"); const w = nightOf(LOC); if (!w) { el.innerHTML = `<p class="empty">Working out tonight…</p>`; return; }
  const q = sqmAt(LOC.lat, LOC.lon), b = bortle(q), e = dayEvents(LOC, laYMD(w.start)), mStart = moonPos(w.start, LOC.lat, LOC.lon), month = +laYMD(new Date()).slice(5, 7);
  const times = skyTimes(w); UI.skyT = clamp(UI.skyT, 0, times.length - 1); const [tl0, T] = times[UI.skyT]; const tl = tl0 === "Now" ? "right now" : "at " + tl0.toLowerCase();
  const c = nightCloud(LOC, w), kp = LIVE.kpNow ? LIVE.kpNow.kp : null;
  let h = `<h2 style="font-size:26px;margin:8px 0 0">${esc(wTitle(w))} from ${esc(LOC.label)}</h2>
   <p class="muted" style="margin:2px 0 6px">Dark ${fmtT(w.start)}–${fmtT(w.end)} · ${phaseName(mStart.age)} ${Math.round(mStart.illum * 100)}%${e.moonrise ? ", moonrise " + fmtT(e.moonrise) : ""}${e.moonset ? ", moonset " + fmtT(e.moonset) : ""}</p>
   <div class="skycards"><div><small>Sky here</small>${sqmKnown(LOC.lat, LOC.lon) ? `<b>${bortleLabel(q)}</b><small>SQM ≈ ${q.toFixed(2)}</small>` : `<b>Not mapped</b><small><a href="https://www.lightpollutionmap.info/#zoom=9&lat=${LOC.lat}&lon=${LOC.lon}" target="_blank" rel="noopener">light map</a></small>`}</div>
     <div><small>Moon-free</small><b>${w.dark ? fmtT(w.dark.s).replace(" ", "") + "–" + fmtT(w.dark.e).replace(" ", "") : "none"}</b><small>${w.dark ? fmtDur((w.dark.e - w.dark.s) / 60000) : "moon up all night"}</small></div>
     <div><small>Clouds</small><b>${c ? Math.round(c.cc) + "%" : "–"}</b><small>average tonight</small></div>
     <div><small>Aurora</small><b>${kp != null ? "Kp " + kp.toFixed(1) : "–"}</b><small>${KP && KP.max ? "forecast max " + KP.max.toFixed(1) : "now"}</small></div></div>
   <p class="why" style="margin-top:6px">${esc(BORTLE_TXT[b])}.</p>${cloudStrip(LOC, w)}`;
  // darkest reachable spots
  const ranked = rankFor(w).filter(x => !x.s.cats.includes("city")).slice(0, 6);
  h += `<div class="sect"><h3>Best dark-sky spots tonight</h3>${ranked.length ? `<ul class="picks">${ranked.map(x => `<li>${pickRow(x, w)}</li>`).join("")}</ul>` : `<p class="empty">Nothing worthwhile in reach tonight.</p>`}</div>`;
  // time chips
  h += `<div class="chips" style="margin-top:14px">${times.map(([l, t], i) => `<button class="chip" data-skyt="${i}" aria-pressed="${i === UI.skyT}">${l} ${fmtT(t).replace(" ", "").toLowerCase()}</button>`).join("")}</div>`;
  // planets
  const pls = tonightPlanets(LOC, w);
  h += `<div class="sect"><h3>Planets</h3>${pls.length ? pls.map(pl => { const now = planetPos(pl.name, T, LOC.lat, LOC.lon);
      return `<div class="item"><b>${pl.name} <span class="muted">mag ${pl.mag.toFixed(1)} · in ${pl.con}</span></b><p>${now.alt > 0 ? `${cap(tl)}: ${dirTxt(now.az, now.alt)}. ` : `Below the horizon ${tl}. `}Visible ${fmtT(pl.first)}–${fmtT(pl.last)}, highest ${fmtT(pl.best.t)} (${dirTxt(pl.best.az, pl.best.alt)}). ${PL_TIPS[pl.name] || ""}</p></div>`; }).join("") : `<p class="muted">No bright planets in a dark sky tonight.</p>`}</div>`;
  // constellations at T
  const up = CONST.map(([n, ra, dec, note]) => ({ n, note, ...whereNow(ra, dec, T, LOC) })).filter(x => x.alt >= 25).sort((a, b) => b.alt - a.alt);
  const groups = {}; up.forEach(x => { const k = x.alt >= 72 ? "Overhead" : ["North", "Northeast", "East", "Southeast", "South", "Southwest", "West", "Northwest"][Math.round(rev(x.az) / 45) % 8]; (groups[k] = groups[k] || []).push(x); });
  const order = ["Overhead", "North", "Northeast", "East", "Southeast", "South", "Southwest", "West", "Northwest"];
  h += `<div class="sect"><h3>Constellations ${tl} (${fmtT(T)})</h3><p class="muted" style="font-size:13px;margin-top:-4px">Drawn as you'd see them facing that way: north up, east to the left. Bigger dots are brighter stars.</p>${order.filter(k => groups[k]).map(k => `<p class="label">${k}</p><div class="figgrid">${groups[k].map(x => `<div class="figcard">${typeof figSvg === "function" ? figSvg(x.n, 96) : ""}<div><b>${esc(x.n)}</b>${x.note ? `<small>${esc(x.note)}</small>` : ""}</div></div>`).join("")}</div>`).join("")}</div>`;
  // targets
  const tg = DSO.map(o => ({ o, r: bestDuringDark(o.ra, o.dec, w, LOC, o.minAlt) })).filter(x => x.r);
  const mUp = moonPos(T, LOC.lat, LOC.lon); const zl = zodiacalLight(month);
  h += `<div class="sect"><h3>Targets for your X-T5 kit tonight</h3>`;
  if (mUp.alt > 5) h += `<div class="item"><b>🌕 The moon (${Math.round(mUp.illum * 100)}%, ${dirTxt(mUp.az, mUp.alt)})</b><p>70–300 at 300 mm, f/8, ISO 200, 1/250 s; detail is best along the shadow line, so a half moon beats a full one. A low moon over a ridge or Mt. Hood at 300 mm makes it look huge.</p></div>`;
  h += tg.map(({ o, r }) => { const now = whereNow(o.ra, o.dec, T, LOC); const dimmed = o.n.includes("Milky Way") && b >= 5;
    return `<div class="item"><b>${o.n}${dimmed ? " <span class=\"muted\">(needs a darker site)</span>" : ""}</b><p>${now.alt > 0 ? `${cap(tl)}: ${dirTxt(now.az, now.alt)}. ` : ""}Best ${fmtT(r.best.t)}, ${dirTxt(r.best.az, r.best.alt)}; up ${fmtT(r.first)}–${fmtT(r.last)}. ${o.note} <i>${o.lens}.</i></p></div>`; }).join("");
  const core = gcPos(T, LOC.lat, LOC.lon); if (!tg.find(x => x.o.n === "Milky Way core")) h += `<div class="item"><b>Milky Way core</b><p>Not up in a dark sky tonight${month >= 10 || month <= 1 ? "; the core season returns in February as a pre-dawn object, and is best May–August." : "."}</p></div>`;
  if (zl) h += `<div class="item"><b>Zodiacal light</b><p>${zl}</p></div>`;
  h += `<div class="item"><b>Star trails</b><p>${polarisTip()}</p></div></div>`;
  // events
  const sh = showersSoon(45);
  h += `<div class="sect"><h3>Coming up</h3>${sh.map(({ sh: s, t }) => { const m = moonPos(t, LOC.lat, LOC.lon); return `<div class="item"><b>☄️ ${s.n}: peak ${fmtDate(t)}</b><p>Up to ${s.zhr}/hr under a dark sky. Moon ${Math.round(m.illum * 100)}% lit. ${s.note || ""}</p></div>`; }).join("")}
    ${nextPhases(LOC).map(x => `<div class="item"><b>${x.ic} ${x.n}: ${fmtDate(x.t)}</b><p>${x.tip}</p></div>`).join("")}</div>`;
  // tools
  h += `<div class="sect"><h3>Free tools</h3><ul class="plain">
    <li><a href="https://stellarium-web.org/" target="_blank" rel="noopener">Stellarium Web</a>: planetarium to preview compositions</li>
    <li><a href="https://www.lightpollutionmap.info/#zoom=9&lat=${LOC.lat.toFixed(3)}&lon=${LOC.lon.toFixed(3)}" target="_blank" rel="noopener">Light pollution map</a> and <a href="https://djlorenz.github.io/astronomy/lp/" target="_blank" rel="noopener">Lorenz light pollution atlas</a></li>
    <li><a href="https://www.heavens-above.com/PassSummary.aspx?satid=25544&lat=${LOC.lat.toFixed(3)}&lng=${LOC.lon.toFixed(3)}&loc=Here&alt=0&tz=PST" target="_blank" rel="noopener">ISS passes from here</a> (Heavens-Above): a 2–3 min streak across a wide frame</li>
    <li><a href="https://www.swpc.noaa.gov/products/aurora-30-minute-forecast" target="_blank" rel="noopener">NOAA aurora 30-minute forecast</a></li>
    <li><a href="https://siril.org/" target="_blank" rel="noopener">Siril</a> (Mac/PC) or <a href="https://sites.google.com/view/sequator/" target="_blank" rel="noopener">Sequator</a> (PC): free stacking for untracked sky frames</li></ul>
    <p class="muted" style="font-size:13px">Bortle and SQM here are estimates from a town-glow model calibrated to satellite-based light pollution maps; ridges and trees can make a pull-off darker or brighter than shown.</p></div>`;
  el.innerHTML = h;
}
function nextPhases(p) {
  const out = []; const now = new Date(); let prev = moonPos(now, p.lat, p.lon).illum, prevT = now;
  for (let k = 1; k <= 35 * 4 && out.length < 2; k++) { const t = new Date(now.getTime() + k * 6 * 36e5), m = moonPos(t, p.lat, p.lon);
    if (prev > 0.02 && m.illum <= 0.02 && !out.find(x => x.n === "New moon")) out.push({ ic: "🌑", n: "New moon", t, tip: "Darkest nights of the month: plan Milky Way, deep-sky and dark-site trips for the 3–4 nights around it." });
    if (prev < 0.98 && m.illum >= 0.98 && !out.find(x => x.n === "Full moon")) out.push({ ic: "🌕", n: "Full moon", t, tip: "Rises at sunset: shoot it over Mt. Hood or a skyline at 300 mm in the blue hour, when sky and moon balance." });
    prev = m.illum; prevT = t; }
  return out.sort((a, b) => a.t - b.t);
}

/* ---------- spot sheet additions: night sky, cams, reports ---------- */
const CAMS = [
  { re: /Gorge · Oregon|Rooster|Women|Vista House|Latourell|Multnomah|Crown/, cams: [["Crown Point wind cam (Windfinder)", "https://www.windfinder.com/webcams/crown_point"], ["I-84 Gorge road cams (ODOT TripCheck)", "https://www.tripcheck.com/"], ["Gorge & I-84 cam roundup", "https://www.skimountaineer.com/MtnWebCams/OR-MtnWebCams.html"]] },
  { re: /Gorge · Washington|Camas|Close to home|Washougal|Cape Horn|Beacon/, cams: [["SR 14 cams (WSDOT)", "https://wsdot.com/travel/real-time/map/"], ["Crown Point cam across the river", "https://www.windfinder.com/webcams/crown_point"]] },
  { re: /Hood River|East Gorge|Mt. Adams|Trout/, cams: [["Hood River sailing cams (Windance)", "https://windance.com/pages/web-cams"], ["Gorge & I-84 cam roundup", "https://www.skimountaineer.com/MtnWebCams/OR-MtnWebCams.html"]] },
  { re: /Mt. Hood/, cams: [["Timberline conditions & cams", "https://timberlinelodge.com/conditions/"], ["Mt. Hood cam roundup", "https://www.skimountaineer.com/MtnWebCams/Hood-MtnWebCams.html"]] },
  { re: /St. Helens|Lewis/, cams: [["USGS Mount St. Helens webcams", "https://www.usgs.gov/volcanoes/mount-st.-helens/multimedia/webcams"], ["St. Helens cam roundup", "https://www.skimountaineer.com/MtnWebCams/StHelens-MtnWebCams.html"]] },
  { re: /Portland|Willamette/, cams: [["Portland road cams (ODOT TripCheck)", "https://www.tripcheck.com/"]] },
];
const _openSky = openSpot;
openSpot = function (id) {
  _openSky(id); const s = byId[id]; if (!s) return; const body = $("#sheetBody"); if (!body) return;
  const q = spotSqm(s), b = bortle(q), w = nightOf(s), name = s.name.split("(")[0].replace(/^Scout pick: |^Experimental: /, "").trim();
  let h = "";
  if (nightEligible(s) || s.cats.includes("city")) {
    const f = w ? fitFor(s, w) : null, pls = w ? tonightPlanets(s, w).filter(p => p.mag < 2).map(p => p.name) : [];
    if (!sqmKnown(s.lat, s.lon)) h += `<details open><summary>Night sky here</summary><div class="prose"><p>Sky darkness isn't mapped here yet. Check <a href="https://www.lightpollutionmap.info/#zoom=10&lat=${s.lat}&lon=${s.lon}" target="_blank" rel="noopener">the light pollution map</a> before a night trip.</p></div></details>`; else
    h += `<details open><summary>Night sky here</summary><div class="prose"><p><b>${bortleLabel(q)}</b> (SQM ≈ ${q.toFixed(2)}${SQM_MEASURED[s.id] ? ", from the satellite map" : ", estimated"}). ${esc(BORTLE_TXT[b])}.</p>
      ${w ? `<p>${esc(wTitle(w))}: ${f ? `score <b>${f.n}</b>, ${esc(f.why.slice(0, 3).join(", "))}.` : "not a night-sky spot."}${pls.length ? " Planets up: " + pls.join(", ") + "." : ""}</p>` : ""}
      <p class="muted" style="font-size:14px">Full sky details, planets and targets are on the Sky tab. <a href="https://www.lightpollutionmap.info/#zoom=11&lat=${s.lat.toFixed(4)}&lon=${s.lon.toFixed(4)}" target="_blank" rel="noopener">See this spot on the light pollution map</a>.</p></div></details>`;
  }
  const cams = CAMS.filter(c => c.re.test(s.region + " " + s.name)).flatMap(c => c.cams).filter((x, i, a) => a.findIndex(y => y[1] === x[1]) === i);
  const wa = /Washington|Camas|Close to home|Helens|Adams|Rainier|Lewis|WA\b|Yakima|Cascades/.test(s.region);
  h += `<details><summary>Conditions now: cams & trip reports</summary><ul class="plain">${cams.map(([n, u]) => `<li><a href="${u}" target="_blank" rel="noopener">${esc(n)}</a></li>`).join("")}
    <li><a href="https://www.flickr.com/search/?lat=${s.lat.toFixed(4)}&lon=${s.lon.toFixed(4)}&radius=1&has_geo=1&sort=date-taken-desc" target="_blank" rel="noopener">Newest Flickr photos here</a> (how it looks this week)</li>
    ${wa ? `<li><a href="https://www.wta.org/go-outside/hikes?title=${encodeURIComponent(name)}" target="_blank" rel="noopener">WTA trip reports</a></li>` : `<li><a href="https://www.oregonhikers.org/w/index.php?search=${encodeURIComponent(name)}" target="_blank" rel="noopener">Oregon Hikers field guide</a></li>`}
    <li><a href="https://www.inaturalist.org/observations?lat=${s.lat.toFixed(4)}&lng=${s.lon.toFixed(4)}&radius=2&order_by=observed_on" target="_blank" rel="noopener">Recent wildlife & bloom sightings (iNaturalist)</a></li></ul></details>`;
  const box = document.createElement("div"); box.innerHTML = h;
  const anchor = body.querySelector("details"); [...box.children].forEach(ch => anchor ? body.insertBefore(ch, anchor) : body.appendChild(ch));
};

/* ---------- monthly field guide (Calendar tab) ---------- */
const MONTHS = {
  1: ["Bald eagles peak below The Dalles Dam and along the Klickitat; trumpeter and tundra swans at Ridgefield and Sauvie.", "Four-plus days below freezing builds ice at Multnomah, Latourell and Horsetail. Go the first clear morning after.", "Quadrantid meteors before dawn Jan 3–4.", "The sun sets far to the southwest: west-southwest views like Cape Horn line up with the river."],
  2: ["Sunrise behind Mt. Hood from the Washougal waterfront and Steigerwald around Feb 10–12.", "Waterfalls at full winter flow; grass widows open at Catherine Creek late in the month.", "Zodiacal light in the west after dusk from dark sites (Feb–Apr).", "Milky Way core returns as a pre-dawn target by month's end."],
  3: ["First wildflowers at Catherine Creek, Rowena and Memaloose; herons build nests at Maddax Woods.", "Equinox week: the sun rises and sets straight down east–west streets, so street 'henges' line up citywide.", "Snow geese leave Ridgefield and Sauvie; Rufous hummingbirds arrive."],
  4: ["Balsamroot and lupine at Rowena, Columbia Hills and Memaloose (mid-April to mid-May).", "Hood River Fruit Loop blossoms with Mt. Hood behind (mid-April).", "Lyrid meteors around Apr 22; Milky Way core in the pre-dawn southeast."],
  5: ["Dog Mountain and Hamilton balsamroot peak; rhododendrons at Crystal Springs.", "Eta Aquariid meteors pre-dawn early May.", "Milky Way season opens: dark-site trips around the new moon."],
  6: ["Longest days: sunset far to the northwest, so northwest-facing views like Rocky Butte and Council Crest light up.", "Milky Way core visible by midnight; short nights mean late sessions.", "Waterfalls drop; switch to alpine lakes as snow melts."],
  7: ["Alpine wildflowers at Bird Creek Meadows, Paradise and Mt. Hood meadows (late July–August).", "Milky Way core best of the year from Trout Lake, Goldendale and Timberline.", "Wildfire smoke can turn the sun red: swap vistas for a 300 mm sun over a ridge."],
  8: ["Perseids peak Aug 12–13; the radiant rises in the northeast.", "Vaux's swifts begin gathering at chimneys late in the month.", "Huckleberries and the last alpine flowers; smoke sunsets."],
  9: ["Vaux's swift roosts at dusk (peak early Sept to early Oct).", "Fall Chinook at the Bonneville ladder windows; hawk migration at Bonney Butte.", "Equinox street henges again; harvest moon over the Gorge."],
  10: ["Fall color peaks in the west Gorge late in the month; salmon spawn at Oxbow.", "Sandhill cranes stage at Ridgefield and Sauvie; fog season begins, so go above it.", "Orionid meteors around Oct 21; zodiacal light before dawn."],
  11: ["Last fall color early in the month; rains bring the waterfalls back.", "Snow geese and cranes in the Vancouver lowlands; morning inversions put Cape Horn and Women's Forum above the fog.", "Leonids around Nov 17. Orion rises by 9 PM; the Pleiades and Andromeda ride high in the evening.", "Larch Mountain Road gates for winter mid-month."],
  12: ["Geminids Dec 13–14: the best meteor shower of the year, bright and slow.", "Solstice sunsets far to the southwest; hoarfrost and freezing fog mornings.", "Bald eagles build along the Columbia; holiday lights on wet streets at blue hour."],
};
const _renderCal = renderCal;
renderCal = function () {
  _renderCal(); const el = $("#v-cal"), m = +laYMD(new Date()).slice(5, 7), nm = m % 12 + 1;
  const card = document.createElement("div"); card.className = "sect";
  const MN = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  card.innerHTML = `<h3>This month: ${MN[m]}</h3><ul class="plain">${MONTHS[m].map(x => `<li>${esc(x)}</li>`).join("")}</ul><details><summary>Next month: ${MN[nm]}</summary><ul class="plain">${MONTHS[nm].map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>`;
  el.insertBefore(card, el.children[2] || null);
};

/* ---------- wiring ---------- */
const _renderSkyWrap = render;
render = function () { _renderSkyWrap(); if (UI.view === "sky") renderSky(); };
document.addEventListener("click", e => { const t = e.target.closest("[data-skyt]"); if (!t) return; UI.skyT = +t.dataset.skyt; renderSky(); });
const _refreshSky = refresh;
refresh = async function (force) { await _refreshSky(force); loadSeven().then(() => UI.view === "sky" && renderSky()); };
loadSeven();
