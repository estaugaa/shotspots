/* Log outings from photos: read EXIF (time, GPS if present, lens, focal length) from a batch of JPEG/HEIF files,
   group them into outings, match each to a spot and a light window, and send them as outing logs after a quick review.
   Photos never leave the device: only the extracted summary is sent. */
"use strict";
const EXIFR = "https://cdn.jsdelivr.net/npm/exifr@7.1.3/dist/full.umd.js";
let IMP = [];   // sessions under review

function loadExifr() {
  if (window.exifr) return Promise.resolve();
  return new Promise((ok, bad) => { const s = document.createElement("script"); s.src = EXIFR; s.onload = ok; s.onerror = () => bad(new Error("couldn't load the photo reader")); document.head.appendChild(s); });
}
function lightKind(t, lat, lon) {
  const alt = sunPos(t, lat, lon).alt, am = sunPos(new Date(t.getTime() + 6e5), lat, lon).alt > alt;
  if (alt < -18) return "night";
  if (alt < -4) return am ? "blueAM" : "bluePM";
  if (alt < 6) return am ? "sunrise" : "sunset";
  if (alt < 15) return am ? "morning" : "afternoon";
  return "midday";
}
function lensName(x) {
  const m = (x.LensModel || "").match(/(\d+(?:-\d+)?)mm/);   // "XF16-50mmF2.8-4.8 R LM WR" -> "16-50"
  if (m) return m[1];
  if (x.LensModel) return x.LensModel.trim();
  const f = x.FocalLength; return f ? `${Math.round(f)} mm` : "";
}
async function readPhotos(files) {
  await loadExifr();
  const out = [];
  for (const f of files) {
    try {
      const x = await exifr.parse(f, { pick: ["DateTimeOriginal", "OffsetTimeOriginal", "FocalLength", "LensModel", "Model", "ExposureTime", "FNumber", "ISO", "GPSLatitude", "GPSLongitude", "GPSLatitudeRef", "GPSLongitudeRef", "GPSImgDirection"], gps: true });
      if (!x || !x.DateTimeOriginal) continue;
      let t = x.DateTimeOriginal;   // exifr reads it as device-local time; use the camera's offset when it recorded one
      if (x.OffsetTimeOriginal && /^[+-]\d\d:\d\d$/.test(x.OffsetTimeOriginal)) {
        const [h, m] = x.OffsetTimeOriginal.slice(1).split(":").map(Number), sign = x.OffsetTimeOriginal[0] === "-" ? -1 : 1;
        const wall = Date.UTC(t.getFullYear(), t.getMonth(), t.getDate(), t.getHours(), t.getMinutes(), t.getSeconds());
        t = new Date(wall - sign * (h * 60 + m) * 6e4);
      }
      out.push({ t, lat: x.latitude, lon: x.longitude, lens: lensName(x), fl: x.FocalLength, cam: x.Model || "", f, dir: x.GPSImgDirection != null ? Math.round(x.GPSImgDirection) % 360 : null });
    } catch (e) { }
  }
  return out.sort((a, b) => a.t - b.t);
}
function sessions(photos) {
  const ss = []; let cur = null;
  for (const p of photos) {
    const gap = cur ? (p.t - cur.end) / 6e4 : 1e9;
    const jump = cur && cur.lat != null && p.lat != null ? km(cur, p) : 0;
    if (!cur || gap > 90 || jump > 3) { cur = { start: p.t, end: p.t, photos: [] }; ss.push(cur); }
    cur.photos.push(p); cur.end = p.t;
    const g = cur.photos.filter(q => q.lat != null);
    if (g.length) { cur.lat = g[Math.floor(g.length / 2)].lat; cur.lon = g[Math.floor(g.length / 2)].lon; }
  }
  for (const s of ss) {
    const mid = new Date((s.start.getTime() + s.end.getTime()) / 2); s.mid = mid;
    const near = s.lat != null ? SPOTS.map(x => [km(s, x), x]).sort((a, b) => a[0] - b[0]) : [];
    s.spot = near.length && near[0][0] <= 1.5 ? near[0][1].id : null;
    s.cands = near.slice(0, 6).map(([d, x]) => [x.id, d]);
    const where = s.lat != null ? s : (s.spot ? byId[s.spot] : LOC);
    s.kind = lightKind(mid, where.lat, where.lon);
    const lenses = {}; s.photos.forEach(p => { if (p.lens) (lenses[p.lens] = lenses[p.lens] || []).push(p.fl); });
    s.lensTxt = Object.entries(lenses).map(([l, fs]) => { const a = Math.round(Math.min(...fs.filter(Boolean))), b = Math.round(Math.max(...fs.filter(Boolean)));
      return `${l}${isFinite(a) && /\d+-\d+/.test(l) ? ` at ${a === b ? a : a + "–" + b} mm` : ""} ×${fs.length}`; }).join("; ");
    s.rating = ""; s.sky = ""; s.fog = ""; s.color = ""; s.keep = true;
  }
  return ss;
}
const hmT = d => d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
const span = s => s.end - s.start < 6e4 ? hmT(s.start) : `${hmT(s.start)}–${hmT(s.end)}`;
function spotOptions(s) {
  const ids = new Set(s.cands.map(c => c[0])); const near = s.cands.map(([id, d]) => `<option value="${id}" ${id === s.spot ? "selected" : ""}>${esc(byId[id].name)} (${fmtKm(d)})</option>`).join("");
  const rest = SPOTS.filter(x => !ids.has(x.id)).sort((a, b) => a.name.localeCompare(b.name)).map(x => `<option value="${x.id}" ${x.id === s.spot ? "selected" : ""}>${esc(x.name)}</option>`).join("");
  return `<option value="">Pick the spot…</option>${near ? `<optgroup label="Nearest to the photos">${near}</optgroup><optgroup label="All spots">` : ""}${rest}${near ? "</optgroup>" : ""}`;
}
function renderImport(el) {
  const fmtD = d => d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }), fmtH = d => d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const noGps = IMP.filter(s => s.lat == null).length;
  el.querySelector(".sheetbody").innerHTML = `
    <p>${IMP.length} outing${IMP.length === 1 ? "" : "s"} found in ${IMP.reduce((a, s) => a + s.photos.length, 0)} photos.${noGps ? ` ${noGps === IMP.length ? "None" : noGps} had a location, so pick the spot where it's missing.` : ""}</p>
    ${IMP.map((s, i) => `<div class="impcard" data-i="${i}">
      <label class="impkeep"><input type="checkbox" data-k="keep" ${s.keep ? "checked" : ""}> <b>${fmtD(s.start)}, ${span(s)}</b></label>
      <p class="muted" style="margin:2px 0 6px;font-size:14px">${s.photos.length} photo${s.photos.length === 1 ? "" : "s"} · ${KSHORT[s.kind] || s.kind} light${s.dir != null && typeof facing === "function" ? " · facing " + facing(s.dir) : ""}${s.lensTxt ? " · " + esc(s.lensTxt) : ""}${s.lat != null ? "" : " · no location in the files"}</p>
      <select data-k="spot" aria-label="Spot">${spotOptions(s)}</select>
      <div class="impq"><span>How good</span>${chipGroup("rating" + i, [["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]], [s.rating], false)}</div>
      <div class="impq"><span>Sky</span>${chipGroup("sky" + i, [["clear", "Clear"], ["partly", "Partly"], ["overcast", "Overcast"], ["rain", "Rain"]], [s.sky], false)}</div>
      <div class="impq"><span>Fog</span>${chipGroup("fog" + i, [["yes", "Yes"], ["no", "No"]], [s.fog], false)}</div>
      <div class="impq"><span>Colour</span>${chipGroup("color" + i, [["none", "None"], ["some", "Some"], ["strong", "Strong"]], [s.color], false)}</div>
    </div>`).join("")}
    ${IMP.some(s => s.auto) ? `<p class="muted" style="font-size:14px">Sky, fog and colour were read from the photos. Fix anything that's off; how good it was is up to you.</p>` : ""}
    <button class="btn primary wide" id="impSave">Log ${IMP.filter(s => s.keep).length} outing${IMP.filter(s => s.keep).length === 1 ? "" : "s"}</button>
    <p class="muted" style="font-size:13px">Only the time, place, lens and your answers are sent; the photos stay on this device. Keepers are left at 0: edit them in the notes later if you track them.</p>`;
}
/* automatic scoring: read sky, fog and colour from the middle photo of each outing (the same reading as the conditions camera) */
async function autoRead(ss) {
  for (const s of ss) { const p = s.photos[Math.floor(s.photos.length / 2)];
    try { const im = await loadImg(p.f), a = analyse(im); s.sky = a.sky; s.fog = a.fog; s.color = a.colour; s.auto = a.m; URL.revokeObjectURL(im.src); } catch (e) { }
    const d = s.photos.map(q => q.dir).filter(x => x != null); s.dir = d.length ? d[Math.floor(d.length / 2)] : null; }
}
async function importFiles(files) {
  const el = ensureSheet("impSheet", "Log outings from photos"); el.hidden = false;
  el.querySelector(".sheetbody").innerHTML = `<p>Reading ${files.length} photos…</p>`;
  try {
    const ph = await readPhotos(files);
    if (!ph.length) { el.querySelector(".sheetbody").innerHTML = `<p>None of those files had a capture time. Pick the original JPEG or HEIF files, not edited exports or screenshots.</p><button class="btn wide" id="impAgain">Choose other photos</button>`; return; }
    IMP = sessions(ph); el.querySelector(".sheetbody").innerHTML = `<p>Reading the sky in ${IMP.length} outing${IMP.length === 1 ? "" : "s"}…</p>`;
    if (typeof analyse === "function") await autoRead(IMP);
    renderImport(el);
  } catch (err) { el.querySelector(".sheetbody").innerHTML = `<p>${esc(err.message || String(err))}. Check your connection and try again.</p><button class="btn wide" id="impAgain">Try again</button>`; }
}
async function openImport() {
  const el = ensureSheet("impSheet", "Log outings from photos");
  el.querySelector(".sheetbody").innerHTML = `
    <p>Pick the photos from a shoot (or several shoots). ShotSpots reads the time, the location if there is one, and the lens from each file, groups them into outings and matches each to a spot and a light window.</p>
    <label class="btn primary wide" style="justify-content:center">Choose photos<input type="file" id="impFiles" accept="image/jpeg,image/heic,image/heif,.jpg,.jpeg,.heic,.heif" multiple hidden></label>
    <p class="muted" style="font-size:14px"><b>From a camera:</b> pick the JPEGs (RAW files can't be read here). If your camera has no GPS, its maker's phone app can usually add location while paired (for Fujifilm, Location in the FUJIFILM XApp), or pick the spot by hand. Phone photos already carry their location. On a computer you can select straight from the SD card.</p>
    <p class="muted" style="font-size:14px"><b>On iPhone:</b> in the photo picker, tap <i>Options</i> and turn on <i>Location</i> if you see it; otherwise iOS may strip it.</p>`;
  el.hidden = false;
}
document.addEventListener("change", async e => {
  if (e.target.id === "impFiles") { const files = [...e.target.files]; if (files.length) importFiles(files); return; }
  const card = e.target.closest(".impcard"); if (!card) return; const s = IMP[+card.dataset.i];
  if (e.target.dataset.k === "keep") { s.keep = e.target.checked; $("#impSave").textContent = `Log ${IMP.filter(x => x.keep).length} outings`; }
  if (e.target.dataset.k === "spot") s.spot = e.target.value || null;
});
document.addEventListener("click", async e => {
  const t = e.target.closest("#impOpen,#impAgain,#impSave,.impcard [data-opt]"); if (!t) return;
  if (t.id === "impOpen" || t.id === "impAgain") return openImport();
  if (t.dataset.opt != null) { setTimeout(() => { const card = t.closest(".impcard"), s = IMP[+card.dataset.i], g = t.closest("[data-group-name]").dataset.groupName.replace(/\d+$/, "");
    s[g] = t.getAttribute("aria-pressed") === "true" ? t.dataset.opt : ""; }, 0); return; }
  if (t.id === "impSave") {
    const go = IMP.filter(s => s.keep); const miss = go.filter(s => !s.spot);
    if (miss.length) { toast(`Pick the spot for ${miss.length} outing${miss.length === 1 ? "" : "s"} first, or untick ${miss.length === 1 ? "it" : "them"}`); return; }
    for (const s of go) {
      const sp = byId[s.spot], h = hrrrRow(sp.id, s.mid), H = fd("hrrr");   // only the forecast still on hand for that hour counts as a prediction
      const pred = { kind: s.kind, imported: true, score: null, p_clear: h ? h.p_clear : null, p_fog: h ? h.p_fog : null, p_color: h ? h.p_color : null,
        hrrr_run: h && H ? H.run : null, lead_h: h && H ? Math.round((s.mid - new Date(H.run)) / 36e5) : null, photos: s.photos.length, lenses: s.lensTxt, auto: s.auto || null, heading: s.dir };
      OUTQ.push({ spot: sp.id, t: String(s.mid.getTime()), kind: s.kind, rating: s.rating, keepers: "0", sky: s.sky, fog: s.fog, color: s.color, species: "", ebird: "", sqm: "",
        notes: `Imported from ${s.photos.length} photo${s.photos.length === 1 ? "" : "s"}, ${span(s)}${s.lensTxt ? "; " + s.lensTxt : ""}${s.photos[0].cam ? "; " + s.photos[0].cam : ""}`, pred: JSON.stringify(pred) });
      LOG.unshift({ id: sp.id, t: s.mid.getTime(), c: `${s.photos.length} photo${s.photos.length === 1 ? "" : "s"}${s.rating ? ", " + s.rating + "/5" : ""}` });
    }
    store.set("outq", OUTQ); store.set("log", LOG.slice(0, 300));
    const left = await flushOutcomes(); $("#impSheet").hidden = true; IMP.forEach(s => s.photos.forEach(p => delete p.f)); IMP = [];
    toast(left ? `Saved ${go.length}; will send when online` : `Logged ${go.length} outing${go.length === 1 ? "" : "s"} and sent for checking`);
  }
});
/* entry point: next to the shot list */
const _renderSpotsP = renderSpots;
renderSpots = function () { _renderSpotsP();
  const host = $("#v-spots"); if (host && !host.querySelector("#impOpen")) host.insertAdjacentHTML("beforeend", `<button class="btn wide" id="impOpen" style="margin-top:14px">Log outings from photos</button>`); };
