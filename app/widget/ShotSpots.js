// ShotSpots widget for Scriptable (free, App Store). v2
// What to shoot next at home, where to go and when to leave, the week ahead, tonight's sky and wildlife peaks.
// Data: https://estaugaa.github.io/shotspots/feed/widget.json (refreshed by the GitHub pipeline every 30 min).
// Sizes: small, medium, large, and Lock Screen (rectangular / inline). Tapping a row opens that spot in ShotSpots.
// Widget parameter (long-press > Edit Widget > Parameter): "light" (default), "week" or "night" changes what the
// small widget shows.
// icon-color: deep-green; icon-glyph: mountain;

const FEED = "https://estaugaa.github.io/shotspots/feed/widget.json";
const APP = "https://estaugaa.github.io/shotspots/";
const CHECK = "https://api.github.com/repos/estaugaa/shotspots/actions/workflows/regress.yml/runs?per_page=1";
const C = {
  bg: Color.dynamic(new Color("#E3E9E6"), new Color("#10171C")),
  card: Color.dynamic(new Color("#D5DEDA"), new Color("#18222A")),
  ink: Color.dynamic(new Color("#1E2628"), new Color("#E5ECEA")),
  muted: Color.dynamic(new Color("#5B696B"), new Color("#93A3A6")),
  faint: Color.dynamic(new Color("#A9B6B4"), new Color("#34424B")),
  moss: Color.dynamic(new Color("#3D6A49"), new Color("#7DB38A")),
  gold: Color.dynamic(new Color("#B07612"), new Color("#E8B14F")),
  glow: Color.dynamic(new Color("#B0505E"), new Color("#E3909A")),
  river: Color.dynamic(new Color("#2E6580"), new Color("#77B2CF")),
  night: Color.dynamic(new Color("#3C5A86"), new Color("#8FA9D6")),
  bad: Color.dynamic(new Color("#A33A2B"), new Color("#F08C7A")),
};
const RULE_COLOR = { fog_above: C.river, fog_sea: C.river, color: C.glow, alignment: C.gold, dark: C.night, aurora: C.moss, birds: C.moss, wildlife: C.moss };

// ---------- data ----------
async function getJSON(url, file, maxAgeMin) {
  const fm = FileManager.local(), path = fm.joinPath(fm.cacheDirectory(), file);
  if (maxAgeMin && fm.fileExists(path) && (Date.now() - fm.modificationDate(path).getTime()) / 6e4 < maxAgeMin) return { j: JSON.parse(fm.readString(path)), stale: false };
  try { const r = new Request(url); r.timeoutInterval = 15; const j = await r.loadJSON(); fm.writeString(path, JSON.stringify(j)); return { j, stale: false }; }
  catch (e) { return fm.fileExists(path) ? { j: JSON.parse(fm.readString(path)), stale: true } : { j: null, stale: true }; }
}
async function health() {   // nightly site check on GitHub (public API, cached 3 h)
  const { j } = await getJSON(CHECK, "shotspots-check.json", 180);
  const r = j && j.workflow_runs && j.workflow_runs[0]; return r ? r.conclusion : null;
}

// ---------- formatting ----------
const hm = iso => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).replace(" ", "").toLowerCase();
const dayWord = iso => { const d = new Date(iso), n = Math.round((new Date(d.toDateString()) - new Date(new Date().toDateString())) / 864e5);
  return n === 0 ? "Today" : n === 1 ? "Tmrw" : d.toLocaleDateString("en-US", { weekday: "short" }); };
const ageMin = iso => Math.round((Date.now() - new Date(iso)) / 6e4);
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
const shortTitle = t => t.replace(/\s+(today|tomorrow|tonight|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*$/i, "");
const scoreColor = n => n == null ? C.muted : n >= 60 ? C.glow : n >= 35 ? C.gold : n >= 15 ? C.ink : C.muted;
const verdictColor = L => /Fog/.test(L.verdict || "") ? C.river : scoreColor(L.p_color);
const spotURL = id => id ? `${APP}#spot=${encodeURIComponent(id)}` : APP;

function text(st, s, size, color, bold) { const t = st.addText(s); t.font = bold ? Font.boldSystemFont(size) : Font.systemFont(size); t.textColor = color; return t; }
function pill(st, s, color) { const p = st.addStack(); p.setPadding(2, 6, 2, 6); p.cornerRadius = 6; p.backgroundColor = C.card; text(p, s, 10, color, true); return p; }

// the most useful line for a light window: where to go, else fog, else the odds
function goLine(L) {
  if (L.best) return { t: `${L.best.name}`, s: `${L.best.drive} min · leave ${hm(L.best.leave)} · ${L.best.p}%`, id: L.best.id };
  if (L.fogspot) return { t: `Above the fog: ${L.fogspot.name}`, s: `${L.fogspot.drive} min · fog ${L.p_fog}%`, id: L.fogspot.id };
  return { t: L.verdict || "–", s: L.p_color == null ? "forecast not out yet" : `colour ${L.p_color}% · fog ${L.p_fog ?? 0}%`, id: null };
}

// ---------- blocks ----------
function header(w, j, stale, check, big) {
  const h = w.addStack(); h.centerAlignContent();
  text(h, "ShotSpots", big ? 13 : 12, C.moss, true);
  if (big && j.now) { h.addSpacer(8); text(h, `${j.now.temp}° ${j.now.desc}${j.now.wind >= 15 ? ` · ${j.now.wind} mph` : ""}`, 11, j.now.rain ? C.river : C.muted); }
  h.addSpacer();
  const old = j.gen && ageMin(j.gen) > 90;
  if (stale || old) text(h, stale ? "offline" : `${Math.round(ageMin(j.gen) / 60)}h old`, 10, C.bad, true);
  else if (j.smoke) text(h, "smoke", 10, C.glow, true);
  else if (check === "failure") text(h, "●", 10, C.bad, true);
}

function lightHero(st, L) {   // big time, verdict, where to go
  const v = st.addStack(); v.layoutVertically(); v.url = spotURL(L.best && L.best.id);
  text(v, `${dayWord(L.at)} ${L.kind}`, 11, C.muted, true);
  text(v, hm(L.at), 24, C.ink, true);
  text(v, L.verdict || "–", 12, verdictColor(L), true).lineLimit = 1;
  const g = goLine(L);
  if (L.best || L.fogspot) { v.addSpacer(2); text(v, g.t, 11, C.ink, true).lineLimit = 1; text(v, g.s, 10, C.muted).lineLimit = 1; }
  return v;
}

function lightRow(st, L) {   // compact: "Tmrw sunrise 7:00am  Some chance  Cape Horn · leave 6:03"
  const r = st.addStack(); r.centerAlignContent(); r.spacing = 8; const g = goLine(L); r.url = spotURL(g.id);
  const a = r.addStack(); a.layoutVertically(); a.size = new Size(70, 0);
  text(a, `${dayWord(L.at)} ${L.kind}`, 10, C.muted, true); text(a, hm(L.at), 14, C.ink, true);
  const b = r.addStack(); b.layoutVertically();
  text(b, L.verdict || "–", 12, verdictColor(L), true).lineLimit = 1;
  text(b, L.best || L.fogspot ? `${g.t} · ${g.s}` : g.s, 10, C.muted).lineLimit = 1;
  r.addSpacer();
}

function weekStrip(st, days, compact) {   // 7 columns: day letter, sunrise and sunset bars, star on the best day
  if (!days || !days.length) return;
  const best = days.reduce((m, d, i) => Math.max(d.sunrise, d.sunset) > Math.max(days[m].sunrise, days[m].sunset) ? i : m, 0);
  const row = st.addStack(); row.bottomAlignContent();
  days.slice(0, 7).forEach((d, i) => {
    const col = row.addStack(); col.layoutVertically(); col.centerAlignContent();
    const bars = col.addStack(); bars.bottomAlignContent(); bars.spacing = 2;
    for (const n of [d.sunrise, d.sunset]) { const H = compact ? 16 : 24, b = bars.addStack(); b.size = new Size(compact ? 6 : 8, Math.max(2, Math.round(H * n / 100))); b.backgroundColor = n >= 15 ? scoreColor(n) : C.faint; b.cornerRadius = 2; }
    col.addSpacer(2);
    const lab = new Date(d.date + "T12:00:00").toLocaleDateString("en-US", { weekday: "narrow" });
    text(col, (i === best && Math.max(d.sunrise, d.sunset) >= 35 ? "★" : "") + (i === 0 ? "T" : lab), 9, i === best ? C.gold : C.muted, i === best);
    if (i < 6) row.addSpacer();
  });
}

function nightLine(st, n) {
  if (!n) return;
  const r = st.addStack(); r.centerAlignContent(); r.spacing = 6;
  text(r, "Tonight", 10, C.muted, true);
  text(r, n.verdict, 11, /dark/.test(n.verdict) ? C.night : C.ink, true);
  text(r, `${n.cloud}% cloud${n.moon != null ? ` · moon ${n.moon}%` : ""} · from ${n.from.toLowerCase().replace(" ", "")}`, 10, C.muted).lineLimit = 1;
}

function wildLine(st, wild) {
  if (!wild || !wild.length) return;
  const x = wild[0], r = st.addStack(); r.centerAlignContent(); r.spacing = 6; r.url = spotURL(x.id);
  text(r, "Wildlife", 10, C.muted, true);
  text(r, `${x.icon} ${x.name}${x.spot ? ` · ${x.spot}` : ""}`, 11, C.moss, true).lineLimit = 1;
}

function alertRow(st, a) {
  const r = st.addStack(); r.centerAlignContent(); r.spacing = 6; r.url = spotURL(a.spot);
  const bar = r.addStack(); bar.size = new Size(3, 26); bar.backgroundColor = RULE_COLOR[a.rule] || C.gold; bar.cornerRadius = 1.5;
  const v = r.addStack(); v.layoutVertically();
  text(v, shortTitle(a.title), 12, C.ink, true).lineLimit = 1;
  if (a.at) text(v, `${dayWord(a.at)} ${hm(a.at)}`, 10, C.muted).lineLimit = 1;
  r.addSpacer(); if (a.p != null) text(r, `${a.p}%`, 13, RULE_COLOR[a.rule] || C.gold, true);
}

// ---------- layouts ----------
async function build() {
  const [{ j, stale }, check] = await Promise.all([getJSON(FEED, "shotspots-widget.json"), health().catch(() => null)]);
  const fam = config.widgetFamily || "large", param = (args.widgetParameter || "light").toLowerCase();
  const w = new ListWidget(); w.url = APP; w.backgroundColor = C.bg; w.refreshAfterDate = new Date(Date.now() + 30 * 6e4);
  if (!j) { text(w, "ShotSpots", 13, C.ink, true); text(w, "No data yet. Check your connection.", 11, C.muted); return w; }
  const light = j.light || [], L = light[0], alerts = j.alerts || [], days = j.days || [];

  if (fam === "accessoryInline") {
    w.addText(alerts[0] ? `${shortTitle(alerts[0].title)} ${alerts[0].p ?? ""}%` : L ? `${cap(L.kind)} ${hm(L.at)} · ${L.verdict}${L.best ? " · leave " + hm(L.best.leave) : ""}` : "ShotSpots"); return w; }
  if (fam === "accessoryRectangular") {
    if (L) { text(w, `${cap(L.kind)} ${hm(L.at)} · ${L.verdict}`, 13, Color.white(), true).lineLimit = 1; const g = goLine(L);
      if (L.best || L.fogspot) { text(w, g.t, 12, Color.white()).lineLimit = 1; text(w, g.s, 11, Color.white()).lineLimit = 1; } else text(w, g.s, 12, Color.white()).lineLimit = 1; }
    else text(w, "ShotSpots", 13, Color.white(), true);
    if (alerts[0] && !(L && L.best)) text(w, shortTitle(alerts[0].title), 11, Color.white()).lineLimit = 1;
    return w;
  }

  w.setPadding(12, 14, 12, 14);
  if (fam === "small") {
    header(w, j, stale, check, false); w.addSpacer(4);
    if (param === "week" && days.length) { text(w, "This week", 11, C.muted, true); w.addSpacer(6); weekStrip(w, days, false); w.addSpacer(); text(w, "bars: sunrise | sunset", 9, C.muted); return w; }
    if (param === "night" && j.night) { text(w, "Tonight", 11, C.muted, true); text(w, j.night.verdict, 16, C.night, true); text(w, `${j.night.cloud}% cloud`, 11, C.muted); if (j.night.moon != null) text(w, `moon ${j.night.moon}%`, 11, C.muted); w.addSpacer(); return w; }
    if (L) lightHero(w, L);
    w.addSpacer();
    if (alerts[0]) { const a = text(w, shortTitle(alerts[0].title), 10, RULE_COLOR[alerts[0].rule] || C.gold, true); a.lineLimit = 2; }
    else if (j.wild && j.wild[0]) text(w, `${j.wild[0].icon} ${j.wild[0].name}`, 10, C.moss, true).lineLimit = 1;
    return w;
  }

  if (fam === "medium") {
    header(w, j, stale, check, true); w.addSpacer(6);
    const row = w.addStack(); row.spacing = 12;
    if (L) { const left = row.addStack(); left.size = new Size(128, 0); lightHero(left, L); }
    const right = row.addStack(); right.layoutVertically(); right.spacing = 6;
    light.slice(1, 3).forEach(x => lightRow(right, x));
    if (alerts[0]) alertRow(right, alerts[0]);
    w.addSpacer(); weekStrip(w, days, true);
    return w;
  }

  // large
  header(w, j, stale, check, true); w.addSpacer(8);
  text(w, "Next light", 11, C.muted, true); w.addSpacer(4);
  if (!light.length) text(w, "No forecast yet.", 11, C.muted);
  light.slice(0, 3).forEach(x => { lightRow(w, x); w.addSpacer(6); });
  w.addSpacer(4);
  if (days.length) { const h = w.addStack(); text(h, "This week", 11, C.muted, true); h.addSpacer(); text(h, "sunrise | sunset", 9, C.muted); w.addSpacer(4); weekStrip(w, days, false); w.addSpacer(8); }
  nightLine(w, j.night); w.addSpacer(4);
  wildLine(w, j.wild);
  if (alerts.length || (j.weekend || []).length) {
    w.addSpacer(8); text(w, alerts.length ? "Alerts" : "This weekend", 11, C.muted, true); w.addSpacer(4);
    (alerts.length ? alerts : j.weekend).slice(0, 2).forEach(a => { alertRow(w, a); w.addSpacer(4); });
  }
  w.addSpacer();
  const f = w.addStack(); f.centerAlignContent();
  text(f, `Updated ${hm(j.gen)}`, 9, C.muted); f.addSpacer();
  if (check) text(f, check === "success" ? "✓ nightly check" : check === "failure" ? "✗ nightly check failed" : `nightly check: ${check}`, 9, check === "failure" ? C.bad : C.muted, check === "failure");
  return w;
}

const widget = await build();
if (config.runsInWidget || config.runsInAccessoryWidget) Script.setWidget(widget);
else await widget.presentLarge();
Script.complete();
