// POST — record what someone paid for a medicine (Turnstile-checked, honeypot).
// GET  — public summary: per medicine and script kind, the count, median, lowest and
//        highest reported in the last 180 days, shown only once 3 or more reports exist.
// Needs the same D1 binding (DB) and TURNSTILE_SECRET as /api/feedback.
const DAYS = 180, MIN = 3;
const KINDS = new Set(["pbs", "private"]);
const STATES = new Set(["", "ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"]);
const PHARM = new Set(["", "chain", "independent", "online"]);
const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

export async function onRequestPost({ request, env }) {
  if (!env.DB || !env.TURNSTILE_SECRET) return json({ ok: false, error: "not-configured" }, 503);
  let b; try { b = await request.json(); } catch { return json({ ok: false, error: "bad-request" }, 400); }
  if (b.website) return json({ ok: true });
  const medicine = String(b.medicine || "").trim();
  const kind = String(b.kind || "").trim();
  const cents = Math.round(Number(b.amount) * 100);
  const state = String(b.state || "").trim().toUpperCase();
  const pharmacy = String(b.pharmacy || "").trim();
  if (!/^[a-z0-9-]{3,60}$/.test(medicine)) return json({ ok: false, error: "medicine" }, 400);
  if (!KINDS.has(kind) || !STATES.has(state) || !PHARM.has(pharmacy)) return json({ ok: false, error: "field" }, 400);
  if (!Number.isFinite(cents) || cents < 100 || cents > 500000) return json({ ok: false, error: "amount" }, 400);
  const form = new FormData(); form.append("secret", env.TURNSTILE_SECRET); form.append("response", String(b.token || ""));
  const check = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form })
    .then((r) => r.json()).catch(() => ({ success: false }));
  if (!check.success) return json({ ok: false, error: "verify", codes: check["error-codes"] || [] }, 403);
  await env.DB.prepare("INSERT INTO prices (created, medicine, kind, cents, state, pharmacy) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(new Date().toISOString(), medicine, kind, cents, state, pharmacy).run();
  return json({ ok: true });
}

export async function onRequestGet({ env }) {
  if (!env.DB) return json({ ok: false, error: "not-configured" }, 503);
  const since = new Date(Date.now() - DAYS * 864e5).toISOString();
  const { results } = await env.DB.prepare("SELECT medicine, kind, cents, created FROM prices WHERE created >= ? ORDER BY medicine, kind, cents")
    .bind(since).all();
  const groups = {};
  for (const r of results) { const k = r.medicine + "|" + r.kind; (groups[k] = groups[k] || []).push(r); }
  const summary = [];
  for (const k in groups) {
    const rows = groups[k]; if (rows.length < MIN) continue;
    const c = rows.map((r) => r.cents), mid = c.length >> 1;
    const median = c.length % 2 ? c[mid] : Math.round((c[mid - 1] + c[mid]) / 2);
    summary.push({ medicine: rows[0].medicine, kind: rows[0].kind, n: rows.length, median, low: c[0], high: c[c.length - 1],
      latest: rows.map((r) => r.created).sort().pop().slice(0, 10) });
  }
  return json({ ok: true, days: DAYS, summary });
}
