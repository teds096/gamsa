#!/usr/bin/env python3
"""Daily inbox check: new feedback messages, pending pharmacist registrations and new patient sightings.

Reads /api/admin with ADMIN_TOKEN sent in the Authorization header (v19: never in a URL), compares with
data/inbox-state.json,
writes an issue body to /tmp/inbox.md when there is anything new, and updates the
state file. Prints INBOX_NEW when an issue should be opened. Exits 0 always; with no
token it does nothing.

Privacy: the repository is public, so the issue body, the title, the log and the committed state file hold
counts and row ids only: never a message, email, name, AHPRA number, pharmacy, suburb or note. The links in the
issue open the admin page (https://gamsa.au/admin?feedback=ID …) with ids only; Ted pastes his admin key there once
per browser tab and acts on each item with a button. Pending pharmacists have no id, so the state file keeps a
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


def new_held(held, state):
    """Pharmacist reports held for a missing or wrong report key, newer than the last ones reported."""
    ids_ = [int(x["id"]) for x in held]
    if "lastHeldId" not in state: return sorted(held, key=lambda x: int(x["id"])), max(ids_, default=0)
    last = int(state["lastHeldId"])
    return sorted([x for x in held if int(x["id"]) > last], key=lambda x: int(x["id"])), max([last] + ids_)


def link(**q):
    """Admin page link carrying ids only (never the token)."""
    return f"{SITE}/admin?" + "&".join(f"{k}={v}" for k, v in q.items())


def body(new_fb, new_pd, new_si=(), new_hd=()):
    """Issue body for the public repository: counts and row ids only, plus admin-page links with ids only.
    Never a message, email, name, AHPRA number, pharmacy, suburb or note (see the module docstring)."""
    out = ["Counts only: the details stay in the site's database. Each link opens the admin page; paste your admin key "
           "(ADMIN_TOKEN) there once, then follow the steps on screen.\n"]
    if new_fb:
        out.append(f"- **New feedback: {len(new_fb)}** (ids {ids(new_fb)}). Read or delete: {link(feedback=ids(new_fb).replace(', ', ','))}")
    if new_pd:
        out.append(f"- **Pharmacist registrations waiting: {len(new_pd)}**. Check on AHPRA, then approve or block: {link(show='pharmacists')}")
    if new_hd:
        out.append(f"- **Pharmacist reports held (report key missing or wrong): {len(new_hd)}** (ids {ids(new_hd)}). "
                   f"Publish, send a key, or leave: {link(report=int(new_hd[0]['id'])) if len(new_hd) == 1 else link(show='pharmacists')}")
    if new_si:
        waiting = [x for x in new_si if str(x.get("published", 1)) in ("0", "False", "false")]
        out.append(f"- **New patient sightings: {len(new_si)}** (ids {ids(new_si)}), "
                   + (f"{len(waiting)} waiting for you to publish. " if waiting else "already live on the supply page, marked unverified. ")
                   + f"Check or delete: {link(sighting=int(new_si[0]['id'])) if len(new_si) == 1 else link(show='sightings')}")
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
    auth = {"Authorization": f"Bearer {token}"}
    try:
        for key, lst, extra in (("feedback", "feedback", {"new": "1"}), ("pending", "pharmacists", {}), ("sightings", "sightings", {})):
            r = requests.get(f"{SITE}/api/admin", params={"list": lst, **extra}, headers=auth, timeout=30)
            path = f"admin?list={lst}"
            if r.status_code in (401, 403, 404):
                # the site rejected the token: GitHub's ADMIN_TOKEN secret does not match Cloudflare's — fail the step so status.json shows it
                msg = (f"The site rejected GitHub's ADMIN_TOKEN at /api/{path} (HTTP {r.status_code}), so new feedback, pharmacist "
                       "registrations and sightings cannot be read. Make the GitHub secret (Settings → Secrets → Actions → ADMIN_TOKEN) "
                       "exactly match the Cloudflare Pages variable ADMIN_TOKEN, then Run workflow. Close this issue once the next run says nothing new.")
                print(f"inbox: {msg}")
                pathlib.Path("/tmp/inbox.md").write_text(msg + "\n")
                pathlib.Path("/tmp/inbox-title.txt").write_text("Inbox cannot be read: admin token mismatch")
                print("INBOX_NEW"); return 0   # opens/comments the "inbox" issue, which GitHub emails to Ted
            r.raise_for_status()   # e.g. 429 after too many wrong tokens: report it, do not treat it as "nothing new"
            j = r.json()
            out[key] = j.get(key, [])
            if key == "pending": out["held"] = j.get("held", [])
    except Exception as exc:
        print(f"inbox: could not read admin endpoints ({safe(exc)})", file=sys.stderr); return 0
    fb, pd, si = out["feedback"], out["pending"], out["sightings"]
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    new_fb, new_pd, new_state = diff(fb, pd, state, token)
    new_si, new_state["lastSightingId"] = new_sightings(si, state)
    new_hd, new_state["lastHeldId"] = new_held(out.get("held", []), state)
    STATE.write_text(json.dumps(new_state, indent=1) + "\n")
    if not new_fb and not new_pd and not new_si and not new_hd:
        print("inbox: nothing new (token accepted by the admin endpoint for all three lists)"); return 0
    pathlib.Path("/tmp/inbox.md").write_text(body(new_fb, new_pd, new_si, new_hd))
    spam = len(new_si) >= 10 or len(new_pd) >= 5 or len(new_fb) >= 15   # far above normal daily volume: possible spam or a bot
    pathlib.Path("/tmp/inbox-title.txt").write_text(("UNUSUAL VOLUME — check for spam: " if spam else "") +
        " / ".join(x for x in [f"New feedback ({len(new_fb)})" if new_fb else "", f"pending pharmacist ({len(new_pd)})" if new_pd else "",
                            f"held pharmacist reports ({len(new_hd)})" if new_hd else "",
                            f"New sightings ({len(new_si)})" if new_si else ""] if x))
    if new_fb:   # mark as reported so tomorrow's run (or a restored state file) never repeats them
        try: requests.post(f"{SITE}/api/admin", json={"action": "ack", "ids": [int(f["id"]) for f in new_fb]}, headers=auth, timeout=30)
        except Exception as exc: print(f"inbox: could not ack ({safe(exc)})", file=sys.stderr)
    print("INBOX_NEW"); return 0


if __name__ == "__main__":
    sys.exit(main())
