#!/usr/bin/env python3
"""Monthly external link check over the built site (dist/).

Every external https link on every page is requested once. 2xx/3xx is fine; 401/403/405/429
are treated as "blocked to bots", not broken (government sites often refuse scripts).
404/410, 5xx and connection failures are reported. Writes /tmp/links.md and prints
LINKS_BROKEN when anything needs attention. Always exits 0: a dead outside link must
never stop the data refresh.
"""
import re, pathlib, sys, concurrent.futures as cf
import requests

D = pathlib.Path(__file__).resolve().parents[1] / "dist"
SKIP = re.compile(r"fonts\.(googleapis|gstatic)|cloudflareinsights|challenges\.cloudflare|schema\.org|w3\.org|google\.com\.au/?$")
UA = {"User-Agent": "Mozilla/5.0 (compatible; GAMSA link check; +https://gamsa.au)"}

def pages():
    for f in D.rglob("*.html"):
        rel = "/" + str(f.relative_to(D)).removesuffix(".html").replace("index", "")
        yield rel, f.read_text(errors="ignore")

def check(url):
    for attempt in range(2):
        try:
            r = requests.get(url, headers=UA, timeout=25, allow_redirects=True, stream=True)
            r.close()
            return r.status_code
        except Exception as exc:
            err = type(exc).__name__
    return err

def main():
    where = {}
    for page, html in pages():
        for u in re.findall(r'https://(?!gamsa\.au)[^\s"\'<>)\\]+', html):
            u = u.rstrip(".,;")
            if not SKIP.search(u):
                where.setdefault(u, set()).add(page)
    with cf.ThreadPoolExecutor(12) as ex:
        res = dict(zip(where, ex.map(check, where)))
    bad = {u: c for u, c in res.items() if not (isinstance(c, int) and (c < 400 or c in (401, 403, 405, 429)))}
    print(f"links: {len(res)} checked, {len(bad)} broken")
    if bad:
        lines = [f"## Broken outside links ({len(bad)})\n"]
        for u, c in sorted(bad.items()):
            lines.append(f"- `{c}` {u}\n  on: {', '.join(sorted(where[u])[:5])}")
        pathlib.Path("/tmp/links.md").write_text("\n".join(lines) + "\n\nOften a page has moved: search the site for the new address and update the content JSON or data/manual.json.\n")
        print("LINKS_BROKEN")
    return 0

if __name__ == "__main__":
    sys.exit(main())
