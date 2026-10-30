// Patient sightings (v12; v19 security release). POST — record what a patient saw on a pharmacy shelf
// (Turnstile-checked, honeypot, nothing identifying). GET — public list, newest first, last 14 days.
// Same D1 binding (DB) and TURNSTILE_SECRET as the other forms. Admin list and delete moved to /api/admin.
import { json, clean, readJson, turnstileOk, tooMany, tableBusy, factsOnly, ensureSchema } from "../_lib/util.js";
//
// Every sighting is marked unverified ("verified": false, "label": "Unverified") in the public list.
// One-line switch: set HOLD_FOR_REVIEW to true to keep new sightings off the site until Ted presses
// Publish on /admin (they are stored with published = 0). false = they show straight away, labelled unverified.
const HOLD_FOR_REVIEW = false;

const DAYS = 14, MAX = 60;
const STATUS = new Set(["in_stock", "limited_qty", "out_of_stock"]);

export async function onRequestPost({ request, env }) {
  if (!env.DB || !env.TURNSTILE_SECRET) return json({ ok: false, error: "not-configured" }, 503);
  const { b, res } = await readJson(request);
  if (res) return res;
  if (b.website) return json({ ok: true });
  const medicine = clean(b.medicine, 60), pharmacy = clean(b.pharmacy, 60), region = clean(b.region, 40),
        rawNote = clean(b.note, 140), status = String(b.status || "");
  if (medicine.length < 2 || region.length < 2) return json({ ok: false, error: "field" }, 400);
  if (!STATUS.has(status)) return json({ ok: false, error: "status" }, 400);
  if (/@|https?:\/\/|\bwww\.|\b\d{8,}\b/i.test(medicine + " " + pharmacy + " " + region + " " + rawNote)) return json({ ok: false, error: "personal" }, 400);
  const note = factsOnly(rawNote);
  if (await tooMany(request, "si", 5, 10 * 60e3)) return json({ ok: false, error: "rate" }, 429);
  // sendIp false: sightings are anonymous, so the visitor's IP is not passed on to Turnstile
  if (!(await turnstileOk(request, env, b.token, { sendIp: false }))) return json({ ok: false, error: "verify" }, 403);
  await ensureSchema(env);
  if (await tableBusy(env, "sightings", 40)) return json({ ok: false, error: "rate" }, 429);
  await env.DB.prepare("INSERT INTO sightings (created, medicine, pharmacy, region, status, note, published) VALUES (?, ?, ?, ?, ?, ?, ?)")
    .bind(new Date().toISOString(), medicine, pharmacy, region, status, note, HOLD_FOR_REVIEW ? 0 : 1).run();
  const out = { ok: true, published: !HOLD_FOR_REVIEW, verified: false };
  if (HOLD_FOR_REVIEW) out.held = "review";
  if (rawNote && !note) out.noteRemoved = true;
  return json(out);
}

export async function onRequestGet({ env }) {
  if (!env.DB) return json({ reports: [] });
  await ensureSchema(env);
  const since = new Date(Date.now() - DAYS * 864e5).toISOString();
  const { results } = await env.DB.prepare(
    "SELECT created, medicine, pharmacy, region, status, note FROM sightings WHERE published = 1 AND created >= ? ORDER BY created DESC LIMIT ?")
    .bind(since, MAX).all();
  return json({ reports: results.map((r) => ({ channel: "patient", medicine: r.medicine, pharmacy: r.pharmacy, region: r.region,
    status: r.status, note: factsOnly(r.note), createdAt: r.created, verified: false, label: "Unverified" })) });
}
