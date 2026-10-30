// /api/csp-report (v19) — browsers post here when the site's Content-Security-Policy blocks something
// (enforced policy) or would block it (Report-Only trial policy). Ted reads the totals on /admin.
//
// Stored per day: the rule that fired, the blocked address reduced to its site (no path or query), the page path,
// and a count. No IP address, user agent, cookie or query string is stored. Browser add-ons cause noise, so their
// reports are ignored. The table is capped at 2000 rows: after that only existing rows are counted up.
import { json, tooMany, ensureSchema } from "../_lib/util.js";

const CAP = 2000, MAX_BODY = 32768;
const NOISE = /^(chrome|moz|safari|safari-web|ms-browser)-extension:|^about:|^webkit-masked-url:/i;

function site(u) {
  const s = String(u || "").trim();
  if (!s) return "(none)";
  if (/^(inline|eval|wasm-eval|data|blob|self|trusted-types-sink|trusted-types-policy)$/i.test(s)) return s.toLowerCase();
  try { const x = new URL(s); return /^https?:$/.test(x.protocol) ? x.origin : x.protocol.replace(":", ""); }
  catch { return s.replace(/[?#].*$/, "").slice(0, 80); }
}
function path(u) {
  try { return new URL(String(u)).pathname.slice(0, 120) || "/"; } catch { return "(unknown)"; }
}

function pick(r) {
  // legacy report-uri: {"csp-report": {...}}; Reporting API: [{type: "csp-violation", body: {...}}]
  const b = r && (r["csp-report"] || r.body || r);
  if (!b || typeof b !== "object") return null;
  const blockedRaw = b["blocked-uri"] ?? b.blockedURL ?? "";
  const sourceRaw = b["source-file"] ?? b.sourceFile ?? "";
  if (NOISE.test(String(blockedRaw)) || NOISE.test(String(sourceRaw))) return null;
  const directive = String(b["effective-directive"] || b.effectiveDirective || b["violated-directive"] || "unknown").split(" ")[0].slice(0, 40);
  const mode = String(b.disposition || "").toLowerCase() === "report" ? "report-only" : "enforced";
  return { directive, blocked: site(blockedRaw), page: path(b["document-uri"] || b.documentURL || r.url || ""), mode };
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return new Response(null, { status: 204 });
  if (await tooMany(request, "csp", 20, 60e3)) return new Response(null, { status: 204 });
  let text = "";
  try { text = await request.text(); } catch { return new Response(null, { status: 204 }); }
  if (!text || text.length > MAX_BODY) return new Response(null, { status: 204 });
  let data;
  try { data = JSON.parse(text); } catch { return new Response(null, { status: 204 }); }
  const list = (Array.isArray(data) ? data : [data])
    .filter((r) => !Array.isArray(data) || !r || !r.type || r.type === "csp-violation")
    .slice(0, 10).map(pick).filter(Boolean);
  if (!list.length) return new Response(null, { status: 204 });
  await ensureSchema(env);
  const now = new Date().toISOString(), day = now.slice(0, 10);
  const full = await env.DB.prepare("SELECT COUNT(*) AS n FROM csp_reports").first();
  for (const v of list) {
    const sql = full && full.n >= CAP
      ? "UPDATE csp_reports SET count = count + 1, last = ?6 WHERE day = ?1 AND directive = ?2 AND blocked = ?3 AND page = ?4 AND mode = ?5"
      : "INSERT INTO csp_reports (day, directive, blocked, page, mode, count, last) VALUES (?1, ?2, ?3, ?4, ?5, 1, ?6) " +
        "ON CONFLICT (day, directive, blocked, page, mode) DO UPDATE SET count = count + 1, last = excluded.last";
    await env.DB.prepare(sql).bind(day, v.directive, v.blocked, v.page, v.mode, now).run();
  }
  return new Response(null, { status: 204 });
}

export async function onRequestGet() {
  return json({ ok: false }, 404);
}
