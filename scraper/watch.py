#!/usr/bin/env python3
"""Weekly: has anything new appeared on the clinical, policy or supply pages GAMSA relies on?

Added in v19.8 (Ted, 17 Nov 2026: "a news, guidelines, reference scraper for any clinical updates").
For each source page below it collects the link texts, headings and sentences that mention a GAMSA topic
(KEYWORDS), and compares them with data/watch-state.json. Anything not seen before is listed in /tmp/watch.md
and the script prints WATCH_NEW, so the workflow adds it to the open "watch" issue (GitHub emails Ted).
The first run for a page only records a baseline. Pages that do not load are skipped and tried next week.
It never changes the site: a person reads the item and decides whether a page needs updating.
Same manners as pi_check.py: one request at a time, a pause between pages, a time budget. Always exits 0.
"""
import hashlib, html, json, pathlib, re, sys, time, urllib.parse
import requests

R = pathlib.Path(__file__).resolve().parents[1]
STATE = R / "data/watch-state.json"
BUDGET = 300  # seconds
# A plain browser User-Agent with a GAMSA tag: NHMRC times out bot-style agents (17 Nov 2026).
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36 GAMSA-update-watch"}

SOURCES = [  # (name, url): listing or guideline pages, Australian sources first
    ("NHMRC under-18 guidelines", "https://www.nhmrc.gov.au/health-advice/guidelines-care-trans-and-gender-diverse-people"),
    ("NHMRC puberty suppressant advice", "https://www.nhmrc.gov.au/health-advice/guidelines-care-trans-and-gender-diverse-people/advice-puberty-suppressants"),
    ("AusPATH standards of care", "https://auspath.org.au/standards-of-care/"),
    ("TGA safety alerts", "https://www.tga.gov.au/news/safety-alerts"),
    ("TGA news", "https://www.tga.gov.au/news/news"),
    ("PBS news", "https://www.pbs.gov.au/info/news"),
    ("Australian Government health news", "https://www.health.gov.au/news"),
    ("Queensland Government statements", "https://statements.qld.gov.au/"),
    ("RCH gender service", "https://www.rch.org.au/adolescent-medicine/gender-service/"),
    ("UK PATHWAYS trial updates", "https://www.hra.nhs.uk/about-us/news-updates/"),
]

KEYWORDS = re.compile(
    r"puberty|gender|\btrans\b|transgender|non-binary|testosteron|estradiol|oestradiol|estrogen|oestrogen|"
    r"progesteron|spironolacton|cyproterone|androcur|bicalutamide|finasteride|dutasteride|gnrh|goserelin|"
    r"zoladex|leuprorelin|lucrin|eligard|triptorelin|reandron|testogel|androforte|primoteston|estradot|"
    r"estraderm|climara|sandrena|estrogel|progynova|zumenon|shortage|auspath|hormone", re.I)

def items(url, text):
    """Keyword items on a page: {hash: (short text, link or page url)}."""
    t = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", text)
    out = {}
    def add(s, link):
        s = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()
        if 12 <= len(s) <= 400 and KEYWORDS.search(s):
            out[hashlib.sha1(s.lower().encode()).hexdigest()[:16]] = (s[:300], link)
    for href, a in re.findall(r'(?is)<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', t):
        add(a, urllib.parse.urljoin(url, html.unescape(href)))
    for h in re.findall(r"(?is)<h[1-4]\b[^>]*>(.*?)</h[1-4]>", t):
        add(h, url)
    body = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(nav|header|footer)\b.*?</\1>", " ", t))
    for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", html.unescape(body))):
        add(s, url)
    return out

def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    start, new, skipped = time.time(), [], []
    for name, url in sorted(SOURCES, key=lambda s: state.get(s[1], {}).get("checked", "")):
        if time.time() - start > BUDGET:
            skipped.append(name + " (out of time)"); continue
        try:
            r = requests.get(url, headers=UA, timeout=25)
            r.raise_for_status()
        except Exception as e:
            skipped.append(f"{name} ({type(e).__name__})"); time.sleep(2); continue
        found = items(url, r.text)
        old = state.get(url)
        if old is not None:
            seen = set(old.get("seen", []))
            for k, (s, link) in found.items():
                if k not in seen:
                    new.append((name, s, link))
            seen |= set(found)
        else:
            seen = set(found)
        state[url] = {"name": name, "checked": time.strftime("%Y-%m-%d"), "seen": sorted(seen)[-3000:]}
        STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
        time.sleep(3)
    lines = []
    if new:
        lines += [f"New items on pages GAMSA watches ({time.strftime('%d %b %Y')}). Read each and decide whether a page needs updating:", ""]
        for name, s, link in new[:60]:
            lines.append(f"- **{name}**: {s} ({link})")
        if len(new) > 60: lines.append(f"- ...and {len(new) - 60} more")
    if skipped:
        lines += ["", "Not checked this time (tried again next week): " + "; ".join(skipped)]
    pathlib.Path("/tmp/watch.md").write_text("\n".join(lines) + "\n")
    print(f"watch: {len(new)} new, {len(skipped)} skipped")
    if new: print("WATCH_NEW")

if __name__ == "__main__":
    try: main()
    except Exception as e: print("watch failed:", e)
    sys.exit(0)
