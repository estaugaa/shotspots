/* Conditions camera: snap the sky/scene, and ShotSpots records where (GPS) and when, checks you're at a spot,
   reads the sky from the photo on the device (colour, cloud, haze), and sends a small thumbnail plus its own
   forecast for that moment, so predictions can be scored against what was really there.
   Photos are re-encoded on the device (which strips EXIF) and shown in the app for 48 hours without names. */
"use strict";
const CAM_MAX_KM = 1.5;
let CAM = null;   // current report under review

function camButton(spotId) { return `<button class="btn camb" data-cam="${spotId || ""}"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg> Report conditions</button>`; }
function hiddenInput() {
  let i = $("#camInput"); if (i) return i;
  document.body.insertAdjacentHTML("beforeend", `<input type="file" id="camInput" accept="image/*" capture="environment" hidden>`); return $("#camInput");
}
function where(timeout = 9000) {
  return new Promise(ok => { if (!navigator.geolocation) return ok(null);
    navigator.geolocation.getCurrentPosition(p => ok({ lat: p.coords.latitude, lon: p.coords.longitude, acc: Math.round(p.coords.accuracy) }), () => ok(null), { enableHighAccuracy: true, timeout, maximumAge: 0 }); });
}
async function loadImg(file) { const url = URL.createObjectURL(file); const im = new Image(); await new Promise((ok, bad) => { im.onload = ok; im.onerror = bad; im.src = url; }); return im; }
function thumb(im, max = 640) { const k = Math.min(1, max / Math.max(im.width, im.height)), c = document.createElement("canvas"); c.width = Math.round(im.width * k); c.height = Math.round(im.height * k);
  c.getContext("2d").drawImage(im, 0, 0, c.width, c.height); return c.toDataURL("image/jpeg", 0.72); }
/* read the sky: top 40% of the frame, 72x72 sample */
function analyse(im) {
  const N = 72, c = document.createElement("canvas"); c.width = N; c.height = N; const g = c.getContext("2d"); g.drawImage(im, 0, 0, N, N);
  const d = g.getImageData(0, 0, N, N).data; let n = 0, warm = 0, blue = 0, grey = 0, bright = 0, lum = [], all = [];
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const i = (y * N + x) * 4, r = d[i] / 255, gg = d[i + 1] / 255, b = d[i + 2] / 255, mx = Math.max(r, gg, b), mn = Math.min(r, gg, b), v = mx, s = mx ? (mx - mn) / mx : 0;
    let h = 0; if (mx !== mn) { h = mx === r ? ((gg - b) / (mx - mn)) % 6 : mx === gg ? (b - r) / (mx - mn) + 2 : (r - gg) / (mx - mn) + 4; h = (h * 60 + 360) % 360; }
    const L = 0.2126 * r + 0.7152 * gg + 0.0722 * b; all.push(L);
    if (y > N * 0.4) continue; n++; lum.push(L); bright += L;
    if (s > 0.35 && v > 0.3 && (h < 55 || h > 300)) warm++;
    else if (s > 0.22 && h > 185 && h < 250 && v > 0.35) blue++;
    else if (s < 0.14) grey++;
  }
  const mean = a => a.reduce((x, y) => x + y, 0) / a.length, sd = a => { const m = mean(a); return Math.sqrt(mean(a.map(x => (x - m) ** 2))); };
  const fw = warm / n, fb = blue / n, fg = grey / n, contrast = sd(all), skyB = bright / n;
  return {
    colour: fw > 0.22 ? "strong" : fw > 0.07 ? "some" : "none",
    sky: fb > 0.45 ? "clear" : fb > 0.15 || (fw > 0.1 && fg < 0.6) ? "partly" : "overcast",
    fog: contrast < 0.09 && skyB > 0.45 && fg > 0.6 ? "yes" : "no",
    m: { warm: +fw.toFixed(3), blue: +fb.toFixed(3), grey: +fg.toFixed(3), contrast: +contrast.toFixed(3), sky_brightness: +skyB.toFixed(3) },
  };
}
async function camStart(spotId) {
  const inp = hiddenInput(); inp.value = ""; inp.dataset.spot = spotId || "";
  CAM = { pos: where() };   // ask for location while the camera is open
  inp.click();
}
document.addEventListener("change", async e => {
  if (e.target.id !== "camInput" || !e.target.files[0]) return;
  const file = e.target.files[0], el = ensureSheet("camSheet", "Report conditions");
  el.querySelector(".sheetbody").innerHTML = `<p>Reading the photo and your location…</p>`; el.hidden = false;
  try {
    const im = await loadImg(file), a = analyse(im), img = thumb(im), pos = await CAM.pos, now = new Date();
    let shot = now; try { if (window.exifr) { const x = await exifr.parse(file, ["DateTimeOriginal"]); if (x && x.DateTimeOriginal) shot = x.DateTimeOriginal; } } catch (er) { }
    const ageMin = Math.abs(now - shot) / 6e4;
    const near = pos ? SPOTS.map(s => [km(pos, s), s]).sort((x, y) => x[0] - y[0]).slice(0, 5) : [];
    const pick = e.target.dataset.spot && byId[e.target.dataset.spot] ? byId[e.target.dataset.spot] : near.length && near[0][0] <= CAM_MAX_KM ? near[0][1] : null;
    const dist = pick && pos ? km(pos, pick) : null;
    const verified = !!(pos && dist != null && dist <= CAM_MAX_KM && ageMin <= 20);
    CAM = { ...CAM, img, a, pos, t: shot, spot: pick ? pick.id : "", near, dist, verified, ans: { sky: a.sky, fog: a.fog, color: a.colour } };
    camRender();
  } catch (er) { el.querySelector(".sheetbody").innerHTML = `<p>Couldn't read that photo. Try again, or pick a JPEG/HEIF.</p>`; }
});
function camRender() {
  const el = $("#camSheet"), c = CAM, sp = byId[c.spot];
  const opts = c.near.map(([d, s]) => `<option value="${s.id}" ${s.id === c.spot ? "selected" : ""}>${esc(s.name)} (${d < 1 ? Math.round(d * 1000) + " m" : d.toFixed(1) + " km"})</option>`).join("");
  const ver = c.verified ? `<span class="seasontag">Verified: ${Math.round(c.dist * 1000)} m from the spot, taken just now</span>`
    : `<span class="seasontag warn">${!c.pos ? "No location: allow location to verify" : c.dist == null ? "Pick the spot" : c.dist > CAM_MAX_KM ? `You're ${c.dist.toFixed(1)} km from the nearest spot` : "Photo isn't from the last 20 minutes"}</span>`;
  el.querySelector(".sheetbody").innerHTML = `
    <img src="${c.img}" alt="Your photo" class="camimg">
    <p style="margin:6px 0">${ver}</p>
    <select id="camSpot" aria-label="Spot">${opts || `<option value="">No spots nearby</option>`}</select>
    <p class="muted" style="font-size:14px;margin:8px 0 2px">Read from the photo; fix anything that's off:</p>
    <div class="impq"><span>Sky</span>${chipGroup("camsky", [["clear", "Clear"], ["partly", "Partly"], ["overcast", "Overcast"], ["rain", "Rain"]], [c.ans.sky], false)}</div>
    <div class="impq"><span>Fog</span>${chipGroup("camfog", [["yes", "Yes"], ["no", "No"]], [c.ans.fog], false)}</div>
    <div class="impq"><span>Colour</span>${chipGroup("camcolor", [["none", "None"], ["some", "Some"], ["strong", "Strong"]], [c.ans.color], false)}</div>
    <label class="impkeep" style="margin:10px 0"><input type="checkbox" id="camShare" checked> Show this photo in ShotSpots for 48 hours (no name attached)</label>
    <button class="btn primary wide" id="camSend" ${c.spot ? "" : "disabled"}>Send report</button>
    ${sp ? `<p class="muted" style="font-size:13px">ShotSpots' forecast for ${esc(sp.name)} right now goes with it, so the report also checks the prediction.</p>` : ""}`;
}
document.addEventListener("change", e => { if (e.target.id === "camSpot" && CAM) { CAM.spot = e.target.value; const s = byId[CAM.spot];
  CAM.dist = s && CAM.pos ? km(CAM.pos, s) : null; CAM.verified = !!(CAM.pos && CAM.dist != null && CAM.dist <= CAM_MAX_KM && Math.abs(new Date() - CAM.t) / 6e4 <= 20); camRender(); } });
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-cam]"); if (b) { e.preventDefault(); return camStart(b.dataset.cam); }
  const o = e.target.closest("#camSheet [data-opt]"); if (o && CAM) { setTimeout(() => { const g = o.closest("[data-group-name]").dataset.groupName.replace("cam", ""); CAM.ans[g === "color" ? "color" : g] = o.getAttribute("aria-pressed") === "true" ? o.dataset.opt : ""; }, 0); return; }
  if (e.target.closest("#camSend") && CAM && CAM.spot) {
    const s = byId[CAM.spot], h = hrrrRow(s.id, CAM.t), H = fd("hrrr");
    const pred = { p_clear: h ? h.p_clear : null, p_fog: h ? h.p_fog : null, p_color: h ? h.p_color : null, hrrr_run: h && H ? H.run : null, lead_h: h && H ? Math.round((CAM.t - new Date(H.run)) / 36e5) : null };
    const share = $("#camShare").checked;
    const ok = await postForm("conditions", { spot: s.id, t: String(CAM.t.getTime()), lat: CAM.pos ? CAM.pos.lat.toFixed(5) : "", lon: CAM.pos ? CAM.pos.lon.toFixed(5) : "", acc: CAM.pos ? CAM.pos.acc : "",
      dist_m: CAM.dist != null ? Math.round(CAM.dist * 1000) : "", verified: CAM.verified ? "1" : "0", sky: CAM.ans.sky, fog: CAM.ans.fog, color: CAM.ans.color,
      auto: JSON.stringify(CAM.a), pred: JSON.stringify(pred), share: share ? "1" : "0", img: share ? CAM.img : "" });
    $("#camSheet").hidden = true; toast(ok ? "Thanks: report sent" + (share ? ". It'll show on the spot within the hour." : "") : "Couldn't send. Check your connection and try again."); CAM = null;
  }
});
/* entry points: the Plan screen and every spot page */
const _renderNowC = renderNow;
renderNow = function () { _renderNowC(); const d = $("#winDetail"); if (d && !d.querySelector(".camb") && (d.querySelector(".verdict") || 0)) d.querySelector(".verdict").insertAdjacentHTML("beforebegin", `<div style="float:right;margin-top:2px">${camButton("")}</div>`); };
const _openC = openSpot;
openSpot = function (id) { _openC(id); const b = $("#sheetBody"); const row = b && b.querySelector("#outcomeBtn"); if (row && !b.querySelector(".camb")) row.insertAdjacentHTML("afterend", camButton(id)); };
