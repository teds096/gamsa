#!/usr/bin/env python3
"""Monthly refresh of PBS co-payment and Safety Net figures in content/costs.json.

Reads the PBS "Fees, Patient Contributions and Safety Net Thresholds" page and
pulls the four figures out of the two labelled blocks on it:

    Patient Co-payment Amounts   General $X   Concessional $Y
    Safety Net Thresholds        General $X   Concessional $Y

Each figure is then sanity-checked against a plausible range. If the page cannot
be parsed, or a figure looks wrong, the script exits non-zero and changes
nothing, so the site keeps serving the last verified numbers.

Figures are swapped by exact previous value, recorded in "pbsFigures" at the
foot of content/costs.json — never by a loose pattern, which used to catch
unrelated prices in the prose.
"""
import json, pathlib, re, sys
import requests

URL = "https://www.pbs.gov.au/healthpro/explanatory-notes/front/fee"
R = pathlib.Path(__file__).parent.parent
COSTS = R / "content" / "costs.json"

MONEY = r"\$(\d{1,3}(?:,\d{3})?\.\d{2})"

# key -> (block heading, row label, plausible low, plausible high)
FIELDS = [
    ("general_copay", "Patient Co-payment Amounts", "General",      15, 80),
    ("conc_copay",    "Patient Co-payment Amounts", "Concessional",  3, 20),
    ("sn_general",    "Safety Net Thresholds",      "General",     800, 4000),
    ("sn_conc",       "Safety Net Thresholds",      "Concessional", 100, 900),
]


def pick(text, heading, label, lo, hi, key):
    """First plausible $ figure under `heading` then `label`.

    The heading words also appear in the page title, breadcrumb and side nav, so
    every occurrence is tried in turn and the first one that yields a figure in
    the plausible range wins. A figure outside the range is treated as the wrong
    occurrence, not as an answer.
    """
    seen_heading = seen_label = False
    for h in re.finditer(re.escape(heading), text):
        seen_heading = True
        window = text[h.end(): h.end() + 900]
        l = re.search(r"\b" + re.escape(label) + r"\b", window)
        if not l:
            continue
        seen_label = True
        m = re.search(MONEY, window[l.end(): l.end() + 200])
        if not m:
            continue
        val = float(m.group(1).replace(",", ""))
        if lo <= val <= hi:
            return m.group(1)
    if not seen_heading:
        print(f"FAIL: heading {heading!r} not found — the PBS page layout has changed.", file=sys.stderr)
    elif not seen_label:
        print(f"FAIL: row {label!r} not found under {heading!r}.", file=sys.stderr)
    else:
        print(f"FAIL: no figure for {key} in the plausible range ${lo}-${hi} under "
              f"{heading!r} / {label!r}. Check the page by hand.", file=sys.stderr)
    return None


def main():
    try:
        page = requests.get(URL, timeout=30, headers={"User-Agent": "gamsa/1.0"}).text
    except Exception as exc:
        print(f"FAIL: could not fetch {URL}: {exc}", file=sys.stderr)
        return 1
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))

    found = {}
    for key, heading, label, lo, hi in FIELDS:
        v = pick(text, heading, label, lo, hi, key)
        if v is None:
            return 1
        found[key] = v
    print("Parsed:", found)

    raw = COSTS.read_text()
    data = json.loads(raw)
    prev = data.get("pbsFigures")
    if not prev:
        print("FAIL: content/costs.json has no pbsFigures block to compare against.", file=sys.stderr)
        return 1

    changed = []
    for key, new in found.items():
        old = prev.get(key)
        if old is None:
            print(f"FAIL: pbsFigures is missing {key}.", file=sys.stderr)
            return 1
        if old == new:
            continue
        if f"${old}" not in raw:
            print(f"FAIL: {key} changed ${old} -> ${new} but ${old} does not appear in the page copy. "
                  f"Update content/costs.json by hand.", file=sys.stderr)
            return 1
        raw = raw.replace(f"${old}", f"${new}")
        changed.append(f"{key}: ${old} -> ${new}")

    data = json.loads(raw)          # must still be valid JSON
    data["pbsFigures"] = found
    COSTS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    print("Updated:" if changed else "No change — figures already current:",
          "; ".join(changed) if changed else ", ".join(f"{k}=${v}" for k, v in found.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
