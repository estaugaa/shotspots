// ShotSpots forms Worker: the app POSTs form data here; it's stored in D1. Nothing is readable from this public
// endpoint: the pipeline reads D1 through the Cloudflare API with its own token.
const FORMS = new Set(["outcome", "research", "research_settings", "alert_settings", "push_sub", "spot_feedback", "lead"]);
const ORIGINS = ["https://estaugaa.github.io", "https://shotspots-eric.netlify.app", "http://localhost:8765"];
const MAX = 20000;

function cors(req) {
  const o = req.headers.get("Origin") || "";
  return { "Access-Control-Allow-Origin": ORIGINS.includes(o) ? o : ORIGINS[0], "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400", "Vary": "Origin" };
}
const json = (req, obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...cors(req) } });

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req) });
    if (req.method === "GET" && url.pathname === "/health") return json(req, { ok: true });
    const m = url.pathname.match(/^\/f\/([a-z_]+)$/);
    if (req.method !== "POST" || !m) return json(req, { ok: false, error: "not found" }, 404);
    const form = m[1];
    if (!FORMS.has(form)) return json(req, { ok: false, error: "unknown form" }, 400);
    const body = await req.text();
    if (body.length > MAX) return json(req, { ok: false, error: "too large" }, 413);
    let data;
    const ct = req.headers.get("Content-Type") || "";
    try { data = ct.includes("application/json") ? JSON.parse(body) : Object.fromEntries(new URLSearchParams(body)); }
    catch (e) { return json(req, { ok: false, error: "bad body" }, 400); }
    delete data["form-name"]; delete data["bot-field"];
    // light abuse guard: at most 60 submissions per IP per hour
    const ip = req.headers.get("CF-Connecting-IP") || "";
    const ipHash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(ip + (env.SALT || "ss"))))].slice(0, 8).map(b => b.toString(16).padStart(2, "0")).join("");
    const n = await env.DB.prepare("SELECT COUNT(*) AS n FROM submissions WHERE ip = ? AND created_at > datetime('now','-1 hour')").bind(ipHash).first("n");
    if (n >= 60) return json(req, { ok: false, error: "slow down" }, 429);
    await env.DB.prepare("INSERT INTO submissions (form, created_at, data, ip) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?)").bind(form, JSON.stringify(data), ipHash).run();
    return json(req, { ok: true });
  },
};
