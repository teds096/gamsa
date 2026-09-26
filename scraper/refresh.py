#!/usr/bin/env python3
"""Refresh official HRT shortage data from the TGA.

Pulls the TGA medicine-shortage detail page for each tracked ingredient, parses the
product rows, and merges the result with docs/data/manual.json (entries that have no
machine-readable TGA record and are maintained by hand).

Fails loudly. If the TGA changes its page structure the parse yields nothing, the
script exits non-zero, and the GitHub Action opens an issue instead of silently
committing an empty file.
"""

import json
import pathlib
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

BASE = "https://apps.tga.gov.au/shortages/search/Details/{}"

# Ingredients with a machine-readable TGA shortage page, mapped to the hormone class
# used by the site's filters.
INGREDIENTS = {
    "estradiol": "estrogen",
    "testosterone": "testosterone",
    "progesterone": "progestogen",
    "medroxyprogesterone": "progestogen",
    "norethisterone": "progestogen",
    "spironolactone": "anti-androgen",
    "cyproterone": "anti-androgen",
    "goserelin": "gnrh-analogue",
    "leuprorelin": "gnrh-analogue",
}

# A parse that returns fewer than this many rows across all ingredients means the page
# structure has almost certainly changed. Estradiol alone normally yields several.
MIN_EXPECTED_ROWS = 4

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "medicines.json"
MANUAL = ROOT / "data" / "manual.json"

HEADERS = {"User-Agent": "hrt-stock-watch/1.0 (+https://github.com/)"}


def slug(text):
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")[:60]


def status_from(text):
    t = text.lower()
    if "discontinu" in t:
        return "discontinued", "Discontinued"
    if "limited" in t or "anticipated" in t:
        return "limited", "Limited availability"
    if "resolved" in t or "available" in t:
        return "in_supply", "Available"
    if "current" in t or "shortage" in t:
        return "shortage", "Current shortage"
    return "unverified", text.strip()[:60] or "Status unclear"


def scrape(ingredient, category):
    url = BASE.format(ingredient)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"  ! {ingredient}: HTTP {resp.status_code}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) < 2:
                continue
            cellmap = dict(zip(headers, cells))
            name = cellmap.get("medicine") or cellmap.get("product") or cells[0]
            if not name:
                continue
            raw_status = (
                cellmap.get("status")
                or cellmap.get("availability")
                or cellmap.get("shortage status")
                or " ".join(cells[1:3])
            )
            status, label = status_from(raw_status)
            rows.append(
                {
                    "id": slug(name),
                    "brand": name,
                    "genericName": ingredient.capitalize(),
                    "brands": [name],
                    "form": cellmap.get("dosage form") or "",
                    "strengthLabel": cellmap.get("strength") or cellmap.get("dosage form") or "",
                    "category": category,
                    "status": status,
                    "statusLabel": label,
                    "since": cellmap.get("shortage start date") or cellmap.get("start date") or "—",
                    "expectedReturn": cellmap.get("expected resolution date")
                    or cellmap.get("resolution date")
                    or "—",
                    "mechanism": cellmap.get("action") or "",
                    "note": "Automatically pulled from the TGA shortage record.",
                    "sourceUrl": url,
                    "sourceLabel": "TGA shortage record",
                    "lastVerified": date.today().isoformat(),
                }
            )
    print(f"  {ingredient}: {len(rows)} rows")
    return rows


def main():
    scraped = []
    for ingredient, category in INGREDIENTS.items():
        try:
            scraped.extend(scrape(ingredient, category))
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  ! {ingredient}: {exc}", file=sys.stderr)

    if len(scraped) < MIN_EXPECTED_ROWS:
        print(
            f"FAIL: only {len(scraped)} rows parsed (expected at least {MIN_EXPECTED_ROWS}). "
            "The TGA page structure has probably changed — the parser needs updating.",
            file=sys.stderr,
        )
        return 1

    # Start from what the site already shows, so curated entries survive a refresh,
    # then layer the hand-maintained file over it.
    existing = []
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text()).get("medicines", [])
        except Exception:
            existing = []
    manual = json.loads(MANUAL.read_text()) if MANUAL.exists() else []
    by_id = {m["id"]: m for m in existing}
    for m in manual:
        by_id[m["id"]] = {**by_id.get(m["id"], {}), **m}
    curated = list(by_id.values())

    # Match each scraped row onto a curated entry where we can, so the ids the site
    # links to (content/medicines.json supplyIds) stay stable. Scraped status wins;
    # the curated name, brands and strength stay, because they are written for patients.
    def curated_match(row):
        text = " ".join([row.get("brand", ""), row.get("genericName", "")]).lower()
        best = None
        for m in curated:
            names = [m.get("brand", "")] + list(m.get("brands", []))
            for n in names:
                n = (n or "").strip().lower()
                if len(n) > 3 and n in text:
                    if best is None or len(n) > best[1]:
                        best = (m["id"], len(n))
        return best[0] if best else None

    LIVE = ("status", "statusLabel", "since", "expectedReturn", "mechanism",
            "note", "sourceUrl", "sourceLabel", "lastVerified")
    for row in scraped:
        mid = curated_match(row)
        if mid:
            entry = dict(by_id[mid])
            for k in LIVE:
                if row.get(k):
                    entry[k] = row[k]
            by_id[mid] = entry
        else:
            by_id[row["id"]] = row

    payload = {
        "generatedAt": date.today().strftime("%-d %b %Y"),
        "source": "TGA medicine shortage records + manually maintained entries",
        "scrapedCount": len(scraped),
        "medicines": sorted(by_id.values(), key=lambda m: (m.get("genericName") or m["brand"], m["brand"])),
    }
    OUT.write_text(json.dumps(payload, indent=1))
    print(f"Wrote {OUT} with {len(payload['medicines'])} products ({len(scraped)} scraped).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
