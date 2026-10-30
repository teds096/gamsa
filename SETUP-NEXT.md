# GAMSA — setting up this release

Upload everything in this folder to the GitHub repo (it overwrites what is there).
The zip leaves out the data files the daily refresh owns; `data/manual.json` is in the zip and should be uploaded.
In Finder, press Cmd+Shift+. to show the hidden `.gitignore` file so it uploads too.

## 1. Check one Cloudflare Pages setting (2 minutes, before uploading)

Workers & Pages → gamsa → Settings → Build:
- Build output directory: `dist`
- Build command: `python build.py` (or empty — the built `dist/` is included either way)

Pages now serves real addresses: gamsa.au/costs, gamsa.au/medicines/spironolactone, gamsa.au/easy/doses.
Old links like gamsa.au/#/costs keep working and redirect to the new address.

## 2. www → gamsa.au redirect
Done 2 Oct 2026 (Rules → Redirect Rules → "Redirect from WWW to root", 301, query string preserved).

## 3. Turn on the feedback form (10 minutes)

1. Storage & databases → D1 → Create database → name `gamsa`.
   Open it → Console → paste the contents of `functions/schema.sql` → Execute.
2. Workers & Pages → gamsa → Settings → Bindings → Add → D1 database →
   Variable name `DB` → database `gamsa` → Save.
3. Turnstile (left menu) → Add widget → name `GAMSA`, hostnames `gamsa.au` and
   `www.gamsa.au`, mode Managed → Create. Keep the page open.
4. Workers & Pages → gamsa → Settings → Variables and Secrets → Add:
   - `TURNSTILE_SECRET` = the Turnstile **secret** key (type: Secret)
   - `ADMIN_TOKEN` = any long random string, 30+ characters (type: Secret)
5. In GitHub, edit `site-config.json` and paste the Turnstile **site** key:
   `{ "turnstileSiteKey": "0x4AAAA..." }` → Commit. The form switches on with the next build.

Reading feedback (from v19): open `https://gamsa.au/admin`, paste the admin key (ADMIN_TOKEN) once per browser tab,
then press Feedback messages. The key is kept in that tab only and never goes in a link. Or in the D1 console run
`SELECT * FROM feedback ORDER BY id DESC;`

## 3b. Pharmacy stock reports (uses the same setup as step 3)

The register shares the database, Turnstile widget and secrets above. If you created the
database before this release, open the D1 console and run only the `pharmacists` and
`pharmacy_reports` statements from `functions/schema.sql`. Do not run the whole file again: it still holds
the old `prices` table, which was removed on 18 Oct 2026, and would bring it back empty.

Approving a pharmacist (once per registration number; v19):
1. Open `https://gamsa.au/admin` (or the link in the daily inbox email), paste the admin key, press Pharmacists.
2. Open the person waiting, press Open the AHPRA register and check the number and name.
3. Press Approve (or Block). The next screen shows their private report key: press Email the key, check the address, Send.
Later reports publish immediately only when they carry that report key (AHPRA numbers are public, so the number alone
is not enough). Reports without the key wait on /admin under "Reports held"; publish them there if genuine.
Published reports show stock facts only (status and date); notes with prices, offers or contact details are dropped.
Reports expire after 14 days.

## 4. Turn on Web Analytics (1 minute)

Workers & Pages → gamsa → Metrics → Web Analytics → Enable.
Cookieless, no consent banner needed. After a week or two of visits it shows real
Core Web Vitals (LCP, INP, CLS) from visitors' devices.

## 5. Register with search engines (10 minutes)

- Google Search Console → Add property → Domain → `gamsa.au` → verify with the
  DNS record it gives you (add it in Cloudflare DNS). Then Sitemaps → submit `sitemap.xml`.
- Bing Webmaster Tools → Import from Google Search Console.

## Monthly PBS check (added v11)
On the first of each month the workflow also runs `scraper/premiums.py`. It rewrites `data/premiums.json` with the brand premium table, and for every PBS item code cited in the content it records the schedule, authority level, dispensed price, general patient charge, and the brands marked "a" (substitutable). The costs page and each medicine's "Cost and PBS" section render from that file, with the "checked" date, so nothing needs hand-editing. If any cited item has vanished from the PBS, the step fails and an issue is opened; if figures changed, a "pbs" issue is opened for a wording read-through. `pbs.gov.au` blocks some cloud networks, so run it locally or in Actions, not from an ad-hoc container.

## Patient sightings (added v12)
The "Seen it in stock, or missed out?" form on the Supply page now posts to `/api/reports`, using the same database, Turnstile key and secret as the other forms. Run the `sightings` table statement from `functions/schema.sql` in the D1 console. Nothing identifying is stored (medicine, pharmacy name, suburb, what happened, optional note; notes containing an email, link or long number are rejected). Reports show for 14 days on the Supply page, each medicine page and the Patient sightings page. From v19 each sighting is labelled Unverified, and you remove one on `https://gamsa.au/admin` → Patient sightings → Open → Delete.
To hold new sightings for your OK instead of showing them at once, set `HOLD_FOR_REVIEW = true` in `functions/api/reports.js` (one line). The old `config.js` / separate Worker idea is gone.

## Price reports (added v12, removed from the site in v15)
The reader price-report form and lists were taken off the costs page in v15. The unused `/api/prices` endpoint was removed in v18.2 (delete `functions/api/prices.js` on GitHub when uploading v18.2). The D1 `prices` table was removed from the database on 18 Oct 2026 (Ted approved 17 Oct). Its definition is still in `functions/schema.sql` until the next security release takes it out.

## Dates that now update themselves
Supply (daily), PBS co-payments (monthly), PBS prices/premiums/listings (monthly) each carry the date of their last check. The costs page, medicine pages, footer and the "Accessed" dates of the references the scrapers actually fetch (PBS item pages, brand premium table, fee schedule, TGA shortages database) are all stamped at build time. Other references keep the date they were read by hand.

## Release zips and live data (from v14)
`data/medicines.json` and `data/premiums.json` are written by the scrapers on GitHub. Release zips no longer include them, so an upload cannot overwrite live data with a stale copy (that is what opened the three duplicate "pbs" issues on 2 Oct). `data/manual.json` is still shipped — it is the hand-maintained overlay.

## Inbox alerts (added v15)
Each daily run reads the feedback inbox and pending pharmacist registrations and, when there is anything new, opens a GitHub issue labelled "inbox" (or comments on the open one). The repo is public, so the issue gives counts and row ids only, never a message, email, name, AHPRA number or the token; each line links to `https://gamsa.au/admin?...` with ids only (v19); paste the admin key there. GitHub emails you for every issue and comment. One-off setup: GitHub → repo → Settings → Secrets and variables → Actions → New repository secret → name `ADMIN_TOKEN`, value the same token you set in Cloudflare Pages. Close the "inbox" issue once you have dealt with it; the next batch opens a fresh one. State lives in `data/inbox-state.json` (scraper-owned, not shipped in zips).

From v17 the feedback table has a `notified` column: the daily inbox step reads only new rows and marks them as reported afterwards (v19: `/api/admin`, token in a header), so a message is reported once even if `data/inbox-state.json` is reset. Existing database: run once in the D1 console `ALTER TABLE feedback ADD COLUMN notified INTEGER NOT NULL DEFAULT 0;` (done 2 Oct 2026 before v17 went live). Remove a message on `/admin` → Feedback messages → Open → Delete.


## Run status (added v17)
Every workflow run, pass or fail, ends by writing and committing `data/status.json` (`finishedAt`, `ok`, `failedSteps`, `issue`, `monthlyCostsRun`) for the external health check. It is run metadata only: not read by `build.py`, not a drift-guard input, and excluded from release zips with the other workflow-owned data files.

## Outside link check (added v17.1)
On the 1st of each month (and on any manual Run workflow) `scraper/links.py` requests every outside link on the built site from the GitHub runner. 404/410, server errors and dead hosts are listed in a "links" issue (one open at a time; later runs comment on it) and `data/status.json` gets `linksBroken: true`. 401/403/405/429 count as "blocked to bots", not broken. It never stops the data refresh.
