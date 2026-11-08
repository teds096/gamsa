// /api/ref (v19.5, 7 Nov 2026) — outreach tags. A link such as https://gamsa.au/?ref=tgv-email makes the page send the tag
// here once (navigator.sendBeacon), then drops it from the address bar. Only the tag and a daily total are kept: no referrer
// address, IP, user agent or cookie. Tags must be 1 to 30 of a-z, 0-9 and "-"; anything else is ignored. Always 204.
import { tooMany } from "../_lib/util.js";
import { addCount } from "../_lib/counts.js";

const TAG = /^[a-z0-9-]{1,30}$/;
// Same robot filter as the download counter: link previewers, crawlers and our own check tools are not counted.
const BOT = /bot|crawl|spider|slurp|preview|monitor|headless|lighthouse|curl|wget|python|httpx|go-http|java\/|gamsa/i;

export async function onRequestPost(context) {
  const { request, env } = context;
  const done = new Response(null, { status: 204 });
  try {
    if (Number(request.headers.get("Content-Length") || 0) > 64) return done;
    const tag = (await request.text()).trim();
    if (!TAG.test(tag)) return done;
    if (BOT.test(request.headers.get("User-Agent") || "")) return done;
    if (await tooMany(request, "ref", 5, 10 * 60e3)) return done;   // a visitor counts at most 5 times in 10 minutes
    context.waitUntil(addCount(env, "ref", tag, 200).catch((e) => console.error("ref count failed:", String(e && e.message).slice(0, 200))));
  } catch { /* ignore */ }
  return done;
}

export async function onRequestGet() {
  return new Response(null, { status: 404 });
}
