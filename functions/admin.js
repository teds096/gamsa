// /admin (v19) — Ted's admin page: paste the admin key (ADMIN_TOKEN) once, then read feedback, check and approve
// pharmacists, send report keys, and remove sightings. The key is kept in this browser tab only (sessionStorage),
// never in the address bar; every action is a POST to /api/admin with the key in a header.
//
// Served by a Function rather than a static file so it gets its own strict headers (the site's _headers file
// does not reach Function replies): a fresh nonce-only Content-Security-Policy, no caching, no indexing, no
// referrer, no framing. All text from the database is shown with textContent, never as HTML.
//
// Links from the daily inbox email open it on one item: /admin?feedback=12  /admin?sighting=40  /admin?report=7
// /admin?show=pharmacists | sightings | feedback | csp
import { SECURITY_HEADERS } from "./_lib/util.js";

export async function onRequestGet() {
  const nonce = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16))));
  const csp = ["default-src 'none'", "script-src 'nonce-" + nonce + "'", "style-src 'nonce-" + nonce + "'", "connect-src 'self'",
    "img-src 'self'", "base-uri 'none'", "form-action 'none'", "frame-ancestors 'none'", "report-uri /api/csp-report"].join("; ");
  return new Response(PAGE.split("{{nonce}}").join(nonce), {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "Content-Security-Policy": csp,
      ...SECURITY_HEADERS,
      "Cross-Origin-Opener-Policy": "same-origin",
      "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    },
  });
}

const PAGE = String.raw`<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="referrer" content="no-referrer">
<title>GAMSA admin</title>
<style nonce="{{nonce}}">
:root{--bg:#fbfaf7;--fg:#1d1d1f;--muted:#5b5b63;--card:#ffffff;--line:#d9d6cf;--go:#1f6f4a;--goFg:#fff;--bad:#a61b1b;--badFg:#fff;--focus:#1a5fb4;--keybg:#f1efe8}
@media (prefers-color-scheme: dark){:root{--bg:#17181b;--fg:#ececef;--muted:#b4b4bd;--card:#212227;--line:#3a3b42;--go:#2f9a69;--goFg:#08130d;--bad:#e06464;--badFg:#1a0606;--focus:#8ab4f8;--keybg:#2a2b31}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:18px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:44rem;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;line-height:1.25;margin:0 0 12px}
h2{font-size:1.15rem;margin:28px 0 8px}
h1:focus{outline:none}
ol.steps{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px 14px 40px;margin:0 0 20px}
ol.steps li{margin:4px 0}
ul.cards,ul.menu{list-style:none;padding:0;margin:0}
ul.cards li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:0 0 10px}
ul.cards p{margin:0 0 6px}
ul.menu li{margin:0 0 10px}
.meta{color:var(--muted);font-size:.9rem}
button,a.button{display:inline-block;font:inherit;font-size:1rem;padding:10px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer;text-decoration:none;margin:4px 8px 4px 0;min-height:44px}
button.big{width:100%;text-align:left;padding:14px 16px}
button.go,a.button.go{background:var(--go);border-color:var(--go);color:var(--goFg)}
button.danger{background:var(--bad);border-color:var(--bad);color:var(--badFg)}
button.quiet{background:transparent}
button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
label{display:block;font-weight:600;margin:0 0 6px}
input{font:inherit;width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);margin:0 0 12px}
dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:0 0 14px}
dl.facts dt{color:var(--muted)}
dl.facts dd{margin:0;overflow-wrap:anywhere}
blockquote.msg{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--card);border-left:4px solid var(--line);margin:0 0 14px;padding:12px 14px}
.key{font:700 1.5rem/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.04em;background:var(--keybg);border-radius:8px;padding:14px;text-align:center;overflow-wrap:anywhere}
#say{min-height:1.5em;margin:0 0 10px;font-weight:600}
#say.bad{color:var(--bad)}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;font-size:.9rem;width:100%}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
a{color:var(--focus)}
</style>
</head>
<body>
<main>
<p id="say" role="status" aria-live="polite"></p>
<div id="app"><h1>GAMSA admin</h1><noscript><p>This page needs JavaScript switched on.</p></noscript></div>
</main>
<script nonce="{{nonce}}">
(function () {
  "use strict";
  var SK = "gamsaAdminToken", mem = "", app = document.getElementById("app"), sayEl = document.getElementById("say");
  var REG = "https://www.ahpra.gov.au/Registration/Registers-of-Practitioners.aspx";
  var PR = { in_stock: "In stock", low: "Low stock", order: "Can order", none: "None" };
  var SI = { in_stock: "In stock", limited_qty: "Low stock", out_of_stock: "None available" };
  var TOPIC = { wrong: "Something is wrong", missing: "Something is missing", access: "Hard to use", other: "Other" };

  function getTok() { try { return sessionStorage.getItem(SK) || mem; } catch (e) { return mem; } }
  function setTok(t) { mem = t || ""; try { if (t) sessionStorage.setItem(SK, t); else sessionStorage.removeItem(SK); } catch (e) {} }

  // Build elements. Text always goes in as text nodes, never as HTML.
  function h(tag, attrs) {
    var e = document.createElement(tag), k, i;
    attrs = attrs || {};
    for (k in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, k) || attrs[k] == null || attrs[k] === false) continue;
      if (k === "on") { for (var ev in attrs.on) e.addEventListener(ev, attrs.on[ev]); }
      else e.setAttribute(k, attrs[k] === true ? "" : String(attrs[k]));
    }
    for (i = 2; i < arguments.length; i++) put(e, arguments[i]);
    return e;
  }
  function put(e, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { for (var i = 0; i < c.length; i++) put(e, c[i]); return; }
    e.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
  }
  function btn(label, fn, cls) { return h("button", { type: "button", "class": cls || null, on: { click: fn } }, label); }
  function say(msg, bad) { sayEl.textContent = msg || ""; sayEl.className = bad ? "bad" : ""; }
  function route(q) { try { history.replaceState(null, "", "/admin" + (q ? "?" + q : "")); } catch (e) {} }
  function day(iso) { return String(iso || "").slice(0, 10); }
  function when(iso) { var d = new Date(iso); return isNaN(d) ? String(iso || "") : d.toLocaleString("en-AU", { dateStyle: "medium", timeStyle: "short" }); }
  function cut(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
  function facts(pairs) { var d = h("dl", { "class": "facts" }); pairs.forEach(function (p) { put(d, [h("dt", null, p[0]), h("dd", null, p[1])]); }); return d; }
  function row() { var p = h("p", { "class": "row" }); put(p, Array.prototype.slice.call(arguments)); return p; }

  function screen(title, steps, body, noHome) {
    app.textContent = "";
    var head = h("h1", { tabindex: "-1" }, title);
    put(app, head);
    if (steps && steps.length) put(app, h("ol", { "class": "steps" }, steps.map(function (s) { return h("li", null, s); })));
    put(app, body);
    if (!noHome) put(app, h("p", null, btn("Back to the start", function () { say(""); home(); }, "quiet")));
    window.scrollTo(0, 0);
    head.focus();
  }

  function api(method, query, body) {
    var o = { method: method, headers: { "Authorization": "Bearer " + getTok() }, cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer" };
    if (body) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(body); }
    return fetch("/api/admin" + (query ? "?" + query : ""), o).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (j) {
        if (r.status === 401) { setTok(""); throw new Error("auth"); }
        if (r.status === 429) throw new Error("busy");
        if (!r.ok || !j || !j.ok) throw new Error((j && j.error) || ("code " + r.status));
        return j;
      });
    });
  }
  function fail(e) {
    var m = String((e && e.message) || e);
    if (m === "auth") return keyScreen("That admin key was not accepted. Paste it again.");
    if (m === "busy") return say("Too many wrong keys from this connection. Wait 15 minutes, then try again.", true);
    if (m === "not-found") return say("That item is no longer there. It may already have been dealt with.", true);
    say("Something went wrong (" + m + "). Wait a minute and try again.", true);
  }
  function copy(text, what) {
    var done = function () { say(what + " copied. Paste it with Command-V."); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () { say("Copying did not work. Select the text and press Command-C.", true); });
    else say("Copying did not work. Select the text and press Command-C.", true);
  }

  // ---------- start ----------
  var P = new URLSearchParams(location.search), START = null;
  if (P.get("feedback")) START = { v: "feedback", ids: P.get("feedback") };
  else if (P.get("sighting")) START = { v: "sighting", id: P.get("sighting") };
  else if (P.get("report")) START = { v: "report", id: P.get("report") };
  else if (P.get("show")) START = { v: P.get("show") };
  if (P.has("token")) route("");   // an old-style link: never use a key from the address bar, and wipe it from view

  function go(s) {
    if (!s) return home();
    if (s.v === "feedback") return feedbackList(s.ids);
    if (s.v === "sighting") return sightingItem(s.id);
    if (s.v === "sightings") return sightingsList();
    if (s.v === "report") return heldItem(s.id);
    if (s.v === "pharmacists") return pharmacistsList();
    if (s.v === "csp") return cspList();
    return home();
  }

  function keyScreen(msg) {
    var inp = h("input", { id: "tok", type: "password", autocomplete: "off", autocapitalize: "off", spellcheck: "false", required: true });
    var f = h("form", { on: { submit: function (e) {
      e.preventDefault();
      var t = inp.value.trim();
      if (t.length < 24) { say("That is too short to be the admin key. Paste the whole key.", true); inp.focus(); return; }
      setTok(t); say("Checking…");
      api("GET", "list=summary").then(function () { say(""); var s = START; START = null; go(s); }).catch(fail);
    } } }, h("label", { "for": "tok" }, "Admin key"), inp, h("button", { type: "submit", "class": "go" }, "Open"));
    screen("GAMSA admin", [
      "Copy your admin key (the ADMIN_TOKEN you saved when the site was set up).",
      "Paste it in the box below and press Open.",
      "The key stays in this browser tab only. It is forgotten when you close the tab."], f, true);
    say(msg || "", !!msg);
    inp.focus();
  }

  function home() {
    route("");
    return api("GET", "list=summary").then(function (j) {
      var c = j.counts, items = [
        ["Feedback messages: " + c.feedback, function () { say(""); feedbackList(); }],
        ["Pharmacists waiting for a check: " + c.pending, pharmacistsList],
        ["Pharmacist reports held: " + c.held, pharmacistsList],
        ["Approved pharmacists with no report key: " + c.keyless, pharmacistsList],
        ["Patient sightings in the last 14 days: " + c.sightings + (c.sightingsHeld ? " (" + c.sightingsHeld + " waiting for you)" : ""), sightingsList],
        ["Blocked-content reports in the last 14 days: " + c.csp, cspList]];
      screen("GAMSA admin", ["Pick what you want to look at.", "Each one opens with its own steps."], [
        h("ul", { "class": "menu" }, items.map(function (x) { return h("li", null, h("button", { type: "button", "class": "big", on: { click: function () { say(""); x[1](); } } }, x[0])); })),
        h("p", null, btn("Forget the admin key on this tab", function () { setTok(""); keyScreen(""); say("The admin key has been forgotten on this tab."); }, "quiet"))], true);
    }).catch(fail);
  }

  // ---------- feedback ----------
  function feedbackList(ids) {
    var want = ids ? String(ids).split(",").map(Number).filter(function (n) { return n > 0; }) : null;
    route(want ? "feedback=" + want.join(",") : "show=feedback");
    return api("GET", "list=feedback").then(function (j) {
      var rows = j.feedback.filter(function (f) { return !want || want.indexOf(f.id) >= 0; });
      if (want && rows.length === 1) return feedbackItem(rows[0]);
      screen(want ? "Feedback from the email" : "Feedback messages", ["Press Open to read a message.", "Each message has its own Delete button."],
        rows.length ? h("ul", { "class": "cards" }, rows.map(function (f) {
          return h("li", null, h("p", { "class": "meta" }, "No. " + f.id + " · " + day(f.created) + " · " + (TOPIC[f.topic] || f.topic)),
            h("p", null, cut(f.message, 160)), btn("Open message " + f.id, function () { say(""); feedbackItem(f); }));
        })) : h("p", null, want ? "Those messages are no longer there. They may already have been deleted." : "No feedback messages."));
    }).catch(fail);
  }
  function feedbackItem(f) {
    route("feedback=" + f.id);
    screen("Feedback message " + f.id, [
      "Read the message.",
      f.email ? "To reply, write to " + f.email + " from your own email." : "No email address was left, so there is no one to reply to.",
      "When you are done, press Delete. Or press Back to the list to keep it."],
      [facts([["Sent", when(f.created)], ["Topic", TOPIC[f.topic] || f.topic], ["Page", f.page || "—"], ["Email", f.email || "none given"]]),
       h("blockquote", { "class": "msg" }, f.message),
       row(btn("Delete this message", function () {
         if (!window.confirm("Delete message " + f.id + " for good? This cannot be undone.")) return;
         api("POST", "", { action: "delete", kind: "feedback", id: f.id })
           .then(function () { return feedbackList().then(function () { say("Message " + f.id + " deleted."); }); }).catch(fail);
       }, "danger"), btn("Back to the list", function () { say(""); feedbackList(); }, "quiet"))]);
  }

  // ---------- pharmacists ----------
  function repCard(r) {
    return h("li", null, h("p", null, h("strong", null, r.medicine), " — " + (PR[r.status] || r.status)),
      h("p", null, r.pharmacy + ", " + r.suburb), h("p", { "class": "meta" }, "No. " + r.id + " · " + day(r.created) + (r.note ? " · Note: " + r.note : "")));
  }
  function pharmacistsList() {
    route("show=pharmacists");
    return api("GET", "list=pharmacists").then(function (j) {
      screen("Pharmacists", ["Open anyone waiting for a check and follow the steps there.", "Below that: reports held because the report key was missing, and approved pharmacists who still need a key."], [
        h("h2", null, "Waiting for a check (" + j.pending.length + ")"),
        j.pending.length ? h("ul", { "class": "cards" }, j.pending.map(function (p) {
          return h("li", null, h("p", null, h("strong", null, p.name), " · " + p.ahpra),
            h("p", { "class": "meta" }, p.reports.length + " report(s) waiting · first seen " + day(p.created)),
            btn("Open " + p.name, function () { say(""); pendingItem(p); }));
        })) : h("p", null, "Nobody is waiting."),
        h("h2", null, "Reports held: report key missing or wrong (" + j.held.length + ")"),
        j.held.length ? h("ul", { "class": "cards" }, j.held.map(function (r) {
          return h("li", null, h("p", null, h("strong", null, r.medicine), " — " + (PR[r.status] || r.status) + " · " + r.pharmacy + ", " + r.suburb),
            h("p", { "class": "meta" }, "No. " + r.id + " · " + day(r.created) + " · number of " + r.name),
            btn("Open report " + r.id, function () { say(""); heldItem(r); }));
        })) : h("p", null, "None."),
        h("h2", null, "Approved, but no report key yet (" + j.keyless.length + ")"),
        j.keyless.length ? h("ul", { "class": "cards" }, j.keyless.map(function (k) {
          return h("li", null, h("p", null, h("strong", null, k.name), " · " + k.ahpra), btn("Make a key for " + k.name, function () { makeKey(k, false); }));
        })) : h("p", null, "None.")]);
    }).catch(fail);
  }
  function pendingItem(p) {
    route("show=pharmacists");
    screen("Check " + p.name, [
      "Press Open the AHPRA register. It opens in a new tab.",
      "Search for " + p.ahpra + " or the name. Check it is a pharmacist, the registration is current, and the name matches " + p.name + ".",
      "Come back to this tab. If everything matches, press Approve. If not, press Block.",
      "After Approve, the next screen gives you their report key to email to them."],
      [facts([["Name", p.name], ["Registration number", p.ahpra], ["Email", p.email || "none given"], ["First seen", when(p.created)]]),
       h("h2", null, "Their reports"),
       h("ul", { "class": "cards" }, p.reports.map(repCard)),
       row(h("a", { "class": "button", href: REG, target: "_blank", rel: "noopener noreferrer" }, "Open the AHPRA register"),
         btn("Approve", function () { decide("approve", p); }, "go"),
         btn("Block", function () { if (window.confirm("Block " + p.ahpra + "? Their reports will be hidden and new ones refused.")) decide("block", p); }, "danger"))]);
  }
  function decide(action, p) {
    api("POST", "", { action: action, ahpra: p.ahpra }).then(function (j) {
      if (action === "block") return pharmacistsList().then(function () { say(p.ahpra + " is blocked. " + j.hidden + " report(s) hidden."); });
      var lead = "Approved. " + j.published + " report(s) from " + j.name + " are now live.";
      if (j.key) return keyShown(j, lead);
      return pharmacistsList().then(function () { say(lead); });
    }).catch(fail);
  }
  function makeKey(p, hadKey) {
    if (!window.confirm("Make a " + (hadKey ? "new " : "") + "report key for " + p.name + "?" + (hadKey ? " Their old key stops working." : ""))) return;
    api("POST", "", { action: "newkey", ahpra: p.ahpra }).then(function (j) { keyShown(j, ""); }).catch(fail);
  }
  function letter(name, key) {
    return "Hello " + name + ",\n\nThank you for posting pharmacy stock reports on gamsa.au. Your registration number has been checked on the AHPRA register.\n\n" +
      "Your report key: " + key + "\n\nType it in the “Report key” box each time you post a stock report. Reports with the key appear straight away. " +
      "Reports without it wait for a manual check first.\n\nPlease keep the key private: anyone who has it can post reports under your registration number. " +
      "If you lose it, reply to this email and you will get a new one.\n\nThank you,\nGAMSA (gamsa.au)";
  }
  function mailto(addr, subject, body) {
    var at = addr.lastIndexOf("@");
    return "mailto:" + encodeURIComponent(addr.slice(0, at)) + "@" + encodeURIComponent(addr.slice(at + 1)) +
      "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
  }
  function keyShown(j, lead) {
    route("show=pharmacists");
    var text = letter(j.name, j.key);
    screen("Report key for " + j.name, j.email ? [
        "Press Email the key. Your email app opens with the message already written.",
        "Check it is going to " + j.email + ", then press Send.",
        "If no email app opens, press Copy the email, start a new email to " + j.email + " (for example in Gmail), paste, and send.",
        "This key is shown only now. If it gets lost, open Pharmacists and make a new key."] : [
        "No email address was given, so the key cannot be emailed from here.",
        "Find the pharmacy’s phone number on its website, ring, ask for " + j.name + " and read the key out.",
        "This key is shown only now. If it gets lost, open Pharmacists and make a new key."],
      [lead ? h("p", null, lead) : null,
       h("p", { "class": "key" }, j.key),
       row(j.email ? h("a", { "class": "button go", href: mailto(j.email, "Your GAMSA report key", text) }, "Email the key to " + j.name) : null,
         j.email ? btn("Copy the email", function () { copy(text, "The email"); }) : null,
         btn("Copy the key", function () { copy(j.key, "The key"); }),
         btn("Done", function () { say(""); pharmacistsList(); }, "quiet"))]);
    if (lead) say(lead);
  }
  function heldItem(r) {
    if (typeof r !== "object") {
      var id = Number(r);
      route("report=" + id);
      return api("GET", "list=pharmacists").then(function (j) {
        var x = j.held.filter(function (y) { return y.id === id; })[0];
        if (x) return heldItem(x);
        var p = j.pending.filter(function (q) { return q.reports.some(function (z) { return z.id === id; }); })[0];
        if (p) return pendingItem(p);
        return pharmacistsList().then(function () { say("Report " + id + " is no longer waiting. It was published or blocked, or is older than 14 days.", true); });
      }).catch(fail);
    }
    route("report=" + r.id);
    var has = !!Number(r.has_key);
    screen("Held report " + r.id, [
      "This report used the registration number of " + r.name + " (" + r.ahpra + ") " + (has ? "with a missing or wrong report key." : "before they had a report key."),
      "If you are sure " + r.name + " sent it (for example, they told you by email), press Publish.",
      "If you are not sure, leave it. Held reports are never shown and drop off after 14 days. If the number is being misused, press Block number.",
      has ? "If they lost their key, press Make a new key and email it to them." : "Press Make a key to send them their report key, so their next reports go live straight away."],
      [h("ul", { "class": "cards" }, repCard(r)),
       row(btn("Publish", function () {
           api("POST", "", { action: "publish", kind: "report", id: r.id })
             .then(function () { return pharmacistsList().then(function () { say("Report " + r.id + " is now live."); }); }).catch(fail);
         }, "go"),
         btn(has ? "Make a new key" : "Make a key", function () { makeKey(r, has); }),
         btn("Block number", function () { if (window.confirm("Block " + r.ahpra + "? All reports from this number will be hidden and new ones refused.")) decide("block", r); }, "danger"),
         btn("Back to the list", function () { say(""); pharmacistsList(); }, "quiet"))]);
  }

  // ---------- sightings ----------
  function sightingsList() {
    route("show=sightings");
    return api("GET", "list=sightings").then(function (j) {
      screen("Patient sightings", ["Press Open to check a sighting.", "Delete anything that is spam, rude, an advert or names a person."],
        j.sightings.length ? h("ul", { "class": "cards" }, j.sightings.map(function (x) {
          return h("li", null, h("p", null, h("strong", null, x.medicine), " — " + (SI[x.status] || x.status) + (Number(x.published) ? "" : " · waiting for you")),
            h("p", { "class": "meta" }, "No. " + x.id + " · " + day(x.created) + " · " + x.region),
            btn("Open sighting " + x.id, function () { say(""); sightingItem(x); }));
        })) : h("p", null, "No sightings."));
    }).catch(fail);
  }
  function sightingItem(x) {
    if (typeof x !== "object") {
      var id = Number(x);
      route("sighting=" + id);
      return api("GET", "list=sightings").then(function (j) {
        var s = j.sightings.filter(function (y) { return y.id === id; })[0];
        if (s) return sightingItem(s);
        return sightingsList().then(function () { say("Sighting " + id + " is no longer there. It may already have been deleted.", true); });
      }).catch(fail);
    }
    route("sighting=" + x.id);
    var live = !!Number(x.published);
    screen("Sighting " + x.id, [
      "Check it looks like a real sighting: a medicine, a pharmacy, a suburb, and what they saw.",
      live ? "It is on the site now, marked Unverified." : "It is waiting: nobody sees it until you press Publish.",
      "If it is spam, rude, an advert or names a person, press Delete."],
      [facts([["Medicine", x.medicine], ["What they saw", SI[x.status] || x.status], ["Pharmacy", x.pharmacy || "—"], ["Suburb", x.region], ["Note", x.note || "—"], ["Sent", when(x.created)]]),
       row(live ? null : btn("Publish", function () {
           api("POST", "", { action: "publish", kind: "sighting", id: x.id })
             .then(function () { return sightingsList().then(function () { say("Sighting " + x.id + " is now on the site."); }); }).catch(fail);
         }, "go"),
         btn("Delete this sighting", function () {
           if (!window.confirm("Delete sighting " + x.id + " for good? This cannot be undone.")) return;
           api("POST", "", { action: "delete", kind: "sighting", id: x.id })
             .then(function () { return sightingsList().then(function () { say("Sighting " + x.id + " deleted."); }); }).catch(fail);
         }, "danger"),
         btn("Back to the list", function () { say(""); sightingsList(); }, "quiet"))]);
  }

  // ---------- blocked-content (CSP) reports ----------
  function cspList() {
    route("show=csp");
    return api("GET", "list=csp").then(function (j) {
      var t = h("table", null, h("caption", { "class": "meta" }, "Newest day first"),
        h("thead", null, h("tr", null, ["Day", "Rule", "Blocked", "Page", "Kind", "Times"].map(function (c) { return h("th", { scope: "col" }, c); }))),
        h("tbody", null, j.csp.map(function (r) {
          return h("tr", null, [r.day, r.directive, r.blocked, r.page, r.mode === "enforced" ? "blocked" : "trial only", String(r.count)].map(function (c) { return h("td", null, c); }));
        })));
      screen("Blocked-content reports", [
        "These are things a visitor’s browser blocked on gamsa.au because of the site’s safety rules.",
        "A few are normal: browser add-ons and old browsers cause them.",
        "“trial only” lines are a test of stricter rules and did not block anything.",
        "If the same page and rule appear many times a day, or a page looks broken, tell Claude and copy this list."],
        j.csp.length ? h("div", { "class": "tablewrap" }, t) : h("p", null, "Nothing has been blocked."));
    }).catch(fail);
  }

  if (getTok()) { var s0 = START; START = null; api("GET", "list=summary").then(function () { go(s0); }).catch(function (e) { START = s0; fail(e); }); }
  else keyScreen("");
})();
</script>
</body>
</html>
`;
