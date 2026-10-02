// Cloudflare Pages Function: /api/pharmacy — stock reports from registered pharmacists.
//
// How verification works (as automated as it can be without an AHPRA API):
//   automatic  — AHPRA number format (PHA + 10 digits), Turnstile, honeypot, rate limit,
//                14-day expiry, and a block list
//   once only  — the FIRST report from a registration number is held until the site owner
//                checks the number on the public AHPRA register and approves it (one link click).
//                Every later report from that number publishes immediately.
//
// Bindings: DB (D1), TURNSTILE_SECRET, ADMIN_TOKEN — same as feedback.js. Schema in schema.sql.

const STATUSES = new Set(["in_stock", "low", "order", "none"]);
const DAYS = 14;
const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
const clean = (v, n) => String(v || "").replace(/\s+/g, " ").trim().slice(0, n);
const since = () => new Date(Date.now() - DAYS * 864e5).toISOString();

export async function onRequestGet({ request, env }) {
  if (!env.DB) return json({ ok: false, error: "not-configured" }, 503);
  const url = new URL(request.url);
  const token = url.searchParams.get("token") || "";
  const admin = env.ADMIN_TOKEN && token.length >= 24 && token === env.ADMIN_TOKEN;

  if (admin && url.searchParams.get("approve")) {
    const a = url.searchParams.get("approve").toUpperCase();
    await env.DB.prepare("UPDATE pharmacists SET state='approved', decided=? WHERE ahpra=?").bind(new Date().toISOString(), a).run();
    await env.DB.prepare("UPDATE pharmacy_reports SET published=1 WHERE ahpra=?").bind(a).run();
    return json({ ok: true, approved: a });
  }
  if (admin && url.searchParams.get("block")) {
    const a = url.searchParams.get("block").toUpperCase();
    await env.DB.prepare("UPDATE pharmacists SET state='blocked', decided=? WHERE ahpra=?").bind(new Date().toISOString(), a).run();
    await env.DB.prepare("UPDATE pharmacy_reports SET published=0 WHERE ahpra=?").bind(a).run();
    return json({ ok: true, blocked: a });
  }
  if (admin) {
    const pending = await env.DB.prepare(
      "SELECT p.ahpra, p.name, p.email, p.created, r.pharmacy, r.suburb, r.medicine, r.status FROM pharmacists p " +
      "LEFT JOIN pharmacy_reports r ON r.ahpra = p.ahpra WHERE p.state='pending' ORDER BY p.created").all();
    const base = url.origin + "/api/pharmacy?token=" + encodeURIComponent(token);
    return json({ ok: true, pending: pending.results.map((p) => ({
      ...p, check: "https://www.ahpra.gov.au/Registration/Registers-of-Practitioners.aspx",
      approve: base + "&approve=" + p.ahpra, block: base + "&block=" + p.ahpra })) });
  }
  // public: published reports from the last 14 days, registration number never exposed
  const { results } = await env.DB.prepare(
    "SELECT created, pharmacy, suburb, medicine, status, note FROM pharmacy_reports " +
    "WHERE published=1 AND created > ? ORDER BY id DESC LIMIT 300").bind(since()).all();
  return json({ ok: true, reports: results });
}

export async function onRequestPost({ request, env }) {
  if (!env.DB || !env.TURNSTILE_SECRET) return json({ ok: false, error: "not-configured" }, 503);
  let b;
  try { b = await request.json(); } catch { return json({ ok: false, error: "bad-request" }, 400); }
  if (b.website) return json({ ok: true, published: false });   // honeypot

  const ahpra = clean(b.ahpra, 13).toUpperCase();
  if (!/^PHA\d{10}$/.test(ahpra)) return json({ ok: false, error: "ahpra" }, 400);
  const name = clean(b.name, 80), pharmacy = clean(b.pharmacy, 80), suburb = clean(b.suburb, 40),
        medicine = clean(b.medicine, 80), note = clean(b.note, 200), email = clean(b.email, 200);
  if (!name || !pharmacy || !suburb || !medicine) return json({ ok: false, error: "fields" }, 400);
  if (!STATUSES.has(b.status)) return json({ ok: false, error: "status" }, 400);
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ ok: false, error: "email" }, 400);

  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", String(b.token || ""));
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) form.append("remoteip", ip);
  const check = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form })
    .then((r) => r.json()).catch(() => ({ success: false }));
  if (!check.success) return json({ ok: false, error: "verify" }, 403);

  // rate limit: 20 reports per registration number per day
  const recent = await env.DB.prepare("SELECT COUNT(*) AS n FROM pharmacy_reports WHERE ahpra=? AND created > ?")
    .bind(ahpra, new Date(Date.now() - 864e5).toISOString()).first();
  if (recent && recent.n >= 20) return json({ ok: false, error: "rate" }, 429);

  const now = new Date().toISOString();
  let p = await env.DB.prepare("SELECT state FROM pharmacists WHERE ahpra=?").bind(ahpra).first();
  if (!p) {
    await env.DB.prepare("INSERT INTO pharmacists (ahpra, name, email, state, created) VALUES (?, ?, ?, 'pending', ?)")
      .bind(ahpra, name, email || null, now).run();
    p = { state: "pending" };
  }
  if (p.state === "blocked") return json({ ok: false, error: "blocked" }, 403);
  const published = p.state === "approved" ? 1 : 0;
  await env.DB.prepare(
    "INSERT INTO pharmacy_reports (created, ahpra, pharmacy, suburb, medicine, status, note, published) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
    .bind(now, ahpra, pharmacy, suburb, medicine, b.status, note || null, published).run();
  return json({ ok: true, published: !!published });
}
