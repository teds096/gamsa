// Cloudflare Pages Function: /api/pharmacy — stock reports from registered pharmacists.
//
// How verification works (v19):
//   automatic  — AHPRA number format (PHA + 10 digits), Turnstile (and the site it was solved on), honeypot,
//                rate limits, 14-day expiry, and a block list
//   once only  — the FIRST report from a registration number is held until the site owner checks the number
//                on the public AHPRA register and approves it on /admin. Approving creates a private REPORT KEY,
//                which the site owner emails to the pharmacist from /admin (one button opens a written email).
//   every time — a later report publishes straight away only if it carries that pharmacist's report key.
//                AHPRA numbers are public, so the number alone is no longer enough: without the key (or with a
//                wrong one) the report is held for the site owner, who can publish it on /admin.
// Published reports show stock facts only: medicine, pharmacy, suburb, status and date. A note that mentions
// prices, offers or contact details is dropped.
//
// Bindings: DB (D1), TURNSTILE_SECRET, ADMIN_TOKEN. Schema in schema.sql. Admin actions are in admin.js.
import { json, clean, readJson, turnstileOk, tooMany, tableBusy, factsOnly, NAME_BAD, EMAIL_RE,
         sha256hex, sameSecret, normKey, ensureSchema } from "../_lib/util.js";

const STATUSES = new Set(["in_stock", "low", "order", "none"]);
const DAYS = 14;
const since = () => new Date(Date.now() - DAYS * 864e5).toISOString();

export async function onRequestGet({ env }) {
  if (!env.DB) return json({ ok: false, error: "not-configured" }, 503);
  // public: published reports from the last 14 days; registration number, name and email never exposed
  const { results } = await env.DB.prepare(
    "SELECT created, pharmacy, suburb, medicine, status, note FROM pharmacy_reports " +
    "WHERE published=1 AND created > ? ORDER BY id DESC LIMIT 300").bind(since()).all();
  return json({ ok: true, reports: results.map((r) => ({
    created: r.created, pharmacy: r.pharmacy, suburb: r.suburb, medicine: r.medicine, status: r.status,
    note: factsOnly(r.note) || null })) });
}

export async function onRequestPost({ request, env }) {
  if (!env.DB || !env.TURNSTILE_SECRET) return json({ ok: false, error: "not-configured" }, 503);
  const { b, res } = await readJson(request);
  if (res) return res;
  if (b.website) return json({ ok: true, published: false });   // honeypot

  const ahpra = clean(b.ahpra, 13).toUpperCase();
  if (!/^PHA\d{10}$/.test(ahpra)) return json({ ok: false, error: "ahpra" }, 400);
  const name = clean(b.name, 80), pharmacy = clean(b.pharmacy, 80), suburb = clean(b.suburb, 40),
        medicine = clean(b.medicine, 80), email = clean(b.email, 200), rawNote = clean(b.note, 200);
  if (!name || !pharmacy || !suburb || !medicine) return json({ ok: false, error: "fields" }, 400);
  if (NAME_BAD.test(name + " " + pharmacy + " " + suburb + " " + medicine)) return json({ ok: false, error: "fields" }, 400);
  if (!STATUSES.has(b.status)) return json({ ok: false, error: "status" }, 400);
  if (email && !EMAIL_RE.test(email)) return json({ ok: false, error: "email" }, 400);
  const note = factsOnly(rawNote);

  if (await tooMany(request, "pr", 10, 10 * 60e3)) return json({ ok: false, error: "rate" }, 429);
  if (!(await turnstileOk(request, env, b.token))) return json({ ok: false, error: "verify" }, 403);
  await ensureSchema(env);

  // rate limits: 20 reports per registration number per day; 60 a hour across the site
  const recent = await env.DB.prepare("SELECT COUNT(*) AS n FROM pharmacy_reports WHERE ahpra=? AND created > ?")
    .bind(ahpra, new Date(Date.now() - 864e5).toISOString()).first();
  if (recent && recent.n >= 20) return json({ ok: false, error: "rate" }, 429);
  if (await tableBusy(env, "pharmacy_reports", 60)) return json({ ok: false, error: "rate" }, 429);

  const now = new Date().toISOString();
  let p = await env.DB.prepare("SELECT state, key_hash FROM pharmacists WHERE ahpra=?").bind(ahpra).first();
  if (!p) {
    await env.DB.prepare("INSERT OR IGNORE INTO pharmacists (ahpra, name, email, state, created) VALUES (?, ?, ?, 'pending', ?)")
      .bind(ahpra, name, email || null, now).run();
    p = (await env.DB.prepare("SELECT state, key_hash FROM pharmacists WHERE ahpra=?").bind(ahpra).first()) || { state: "pending" };
  }
  if (p.state === "blocked") return json({ ok: false, error: "blocked" }, 403);

  let published = 0, held = "new";
  if (p.state === "approved") {
    const key = normKey(b.key);
    if (key && p.key_hash && (await sameSecret(await sha256hex(key), p.key_hash))) { published = 1; held = null; }
    else held = "key";   // approved number, but no key or the wrong key: Ted checks it on /admin
  }
  await env.DB.prepare(
    "INSERT INTO pharmacy_reports (created, ahpra, pharmacy, suburb, medicine, status, note, published) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
    .bind(now, ahpra, pharmacy, suburb, medicine, b.status, note || null, published).run();
  const out = { ok: true, published: !!published };
  if (held) out.held = held;                       // "new" = first report, waits for the AHPRA check; "key" = report key missing or wrong
  if (rawNote && !note) out.noteRemoved = true;    // the note mentioned a price, an offer or contact details
  return json(out);
}
