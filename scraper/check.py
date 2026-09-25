#!/usr/bin/env python3
"""Fail the refresh if the data and the content pages have drifted apart.

Run after the scrapers. Catches the failure mode where a supply id the medicine
pages link to stops existing, which would silently drop the status from a page.
"""
import json, pathlib, sys

R = pathlib.Path(__file__).resolve().parent.parent
supply = {m["id"] for m in json.loads((R / "data/medicines.json").read_text())["medicines"]}
meds = json.loads((R / "content/medicines.json").read_text())["medicines"]

problems = []
for m in meds:
    missing = [s for s in m.get("supplyIds", []) if s not in supply]
    if missing:
        problems.append(f'{m["id"]}: supplyIds not in data/medicines.json -> {", ".join(missing)}')

for name, path in (("dosing", "content/dosing.json"), ("administration", "content/administration.json"),
                   ("costs", "content/costs.json")):
    d = json.loads((R / path).read_text())
    ns = [r["n"] for r in d.get("references", [])]
    if ns != list(range(1, len(ns) + 1)):
        problems.append(f"{name}: reference numbering has a gap or duplicate")

for m in meds:
    ns = [r["n"] for r in m.get("references", [])]
    if ns != list(range(1, len(ns) + 1)):
        problems.append(f'{m["id"]}: reference numbering has a gap or duplicate')

if problems:
    print("Data and content have drifted:", file=sys.stderr)
    for p in problems:
        print("  - " + p, file=sys.stderr)
    sys.exit(1)
print(f"OK: {len(meds)} medicine pages, {len(supply)} supply records, references consistent.")
