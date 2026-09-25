# Gender-Affirming Medicines South Australia (GAMSA)

Patient information site: supply and shortages, costs and the PBS, doses and
formulations, and how to use each form. South Australian focus.

```
template.html     the page shell (edit this for design changes)
content/*.json    written clinical content + inline SVG figures (never auto-edited)
data/*.json       supply data (auto-refreshed daily)
build.py          renders template + content + data -> index.html
scraper/refresh.py  daily TGA supply refresh
scraper/costs.py    monthly PBS co-payment / Safety Net refresh (1st of month)
config.js         set `api` to the Worker URL to switch patient sightings on
.github/          the schedule that runs both scrapers and rebuilds the site
```

**Deploy:** push to a public GitHub repo, then either enable GitHub Pages on the
repo root, or connect the repo to Cloudflare Pages (build command `python build.py`,
output directory `dist`). Add your domain in Cloudflare.

**After editing content:** run `python build.py` and commit the regenerated
`index.html`. The daily job does this automatically.

Clinical content in `content/` is written and reviewed by hand. The scrapers only
touch `data/` and the dollar figures in `content/costs.json`, and both fail loudly
rather than writing bad data.
