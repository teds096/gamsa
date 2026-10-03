#!/usr/bin/env python3
"""Monthly: has any Product Information (PI) or Consumer Medicine Information (CMI) the site cites been revised?

Reads every PI/CMI reference in content/medicines.json (Safety and Quality / NPS medicine-finder pages),
pulls the revision dates printed on each page ("Date of Revision", "MIMS Revision Date",
"This leaflet was prepared in", "Published by MIMS") and compares them with data/pi-state.json.
A changed date means the medicine page and the clinician package should be re-checked against the new PI/CMI.
Writes /tmp/pi.md and prints PI_CHANGED when anything changed. First run only records a baseline.
Pages that do not load are skipped (their old dates are kept). Always exits 0.
Big .gov.au sites throttle GitHub's servers, so: one request at a time with pauses, a site is skipped for the
rest of the run after 2 failures in a row, the whole check stops after BUDGET seconds (well inside the
workflow's 10-minute limit), the least recently checked documents go first (so a short run still covers
everything over a few months), and the state file is saved after every document.
"""
import json, re, sys, time, pathlib, urllib.parse
import requests

R = pathlib.Path(__file__).resolve().parents[1]
STATE = R / "data/pi-state.json"
BUDGET = 420  # seconds
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
    """Dates found on the page, {"error": ...} for a dead page, or None if it could not be read this time."""
    try:
        r = requests.get(url, headers=UA, timeout=(8, 15))
    except Exception:
        return None
    if r.status_code == 200:
        txt = re.sub(r"<[^>]+>", " ", r.text); txt = re.sub(r"\s+", " ", txt)
        return {k: (re.search(p, txt, re.I) or [None, None])[1] for k, p in PAT.items()}
    if r.status_code in (404, 410): return {"error": f"HTTP {r.status_code}"}
    return None

def main():
    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    new, changed, skipped, fails = dict(old), [], 0, {}
    start = time.time()
    docs = sorted(refs().items(), key=lambda kv: old.get(kv[0], {}).get("checked", ""))
    for url, info in docs:
        host = urllib.parse.urlparse(url).netloc
        if time.time() - start > BUDGET or fails.get(host, 0) >= 2:
            skipped += 1; continue
        d = dates(url); time.sleep(2)
        if d is None:
            fails[host] = fails.get(host, 0) + 1; skipped += 1; continue
        fails[host] = 0
        prev = old.get(url, {}).get("dates")
        if prev and any(d.get(k) and d.get(k) != prev.get(k) for k in PAT) or (d.get("error") and prev and not prev.get("error")):
            diff = "; ".join(f"{k}: {prev.get(k)} → {d.get(k)}" for k in list(PAT) + ["error"] if d.get(k) != prev.get(k) and d.get(k))
            changed.append(f"- **{info['title']}** ({', '.join(info['medicines'])}) — {diff}\n  {url}")
        new[url] = {"title": info["title"], "medicines": info["medicines"], "dates": d, "checked": time.strftime("%Y-%m-%d")}
        STATE.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
    if not STATE.exists(): STATE.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
    hosts = ", ".join(h for h, n in fails.items() if n >= 2)
    print(f"PI check: {len(new)} documents, {len(changed)} revised, {skipped} could not be read this time (old dates kept)" + (f"; skipped after repeated failures: {hosts}" if hosts else ""))
    if changed:
        pathlib.Path("/tmp/pi.md").write_text(f"## Product information / CMI revised ({len(changed)})\n\n" + "\n".join(changed) +
            "\n\nRe-check the medicine page(s) and, for testosterone undecanoate, the clinician package (wording card, SOP, competency checklist, adverse event form) against the new document. Update the reference's 'Accessed' date. Close this issue when done.\n")
        print("PI_CHANGED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
