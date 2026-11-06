/* Photos on the spot page:
   - "Right now": conditions reports from the in-app camera (last 48 h), with what ShotSpots predicted
   - "Best photos here": Wikimedia Commons photos taken within ~600 m; Featured / Quality / Valued images are
     juried by Commons reviewers, so they're badged and shown first. Credit and licence come from Commons.
   - Flickr's most interesting photos here, when the pipeline has a Flickr key (feed/photos.json). */
"use strict";
const COMMONS = "https://commons.wikimedia.org/w/api.php";
const JURY = { "Featured pictures on Wikimedia Commons": ["Featured", 3], "Quality images": ["Quality", 2], "Valued images sorted by promotion date": ["Valued", 1], "Valued images": ["Valued", 1] };
const __commons = {};
const phStrip = h => { const d = document.createElement("div"); d.innerHTML = h || ""; return (d.textContent || "").trim(); };
async function commonsNear(s) {
  if (__commons[s.id]) return __commons[s.id];
  const r = s.cats.some(c => ["vista", "mountain"].includes(c)) ? 900 : 600;
  const q = new URLSearchParams({ action: "query", format: "json", origin: "*", generator: "geosearch", ggscoord: `${s.lat}|${s.lon}`, ggsradius: r, ggslimit: 50, ggsnamespace: 6,
    prop: "imageinfo|categories", iiprop: "url|extmetadata|mime|size", iiurlwidth: 480, iiextmetadatafilter: "Artist|LicenseShortName|ObjectName|DateTimeOriginal",
    clcategories: Object.keys(JURY).map(c => "Category:" + c).join("|"), cllimit: "max" });
  const p = fetch(`${COMMONS}?${q}`).then(r => r.json()).then(j => Object.values((j.query && j.query.pages) || {}).map(pg => {
    const ii = (pg.imageinfo || [])[0]; if (!ii || ii.mime !== "image/jpeg" || ii.width < 1200) return null;
    const m = ii.extmetadata || {}, cats = (pg.categories || []).map(c => c.title.replace("Category:", ""));
    const jury = cats.map(c => JURY[c]).filter(Boolean).sort((a, b) => b[1] - a[1])[0] || null;
    return { thumb: ii.thumburl, page: ii.descriptionurl, title: phStrip(m.ObjectName && m.ObjectName.value) || pg.title.replace(/^File:|\.[a-z]+$/gi, ""),
      by: phStrip(m.Artist && m.Artist.value).slice(0, 60) || "unknown", lic: (m.LicenseShortName && m.LicenseShortName.value) || "", jury: jury ? jury[0] : null, rank: jury ? jury[1] : 0, px: ii.width * ii.height };
  }).filter(Boolean).sort((a, b) => b.rank - a.rank || b.px - a.px).slice(0, 10)).catch(() => []);
  return (__commons[s.id] = p);
}
const phAgo = t => { const m = Math.round((Date.now() - new Date(t)) / 6e4); return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };
function predCheck(r) {
  const p = r.pred || {}, out = [];
  if (p.p_color != null && r.color) out.push(`colour ${p.p_color}% → ${r.color}${(p.p_color >= 50) === (r.color !== "none") ? " ✓" : " ✗"}`);
  if (p.p_fog != null && r.fog) out.push(`fog ${p.p_fog}% → ${r.fog}${(p.p_fog >= 50) === (r.fog === "yes") ? " ✓" : " ✗"}`);
  if (p.p_clear != null && r.sky) out.push(`clear ${p.p_clear}% → ${r.sky}${(p.p_clear >= 50) === (r.sky === "clear") ? " ✓" : " ✗"}`);
  return out.join(" · ");
}
function reportsHtml(s) {
  const R = ((fd("reports") || {}).reports || []).filter(r => r.spot === s.id); if (!R.length) return "";
  return `<h3>Right now from people there</h3><div class="photostrip">${R.slice(0, 6).map(r => `<figure class="ph"><img src="feed/${r.img}" alt="Conditions at ${esc(s.name)}" loading="lazy">
    <figcaption><b>${phAgo(r.at)}</b>${r.verified ? " · verified" : ""}<br>${[r.sky, r.fog === "yes" ? "fog" : "", r.color && r.color !== "none" ? r.color + " colour" : ""].filter(Boolean).join(", ")}${predCheck(r) ? `<br><small>${esc(predCheck(r))}</small>` : ""}</figcaption></figure>`).join("")}</div>`;
}
function flickrHtml(s) {
  const F = ((fd("photos") || {}).spots || {})[s.id]; if (!F || !F.length) return "";
  return `<p class="label">Most interesting on Flickr</p><div class="photostrip">${F.slice(0, 8).map(p => `<a class="ph" href="${p.page}" target="_blank" rel="noopener"><img src="${p.thumb}" alt="${esc(p.title)}" loading="lazy"><figcaption>${esc(p.by)}</figcaption></a>`).join("")}</div>`;
}
async function photosInto(s, box) {
  box.innerHTML = reportsHtml(s) + `<h3>Best photos here</h3><p class="muted" style="font-size:14px">Looking for photos taken here…</p>` + flickrHtml(s);
  const list = await commonsNear(s); if (!box.isConnected) return;
  const best = list.length ? `<div class="photostrip">${list.map(p => `<a class="ph" href="${p.page}" target="_blank" rel="noopener"><img src="${p.thumb}" alt="${esc(p.title)}" loading="lazy">${p.jury ? `<span class="jury">${p.jury}</span>` : ""}<figcaption>${esc(p.by)}${p.lic ? ` · ${esc(p.lic)}` : ""}</figcaption></a>`).join("")}</div>
    <p class="muted" style="font-size:13px">From Wikimedia Commons, taken within about ${s.cats.some(c => ["vista", "mountain"].includes(c)) ? 900 : 600} m. <b>Featured</b> and <b>Quality</b> images are juried by Commons reviewers. Tap a photo for its full credit and licence.</p>`
    : `<p class="muted" style="font-size:14px">No juried or high-resolution photos from this exact spot on Wikimedia Commons yet.</p>`;
  box.innerHTML = reportsHtml(s) + `<h3>Best photos here</h3>` + best + flickrHtml(s);
}
const _openP = openSpot;
openSpot = function (id) {
  _openP(id); const s = byId[id], b = $("#sheetBody"); if (!s || !b || b.querySelector(".photosbox")) return;
  const anchor = b.querySelector(".prose"); const box = document.createElement("div"); box.className = "photosbox";
  if (anchor) anchor.after(box); else b.appendChild(box);
  photosInto(s, box);
};
