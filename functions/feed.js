// v19.7 (13 Nov 2026): /feed?m=estradiol-patches,spironolactone gives the shortage feed for the chosen medicines only
// (built with "Make your own feed" on /alerts). It reads the site's own static /feed.xml and keeps the matching items
// (functions/_lib/feed.js). /feed with no medicines gives the whole feed. The plain /feed.xml is a static file and
// never passes through here. No cookies, no accounts, nothing stored, no outside services.
import { parseSlugs, filterFeed } from "./_lib/feed.js";
import { FEED_NAMES } from "./_lib/feed_names.js";

// The site's _headers rules may not reach Function replies, so the ones that matter are set here.
const HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
  "Access-Control-Allow-Origin": "*",   // web feed readers fetch from their own sites; the feed is public
};
const text = (msg, status) => new Response(msg + "\n", {
  status, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", ...HEADERS },
});

export async function onRequest({ request, env }) {
  if (request.method !== "GET" && request.method !== "HEAD")
    return new Response(null, { status: 405, headers: { Allow: "GET, HEAD", ...HEADERS } });
  const url = new URL(request.url);
  const { ok, slugs } = parseSlugs(url.searchParams.get("m"));
  if (!ok) return text("This feed address is not recognised. Make a new one at https://gamsa.au/alerts", 400);
  let xml;
  try {
    const src = await env.ASSETS.fetch(new URL("/feed.xml", url.origin));
    if (!src.ok) throw new Error("feed.xml " + src.status);
    xml = await src.text();
  } catch (e) {
    console.error("feed failed:", String(e && e.message).slice(0, 200));
    return text("The feed is not available just now. Please try again later.", 503);
  }
  const body = filterFeed(xml, slugs, FEED_NAMES);
  return new Response(request.method === "HEAD" ? null : body, {
    status: 200,
    headers: { "Content-Type": "application/rss+xml; charset=utf-8", "Cache-Control": "public, max-age=3600", ...HEADERS },
  });
}
