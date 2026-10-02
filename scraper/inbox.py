#!/usr/bin/env python3
"""Daily inbox check: new feedback messages and pending pharmacist registrations.

Reads the two admin endpoints with ADMIN_TOKEN, compares with data/inbox-state.json,
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
    last = int(state.get("lastFeedbackId", 0))
    seen = set(state.get("pendingSeen", []))
    new_fb = sorted([f for f in feedback if int(f["id"]) > last], key=lambda f: int(f["id"]))
    new_pd = [p for p in pending if p["ahpra"] not in seen]
    new_state = {"lastFeedbackId": max([last] + [int(f["id"]) for f in feedback]),
                 "pendingSeen": sorted({p["ahpra"] for p in pending})}
    return new_fb, new_pd, new_state


def body(new_fb, new_pd):
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
                       f"  [Check on AHPRA]({p.get('check','')}) · [Approve]({p.get('approve','')}) · [Block]({p.get('block','')})\n")
    out.append(f"\nFull inbox: {SITE}/api/feedback?token=… and {SITE}/api/pharmacy?token=… (your ADMIN_TOKEN).")
    return "\n".join(out)


def main():
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        print("inbox: ADMIN_TOKEN not set — skipping"); return 0
    try:
        fb = requests.get(f"{SITE}/api/feedback", params={"token": token}, timeout=30).json().get("feedback", [])
        pd = requests.get(f"{SITE}/api/pharmacy", params={"token": token}, timeout=30).json().get("pending", [])
    except Exception as exc:
        print(f"inbox: could not read admin endpoints ({exc})", file=sys.stderr); return 0
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    new_fb, new_pd, new_state = diff(fb, pd, state)
    STATE.write_text(json.dumps(new_state, indent=1) + "\n")
    if not new_fb and not new_pd:
        print("inbox: nothing new"); return 0
    pathlib.Path("/tmp/inbox.md").write_text(body(new_fb, new_pd))
    pathlib.Path("/tmp/inbox-title.txt").write_text(
        " / ".join(x for x in [f"New feedback ({len(new_fb)})" if new_fb else "", f"pending pharmacist ({len(new_pd)})" if new_pd else ""] if x))
    print("INBOX_NEW"); return 0


if __name__ == "__main__":
    sys.exit(main())
