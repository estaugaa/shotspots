// ShotSpots forms Worker: the app POSTs form data here; it's stored in D1. Nothing is readable from this public
// endpoint: the pipeline reads D1 through the Cloudflare API with its own token.
const FORMS = new Set(["outcome", "research", "research_settings", "alert_settings", "push_sub", "spot_feedback", "lead", "conditions", "debug"]);
const ORIGINS = ["https://estaugaa.github.io", "https://shotspots-eric.netlify.app", "http://localhost:8765"];
const MAX = 20000;
// Owner-only forms: they change shared settings or spend the owner's Claude usage. The owner's devices send the
// owner key (set once via the #owner= link); only its SHA-256 lives here.
const OWNER_HASH = "960c6a09c50ff6f4bba3993a8c350f23e12ce3f0abfce5704ee5c39fb57b5fe5";
const OWNER_ONLY = new Set(["research", "research_settings", "alert_settings", "lead"]);
async function sha256hex(t) { return [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t)))].map(b => b.toString(16).padStart(2, "0")).join(""); }

function cors(req) {
  const o = req.headers.get("Origin") || "";
  return { "Access-Control-Allow-Origin": ORIGINS.includes(o) ? o : ORIGINS[0], "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400", "Vary": "Origin" };
}
const json = (req, obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...cors(req) } });

// Scheduler: GitHub's own cron is best-effort on free repos and drops most runs, so Cloudflare's cron (reliable)
// asks GitHub to run each pipeline job. One dispatch per tick, because the jobs share a GitHub concurrency group
// where a second queued run would cancel the first.
const REPO = "estaugaa/shotspots";
function jobFor(d) {
  const h = d.getUTCHours(), m = d.getUTCMinutes() < 30 ? 7 : 37, dow = d.getUTCDay(), dom = d.getUTCDate();
  if (dom === 1 && h === 15 && m === 7) return "monthly.yml";
  if (dow === 1 && h === 13 && m === 7) return "weekly.yml";
  if (h === 11 && m === 7) return "daily.yml";       // 3:07 / 4:07 AM Pacific
  if (h === 14 && m === 7) return "outcomes.yml";
  if (h === 16 && m === 37) return "trails.yml";
  if (h % 3 === 0 && m === 7) return "conditions.yml"; // every 3 h, with the new HRRR run
  return "goes.yml";                                   // every other half hour
}
async function dispatch(env, wf) {
  if (!env.GH_TOKEN) return "no GH_TOKEN";
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${wf}/dispatches`, { method: "POST",
    headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "shotspots-scheduler", "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main" }) });
  return `${wf} ${r.status}`;
}

export default {
  async scheduled(event, env, ctx) {
    const wf = jobFor(new Date(event.scheduledTime));
    const res = await dispatch(env, wf);
    try { await env.DB.prepare("INSERT INTO ticks (at, job, result) VALUES (strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?)").bind(wf, res).run(); } catch (e) { }
  },
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req) });
    if (req.method === "GET" && url.pathname === "/health") {
      let last = null; try { last = await env.DB.prepare("SELECT at, job, result FROM ticks ORDER BY rowid DESC LIMIT 3").all(); } catch (e) { }
      return json(req, { ok: true, scheduler: env.GH_TOKEN ? "on" : "waiting for GH_TOKEN", recent: last && last.results }); }
    // 7Timer seeing/transparency: its server sends no CORS header, so phones can't read it directly. Proxy it,
    // rounded to 0.25° and cached for 3 hours at Cloudflare's edge so 7Timer sees few requests.
    // Open-Meteo fallback: when a phone's own request is refused (busy, 429) the app retries through here.
    // Only Open-Meteo hosts; identical requests share a 15-minute edge cache.
    if (req.method === "GET" && url.pathname === "/om") {
      let u; try { u = new URL(url.searchParams.get("u") || ""); } catch (e) { return json(req, { ok: false, error: "bad url" }, 400); }
      if (u.protocol !== "https:" || !/^(api|air-quality-api|marine-api)\.open-meteo\.com$/.test(u.hostname)) return json(req, { ok: false, error: "not allowed" }, 400);
      const cache = caches.default, key = new Request(u.toString()); let res = await cache.match(key);
      if (!res) { const up = await fetch(u.toString(), { headers: { "User-Agent": "ShotSpots/1.0" } }); if (!up.ok) return json(req, { ok: false, error: "open-meteo " + up.status }, up.status);
        res = new Response(await up.text(), { headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=900" } }); await cache.put(key, res.clone()); }
      return new Response(res.body, { headers: { "Content-Type": "application/json", ...cors(req), "Access-Control-Allow-Methods": "GET, POST, OPTIONS" } });
    }
    if (req.method === "GET" && url.pathname === "/seeing") {
      const r4 = v => (Math.round(parseFloat(v) * 4) / 4).toFixed(2), lat = r4(url.searchParams.get("lat")), lon = r4(url.searchParams.get("lon"));
      if (!isFinite(lat) || !isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return json(req, { ok: false, error: "bad lat/lon" }, 400);
      const src = `https://www.7timer.info/bin/astro.php?lon=${lon}&lat=${lat}&ac=0&unit=metric&output=json&tzshift=0`;
      const cache = caches.default, key = new Request(src); let res = await cache.match(key);
      if (!res) { const up = await fetch(src, { headers: { "User-Agent": "ShotSpots/1.0" } }); if (!up.ok) return json(req, { ok: false, error: "7timer " + up.status }, 502);
        res = new Response(await up.text(), { headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=10800" } }); await cache.put(key, res.clone()); }
      return new Response(res.body, { headers: { "Content-Type": "application/json", ...cors(req), "Access-Control-Allow-Methods": "GET, POST, OPTIONS" } });
    }
    const m = url.pathname.match(/^\/f\/([a-z_]+)$/);
    if (req.method !== "POST" || !m) return json(req, { ok: false, error: "not found" }, 404);
    const form = m[1];
    if (!FORMS.has(form)) return json(req, { ok: false, error: "unknown form" }, 400);
    const body = await req.text();
    if (body.length > (form === "conditions" ? 400000 : MAX)) return json(req, { ok: false, error: "too large" }, 413);   // conditions carry a ~80 KB thumbnail
    let data;
    const ct = req.headers.get("Content-Type") || "";
    try { data = ct.includes("application/json") ? JSON.parse(body) : Object.fromEntries(new URLSearchParams(body)); }
    catch (e) { return json(req, { ok: false, error: "bad body" }, 400); }
    delete data["form-name"]; delete data["bot-field"];
    const key = data._k || ""; delete data._k;
    const owner = key ? (await sha256hex(key)) === OWNER_HASH : false;
    if (OWNER_ONLY.has(form) && !owner) return json(req, { ok: false, error: "owner only" }, 403);
    data._owner = owner ? 1 : 0;
    const dev = (data._dev || "").slice(0, 24); delete data._dev; if (dev) data._dev = dev;
    // light abuse guard: at most 60 submissions per IP per hour
    const ip = req.headers.get("CF-Connecting-IP") || "";
    const ipHash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(ip + (env.SALT || "ss"))))].slice(0, 8).map(b => b.toString(16).padStart(2, "0")).join("");
    const n = await env.DB.prepare("SELECT COUNT(*) AS n FROM submissions WHERE ip = ? AND created_at > datetime('now','-1 hour')").bind(ipHash).first("n");
    if (n >= 60) return json(req, { ok: false, error: "slow down" }, 429);
    await env.DB.prepare("INSERT INTO submissions (form, created_at, data, ip) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?)").bind(form, JSON.stringify(data), ipHash).run();
    return json(req, { ok: true });
  },
};
