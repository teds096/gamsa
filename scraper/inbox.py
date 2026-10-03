#!/usr/bin/env python3
"""Daily inbox check: new feedback messages, pending pharmacist registrations and new patient sightings.

Reads the three admin endpoints with ADMIN_TOKEN (sightings publish immediately, so Ted is told the next day
and can remove spam with /api/reports?token=…&delete=ID), compares with data/inbox-state.json,
writes an issue body to /tmp/inbox.md when there is anything new, and updates the
state file. Prints INBOX_NEW when an issue should be opened. Exits 0 always; with no
token it does nothing.
"""
import json, os, pathlib, sys
import requests

STATE = pathlib.Path(__file__).resolve().parents[1] / "data" / "inbox-state.json"
SITE = "https://gamsa.au"


def diff(feedback, pending, state):
    """Return (new_feedback, new_pending, new_state)."""
    # feedback rows arrive already filtered to notified=0 by the API, so a reset state file can never re-report them
    last = int(state.get("lastFeedbackId", 0))
    seen = set(state.get("pendingSeen", []))
    new_fb = sorted([f for f in feedback if not f.get("notified")], key=lambda f: int(f["id"]))
    new_pd = [p for p in pending if p["ahpra"] not in seen]
    new_state = {"lastFeedbackId": max([last] + [int(f["id"]) for f in feedback]),
                 "pendingSeen": sorted({p["ahpra"] for p in pending})}
    return new_fb, new_pd, new_state


def new_sightings(sightings, state):
    """Sightings newer than the last one reported. First run with no record only sets the baseline."""
    ids = [int(x["id"]) for x in sightings]
    if "lastSightingId" not in state: return [], max(ids, default=0)
    last = int(state["lastSightingId"])
    return sorted([x for x in sightings if int(x["id"]) > last], key=lambda x: int(x["id"])), max([last] + ids)


def body(new_fb, new_pd, new_si=()):
    out = []
    if new_fb:
        out.append(f"## New feedback ({len(new_fb)})\n")
        for f in new_fb:
            out.append(f"- **{f.get('topic','')}** · {f.get('created','')[:10]} · page `{f.get('page','')}`"
                       + (f" · reply to {f['email']}" if f.get("email") else "") + f"\n\n  > {f.get('message','').strip()}\n")
    if new_pd:
        out.append(f"## Pending pharmacist registrations ({len(new_pd)})\n")
        for p in new_pd:
            out.append(f"- **{p.get('name','')}** ({p.get('ahpra','')}) · {p.get('pharmacy','')}, {p.get('suburb','')} · first report: {p.get('medicine','')} — {p.get('status','')}\n"
                       f"  [Check on AHPRA]({p.get('check','')}) · approve: {SITE}/api/pharmacy?token=…&approve={p.get('ahpra','')} · block: …&block={p.get('ahpra','')}\n")
    # Never put the admin token in the issue: the repository is public. Ted pastes his ADMIN_TOKEN in place of …
    if new_si:
        out.append(f"## New patient sightings ({len(new_si)}) — already live on the supply page\n")
        for x in new_si:
            out.append(f"- **{x.get('medicine','')}** · {x.get('status','')} · {x.get('pharmacy','')}, {x.get('region','')} · {str(x.get('created',''))[:16]} (id {x.get('id')})"
                       + (f"\n  > {str(x.get('note')).strip()}" if x.get("note") else "") + "\n")
        out.append(f"Remove a wrong or spam sighting: {SITE}/api/reports?token=…&delete=ID\n")
    out.append(f"\nFull inbox: {SITE}/api/feedback?token=… (add &delete=ID to remove a message) and {SITE}/api/pharmacy?token=… (your ADMIN_TOKEN).")
    return "\n".join(out)


def main():
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        print("inbox: ADMIN_TOKEN not set — skipping"); return 0
    try:
        fb = requests.get(f"{SITE}/api/feedback", params={"token": token, "new": "1"}, timeout=30).json().get("feedback", [])
        pd = requests.get(f"{SITE}/api/pharmacy", params={"token": token}, timeout=30).json().get("pending", [])
        si = requests.get(f"{SITE}/api/reports", params={"token": token}, timeout=30).json().get("sightings", [])
    except Exception as exc:
        print(f"inbox: could not read admin endpoints ({exc})", file=sys.stderr); return 0
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    new_fb, new_pd, new_state = diff(fb, pd, state)
    new_si, new_state["lastSightingId"] = new_sightings(si, state)
    STATE.write_text(json.dumps(new_state, indent=1) + "\n")
    if not new_fb and not new_pd and not new_si:
        print("inbox: nothing new"); return 0
    pathlib.Path("/tmp/inbox.md").write_text(body(new_fb, new_pd, new_si))
    pathlib.Path("/tmp/inbox-title.txt").write_text(
        " / ".join(x for x in [f"New feedback ({len(new_fb)})" if new_fb else "", f"pending pharmacist ({len(new_pd)})" if new_pd else "",
                            f"New sightings ({len(new_si)})" if new_si else ""] if x))
    if new_fb:   # mark as reported so tomorrow's run (or a restored state file) never repeats them
        try: requests.get(f"{SITE}/api/feedback", params={"token": token, "ack": ",".join(str(f["id"]) for f in new_fb)}, timeout=30)
        except Exception as exc: print(f"inbox: could not ack ({exc})", file=sys.stderr)
    print("INBOX_NEW"); return 0


if __name__ == "__main__":
    sys.exit(main())
