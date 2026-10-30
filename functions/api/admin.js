// /api/admin (v19) — everything that needs ADMIN_TOKEN, used by the admin page (/admin) and the daily inbox step.
// The token goes in the header "Authorization: Bearer <token>" and is compared in constant time.
// It is never accepted in a link (?token=), so it cannot leak through browser history, logs or a forwarded email.
//
// GET  /api/admin?list=summary | feedback[&new=1] | pharmacists | sightings | csp
// POST /api/admin  JSON {action, ...}
//   ack      {ids:[1,2]}                         feedback: mark as reported by the daily inbox step
//   delete   {kind:"feedback"|"sighting", id}    remove one row (Ted presses Delete on /admin)
//   approve  {ahpra}                             pharmacist checked on AHPRA: publish their reports, make a report key
//   block    {ahpra}                             stop and hide all reports from that number
//   newkey   {ahpra}                             replace a lost or leaked report key (approved pharmacists only)
//   publish  {kind:"report"|"sighting", id}      publish one held report or sighting
// A new report key is returned once, in the reply to approve/newkey; only its SHA-256 hash is stored.
import { json, readJson, isAdmin, tooMany, ensureSchema, sha256hex, newReportKey } from "../_lib/util.js";

const DAYS = 14;
const since = () => new Date(Date.now() - DAYS * 864e5).toISOString();
const AHPRA = /^PHA\d{10}$/;
const id1 = (v) => { const n = Number(v); return Number.isInteger(n) && n > 0 && n < 2 ** 53 ? n : 0; };

async function gate(request, env) {
  if (!env.DB) return json({ ok: false, error: "not-configured" }, 503);
  // ten wrong tokens in 15 minutes from one address: that address waits, even with the right token
  if (await tooMany(request, "adminbad", 10, 15 * 60e3, { peek: true })) return json({ ok: false, error: "busy" }, 429);
  if (!(await isAdmin(request, env))) {
    await tooMany(request, "adminbad", 10, 15 * 60e3);   // count this failure
    return json({ ok: false, error: "auth" }, 401);
  }
  await ensureSchema(env);
  return null;
}

export async function onRequestGet({ request, env }) {
  const stop = await gate(request, env);
  if (stop) return stop;
  const q = new URL(request.url).searchParams, list = q.get("list") || "summary", DB = env.DB;

  if (list === "feedback") {
    const where = q.get("new") === "1" ? " WHERE notified = 0" : "";
    const { results } = await DB.prepare(
      "SELECT id, created, topic, page, message, email, notified FROM feedback" + where + " ORDER BY id DESC LIMIT 200").all();
    return json({ ok: true, feedback: results });
  }
  if (list === "pharmacists") {
    const ppl = (await DB.prepare(
      "SELECT ahpra, name, email, state, created FROM pharmacists WHERE state='pending' ORDER BY created LIMIT 100").all()).results;
    const reps = ppl.length ? (await DB.prepare(
      "SELECT r.id, r.ahpra, r.created, r.pharmacy, r.suburb, r.medicine, r.status, r.note FROM pharmacy_reports r " +
      "JOIN pharmacists p ON p.ahpra = r.ahpra WHERE p.state='pending' ORDER BY r.id LIMIT 500").all()).results : [];
    const pending = ppl.map((p) => ({ ...p, reports: reps.filter((r) => r.ahpra === p.ahpra) }));
    const held = (await DB.prepare(
      "SELECT r.id, r.ahpra, r.created, r.pharmacy, r.suburb, r.medicine, r.status, r.note, p.name, p.email, (p.key_hash IS NOT NULL) AS has_key " +
      "FROM pharmacy_reports r JOIN pharmacists p ON p.ahpra = r.ahpra " +
      "WHERE p.state='approved' AND r.published=0 AND r.created > ? ORDER BY r.id DESC LIMIT 200").bind(since()).all()).results;
    const keyless = (await DB.prepare(
      "SELECT ahpra, name, email, decided FROM pharmacists WHERE state='approved' AND key_hash IS NULL ORDER BY decided LIMIT 200").all()).results;
    return json({ ok: true, pending, held, keyless,
      check: "https://www.ahpra.gov.au/Registration/Registers-of-Practitioners.aspx" });
  }
  if (list === "sightings") {
    const { results } = await DB.prepare(
      "SELECT id, created, medicine, pharmacy, region, status, note, published FROM sightings ORDER BY id DESC LIMIT 200").all();
    return json({ ok: true, sightings: results });
  }
  if (list === "csp") {
    const { results } = await DB.prepare(
      "SELECT day, directive, blocked, page, mode, count, last FROM csp_reports ORDER BY day DESC, count DESC LIMIT 200").all();
    return json({ ok: true, csp: results });
  }
  if (list === "summary") {
    const n = async (sql, ...a) => ((await DB.prepare(sql).bind(...a).first()) || {}).n || 0;
    const counts = {
      feedback: await n("SELECT COUNT(*) AS n FROM feedback"),
      pending: await n("SELECT COUNT(*) AS n FROM pharmacists WHERE state='pending'"),
      held: await n("SELECT COUNT(*) AS n FROM pharmacy_reports r JOIN pharmacists p ON p.ahpra = r.ahpra WHERE p.state='approved' AND r.published=0 AND r.created > ?", since()),
      keyless: await n("SELECT COUNT(*) AS n FROM pharmacists WHERE state='approved' AND key_hash IS NULL"),
      sightings: await n("SELECT COUNT(*) AS n FROM sightings WHERE created > ?", since()),
      sightingsHeld: await n("SELECT COUNT(*) AS n FROM sightings WHERE published=0 AND created > ?", since()),
      csp: await n("SELECT COALESCE(SUM(count), 0) AS n FROM csp_reports WHERE day >= ?", since().slice(0, 10)),
    };
    return json({ ok: true, counts });
  }
  return json({ ok: false, error: "list" }, 400);
}

async function issueKey(DB, ahpra) {
  const key = newReportKey();
  await DB.prepare("UPDATE pharmacists SET key_hash=?, key_issued=? WHERE ahpra=?")
    .bind(await sha256hex(key.replace(/-/g, "")), new Date().toISOString(), ahpra).run();
  return key;
}

export async function onRequestPost({ request, env }) {
  const stop = await gate(request, env);
  if (stop) return stop;
  const { b, res } = await readJson(request, 8192);
  if (res) return res;
  const DB = env.DB, action = String(b.action || ""), now = new Date().toISOString();

  if (action === "ack") {
    const ids = (Array.isArray(b.ids) ? b.ids : []).map(id1).filter(Boolean).slice(0, 500);
    if (!ids.length) return json({ ok: false, error: "ids" }, 400);
    const r = await DB.prepare(`UPDATE feedback SET notified = 1 WHERE id IN (${ids.map(() => "?").join(",")})`).bind(...ids).run();
    return json({ ok: true, acked: (r.meta && r.meta.changes) || 0 });
  }
  if (action === "delete" || action === "publish") {
    const id = id1(b.id), kind = String(b.kind || "");
    if (!id) return json({ ok: false, error: "id" }, 400);
    let sql = null;
    if (action === "delete" && kind === "feedback") sql = "DELETE FROM feedback WHERE id = ?";
    if (action === "delete" && kind === "sighting") sql = "DELETE FROM sightings WHERE id = ?";
    if (action === "publish" && kind === "sighting") sql = "UPDATE sightings SET published = 1 WHERE id = ?";
    if (action === "publish" && kind === "report")
      sql = "UPDATE pharmacy_reports SET published = 1 WHERE id = ? AND ahpra IN (SELECT ahpra FROM pharmacists WHERE state <> 'blocked')";
    if (!sql) return json({ ok: false, error: "kind" }, 400);
    const r = await DB.prepare(sql).bind(id).run();
    const changed = (r.meta && r.meta.changes) || 0;
    return json({ ok: changed > 0, done: action, kind, id, error: changed ? undefined : "not-found" }, changed ? 200 : 404);
  }
  if (action === "approve" || action === "block" || action === "newkey") {
    const ahpra = String(b.ahpra || "").trim().toUpperCase();
    if (!AHPRA.test(ahpra)) return json({ ok: false, error: "ahpra" }, 400);
    const p = await DB.prepare("SELECT ahpra, name, email, state, key_hash FROM pharmacists WHERE ahpra=?").bind(ahpra).first();
    if (!p) return json({ ok: false, error: "not-found" }, 404);
    const who = { ahpra, name: p.name, email: p.email || null };
    if (action === "block") {
      await DB.prepare("UPDATE pharmacists SET state='blocked', decided=? WHERE ahpra=?").bind(now, ahpra).run();
      const r = await DB.prepare("UPDATE pharmacy_reports SET published=0 WHERE ahpra=?").bind(ahpra).run();
      return json({ ok: true, blocked: ahpra, hidden: (r.meta && r.meta.changes) || 0 });
    }
    if (action === "newkey") {
      if (p.state !== "approved") return json({ ok: false, error: "not-approved" }, 409);
      return json({ ok: true, ...who, key: await issueKey(DB, ahpra) });
    }
    // approve: first approval (or un-blocking) publishes the reports Ted was shown; a key is made if there is none
    let published = 0;
    if (p.state !== "approved") {
      await DB.prepare("UPDATE pharmacists SET state='approved', decided=? WHERE ahpra=?").bind(now, ahpra).run();
      const r = await DB.prepare("UPDATE pharmacy_reports SET published=1 WHERE ahpra=? AND published=0").bind(ahpra).run();
      published = (r.meta && r.meta.changes) || 0;
    }
    const out = { ok: true, approved: ahpra, ...who, published };
    if (!p.key_hash) out.key = await issueKey(DB, ahpra);
    return json(out);
  }
  return json({ ok: false, error: "action" }, 400);
}

