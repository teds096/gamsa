#!/usr/bin/env python3
"""Monthly refresh of PBS co-payment and Safety Net figures in content/costs.json.

Reads the PBS fees and charges page, extracts the four dollar figures the page
quotes, and rewrites them wherever they appear. Fails loudly: if the page cannot
be parsed, or a figure looks implausible, it exits non-zero and changes nothing,
so the site keeps serving the last verified numbers.
"""
import json, pathlib, re, sys
import requests

URL = "https://www.pbs.gov.au/info/healthpro/explanatory-notes/front/fee"
R = pathlib.Path(__file__).parent.parent
COSTS = R / "content" / "costs.json"

# (key, regex against page text, plausible range)
FIELDS = [
    ("general_copay",  r"general patient[^$]{0,120}\$(\d{2}\.\d{2})",      (20, 60)),
    ("conc_copay",     r"concession[^$]{0,120}\$(\d{1,2}\.\d{2})",         (5, 20)),
    ("sn_general",     r"[Ss]afety [Nn]et[^$]{0,200}\$(1,\d{3}\.\d{2})",   (1000, 3000)),
    ("sn_conc",        r"[Ss]afety [Nn]et[^$]{0,400}\$(\d{3}\.\d{2})",     (150, 600)),
]

def money(s):
    return float(s.replace(",", ""))

def main():
    try:
        page = requests.get(URL, timeout=30, headers={"User-Agent": "gam-au/1.0"}).text
    except Exception as exc:
        print(f"FAIL: could not fetch {URL}: {exc}", file=sys.stderr)
        return 1
    text = re.sub(r"<[^>]+>", " ", page)

    found = {}
    for key, pattern, (lo, hi) in FIELDS:
        m = re.search(pattern, text)
        if not m:
            print(f"FAIL: could not find {key} on the PBS fees page — layout has probably changed.", file=sys.stderr)
            return 1
        val = money(m.group(1))
        if not (lo <= val <= hi):
            print(f"FAIL: {key} parsed as ${val}, outside the plausible range ${lo}-${hi}.", file=sys.stderr)
            return 1
        found[key] = m.group(1)

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
