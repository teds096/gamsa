#!/usr/bin/env python3
"""Monthly check of PBS brand premiums and PBS listings for the medicines on the site.

1. Reads the PBS brand-premium table and keeps the rows for the site's medicines,
   writing data/premiums.json. The costs page renders that list, so the figures on
   the site always match the PBS list as of the last run. If the rows differ from
   last month the script prints PREMIUMS_CHANGED so the workflow can open a note.
2. Fetches every PBS item page cited in the content (item 10205D and so on), confirms
   it still exists, and records its schedule, authority level, price and brands with
   the 'a' (brand substitution permitted) flag — shown on each medicine page. A missing item is printed and the script exits 1, so
   the workflow raises an issue — a delisting needs a human to update the wording.
Fails loudly if the premium table cannot be parsed; the old data file is kept.
"""
import json, pathlib, re, sys, time
import requests
from bs4 import BeautifulSoup

R = pathlib.Path(__file__).parent.parent
OUT = R / "data" / "premiums.json"
URL = "https://www.pbs.gov.au/browse/brand-premium"
H = {"User-Agent": "gamsa/1.0 (+https://gamsa.au)"}

def generics():
    m = json.loads((R / "content/medicines.json").read_text())["medicines"]
    words = set()
    for x in m:
        for part in re.split(r"[+/,]| and ", x["generic"].lower()):
            part = part.strip()
            if len(part) > 4: words.add(part)
    return sorted(words)

def premium_rows(words):
    html = requests.get(URL, timeout=60, headers=H).text
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table: raise SystemExit("FAIL: no table on the brand premium page — layout changed")
    rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < 7: continue
        for d in tds[1].select(".au-legend__item"): d.decompose()
        cell = lambda i: re.sub(r"\s+", " ", tds[i].get_text(" ")).strip()
        product = cell(1)
        if not any(w in product.lower() for w in words): continue
        m = re.search(r"\$(\d+\.\d{2})", cell(5))
        if not m: continue
        bench = [re.sub(r"\s+", " ", a.get_text()).strip() for a in tds[6].find_all("a")] or [cell(6)]
        rows.append({"brand": cell(0), "product": product, "packs": cell(2), "units": cell(3),
                     "repeats": cell(4), "premium": m.group(1), "benchmark": bench})
    if not rows: raise SystemExit("FAIL: brand premium table parsed but no rows matched — check the parser")
    return rows

def listing_codes():
    codes = set()
    for f in (R / "content").glob("*.json"):
        codes |= set(re.findall(r"(?:[Ii]tem|PBS)[^.\n]{0,40}?\b(\d{4,5}[A-Z])\b", f.read_text()))
    return sorted(codes)

def parse_item(html, code):
    """One PBS item page: schedule, authority level, price, and brands with the
    'a' flag (brand substitution permitted)."""
    soup = BeautifulSoup(html, "html.parser")
    if not re.search(r"\b" + code + r"\b", html) or "Page not found" in html: return None
    text = lambda e: re.sub(r"\s+", " ", e.get_text(" ")).strip() if e else ""
    item = {"name": text(soup.select_one("h1")), "schedule": "", "authority": "", "dpmq": "", "general": "", "brands": []}
    # The PBS site serves Vue custom elements in the raw HTML.
    item["schedule"] = text(soup.select_one('medicine-info-row[title="Schedule"]'))
    item["authority"] = text(soup.select_one('medicine-info-row[title="Authority"]'))
    strip = lambda t: re.sub(r"^.*?:\s*", "", t)
    item["dpmq"] = strip(text(soup.select_one("td.col-dpmq")))
    item["general"] = strip(text(soup.select_one("td.col-general-patient-charge")))
    for tr in soup.select("tr.row-brand"):
        a = tr.select_one("td.col-brand-name a")
        if a: item["brands"].append({"name": text(a), "sub": bool(tr.select_one('legend-item[code="a"]'))})
    return item

def check_listings(codes):
    items, missing = {}, []
    for c in codes:
        try:
            r = requests.get(f"https://www.pbs.gov.au/medicine/item/{c}", timeout=60, headers=H)
            it = parse_item(r.text, c) if r.status_code == 200 else None
        except Exception:
            it = None
        if it: items[c] = it
        else: missing.append(c)
        time.sleep(0.5)
    return items, missing

def main():
    words = generics()
    rows = premium_rows(words)
    codes = listing_codes()
    items, missing = check_listings(codes)
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    changed = old.get("rows") != rows or old.get("items") != items
    OUT.write_text(json.dumps({"checkedAt": time.strftime("%-d %b %Y"), "rows": rows, "items": items,
                               "listings": {"checked": codes, "missing": missing}}, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(rows)} premium rows for the site's medicines; {len(codes)} PBS items checked")
    if changed:
        print("PREMIUMS_CHANGED")
        for r in rows: print("  ", r["brand"], "|", r["product"], "|", r["packs"], "pack(s) | $" + r["premium"])
    if missing:
        print("LISTING_MISSING:", ", ".join(missing), file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
