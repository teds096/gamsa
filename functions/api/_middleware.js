// Runs before every /api/* function (v19). Cloudflare does not apply the site's _headers file to Function
// replies, so the security headers are added here, and any unexpected error becomes a plain
// {"ok":false,"error":"server"} reply instead of a stack trace or an HTML error page.
import { json, SECURITY_HEADERS } from "../_lib/util.js";

export async function onRequest(context) {
  let res;
  try {
    res = await context.next();
  } catch (e) {
    console.error("api error:", new URL(context.request.url).pathname, String((e && e.stack) || e).slice(0, 500));
    return json({ ok: false, error: "server" }, 500);
  }
  const out = new Response(res.body, res);
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) if (!out.headers.has(k)) out.headers.set(k, v);
  if (!out.headers.has("Cache-Control")) out.headers.set("Cache-Control", "no-store");
  if (!out.headers.has("Content-Security-Policy")) out.headers.set("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'");
  return out;
}
