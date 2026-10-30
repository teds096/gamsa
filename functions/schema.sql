-- Run once in the D1 console (Cloudflare dashboard → Storage & databases → D1 → gamsa → Console)
CREATE TABLE IF NOT EXISTS feedback (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  created TEXT NOT NULL,
  topic   TEXT NOT NULL,
  page    TEXT,
  message TEXT NOT NULL,
  email   TEXT,
  notified INTEGER NOT NULL DEFAULT 0   -- set by the daily inbox step once reported; existing DBs: ALTER TABLE feedback ADD COLUMN notified INTEGER NOT NULL DEFAULT 0;
);

CREATE TABLE IF NOT EXISTS pharmacists (
  ahpra   TEXT PRIMARY KEY,
  name    TEXT NOT NULL,
  email   TEXT,
  state   TEXT NOT NULL,   -- pending | approved | blocked
  created TEXT NOT NULL,
  decided TEXT,
  key_hash   TEXT,         -- v19: SHA-256 of the pharmacist's report key (the key itself is never stored)
  key_issued TEXT          -- v19: when that key was made
);
CREATE TABLE IF NOT EXISTS pharmacy_reports (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  created   TEXT NOT NULL,
  ahpra     TEXT NOT NULL,
  pharmacy  TEXT NOT NULL,
  suburb    TEXT NOT NULL,
  medicine  TEXT NOT NULL,
  status    TEXT NOT NULL,
  note      TEXT,
  published INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reports_created ON pharmacy_reports (published, created);

-- 23 Oct 2026: the prices table (v12) is no longer created here. The D1 table was dropped on 18 Oct 2026 and nothing uses it.

-- Patient sightings (v12). Anonymous: medicine, pharmacy name, suburb, what happened.
CREATE TABLE IF NOT EXISTS sightings (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  created  TEXT NOT NULL,
  medicine TEXT NOT NULL,
  pharmacy TEXT NOT NULL,
  region   TEXT NOT NULL,
  status   TEXT NOT NULL,     -- in_stock | limited_qty | out_of_stock
  note     TEXT NOT NULL,
  published INTEGER NOT NULL DEFAULT 1   -- v19: 0 = held for review (HOLD_FOR_REVIEW switch in api/reports.js)
);
CREATE INDEX IF NOT EXISTS idx_sightings_created ON sightings (created);

-- v19 (24 Oct 2026): browser reports of content the CSP blocked. Counts per day; no IP, user agent or query string.
CREATE TABLE IF NOT EXISTS csp_reports (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  day       TEXT NOT NULL,
  directive TEXT NOT NULL,
  blocked   TEXT NOT NULL,   -- site only (scheme + host) or a keyword such as inline / eval
  page      TEXT NOT NULL,   -- path only
  mode      TEXT NOT NULL,   -- enforced | report-only
  count     INTEGER NOT NULL DEFAULT 1,
  last      TEXT NOT NULL,
  UNIQUE (day, directive, blocked, page, mode)
);

-- v19 upgrade of an existing database: nothing to run by hand. The functions add the three new columns and the
-- csp_reports table themselves the first time they run (functions/_lib/util.js ensureSchema; add-only, nothing is
-- dropped or rewritten). The same statements, if you ever want to run them in the D1 console yourself:
--   ALTER TABLE pharmacists ADD COLUMN key_hash TEXT;
--   ALTER TABLE pharmacists ADD COLUMN key_issued TEXT;
--   ALTER TABLE sightings ADD COLUMN published INTEGER NOT NULL DEFAULT 1;
--   (and the CREATE TABLE csp_reports statement above)
