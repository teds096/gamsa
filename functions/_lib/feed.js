// v19.7 (13 Nov 2026): "Make your own feed" on /alerts. Pure helpers with no imports, so tools/extra_checks.py can run
// this exact file in a browser. Used by functions/feed.js, which answers /feed?m=<slug>,<slug>.
//
// The daily feed.xml (build.py _rss) gives each item a <category domain="https://gamsa.au/medicines">slug</category>,
// the slug of its medicine page (/medicines/<slug>). Filtering keeps the items whose slug was asked for and drops the
// rest; everything else in the feed (channel text, guid, dates) stays exactly as built, so readers see no duplicates.

export const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+){0,8}$/;
export const MAX_SLUGS = 60;   // the site has 25 medicines today; room for growth, small enough to stay cheap

// "a,b" -> { ok: true, slugs: ["a", "b"] }. Empty or missing -> { ok: true, slugs: [] } (the whole feed).
export function parseSlugs(q) {
  const raw = String(q == null ? "" : q).trim();
  if (!raw) return { ok: true, slugs: [] };
  if (raw.length > 2000) return { ok: false, slugs: [] };
  const slugs = [];
  for (const part of raw.split(",")) {
    const s = part.trim();
    if (!s) continue;
    if (s.length > 60 || !SLUG.test(s)) return { ok: false, slugs: [] };
    if (!slugs.includes(s)) slugs.push(s);
  }
  if (slugs.length > MAX_SLUGS) return { ok: false, slugs: [] };
  return { ok: true, slugs };
}

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// Title for a selection: names from the build-time list, or the slug itself if a name is missing.
export function feedTitle(slugs, names) {
  const n = slugs.map((s) => (names && names[s]) || s);
  const shown = n.length > 3 ? n.slice(0, 3).join(", ") + " and " + (n.length - 3) + " more" : n.join(", ");
  return "GAMSA shortage alerts: " + shown;
}

// Keep only the items for the chosen slugs. No slugs: the feed comes back unchanged.
export function filterFeed(xml, slugs, names) {
  if (!slugs || !slugs.length) return xml;
  const want = new Set(slugs);
  const parts = String(xml).split(/(<item>[\s\S]*?<\/item>)/);
  let titled = false;
  return parts.map((p) => {
    if (p.startsWith("<item>")) {
      const m = p.match(/<category domain="[^"]*\/medicines">([a-z0-9-]+)<\/category>/);
      return m && want.has(m[1]) ? p : "";
    }
    if (!titled && p.includes("<channel>")) {
      titled = true;
      return p.replace(/(<channel>\s*<title>)[^<]*(<\/title>)/, (_, a, b) => a + esc(feedTitle(slugs, names)) + b);
    }
    return p;
  }).join("");
}
