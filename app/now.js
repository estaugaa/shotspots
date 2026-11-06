/* "Right now" weather line at the top of Plan: is it raining (or snowing, or foggy) where you're planning from,
   and when does that change? Open-Meteo current conditions plus its 15-minute precipitation (HRRR-based in the US),
   refreshed every 10 minutes, with the nearest airport report as a cross-check. */
"use strict";
const NOW = { at: 0, key: "", d: null };
const WCODE = c => c == null ? null : c >= 95 ? "Thunderstorms" : c >= 85 ? "Snow showers" : c >= 80 ? (c === 82 ? "Heavy showers" : "Showers") : c >= 71 && c <= 77 ? "Snow" : c >= 66 ? "Freezing rain" : c >= 61 ? (c >= 65 ? "Heavy rain" : c >= 63 ? "Rain" : "Light rain") : c >= 56 ? "Freezing drizzle" : c >= 51 ? "Drizzle" : c === 45 || c === 48 ? "Fog" : null;
async function loadNow(force) {
  const key = `${LOC.lat.toFixed(2)},${LOC.lon.toFixed(2)}`;
  if (!force && NOW.key === key && Date.now() - NOW.at < 10 * 6e4) return;
  NOW.key = key; NOW.at = Date.now();
  try {
    const j = await getJson(`https://api.open-meteo.com/v1/forecast?latitude=${LOC.lat.toFixed(3)}&longitude=${LOC.lon.toFixed(3)}&current=precipitation,rain,showers,snowfall,weather_code,temperature_2m,cloud_cover,wind_speed_10m&minutely_15=precipitation&forecast_minutely_15=16&past_minutely_15=2&timeformat=unixtime&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=GMT`);
    NOW.d = j; if (UI.view === "now") renderNow();
  } catch (e) { NOW.d = null; }
}
function nowLine() {
  const j = NOW.d; if (!j || !j.current) return "";
  const c = j.current, m = j.minutely_15 || { time: [], precipitation: [] }, t0 = Date.now() / 1000;
  const fut = m.time.map((t, i) => [t, m.precipitation[i] || 0]).filter(([t]) => t >= t0 - 450);
  const wetNow = (c.precipitation || 0) > 0 || (fut[0] && fut[0][1] >= 0.1) || [51, 53, 55, 61, 63, 65, 80, 81, 82, 95].includes(c.weather_code);
  const what = WCODE(c.weather_code) || (wetNow ? "Light rain" : null);
  const fmt = t => fmtT(new Date(t * 1000));
  let change = "";
  if (wetNow) { const dry = fut.findIndex(([, p], i) => i > 0 && p < 0.1 && (fut[i + 1] ? fut[i + 1][1] < 0.1 : true));
    change = dry > 0 ? `easing around ${fmt(fut[dry][0])}` : "for the next few hours"; }
  else { const wet = fut.findIndex(([, p]) => p >= 0.2); change = wet >= 0 ? `rain likely from about ${fmt(fut[wet][0])}` : "dry for the next few hours"; }
  // nearest airport report (feed/obs.json), if it's within 25 km and recent
  const o = (fd("obs") || {}).stations || [], st = o.filter(x => x.lat && km(LOC, x) < 25 && Date.now() - new Date(x.t) < 2 * 36e5).sort((a, b) => km(LOC, a) - km(LOC, b))[0];
  const stTxt = st && /RA|DZ|SN|FG|BR|TS/.test(st.wx || "") ? ` <span class="muted">· ${esc(st.name.split("/").pop().replace(/ (Intl|Arpt|Airport|Muni|Fld).*$/i, ""))} airport reports ${[...new Set((st.wx.match(/RA|DZ|SN|FG|BR|TS/g) || []).map(k => ({ RA: "rain", DZ: "drizzle", SN: "snow", FG: "fog", BR: "mist", TS: "thunder" })[k]))].join(" and ")}</span>` : "";
  const icon = wetNow ? (/Snow/.test(what || "") ? "❄" : "🌧") : what === "Fog" ? "🌫" : (c.cloud_cover || 0) > 80 ? "☁" : (c.cloud_cover || 0) > 30 ? "⛅" : "☀";
  return `<div class="nowline${wetNow ? " wet" : ""}" role="status"><span class="ni" aria-hidden="true">${icon}</span><span><b>${esc(what || ((c.cloud_cover || 0) > 80 ? "Overcast" : (c.cloud_cover || 0) > 30 ? "Partly cloudy" : "Clear"))} now</b> · ${fmtTemp(c.temperature_2m)} · ${esc(change)}${wetNow ? ". Waterfalls and wet-pavement city shots come into their own; protect your gear" : ""}.${stTxt}</span></div>`;
}
{ const _rnNow = renderNow; renderNow = function () { _rnNow.apply(this, arguments); loadNow(); const v = $("#v-now"); if (!v) return; const old = v.querySelector(".nowline"); if (old) old.remove();
  const h = nowLine(); if (!h) return; const pl = v.querySelector(".planner"); pl ? pl.insertAdjacentHTML("beforebegin", h) : v.insertAdjacentHTML("afterbegin", h); }; }
setInterval(() => { if (document.visibilityState === "visible") loadNow(); }, 5 * 6e4);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") loadNow(); });
