# Gender-Affirming Medicines South Australia (GAMSA)

Patient information site at https://gamsa.au: supply and shortages, PBS costs, doses,
how to use each form, plus pages for clinicians and allies. South Australian focus.

## How it is built

```
content/*.json     clinical text and figure definitions, written and reviewed by hand
data/*.json        supply, PBS and run data written by the scrapers (data/manual.json is the hand-kept overlay)
template.html      the page shell (design changes go here)
figures.py         draws the infographics from the figure definitions in content/
site-config.json   public settings (the Turnstile site key for the forms)
build.py           template + content + data  ->  dist/ (the hosted site), preview.html, index.html
static/            copied into dist/ as is: downloads, share images, fonts, icons, _redirects
functions/api/     Cloudflare Pages Functions: feedback.js, pharmacy.js, reports.js
functions/schema.sql   tables for the D1 database
scraper/           the scheduled data jobs (see Workflows)
tools/             checks and brand tools (site_check.py, live_check.py, ...)
```

`python3 build.py` writes `dist/`: one real HTML page per address, the sitemap, `feed.xml`,
`robots.txt` and `_headers` (security headers and the script hashes for the Content-Security-Policy).
`preview.html` is a single file for viewing on a computer; `index.html` is a fragment for claude.ai previews.
`dist/` is committed: the daily refresh rebuilds it and commits it.

**Downloads:** `static/clinicians/` (SOP and training guide, training package zip, adverse event form,
clinic audit tool, competency checklist, treatment room card, PBS authority wording card) and
`static/allies/` (pharmacy visit checklist). They are served at `gamsa.au/clinicians/...` and `gamsa.au/allies/...`.

## Hosting

- **Cloudflare Pages**, project `gamsa`, connected to this GitHub repo (branch `main`), output directory `dist`.
  Every push publishes the site. There is no GitHub Pages site and no separate Worker.
- **Pages Functions** in `functions/api/` run the feedback form, pharmacist stock reports and patient sightings.
  They use the **D1 database** `gamsa` (binding `DB`) and two Cloudflare secrets, `TURNSTILE_SECRET` and `ADMIN_TOKEN`.
  `ADMIN_TOKEN` is also a GitHub Actions secret (the daily inbox step); the two copies must match.
- **Web Analytics** (Cloudflare, cookieless) and **Turnstile** (spam check on the forms) are the only outside services.
- `config.js` is a leftover from an old plan for a separate Worker. No page loads it; it can be deleted.

## Workflows (.github/workflows)

| File | When (UTC; Adelaide is 9.5 h ahead, 10.5 h in summer) | What it does |
|---|---|---|
| `refresh.yml` | daily 19:00; monthly part on the 1st at 19:30; or by hand | TGA supply data, inbox counts, data check, rebuild, commit, IndexNow, `data/status.json`. Monthly: PBS costs, brand premiums, outside links, PI revisions. Opens issues labelled `scraper`, `inbox`, `pbs`, `links` or `pi`. |
| `uptime.yml` | every 15 minutes | Loads `/`, `/supply`, `/medicines`; opens or closes a `down` issue. |
| `live.yml` | each push that changes the site; or by hand | Waits for Cloudflare to deploy, then runs `tools/live_check.py` on gamsa.au; opens or closes a `live` issue. |
| `browsers.yml` | each push that changes the site; 3rd of the month at 19:45 | Safari (WebKit) and Firefox render check; opens or closes a `browsers` issue. |

GitHub emails the repo owner about every new issue and comment.

## Checking a change locally

On Ted's Mac the full steps are in `CLAUDE.md` in the GAMSA project folder ("Local setup").
In short, from this folder: `python3 build.py`, then `python3 tools/site_check.py ["release.zip"]`.

## Releases

Claude builds a release zip and checks it; Ted uploads its contents through the GitHub web page
(Add file, Upload files) and deletes any files the release notes list. Workflow files are pasted by hand.
Zips never include `data/medicines.json`, `premiums.json`, `inbox-state.json`, `status.json`, `pi-state.json` or `analytics.json`
(the scrapers own them); `data/manual.json` is shipped. Cloudflare publishes the push and `live.yml` checks it.

## Data rules

The scrapers only change `data/` and the dollar figures in `content/costs.json`. A scraper that cannot read
its source changes nothing, and `scraper/check.py` stops a build when data and content disagree.
Corrections to scraped data go in `data/manual.json`.
