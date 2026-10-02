# GAMSA — setting up this release

Upload everything in this folder to the GitHub repo (it overwrites what is there).
Do not upload a `data/` folder — that is maintained by the daily refresh.
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

Reading feedback: open `https://gamsa.au/api/feedback?token=YOUR_ADMIN_TOKEN`,
or in the D1 console run `SELECT * FROM feedback ORDER BY id DESC;`

## 3b. Pharmacy stock reports (uses the same setup as step 3)

The register shares the database, Turnstile widget and secrets above. If you created the
database before this release, open the D1 console and run `functions/schema.sql` again —
it only adds the two new tables.

Approving a pharmacist (once per registration number):
1. Open `https://gamsa.au/api/pharmacy?token=YOUR_ADMIN_TOKEN` — it lists pending pharmacists
   with their name, number, pharmacy and first report.
2. Check the number on the AHPRA register (link included in the list).
3. Click the `approve` link for that entry, or `block` if it does not check out.
Every later report from an approved number publishes immediately. Reports expire after 14 days.

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
The "Seen it in stock, or missed out?" form on the Supply page now posts to `/api/prices`' sibling `/api/reports`, using the same database, Turnstile key and secret as the other forms. Run the `sightings` table statement from `functions/schema.sql` in the D1 console. Nothing identifying is stored (medicine, pharmacy name, suburb, what happened, optional note; notes containing an email, link or long number are rejected). Reports show for 14 days on the Supply page, each medicine page and the Patient sightings page. To remove one: open `https://gamsa.au/api/reports?token=YOUR_ADMIN_TOKEN` to see ids, then add `&delete=ID`. The old `config.js` / separate Worker idea is gone.

## Price reports (added v12)
Run the new `prices` table statements from `functions/schema.sql` in the D1 console. `/api/prices` uses the same DB binding and TURNSTILE_SECRET as feedback — nothing else to configure. The costs page "What readers report paying" list and the per-medicine line appear once three or more reports exist for a medicine in the last 180 days; until then the page says so. No admin step is needed; if a wrong figure needs removing, delete the row in the D1 console (`DELETE FROM prices WHERE id = …`).

## Dates that now update themselves
Supply (daily), PBS co-payments (monthly), PBS prices/premiums/listings (monthly) each carry the date of their last check. The costs page, medicine pages, footer and the "Accessed" dates of the references the scrapers actually fetch (PBS item pages, brand premium table, fee schedule, TGA shortages database) are all stamped at build time. Other references keep the date they were read by hand.

## Release zips and live data (from v14)
`data/medicines.json` and `data/premiums.json` are written by the scrapers on GitHub. Release zips no longer include them, so an upload cannot overwrite live data with a stale copy (that is what opened the three duplicate "pbs" issues on 2 Oct). `data/manual.json` is still shipped — it is the hand-maintained overlay.
