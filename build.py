#!/usr/bin/env python3
"""Render template.html + data + content into index.html."""
import json, pathlib
R = pathlib.Path(__file__).parent
KEEP = ("id","genericName","brand","brands","form","strengthLabel","category","status","statusLabel","expectedReturn","sourceUrl")
meds = json.loads((R/"data/medicines.json").read_text())
payload = {"generatedAt": meds["generatedAt"],
           "medicines": [{k:m[k] for k in KEEP if k in m} for m in meds["medicines"]]}
content = {k: json.loads((R/f"content/{k}.json").read_text()) for k in ("dosing","administration","costs","easyread")}
medinfo = json.loads((R/"content/medicines.json").read_text())
html = (R/"template.html").read_text() \
    .replace("__MEDS__", json.dumps(payload, separators=(",",":"))) \
    .replace("__CONTENT__", json.dumps(content, separators=(",",":"))) \
    .replace("__MEDINFO__", json.dumps(medinfo, separators=(",",":")))
# artifact.html: fragment form, for publishing inside claude.ai (skeleton added there)
(R/"index.html").write_text(html)  # fragment: for previewing as a claude.ai artifact

# index.html: complete standalone document, for hosting
head = ('<!doctype html>\n<html lang="en-AU">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="description" content="Independent, referenced medicines information for trans and '
        'gender diverse people in South Australia: supply and shortages, costs and the PBS, doses and '
        'formulations, and how to use each form.">\n'
        '<meta name="theme-color" content="#0B5D7A">\n')
i = html.index("</style>") + len("</style>")
doc = head + html[:i] + "\n</head>\n<body>\n" + html[i:] + "\n</body>\n</html>\n"
(R/"dist").mkdir(exist_ok=True)
(R/"dist/index.html").write_text(doc)
import shutil; shutil.copy(R/"config.js", R/"dist/config.js")
print(f"Built dist/index.html ({len(doc)} bytes) for hosting and index.html ({len(html)} bytes) for artifact preview")
