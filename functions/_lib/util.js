// Shared helpers for the Pages Functions (v19 security release). Not a route: it exports no onRequest handler.
//
// What lives here: JSON replies, body reading with size/type limits, the Turnstile check (with hostname check),
// the admin-token check (constant time, token only from the Authorization header), soft rate limits,
// the "stock facts only" filter, report keys, and the small additive schema update the new code needs.

export const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "X-Robots-Tag": "noindex, nofollow",
  "Cross-Origin-Resource-Policy": "same-origin",
  "X-Frame-Options": "DENY",
};

export const json = (obj, status = 200, extra = {}) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
      ...SECURITY_HEADERS,
      ...extra,
    },
  });

// Collapse whitespace, drop control characters, trim and cut to n characters.
export const clean = (v, n) =>
  String(v == null ? "" : v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, n);

export const EMAIL_RE = /^[^\s@<>"',;]+@[^\s@<>"',;]+\.[^\s@<>"',;]+$/;

// Read a JSON object body. Rejects other content types (blocks cross-site plain form posts), bodies over
// `max` bytes and anything that is not a plain object. Returns {b} or {res} (an error response).
export async function readJson(request, max = 16384) {
  const type = (request.headers.get("Content-Type") || "").toLowerCase();
  if (!type.includes("application/json")) return { res: json({ ok: false, error: "type" }, 415) };
  const len = Number(request.headers.get("Content-Length") || 0);
  if (len > max) return { res: json({ ok: false, error: "size" }, 413) };
  let text;
  try { text = await request.text(); } catch { return { res: json({ ok: false, error: "bad-request" }, 400) }; }
  if (text.length > max) return { res: json({ ok: false, error: "size" }, 413) };
  let b;
  try { b = JSON.parse(text); } catch { return { res: json({ ok: false, error: "bad-request" }, 400) }; }
  if (!b || typeof b !== "object" || Array.isArray(b)) return { res: json({ ok: false, error: "bad-request" }, 400) };
  return { b };
}

// ---------- hashing and constant-time comparison ----------
const enc = new TextEncoder();
export async function sha256hex(s) {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(String(s))));
  return Array.from(d, (x) => x.toString(16).padStart(2, "0")).join("");
}
// Compare two strings without leaking where they differ: both are hashed to 32 bytes first,
// so the loop always runs the same length whatever the inputs.
export async function sameSecret(a, b) {
  const [x, y] = await Promise.all([a, b].map((s) => crypto.subtle.digest("SHA-256", enc.encode(String(s)))));
  const u = new Uint8Array(x), v = new Uint8Array(y);
  let diff = 0;
  for (let i = 0; i < u.length; i++) diff |= u[i] ^ v[i];
  return diff === 0;
}

// ---------- admin token ----------
// The token travels only in the Authorization header ("Bearer <token>"), never in a URL.
export async function isAdmin(request, env) {
  const want = String(env.ADMIN_TOKEN || "");
  if (want.length < 24) return false;
  const h = request.headers.get("Authorization") || "";
  const m = /^Bearer\s+(\S{24,512})\s*$/i.exec(h);
  if (!m) return false;
  return sameSecret(m[1], want);
}

// ---------- soft rate limits ----------
// Per visitor, in this server's memory only: the IP address is hashed with a random value that exists only
// in memory, never stored, never logged, and forgotten when the server instance stops (minutes to hours).
// It slows down floods; the database caps below are the hard backstop.
// (made on first use: Workers do not allow random values at module load)
let SALT = "";
const HITS = new Map();
export async function tooMany(request, bucket, max, windowMs, { peek = false } = {}) {
  const ip = request.headers.get("CF-Connecting-IP") || "";
  if (!ip) return false;
  if (!SALT) SALT = Array.from(crypto.getRandomValues(new Uint8Array(16)), (x) => x.toString(16)).join("");
  const k = bucket + ":" + (await sha256hex(SALT + ip)).slice(0, 20);
  const now = Date.now();
  const list = (HITS.get(k) || []).filter((t) => now - t < windowMs);
  const over = list.length >= max;
  if (!over && !peek) list.push(now);
  HITS.set(k, list);
  if (HITS.size > 5000) HITS.clear();
  return over;
}
// Site-wide cap from rows already in the table (no visitor data needed).
export async function tableBusy(env, table, max, hours = 1) {
  const since = new Date(Date.now() - hours * 3.6e6).toISOString();
  const r = await env.DB.prepare(`SELECT COUNT(*) AS n FROM ${table} WHERE created > ?`).bind(since).first();
  return !!r && r.n >= max;
}

// ---------- Turnstile ----------
const DEFAULT_HOSTS = ["gamsa.au", "www.gamsa.au"];
export function hostAllowed(hostname, request, env) {
  const h = String(hostname || "").toLowerCase();
  if (!h) return false;
  const own = new URL(request.url).hostname.toLowerCase();   // e.g. a Cloudflare preview address
  const extra = String(env.TURNSTILE_HOSTNAMES || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  return h === own || DEFAULT_HOSTS.includes(h) || extra.includes(h);
}
// true only if Cloudflare says the token is good AND it was solved on this site.
export async function turnstileOk(request, env, token, { sendIp = true } = {}) {
  const t = String(token || "");
  if (!t || t.length > 2048) return false;
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", t);
  const ip = sendIp ? request.headers.get("CF-Connecting-IP") : null;
  if (ip) form.append("remoteip", ip);
  const opts = { method: "POST", body: form };
  if (typeof AbortSignal !== "undefined" && AbortSignal.timeout) opts.signal = AbortSignal.timeout(8000);
  let r;
  try { r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", opts).then((x) => x.json()); }
  catch { return false; }
  return !!r && r.success === true && hostAllowed(r.hostname, request, env);
}

// ---------- stock facts only ----------
// Published reports show what is on the shelf and when. Notes that mention prices, offers or contact
// details are dropped (the rest of the report is kept). Names and suburbs may not carry prices or links.
const PRICE = /(?:[$€£]|\ba\$|\baud\b)\s?\d|\d\s?(?:aud|dollars?|bucks|cents?)\b|\bprice[sd]?\b|\bpricing\b|\bcosts?\b|\bcosting\b|\bfees?\b|\bcharge[sd]?\b|\bpaid\b|\bpay\b/i;
const PROMO = /\b(?:cheap\w*|discount\w*|sales?|deals?|promo\w*|bargains?|sav(?:e|es|ing|ings)|free|lowest|beat\w*|unbeatable|guarantee\w*|coupons?|vouchers?|bonus\w*|rewards?|loyalty|cashback|half[- ]price|buy (?:one|now|two)|shop now|order now|call (?:us|now|today)|visit (?:us|our)|come (?:in|and see)|hurry|limited time)\b|\d\s?%\s?off\b|%\s?off\b/i;
const CONTACT = /@|https?:\/\/|\bwww\.|\.com\b|\.com\.au\b|\b\d[\d\s()-]{7,}\d\b/i;
export const NAME_BAD = /(?:[$€£])\s?\d|@|https?:\/\/|\bwww\./i;
export function factsOnly(note) {
  const n = String(note || "");
  if (!n) return "";
  return PRICE.test(n) || PROMO.test(n) || CONTACT.test(n) ? "" : n;
}

// ---------- report keys ----------
// 20 characters from a 32-letter alphabet with no look-alikes (100 bits), shown as 4 groups of 5.
const ALPHA = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";
export function newReportKey() {
  const b = crypto.getRandomValues(new Uint8Array(20));
  const s = Array.from(b, (x) => ALPHA[x & 31]).join("");
  return s.match(/.{5}/g).join("-");
}
export const normKey = (k) => String(k || "").toUpperCase().replace(/[^0-9A-Z]/g, "").slice(0, 40);

// ---------- additive schema update ----------
// The v19 code needs two new columns on pharmacists, one on sightings and a new csp_reports table.
// Added once per server instance, only if missing; nothing is dropped or rewritten (see schema.sql).
let schemaReady = null;
const PROBE = "SELECT (SELECT key_hash FROM pharmacists LIMIT 0), (SELECT key_issued FROM pharmacists LIMIT 0), " +
  "(SELECT published FROM sightings LIMIT 0), (SELECT 1 FROM csp_reports LIMIT 0)";
const STEPS = [
  "ALTER TABLE pharmacists ADD COLUMN key_hash TEXT",
  "ALTER TABLE pharmacists ADD COLUMN key_issued TEXT",
  "ALTER TABLE sightings ADD COLUMN published INTEGER NOT NULL DEFAULT 1",
  "CREATE TABLE IF NOT EXISTS csp_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, directive TEXT NOT NULL, " +
    "blocked TEXT NOT NULL, page TEXT NOT NULL, mode TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 1, last TEXT NOT NULL, " +
    "UNIQUE (day, directive, blocked, page, mode))",
];
export function ensureSchema(env) {
  if (!schemaReady) schemaReady = (async () => {
    try { await env.DB.prepare(PROBE).first(); return; } catch { /* something is missing: add it below */ }
    for (const sql of STEPS) {
      try { await env.DB.prepare(sql).run(); }
      catch (e) { if (!/duplicate column/i.test(String(e && e.message))) console.error("schema step failed:", sql.slice(0, 60), String(e && e.message)); }
    }
  })().catch((e) => { schemaReady = null; throw e; });
  return schemaReady;
}
