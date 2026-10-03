#!/usr/bin/env python3
"""Monthly: has any Product Information (PI) or Consumer Medicine Information (CMI) the site cites been revised?

Reads every PI/CMI reference in content/medicines.json (Safety and Quality / NPS medicine-finder pages),
pulls the revision dates printed on each page ("Date of Revision", "MIMS Revision Date",
"This leaflet was prepared in", "Published by MIMS") and compares them with data/pi-state.json.
A changed date means the medicine page and the clinician package should be re-checked against the new PI/CMI.
Writes /tmp/pi.md and prints PI_CHANGED when anything changed. First run only records a baseline.
Pages that do not load are skipped (their old dates are kept). Always exits 0.
"""
import json, re, sys, time, pathlib
import requests

R = pathlib.Path(__file__).resolve().parents[1]
STATE = R / "data/pi-state.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; GAMSA PI check; +https://gamsa.au)"}
PAT = {
    "PI revised": r"Date of (?:most recent amendment|Revision)\s*:?\s*([0-9]{1,2} \w+ [0-9]{4})",
    "MIMS revised": r"MIMS Revision Date\s*:?\s*([0-9]{1,2} \w+ [0-9]{4})",
    "CMI prepared": r"leaflet was prepared (?:in|on) ([0-9]{0,2} ?\w+ [0-9]{4})",
    "Published": r"Published by MIMS ([A-Z][a-z]+ [0-9]{4})",
}

def refs():
    out = {}
    for m in json.loads((R / "content/medicines.json").read_text())["medicines"]:
        for r in m.get("references", []):
            t, u = r.get("text", ""), r.get("url", "")
            if u and re.search(r"product information|consumer medicine|\bPI\b|\bCMI\b", t, re.I):
                out.setdefault(u, {"title": t.split(",")[0][:80], "medicines": []})["medicines"].append(m["id"])
    return out

def dates(url):
    for attempt in range(2):
        try:
            r = requests.get(url, headers=UA, timeout=(10, 30))
            if r.status_code == 200:
                txt = re.sub(r"<[^>]+>", " ", r.text); txt = re.sub(r"\s+", " ", txt)
                return {k: (re.search(p, txt, re.I) or [None, None])[1] for k, p in PAT.items()}
            if r.status_code in (404, 410): return {"error": f"HTTP {r.status_code}"}
        except Exception:
            pass
        time.sleep(5)
    return None

def main():
    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    new, changed, skipped = dict(old), [], 0
    for url, info in refs().items():
        d = dates(url); time.sleep(2)
        if d is None: skipped += 1; continue
        prev = old.get(url, {}).get("dates")
        if prev and any(d.get(k) and d.get(k) != prev.get(k) for k in PAT) or (d.get("error") and prev and not prev.get("error")):
            diff = "; ".join(f"{k}: {prev.get(k)} → {d.get(k)}" for k in list(PAT) + ["error"] if d.get(k) != prev.get(k) and d.get(k))
            changed.append(f"- **{info['title']}** ({', '.join(info['medicines'])}) — {diff}\n  {url}")
        new[url] = {"title": info["title"], "medicines": info["medicines"], "dates": d}
    STATE.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
    print(f"PI check: {len(new)} documents, {len(changed)} revised, {skipped} could not be read (old dates kept)")
    if changed:
        pathlib.Path("/tmp/pi.md").write_text(f"## Product information / CMI revised ({len(changed)})\n\n" + "\n".join(changed) +
            "\n\nRe-check the medicine page(s) and, for testosterone undecanoate, the clinician package (wording card, SOP, competency checklist, adverse event form) against the new document. Update the reference's 'Accessed' date. Close this issue when done.\n")
        print("PI_CHANGED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
