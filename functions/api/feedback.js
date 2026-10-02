// Cloudflare Pages Function: /api/feedback
// POST — store a feedback message (spam-checked with Turnstile).
// GET  — list recent messages; requires ?token=<ADMIN_TOKEN>.
//
// Bindings (Pages project → Settings → Functions / Variables):
//   DB                D1 database (see schema.sql)
//   TURNSTILE_SECRET  secret key from the Turnstile widget
//   ADMIN_TOKEN       a long random string you choose, for reading messages
//
// Privacy: no IP address, cookie or user agent is stored. The IP is passed to
// Turnstile for the spam check only, as Cloudflare recommends.

const TOPICS = new Set(["wrong", "missing", "access", "other"]);
const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });

export async function onRequestPost({ request, env }) {
  if (!env.DB || !env.TURNSTILE_SECRET) return json({ ok: false, error: "not-configured" }, 503);
  let b;
  try { b = await request.json(); } catch { return json({ ok: false, error: "bad-request" }, 400); }

  // honeypot: bots fill the hidden field; pretend success and store nothing
  if (b.website) return json({ ok: true });

  const message = String(b.message || "").trim();
  if (message.length < 5 || message.length > 4000) return json({ ok: false, error: "length" }, 400);
  const topic = TOPICS.has(b.topic) ? b.topic : "other";
  const page = String(b.page || "").slice(0, 200);
  const email = String(b.email || "").trim().slice(0, 200);
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ ok: false, error: "email" }, 400);

  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", String(b.token || ""));
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) form.append("remoteip", ip);
  const check = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form })
    .then((r) => r.json()).catch(() => ({ success: false }));
  if (!check.success) return json({ ok: false, error: "verify", codes: check["error-codes"] || [] }, 403);

  await env.DB.prepare("INSERT INTO feedback (created, topic, page, message, email) VALUES (?, ?, ?, ?, ?)")
    .bind(new Date().toISOString(), topic, page, message, email || null).run();
  return json({ ok: true });
}

export async function onRequestGet({ request, env }) {
  const q = new URL(request.url).searchParams, token = q.get("token") || "";
  if (!env.ADMIN_TOKEN || token.length < 24 || token !== env.ADMIN_TOKEN) return json({ ok: false }, 404);
  const ids = (s) => (s || "").split(",").map((x) => parseInt(x, 10)).filter((n) => n > 0);
  // ?ack=1,2,3 marks messages as notified (the daily inbox issue has reported them); ?delete=ID removes one
  const ack = ids(q.get("ack"));
  if (ack.length) await env.DB.prepare(`UPDATE feedback SET notified = 1 WHERE id IN (${ack.join(",")})`).run();
  const del = ids(q.get("delete"));
  if (del.length) await env.DB.prepare(`DELETE FROM feedback WHERE id IN (${del.join(",")})`).run();
  const where = q.get("new") === "1" ? " WHERE notified = 0" : "";
  const { results } = await env.DB.prepare(
    "SELECT id, created, topic, page, message, email, notified FROM feedback" + where + " ORDER BY id DESC LIMIT 200").all();
  return json({ ok: true, feedback: results, acked: ack.length, deleted: del.length });
}
