// Patient sightings (v12). POST — record what a patient saw on a pharmacy shelf
// (Turnstile-checked, honeypot, nothing identifying). GET — public list, newest first,
// last 14 days. Same D1 binding (DB) and TURNSTILE_SECRET as the other forms.
const DAYS = 14, MAX = 60;
const STATUS = new Set(["in_stock", "limited_qty", "out_of_stock"]);
const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
const clean = (v, n) => String(v || "").replace(/\s+/g, " ").trim().slice(0, n);

export async function onRequestPost({ request, env }) {
  if (!env.DB || !env.TURNSTILE_SECRET) return json({ ok: false, error: "not-configured" }, 503);
  let b; try { b = await request.json(); } catch { return json({ ok: false, error: "bad-request" }, 400); }
  if (b.website) return json({ ok: true });
  const medicine = clean(b.medicine, 60), pharmacy = clean(b.pharmacy, 60), region = clean(b.region, 40),
        note = clean(b.note, 140), status = String(b.status || "");
  if (medicine.length < 2 || region.length < 2) return json({ ok: false, error: "field" }, 400);
  if (!STATUS.has(status)) return json({ ok: false, error: "status" }, 400);
  if (/@|https?:\/\/|\b\d{8,}\b/.test(medicine + pharmacy + region + note)) return json({ ok: false, error: "personal" }, 400);
  const form = new FormData(); form.append("secret", env.TURNSTILE_SECRET); form.append("response", String(b.token || ""));
  const check = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form })
    .then((r) => r.json()).catch(() => ({ success: false }));
  if (!check.success) return json({ ok: false, error: "verify", codes: check["error-codes"] || [] }, 403);
  await env.DB.prepare("INSERT INTO sightings (created, medicine, pharmacy, region, status, note) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(new Date().toISOString(), medicine, pharmacy, region, status, note).run();
  return json({ ok: true });
}

export async function onRequestGet({ request, env }) {
  if (!env.DB) return json({ reports: [] });
  // Admin: /api/reports?token=ADMIN_TOKEN lists ids; &delete=ID removes one sighting.
  const u = new URL(request.url), token = u.searchParams.get("token") || "";
  if (token) {
    if (!env.ADMIN_TOKEN || token.length < 24 || token !== env.ADMIN_TOKEN) return json({ ok: false }, 404);
    const del = u.searchParams.get("delete");
    if (del) { await env.DB.prepare("DELETE FROM sightings WHERE id = ?").bind(Number(del)).run(); return json({ ok: true, deleted: Number(del) }); }
    const { results } = await env.DB.prepare("SELECT id, created, medicine, pharmacy, region, status, note FROM sightings ORDER BY created DESC LIMIT 200").all();
    return json({ ok: true, sightings: results });
  }
  const since = new Date(Date.now() - DAYS * 864e5).toISOString();
  const { results } = await env.DB.prepare("SELECT created, medicine, pharmacy, region, status, note FROM sightings WHERE created >= ? ORDER BY created DESC LIMIT ?")
    .bind(since, MAX).all();
  return json({ reports: results.map((r) => ({ channel: "patient", medicine: r.medicine, pharmacy: r.pharmacy, region: r.region, status: r.status, note: r.note, createdAt: r.created })) });
}
