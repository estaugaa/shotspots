/* Photos on the spot page, all viewed in-app (tap → full-screen viewer with credit and licence):
   - "Right now from people there": conditions reports from the in-app camera (last 48 h), with what ShotSpots predicted
   - "Best photos here", ranked, up to 8, from keyless sources:
       Wikimedia Commons photos taken within ~600–900 m. Featured / Quality / Valued images are juried by Commons
         reviewers, so they're badged and shown first (the closest free stand-in for "professional").
       iNaturalist research-grade observations here, by number of faves (wildlife and wildflower spots).
       Flickr photos under Creative Commons licences, through Openverse (no Flickr key needed; matched by place name,
         since Openverse has no map search, and not ranked by faves).
     With a Flickr key (Pro), the pipeline's most-interesting-by-location list (feed/photos.json) is used instead. */
"use strict";
const COMMONS = "https://commons.wikimedia.org/w/api.php";
const JURY = { "Featured pictures on Wikimedia Commons": ["Featured", 30], "Quality images": ["Quality", 20], "Valued images sorted by promotion date": ["Valued", 10], "Valued images": ["Valued", 10] };
const PH_TTL = 7 * 864e5, __ph = {};
const phStrip = h => { const d = document.createElement("div"); d.innerHTML = h || ""; return (d.textContent || "").trim(); };
const phGet = k => { try { const v = JSON.parse(localStorage.getItem("ss2:ph:" + k) || "null"); return v && Date.now() - v.at < PH_TTL ? v.list : null; } catch (e) { return null; } };
const phPut = (k, list) => { try { localStorage.setItem("ss2:ph:" + k, JSON.stringify({ at: Date.now(), list })); } catch (e) { } };
const phRadius = s => s.cats.some(c => ["vista", "mountain"].includes(c)) ? 900 : 600;

async function commonsNear(s) {
  const q = new URLSearchParams({ action: "query", format: "json", origin: "*", generator: "geosearch", ggscoord: `${s.lat}|${s.lon}`, ggsradius: phRadius(s), ggslimit: 50, ggsnamespace: 6,
    prop: "imageinfo|categories", iiprop: "url|extmetadata|mime|size", iiurlwidth: 480, iiextmetadatafilter: "Artist|LicenseShortName|ObjectName",
    clcategories: Object.keys(JURY).map(c => "Category:" + c).join("|"), cllimit: "max" });
  const j = await (await fetch(`${COMMONS}?${q}`)).json();
  return Object.values((j.query && j.query.pages) || {}).map(pg => {
    const ii = (pg.imageinfo || [])[0]; if (!ii || ii.mime !== "image/jpeg" || ii.width < 1200) return null;
    const m = ii.extmetadata || {}, cats = (pg.categories || []).map(c => c.title.replace("Category:", ""));
    const jury = cats.map(c => JURY[c]).filter(Boolean).sort((a, b) => b[1] - a[1])[0] || null;
    return { src: "Wikimedia Commons", thumb: ii.thumburl, big: ii.thumburl.replace(/\/480px-/, "/1600px-"), page: ii.descriptionurl,
      title: phStrip(m.ObjectName && m.ObjectName.value) || pg.title.replace(/^File:|\.[a-z]+$/gi, ""), by: phStrip(m.Artist && m.Artist.value).slice(0, 60) || "unknown",
      lic: (m.LicenseShortName && m.LicenseShortName.value) || "", badge: jury ? jury[0] : null, rank: jury ? jury[1] : Math.min(6, ii.width * ii.height / 4e6) };
  }).filter(Boolean);
}
async function inatNearP(s) {
  const base = `https://api.inaturalist.org/v1/observations?lat=${s.lat}&lng=${s.lon}&radius=${phRadius(s) / 1000}&photos=true&quality_grade=research&photo_license=cc-by,cc-by-nc,cc-by-sa,cc-by-nc-sa,cc0&per_page=30`;
  let r = await fetch(base + "&order_by=votes&order=desc"); if (!r.ok) r = await fetch(base);   // faves order, else newest
  const j = await r.json();
  return (j.results || []).filter(o => o.photos && o.photos[0]).map(o => { const p = o.photos[0], name = o.taxon ? (o.taxon.preferred_common_name || o.taxon.name) : "Observation";
    return { src: "iNaturalist", thumb: p.url.replace("square", "medium"), big: p.url.replace("square", "large"), page: o.uri, title: name.replace(/^./, c => c.toUpperCase()),
      by: (p.attribution || "").replace(/^\(c\)\s*/i, "").replace(/,.*$/, "").slice(0, 60), lic: (p.license_code || "").toUpperCase().replace(/^CC-/, "CC "), faves: o.faves_count || 0,
      badge: (o.faves_count || 0) >= 3 ? `♥ ${o.faves_count}` : null, rank: 4 + Math.min(12, (o.faves_count || 0) * 2) }; })
    .sort((a, b) => b.faves - a.faves).slice(0, 6);
}
const GENERIC = new Set(["state", "park", "national", "regional", "county", "trail", "falls", "lake", "river", "creek", "point", "viewpoint", "mountain", "wildlife", "refuge", "area", "recreation", "historic", "bridge", "garden", "scout", "pick", "from", "with", "over", "under", "the"]);
async function openverseNear(s) {
  const core = s.name.replace(/^Scout pick:\s*/i, "").replace(/\(.*?\)/g, "").split(/[:&,]| from | at /)[0].trim();
  const keys = core.toLowerCase().split(/[^a-z']+/).filter(w => w.length >= 4 && !GENERIC.has(w)); if (!keys.length) return [];
  const r = await fetch(`https://api.openverse.org/v1/images/?q=${encodeURIComponent(core)}&source=flickr&page_size=20&mature=false`); if (!r.ok) return [];
  const j = await r.json();
  return (j.results || []).filter(x => { const t = ((x.title || "") + " " + (x.tags || []).map(g => g.name).join(" ")).toLowerCase(); return keys.some(k => t.includes(k)) && (x.width || 2000) >= 1000; })
    .slice(0, 6).map(x => ({ src: "Flickr", thumb: x.thumbnail, big: x.url, page: x.foreign_landing_url, title: x.title || core, by: (x.creator || "").slice(0, 60),
      lic: `CC ${String(x.license || "").toUpperCase()} ${x.license_version || ""}`.trim(), badge: "Flickr", rank: 5 }));
}
function flickrKeyed(s) { const F = ((fd("photos") || {}).spots || {})[s.id]; if (!F || !F.length) return null;
  return F.slice(0, 8).map((p, i) => ({ src: "Flickr", thumb: p.thumb, big: p.big || p.thumb, page: p.page, title: p.title, by: p.by, lic: p.lic || "", badge: "Flickr", rank: 9 - i })); }

async function bestPhotos(s) {
  if (__ph[s.id]) return __ph[s.id];
  const cached = phGet(s.id); if (cached) return (__ph[s.id] = Promise.resolve(cached));
  return (__ph[s.id] = (async () => {
    const life = s.cats.some(c => ["birds", "wildlife", "wildflowers"].includes(c));
    const [com, nat] = await Promise.all([commonsNear(s).catch(() => []), life ? inatNearP(s).catch(() => []) : Promise.resolve([])]);
    let fl = flickrKeyed(s);
    const juried = com.filter(p => p.badge).length;
    if (!fl && juried + nat.length < 6) fl = await openverseNear(s).catch(() => []);   // Openverse's anonymous limit is low, so only when needed
    let all = [...com, ...nat, ...(fl || [])].sort((a, b) => b.rank - a.rank);
    if (all.length < 4 && !life) all = all.concat(await inatNearP(s).catch(() => [])).sort((a, b) => b.rank - a.rank);
    all = all.slice(0, 8); phPut(s.id, all); return all;
  })());
}

/* ---------- in-app viewer ---------- */
let LB = null;
function lbOpen(list, i) {
  LB = { list, i }; let el = $("#lightbox");
  if (!el) { document.body.insertAdjacentHTML("beforeend", `<div id="lightbox" role="dialog" aria-modal="true" aria-label="Photo"><button class="lbx" id="lbClose" aria-label="Close">✕</button><button class="lbnav" id="lbPrev" aria-label="Previous photo">‹</button><figure><img id="lbImg" alt=""><figcaption id="lbCap"></figcaption></figure><button class="lbnav" id="lbNext" aria-label="Next photo">›</button></div>`); el = $("#lightbox");
    let x0 = null; el.addEventListener("touchstart", e => { x0 = e.touches[0].clientX; }, { passive: true });
    el.addEventListener("touchend", e => { if (x0 == null) return; const dx = e.changedTouches[0].clientX - x0; x0 = null; if (Math.abs(dx) > 50) lbStep(dx < 0 ? 1 : -1); }); }
  el.hidden = false; lbShow();
}
function lbShow() { const p = LB.list[LB.i], img = $("#lbImg"); img.src = p.thumb; img.alt = p.title; const hi = new Image(); hi.onload = () => { if (LB && LB.list[LB.i] === p) img.src = p.big; }; hi.src = p.big;
  $("#lbCap").innerHTML = `<b>${esc(p.title)}</b><br>${esc(p.by)}${p.lic ? " · " + esc(p.lic) : ""} · <a href="${p.page}" target="_blank" rel="noopener">${esc(p.src)}</a><span class="muted"> · ${LB.i + 1} of ${LB.list.length}</span>`;
  $("#lbPrev").hidden = LB.i === 0; $("#lbNext").hidden = LB.i === LB.list.length - 1; }
function lbStep(d) { if (!LB) return; const n = LB.i + d; if (n < 0 || n >= LB.list.length) return; LB.i = n; lbShow(); }
function lbClose() { const el = $("#lightbox"); if (el) el.hidden = true; LB = null; }
document.addEventListener("click", e => {
  const t = e.target.closest("[data-ph],#lbClose,#lbPrev,#lbNext,#lightbox"); if (!t) return;
  if (t.dataset.ph != null) { e.preventDefault(); const box = t.closest(".photostrip"); return lbOpen(box._list, +t.dataset.ph); }
  if (t.id === "lbPrev") return lbStep(-1); if (t.id === "lbNext") return lbStep(1);
  if (t.id === "lbClose" || e.target.id === "lightbox") return lbClose();
});
document.addEventListener("keydown", e => { if (!LB) return; if (e.key === "Escape") lbClose(); if (e.key === "ArrowRight") lbStep(1); if (e.key === "ArrowLeft") lbStep(-1); });

/* ---------- spot page ---------- */
const phAgo = t => { const m = Math.round((Date.now() - new Date(t)) / 6e4); return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };
function predCheck(r) {
  const p = r.pred || {}, out = [];
  if (p.p_color != null && r.color) out.push(`colour ${p.p_color}% → ${r.color}${(p.p_color >= 50) === (r.color !== "none") ? " ✓" : " ✗"}`);
  if (p.p_fog != null && r.fog) out.push(`fog ${p.p_fog}% → ${r.fog}${(p.p_fog >= 50) === (r.fog === "yes") ? " ✓" : " ✗"}`);
  if (p.p_clear != null && r.sky) out.push(`clear ${p.p_clear}% → ${r.sky}${(p.p_clear >= 50) === (r.sky === "clear") ? " ✓" : " ✗"}`);
  return out.join(" · ");
}
function strip(list) { return `<div class="photostrip">${list.map((p, i) => `<button class="ph" data-ph="${i}" aria-label="${esc(p.title)}, by ${esc(p.by)}"><img src="${p.thumb}" alt="" loading="lazy">${p.badge ? `<span class="jury">${esc(p.badge)}</span>` : ""}<figcaption>${esc(p.by)}${p.lic ? ` · ${esc(p.lic)}` : ""}</figcaption></button>`).join("")}</div>`; }
function reportsHtml(s) {
  const R = ((fd("reports") || {}).reports || []).filter(r => r.spot === s.id); if (!R.length) return "";
  return `<h3>Right now from people there</h3>${strip(R.slice(0, 6).map(r => ({ thumb: "feed/" + r.img, big: "feed/" + r.img, page: "#", src: "ShotSpots report", title: `${phAgo(r.at)} at ${s.name}`, by: [r.sky, r.fog === "yes" ? "fog" : "", r.color && r.color !== "none" ? r.color + " colour" : ""].filter(Boolean).join(", "), lic: predCheck(r), badge: r.verified ? "Verified" : null })))}`
    .replace('<div class="photostrip">', `<div class="photostrip" data-rep="${s.id}">`);
}
async function photosInto(s, box) {
  const head = `<h3>Best photos here</h3>`;
  box.innerHTML = reportsHtml(s) + head + `<p class="muted" style="font-size:14px">Looking for photos taken here…</p>`; wire(box, s, []);
  const list = await bestPhotos(s); if (!box.isConnected) return;
  const srcs = [...new Set(list.map(p => p.src))];
  box.innerHTML = reportsHtml(s) + head + (list.length ? strip(list) + `<p class="muted" style="font-size:13px">${srcs.join(", ")}. <b>Featured</b> and <b>Quality</b> photos were picked by Commons reviewers; ♥ counts are iNaturalist faves. Tap a photo to see it large with its credit.</p>`
    : `<p class="muted" style="font-size:14px">No openly licensed photos from this exact spot yet. Your conditions reports will show up here.</p>`);
  wire(box, s, list);
}
function wire(box, s, list) { const st = box.querySelectorAll(".photostrip"); const rep = box.querySelector("[data-rep]");
  st.forEach(x => { x._list = x === rep ? ((fd("reports") || {}).reports || []).filter(r => r.spot === s.id).slice(0, 6).map(r => ({ thumb: "feed/" + r.img, big: "feed/" + r.img, page: "#", src: "ShotSpots report", title: `${phAgo(r.at)} at ${s.name}`, by: [r.sky, r.fog === "yes" ? "fog" : "", r.color && r.color !== "none" ? r.color + " colour" : ""].filter(Boolean).join(", "), lic: predCheck(r) })) : list; }); }
const _openP = openSpot;
openSpot = function (id) {
  _openP(id); const s = byId[id], b = $("#sheetBody"); if (!s || !b || b.querySelector(".photosbox")) return;
  const anchor = b.querySelector(".prose"); const box = document.createElement("div"); box.className = "photosbox";
  if (anchor) anchor.after(box); else b.appendChild(box);
  photosInto(s, box);
};
