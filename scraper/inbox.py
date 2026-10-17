#!/usr/bin/env python3
"""Daily inbox check: new feedback messages, pending pharmacist registrations and new patient sightings.

Reads the three admin endpoints with ADMIN_TOKEN (sightings publish immediately, so Ted is told the next day
and can remove spam with /api/reports?token=…&delete=ID), compares with data/inbox-state.json,
writes an issue body to /tmp/inbox.md when there is anything new, and updates the
state file. Prints INBOX_NEW when an issue should be opened. Exits 0 always; with no
token it does nothing.

Privacy: the repository is public, so the issue body, the title, the log and the committed state file hold
counts and row ids only: never a message, email, name, AHPRA number, pharmacy, suburb or note. Ted reads the
details in the admin endpoints with his ADMIN_TOKEN. Pending pharmacists have no id, so the state file keeps a
keyed hash of the AHPRA number (HMAC with ADMIN_TOKEN), which cannot be turned back into the number.
"""
import hashlib, hmac, json, os, pathlib, re, sys
import requests

STATE = pathlib.Path(__file__).resolve().parents[1] / "data" / "inbox-state.json"
SITE = "https://gamsa.au"


def tag(ahpra, key):
    """Keyed hash of an AHPRA number for the public state file (cannot be reversed without ADMIN_TOKEN)."""
    return hmac.new(key.encode(), str(ahpra).strip().upper().encode(), hashlib.sha256).hexdigest()[:16]


def diff(feedback, pending, state, key=""):
    """Return (new_feedback, new_pending, new_state)."""
    # feedback rows arrive already filtered to notified=0 by the API, so a reset state file can never re-report them
    last = int(state.get("lastFeedbackId", 0))
    seen = set(state.get("pendingSeen", []))
    new_fb = sorted([f for f in feedback if not f.get("notified")], key=lambda f: int(f["id"]))
    new_pd = [p for p in pending if tag(p["ahpra"], key) not in seen]
    new_state = {"lastFeedbackId": max([last] + [int(f["id"]) for f in feedback]),
                 "pendingSeen": sorted({tag(p["ahpra"], key) for p in pending})}
    return new_fb, new_pd, new_state


def new_sightings(sightings, state):
    """Sightings newer than the last one reported. First run with no record only sets the baseline."""
    ids = [int(x["id"]) for x in sightings]
    if "lastSightingId" not in state: return [], max(ids, default=0)
    last = int(state["lastSightingId"])
    return sorted([x for x in sightings if int(x["id"]) > last], key=lambda x: int(x["id"])), max([last] + ids)


def ids(rows):
    return ", ".join(str(int(r["id"])) for r in rows if str(r.get("id", "")).strip().isdigit())


def body(new_fb, new_pd, new_si=()):
    """Issue body for the public repository: counts and row ids only, plus where to read the details.
    Never a message, email, name, AHPRA number, pharmacy, suburb or note (see the module docstring)."""
    out = ["Counts only: the details stay in the site's database. Open the links below and add your ADMIN_TOKEN in place of …\n"]
    if new_fb:
        out.append(f"- **New feedback: {len(new_fb)}** (ids {ids(new_fb)}). Read: {SITE}/api/feedback?token=… · remove one: …&delete=ID")
    if new_pd:
        out.append(f"- **Pharmacist registrations waiting: {len(new_pd)}**. Read, check on AHPRA, then approve or block: {SITE}/api/pharmacy?token=…")
    if new_si:
        out.append(f"- **New patient sightings: {len(new_si)}** (ids {ids(new_si)}), already live on the supply page. "
                   f"Read: {SITE}/api/reports?token=… · remove a wrong or spam one: …&delete=ID")
    # Never put the admin token in the issue: the repository is public.
    return "\n".join(out) + "\n"


def safe(exc):
    """Error text without the query string (it carries the token)."""
    return re.sub(r"\?[^\s'\")]*", "?…", f"{type(exc).__name__}: {exc}")[:300]


def main():
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        print("inbox: ADMIN_TOKEN not set — skipping"); return 0
    out = {}
    try:
        for key, path, extra in (("feedback", "feedback", {"new": "1"}), ("pending", "pharmacy", {}), ("sightings", "reports", {})):
            r = requests.get(f"{SITE}/api/{path}", params={"token": token, **extra}, timeout=30)
            if r.status_code in (401, 403, 404):
                # the site rejected the token: GitHub's ADMIN_TOKEN secret does not match Cloudflare's — fail the step so status.json shows it
                msg = (f"The site rejected GitHub's ADMIN_TOKEN at /api/{path} (HTTP {r.status_code}), so new feedback, pharmacist "
                       "registrations and sightings cannot be read. Make the GitHub secret (Settings → Secrets → Actions → ADMIN_TOKEN) "
                       "exactly match the Cloudflare Pages variable ADMIN_TOKEN, then Run workflow. Close this issue once the next run says nothing new.")
                print(f"inbox: {msg}")
                pathlib.Path("/tmp/inbox.md").write_text(msg + "\n")
                pathlib.Path("/tmp/inbox-title.txt").write_text("Inbox cannot be read: admin token mismatch")
                print("INBOX_NEW"); return 0   # opens/comments the "inbox" issue, which GitHub emails to Ted
            out[key] = r.json().get(key, [])
    except Exception as exc:
        print(f"inbox: could not read admin endpoints ({safe(exc)})", file=sys.stderr); return 0
    fb, pd, si = out["feedback"], out["pending"], out["sightings"]
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    new_fb, new_pd, new_state = diff(fb, pd, state, token)
    new_si, new_state["lastSightingId"] = new_sightings(si, state)
    STATE.write_text(json.dumps(new_state, indent=1) + "\n")
    if not new_fb and not new_pd and not new_si:
        print("inbox: nothing new (token accepted by all three admin endpoints)"); return 0
    pathlib.Path("/tmp/inbox.md").write_text(body(new_fb, new_pd, new_si))
    spam = len(new_si) >= 10 or len(new_pd) >= 5 or len(new_fb) >= 15   # far above normal daily volume: possible spam or a bot
    pathlib.Path("/tmp/inbox-title.txt").write_text(("UNUSUAL VOLUME — check for spam: " if spam else "") +
        " / ".join(x for x in [f"New feedback ({len(new_fb)})" if new_fb else "", f"pending pharmacist ({len(new_pd)})" if new_pd else "",
                            f"New sightings ({len(new_si)})" if new_si else ""] if x))
    if new_fb:   # mark as reported so tomorrow's run (or a restored state file) never repeats them
        try: requests.get(f"{SITE}/api/feedback", params={"token": token, "ack": ",".join(str(f["id"]) for f in new_fb)}, timeout=30)
        except Exception as exc: print(f"inbox: could not ack ({safe(exc)})", file=sys.stderr)
    print("INBOX_NEW"); return 0


if __name__ == "__main__":
    sys.exit(main())
