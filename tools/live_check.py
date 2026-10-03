"""After-release live check for gamsa.au (runs in GitHub Actions after every site push).

1. Waits until Cloudflare Pages is serving this commit: the live Content-Security-Policy
   must carry the same script hashes as the dist/_headers built from this commit.
2. Then checks the live site: every sitemap page (200, unique title, canonical, rendered view,
   no template tokens), 404s, security headers, every inline script hashed, no cookies,
   only allowed outside hosts referenced, downloads, a few redirects and /api/reports.
Prints PASS/FAIL lines; exit code 1 if anything failed. Standard library only.
"""
import base64, hashlib, re, sys, time, urllib.error, urllib.request

import os
SITE = os.environ.get("LIVE_SITE", "https://gamsa.au")
UA = {"User-Agent": "gamsa-live-check (+https://gamsa.au)", "Cache-Control": "no-cache"}
ALLOWED_HOSTS = {"gamsa.au", "www.gamsa.au", "static.cloudflareinsights.com",
                 "cloudflareinsights.com", "challenges.cloudflare.com"}
fails, lines = [], []


def get(path, redirect=True):
    url = path if path.startswith("http") else SITE + path
    req = urllib.request.Request(url, headers=UA)
    opener = urllib.request.build_opener() if redirect else urllib.request.build_opener(NoRedirect)
    try:
        r = opener.open(req, timeout=30)
        return r.status, dict(r.headers), r.read(), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(), url
    except Exception as e:  # DNS, timeout, TLS: report as status 0
        return 0, {}, str(e).encode(), url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def result(ok, name, detail=""):
    lines.append(("PASS " if ok else "FAIL ") + name + (" — " + detail if detail else ""))
    if not ok:
        fails.append(name)


def hashes(csp):
    return set(re.findall(r"'sha256-[^']+'", csp or ""))


def wait_for_deploy(max_wait=900):
    """Wait for the "Cloudflare Pages" check on this commit (posted by Cloudflare's GitHub app) to finish."""
    import json, os
    sha, repo, tok = os.environ.get("GITHUB_SHA"), os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if os.environ.get("LIVE_NOWAIT") or not (sha and repo and tok):
        print("NOTE not waiting for deploy")
        return True
    url = f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs"
    hdr = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "gamsa-live-check"}
    t0 = time.time()
    while time.time() - t0 < max_wait:
        try:
            runs = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=30))["check_runs"]
            cf = [r for r in runs if "cloudflare" in (r.get("app") or {}).get("slug", "") or r["name"].startswith("Cloudflare")]
            if cf and all(r["status"] == "completed" for r in cf):
                ok = all(r["conclusion"] == "success" for r in cf)
                print(f"Cloudflare deploy {'finished' if ok else 'FAILED'} after {int(time.time() - t0)} s")
                time.sleep(45)  # let the new version reach the edge
                return ok
            if not cf and time.time() - t0 > 300:
                print("NOTE no Cloudflare Pages check on this commit after 5 min — checking the live site anyway")
                return True
        except Exception as e:  # API blip — keep waiting
            print("waiting:", e)
        time.sleep(20)
    return False


def main():
    if not wait_for_deploy():
        result(False, "deploy", "Cloudflare Pages deploy failed or did not finish within 15 minutes")
        return finish()

    # Pages
    st, _, body, _ = get("/sitemap.xml")
    paths = [re.sub(r"^https?://[^/]+", "", u) or "/" for u in re.findall(r"<loc>([^<]+)</loc>", body.decode())]
    bad, titles, dl = [], {}, set()
    for p in paths:
        s, h, b, _ = get(p)
        t = b.decode("utf-8", "replace")
        title = (re.search(r"<title>([^<]*)</title>", t) or [None, ""])[1]
        can = (re.search(r'rel="canonical" href="([^"]+)"', t) or [None, ""])[1]
        if s != 200 or 'class="view on"' not in t or "{{" in t or "__TOKEN__" in t \
                or (can and re.sub(r"^https?://[^/]+", "", can) != p):
            bad.append(f"{p} ({s})")
        titles.setdefault(title, []).append(p)
        dl.update(re.findall(r'(?<![\w.])(/(?:clinicians|allies)/[A-Za-z0-9._-]+\.(?:pdf|zip))', t))
        if "set-cookie" in {k.lower() for k in h}:
            bad.append(f"{p} sets a cookie")
    dup = [ps for ps in titles.values() if len(ps) > 1]
    result(st == 200 and paths and not bad, f"pages — {len(paths)} sitemap pages", "; ".join(bad[:8]))
    result(not dup, "unique titles", "; ".join(", ".join(d) for d in dup[:3]))
    for p in ("/no-such-page", "/medicines/nope"):
        s = get(p)[0]
        result(s == 404, f"404 for {p}", f"got {s}")

    # Home page: headers, CSP hashes, outside hosts
    s, h, b, _ = get("/")
    h = {k.lower(): v for k, v in h.items()}
    html = b.decode("utf-8", "replace")
    need = ["content-security-policy", "strict-transport-security", "x-content-type-options",
            "referrer-policy", "permissions-policy", "x-frame-options"]
    miss = [k for k in need if k not in h]
    result(not miss and "frame-ancestors" in h.get("content-security-policy", ""), "security headers", ", ".join(miss))
    live = hashes(h.get("content-security-policy"))
    unhashed = 0
    for attrs, code in re.findall(r"<script([^>]*)>(.*?)</script>", html, re.S):
        if "src=" in attrs or "ld+json" in attrs:
            continue
        hsh = "'sha256-" + base64.b64encode(hashlib.sha256(code.encode()).digest()).decode() + "'"
        unhashed += hsh not in live
    result(unhashed == 0, "every inline script is in the CSP", f"{unhashed} not hashed")
    # links to outside pages are fine; only scripts, styles, fonts and images count
    loaded = set(re.findall(r'<(?:script|link|img|iframe)[^>]+(?:src|href)="https?://([^/"]+)', html)) - ALLOWED_HOSTS
    result(not loaded, "no outside services loaded", ", ".join(sorted(loaded)))
    result("set-cookie" not in h, "no cookies on /")
    result("bom.gov.au" in html, "quick exit target present")

    # www redirect, downloads, redirects, API
    if SITE == "https://gamsa.au":
        s, _, _, final = get("https://www.gamsa.au/")
        result(final.rstrip("/") == SITE, "www → gamsa.au", final)
    dl = sorted(dl)
    badl = [p for p in dl + ["/og-image.png", "/favicon.ico", "/apple-touch-icon.png", "/feed.xml", "/robots.txt"]
            if get(p)[0] != 200]
    result(not badl, f"downloads and files — {len(dl)} documents", ", ".join(badl))
    try:
        rd = [l.split() for l in open("static/_redirects", encoding="utf-8")
              if l.strip() and not l.startswith("#") and ":splat" not in l and "*" not in l][:4]
    except OSError:
        rd = []
    badr = []
    for src, dst, *_ in rd:
        s, _, _, final = get(src)
        if s != 200 or not final.rstrip("/").endswith(dst.rstrip("/")):
            badr.append(f"{src} → {final} ({s})")
    result(not badr, f"redirects — {len(rd)} sampled", "; ".join(badr))
    result(get("/api/reports")[0] == 200, "/api/reports answers")
    return finish()


def finish():
    print("\n".join(lines))
    print(f"\n{len(lines) - len(fails)}/{len(lines)} live checks passed" + (": fix " + ", ".join(fails) if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
