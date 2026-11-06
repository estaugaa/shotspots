// ShotSpots widget for Scriptable (free, App Store). Shows the next light at home with its odds, your top alerts
// and the weekend plan, from https://shotspots-eric.netlify.app/feed/widget.json (refreshed by the pipeline).
// Sizes: small, medium, large, and Lock Screen (rectangular / inline). Tap opens ShotSpots.
// icon-color: deep-green; icon-glyph: mountain;

const FEED = "https://shotspots-eric.netlify.app/feed/widget.json";
const APP = "https://shotspots-eric.netlify.app/";
const C = {
  bg: Color.dynamic(new Color("#E3E9E6"), new Color("#10171C")),
  ink: Color.dynamic(new Color("#1E2628"), new Color("#E5ECEA")),
  muted: Color.dynamic(new Color("#5B696B"), new Color("#93A3A6")),
  moss: Color.dynamic(new Color("#3D6A49"), new Color("#7DB38A")),
  gold: Color.dynamic(new Color("#B07612"), new Color("#E8B14F")),
  glow: Color.dynamic(new Color("#B0505E"), new Color("#E3909A")),
  river: Color.dynamic(new Color("#2E6580"), new Color("#77B2CF")),
  night: Color.dynamic(new Color("#3C5A86"), new Color("#8FA9D6")),
};
const RULE_COLOR = { fog_above: C.river, color: C.glow, alignment: C.gold, dark: C.night, aurora: C.moss, wildlife: C.moss, fallcolor: C.gold };

async function load() {
  const fm = FileManager.local(), path = fm.joinPath(fm.cacheDirectory(), "shotspots-widget.json");
  try {
    const r = new Request(FEED); r.timeoutInterval = 15;
    const j = await r.loadJSON(); fm.writeString(path, JSON.stringify(j)); return { j, stale: false };
  } catch (e) {
    if (fm.fileExists(path)) return { j: JSON.parse(fm.readString(path)), stale: true };
    return { j: null, stale: true };
  }
}
const hm = iso => { const d = new Date(iso); return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).replace(" ", "").toLowerCase(); };
const dayWord = iso => { const d = new Date(iso), t = new Date(); const a = new Date(d.toDateString()), b = new Date(t.toDateString());
  const n = Math.round((a - b) / 864e5); return n === 0 ? "Today" : n === 1 ? "Tmrw" : d.toLocaleDateString("en-US", { weekday: "short" }); };
const pct = p => p == null ? "–" : `${p}%`;
// alert titles carry their own day/time ("... Sat Nov 7 6:52am"); trim it for small spaces
const shortTitle = t => t.replace(/\s+(today|tomorrow|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*$/i, "");

function text(stack, s, size, color, bold) { const t = stack.addText(s); t.font = bold ? Font.boldSystemFont(size) : Font.systemFont(size); t.textColor = color; return t; }

function lightBlock(st, L, compact) {
  const v = st.addStack(); v.layoutVertically();
  text(v, `${dayWord(L.at)} ${L.kind}`, compact ? 11 : 12, C.muted, true);
  text(v, hm(L.at), compact ? 22 : 26, C.ink, true);
  const odds = v.addStack(); odds.spacing = 6;
  text(odds, `colour ${pct(L.p_color)}`, 11, C.glow, true);
  text(odds, `fog ${pct(L.p_fog)}`, 11, C.river, true);
  if (!compact) text(odds, `clear ${pct(L.p_clear)}`, 11, C.moss, true);
  return v;
}

function alertRow(st, a, lines) {
  const r = st.addStack(); r.centerAlignContent(); r.spacing = 6;
  const bar = r.addStack(); bar.size = new Size(3, lines > 1 ? 30 : 16); bar.backgroundColor = RULE_COLOR[a.rule] || C.gold; bar.cornerRadius = 1.5;
  const v = r.addStack(); v.layoutVertically();
  const t = text(v, shortTitle(a.title), 12, C.ink, true); t.lineLimit = 1;
  if (lines > 1 && a.at) { const s = text(v, `${dayWord(a.at)} ${hm(a.at)}`, 10, C.muted); s.lineLimit = 1; }
  r.addSpacer();
  if (a.p != null) text(r, pct(a.p), 13, RULE_COLOR[a.rule] || C.gold, true);
}

async function build() {
  const { j, stale } = await load();
  const fam = config.widgetFamily || "large";
  const w = new ListWidget(); w.url = APP; w.backgroundColor = C.bg;
  w.refreshAfterDate = new Date(Date.now() + 30 * 60e3);
  if (!j) { text(w, "ShotSpots", 13, C.ink, true); text(w, "No data yet. Check your connection.", 11, C.muted); return w; }
  const L = (j.light || [])[0], alerts = j.alerts || [], wk = j.weekend || [];

  if (fam === "accessoryInline") { w.addText(alerts[0] ? `${shortTitle(alerts[0].title)} ${pct(alerts[0].p)}` : L ? `${L.kind} ${hm(L.at)} · colour ${pct(L.p_color)}` : "ShotSpots"); return w; }
  if (fam === "accessoryRectangular") {
    const a = alerts[0];
    text(w, a ? shortTitle(a.title) : "ShotSpots", 13, Color.white(), true).lineLimit = 1;
    if (a) text(w, `${a.at ? dayWord(a.at) + " " + hm(a.at) : ""} · ${pct(a.p)}`, 12, Color.white());
    if (L) text(w, `${L.kind} ${hm(L.at)} · colour ${pct(L.p_color)}`, 12, Color.white());
    return w;
  }
  w.setPadding(12, 14, 12, 14);
  const head = w.addStack(); head.centerAlignContent();
  text(head, "ShotSpots", 12, C.moss, true); head.addSpacer();
  if (stale) text(head, "offline", 10, C.muted);
  else if (j.smoke) text(head, "smoke", 10, C.glow, true);
  w.addSpacer(6);

  if (fam === "small") {
    if (L) lightBlock(w, L, true);
    w.addSpacer();
    if (alerts[0]) alertRow(w, alerts[0], 1); else text(w, "No alerts", 11, C.muted);
    return w;
  }
  if (fam === "medium") {
    const row = w.addStack(); row.spacing = 14;
    if (L) lightBlock(row, L, false);
    const right = row.addStack(); right.layoutVertically(); right.spacing = 6;
    const items = alerts.length ? alerts : wk;
    if (!items.length) text(right, "Nothing lined up yet.", 11, C.muted);
    items.slice(0, 2).forEach(a => alertRow(right, a, 2));
    w.addSpacer();
    return w;
  }
  // large
  const top = w.addStack(); top.spacing = 18;
  (j.light || []).slice(0, 2).forEach(x => lightBlock(top, x, false));
  w.addSpacer(10);
  text(w, "Alerts", 11, C.muted, true); w.addSpacer(4);
  if (!alerts.length) text(w, "Nothing at your threshold right now.", 11, C.muted);
  alerts.slice(0, 3).forEach(a => { alertRow(w, a, 2); w.addSpacer(5); });
  if (wk.length) {
    w.addSpacer(6); text(w, "This weekend", 11, C.muted, true); w.addSpacer(4);
    wk.slice(0, 3).forEach(a => { alertRow(w, a, 2); w.addSpacer(5); });
  }
  w.addSpacer();
  const f = text(w, `Updated ${hm(j.gen)}`, 9, C.muted); f.rightAlignText();
  return w;
}

const widget = await build();
if (config.runsInWidget || config.runsInAccessoryWidget) Script.setWidget(widget);
else await widget.presentLarge();
Script.complete();
