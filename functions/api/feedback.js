// Cloudflare Pages Function: /api/feedback
// POST — store a feedback message (spam-checked with Turnstile).
// Reading, marking as reported (ack) and deleting moved to /api/admin in v19 (token in a header, never in a link).
//
// Bindings (Pages project → Settings → Functions / Variables):
//   DB                D1 database (see schema.sql)
//   TURNSTILE_SECRET  secret key from the Turnstile widget
//   ADMIN_TOKEN       a long random string you choose, for the admin page (/admin)
//
// Privacy: no IP address, cookie or user agent is stored. The IP is passed to Turnstile for the spam check only,
// as Cloudflare recommends, and used in memory (hashed) to slow down floods.
import { json, clean, readJson, turnstileOk, tooMany, tableBusy, EMAIL_RE } from "../_lib/util.js";

const TOPICS = new Set(["wrong", "missing", "access", "other"]);

export async function onRequestPost({ request, env }) {
  if (!env.DB || !env.TURNSTILE_SECRET) return json({ ok: false, error: "not-configured" }, 503);
  const { b, res } = await readJson(request);
  if (res) return res;

  // honeypot: bots fill the hidden field; pretend success and store nothing
  if (b.website) return json({ ok: true });

  const message = String(b.message == null ? "" : b.message).replace(/\u0000/g, "").trim();
  if (message.length < 5 || message.length > 4000) return json({ ok: false, error: "length" }, 400);
  const topic = TOPICS.has(b.topic) ? b.topic : "other";
  const page = clean(b.page, 200);
  const email = clean(b.email, 200);
  if (email && !EMAIL_RE.test(email)) return json({ ok: false, error: "email" }, 400);

  if (await tooMany(request, "fb", 5, 10 * 60e3)) return json({ ok: false, error: "rate" }, 429);
  if (!(await turnstileOk(request, env, b.token))) return json({ ok: false, error: "verify" }, 403);
  if (await tableBusy(env, "feedback", 30)) return json({ ok: false, error: "rate" }, 429);

  await env.DB.prepare("INSERT INTO feedback (created, topic, page, message, email) VALUES (?, ?, ?, ?, ?)")
    .bind(new Date().toISOString(), topic, page, message, email || null).run();
  return json({ ok: true });
}

// The old ?token= reading address is gone; answer the same way for everyone.
export async function onRequestGet() {
  return json({ ok: false }, 404);
}
