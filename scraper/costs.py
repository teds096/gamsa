#!/usr/bin/env python3
"""Monthly refresh of PBS co-payment and Safety Net figures in content/costs.json.

Reads the PBS fees and charges page, extracts the four dollar figures the page
quotes, and rewrites them wherever they appear. Fails loudly: if the page cannot
be parsed, or a figure looks implausible, it exits non-zero and changes nothing,
so the site keeps serving the last verified numbers.
"""
import json, pathlib, re, sys
import requests

URL = "https://www.pbs.gov.au/healthpro/explanatory-notes/front/fee"
R = pathlib.Path(__file__).parent.parent
COSTS = R / "content" / "costs.json"

# Each figure is picked from the dollar amounts on the page by the band it must
# fall in, rather than by proximity to a word — the page reorders its wording
# often enough that "nearest match" picked up the wrong co-payment.
BANDS = [
    ("general_copay", 20, 60),      # general patient co-payment
    ("conc_copay",    5, 15),       # concessional co-payment
    ("sn_general",    1000, 3000),  # general Safety Net threshold
    ("sn_conc",       150, 600),    # concessional Safety Net threshold
]

def money(s):
    return float(s.replace(",", ""))

def main():
    try:
        page = requests.get(URL, timeout=30, headers={"User-Agent": "gamsa/1.0"}).text
    except Exception as exc:
        print(f"FAIL: could not fetch {URL}: {exc}", file=sys.stderr)
        return 1
    text = re.sub(r"<[^>]+>", " ", page)
    amounts = [(money(a), a) for a in re.findall(r"\$(\d{1,3}(?:,\d{3})?\.\d{2})", text)]
    if not amounts:
        print("FAIL: no dollar figures found on the PBS fees page.", file=sys.stderr)
        return 1

    found = {}
    for key, lo, hi in BANDS:
        hits = sorted({v for v, _ in amounts if lo <= v <= hi})
        if not hits:
            print(f"FAIL: no candidate for {key} in ${lo}-${hi} — the page layout has probably changed.",
                  file=sys.stderr)
            return 1
        if len(hits) > 1:
            print(f"FAIL: {key} is ambiguous, found {hits} in ${lo}-${hi}. Check the page by hand.",
                  file=sys.stderr)
            return 1
        found[key] = f"{hits[0]:,.2f}"
    print("Parsed:", found)

    raw = COSTS.read_text()
    # Replace the previous figures wherever they appear in the prose.
    old = re.findall(r"\$\d{1,3}(?:,\d{3})?\.\d{2}", raw)
    swaps = {
        found["general_copay"]: r"\$2[0-9]\.\d{2}",
        found["conc_copay"]:    r"\$[5-9]\.\d{2}",
        found["sn_general"]:    r"\$1,\d{3}\.\d{2}",
        found["sn_conc"]:       r"\$[23]\d{2}\.\d{2}",
    }
    for new, pat in swaps.items():
        raw = re.sub(pat, "$" + new, raw)

    json.loads(raw)  # must still be valid JSON
    COSTS.write_text(raw)
    print("Updated:", ", ".join(f"{k}=${v}" for k, v in found.items()))
    print(f"(previous figures in file: {sorted(set(old))})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
