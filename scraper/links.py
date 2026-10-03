#!/usr/bin/env python3
"""Monthly external link check over the built site (dist/).

Every external https link on every page is requested once. 2xx/3xx is fine; 401/403/405/429
are treated as "blocked to bots", not broken (government sites often refuse scripts).
404/410, 5xx and DNS/SSL failures are reported. Timeouts and dropped connections are
listed separately as "could not check" (big .gov.au sites throttle GitHub's servers); they
do not raise the issue. Each host is checked one link at a time with a pause, so no site
is hammered. Writes /tmp/links.md and prints
LINKS_BROKEN when anything needs attention. Always exits 0: a dead outside link must
never stop the data refresh.
"""
import re, pathlib, sys, time, concurrent.futures as cf
import requests

D = pathlib.Path(__file__).resolve().parents[1] / "dist"
SKIP = re.compile(r"fonts\.(googleapis|gstatic)|cloudflareinsights|challenges\.cloudflare|schema\.org|w3\.org|google\.com\.au/?$")
UA = {"User-Agent": "Mozilla/5.0 (compatible; GAMSA link check; +https://gamsa.au)"}

def pages():
    for f in D.rglob("*.html"):
        rel = "/" + str(f.relative_to(D)).removesuffix(".html").replace("index", "")
        yield rel, f.read_text(errors="ignore")

SOFT = ("ReadTimeout", "ConnectTimeout", "Timeout", "ConnectionError", "ChunkedEncodingError")

def check(url):
    for attempt in range(2):
        try:
            r = requests.get(url, headers=UA, timeout=20, allow_redirects=True, stream=True)
            r.close()
            if r.status_code in (429, 503) and attempt < 1: time.sleep(10); continue
            return r.status_code
        except Exception as exc:
            err = type(exc).__name__
            if "NameResolution" in str(exc) or "SSL" in err: return err + " (site address or certificate failed)"
            time.sleep(3)
    return err

def by_host(urls):
    # A site that times out twice in a row is throttling us: mark the rest "could not check"
    # instead of waiting minutes per link (keeps the whole step to a few minutes).
    out, strikes = {}, 0
    for u in urls:
        if strikes >= 2: out[u] = "Timeout"; continue
        out[u] = check(u); time.sleep(1.5)
        strikes = strikes + 1 if out[u] in SOFT else 0
    return out

def main():
    where = {}
    for page, html in pages():
        for u in re.findall(r'https://(?!gamsa\.au)[^\s"\'<>)\\]+', html):
            u = u.rstrip(".,;")
            if not SKIP.search(u):
                where.setdefault(u, set()).add(page)
    hosts = {}
    for u in where: hosts.setdefault(u.split("/")[2], []).append(u)
    res = {}
    with cf.ThreadPoolExecutor(12) as ex:
        for part in ex.map(by_host, hosts.values()): res.update(part)
    soft = {u: c for u, c in res.items() if isinstance(c, str) and c in SOFT}
    bad = {u: c for u, c in res.items() if u not in soft and not (isinstance(c, int) and (c < 400 or c in (401, 403, 405, 429)))}
    print(f"links: {len(res)} checked, {len(bad)} broken, {len(soft)} could not check (timeouts)")
    if soft:
        print("Could not check (site slow or throttling GitHub): " + ", ".join(sorted({u.split('/')[2] for u in soft})))
    if bad:
        lines = [f"## Broken outside links ({len(bad)})\n"]
        for u, c in sorted(bad.items()):
            lines.append(f"- `{c}` {u}\n  on: {', '.join(sorted(where[u])[:5])}")
        pathlib.Path("/tmp/links.md").write_text("\n".join(lines) + "\n\nOften a page has moved: search the site for the new address and update the content JSON or data/manual.json.\n")
        print("LINKS_BROKEN")
    return 0

if __name__ == "__main__":
    sys.exit(main())
