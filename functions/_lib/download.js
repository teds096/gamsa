// v19.5 (7 Nov 2026): download totals for the printables. Used by functions/{guides,clinicians,allies}/[file].js, which
// match one file name under those folders only (never the /guides, /clinicians or /allies pages themselves).
//
// The file is served exactly as before (Cloudflare's own static file, same body, type and caching); this only adds 1 to
// today's total for that path, after the reply has gone (waitUntil). It fails open: if the database errors, the file
// still downloads. Not counted: HEAD, repeat checks (304), later parts of a split download, links Ted opens with the
// owner switch on (the page adds ?own=1), and robots or scripts (their user agent is checked here and never stored).
import { addCount } from "./counts.js";
import { FILE_REDIRECTS } from "./file_redirects.js";

const FILE = /\.(pdf|zip)$/i;
const BOT = /bot|crawl|spider|slurp|preview|monitor|headless|lighthouse|curl|wget|python|httpx|go-http|java\/|gamsa/i;  // gamsa: our own check tools (live check, after-release check)
// The site's _headers rules may not reach Function replies, so the ones that matter for a file are added here if missing.
const HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Frame-Options": "DENY",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
};

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const path = url.pathname;
  if (!FILE.test(path)) return context.next();
  const to = FILE_REDIRECTS[path];                       // old file names (static/_redirects), kept working
  if (to) return new Response(null, { status: 301, headers: { Location: to, ...HEADERS } });
  let res = await context.next();
  try {
    const out = new Response(res.body, res);
    for (const [k, v] of Object.entries(HEADERS)) if (!out.headers.has(k)) out.headers.set(k, v);
    res = out;
  } catch { /* keep the reply as it came */ }
  try {
    const range = request.headers.get("Range") || "";
    const whole = res.status === 200 || (res.status === 206 && /^bytes=0-/.test(range));
    if (request.method === "GET" && whole && !url.searchParams.has("own") && !BOT.test(request.headers.get("User-Agent") || ""))
      context.waitUntil(addCount(env, "file", path.slice(0, 120), 300).catch((e) => console.error("count failed:", String(e && e.message).slice(0, 200))));
  } catch { /* never block the download */ }
  return res;
}
