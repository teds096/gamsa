#!/usr/bin/env python3
"""Tell Bing (and other IndexNow search engines) which gamsa.au pages changed.

  python scraper/indexnow.py data   # after a daily data change: pages that show supply/cost data
  python scraper/indexnow.py all    # after a release (manual Run workflow): every page in the sitemap
The key file static/4a74589828bfffd5ccd804e43f732ee8.txt proves the site owns the key. Always exits 0.
"""
import json, re, sys, pathlib, urllib.request
KEY = "4a74589828bfffd5ccd804e43f732ee8"
SITE = "https://gamsa.au"
R = pathlib.Path(__file__).resolve().parents[1]

def main():
    mode = (sys.argv[1:] or ["data"])[0]
    sm = (R / "dist/sitemap.xml").read_text()
    urls = re.findall(r"<loc>([^<]+)</loc>", sm)
    if mode != "all":
        keep = ("/", "/supply", "/alerts", "/costs", "/medicines")
        urls = [u for u in urls if u[len(SITE):] in keep or u[len(SITE):] in ("",) or "/medicines/" in u]
    body = json.dumps({"host": "gamsa.au", "key": KEY, "keyLocation": f"{SITE}/{KEY}.txt", "urlList": urls[:10000]}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", body, {"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: print(f"IndexNow: {len(urls)} URLs sent, HTTP {r.status}")
    except Exception as e:
        print(f"IndexNow: not sent ({e})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
