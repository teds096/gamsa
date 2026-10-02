-- Run once in the D1 console (Cloudflare dashboard → Storage & databases → D1 → gamsa → Console)
CREATE TABLE IF NOT EXISTS feedback (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  created TEXT NOT NULL,
  topic   TEXT NOT NULL,
  page    TEXT,
  message TEXT NOT NULL,
  email   TEXT
);

CREATE TABLE IF NOT EXISTS pharmacists (
  ahpra   TEXT PRIMARY KEY,
  name    TEXT NOT NULL,
  email   TEXT,
  state   TEXT NOT NULL,   -- pending | approved | blocked
  created TEXT NOT NULL,
  decided TEXT
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

-- What people paid (v12). No names, no suburb — state only.
CREATE TABLE IF NOT EXISTS prices (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  created  TEXT NOT NULL,
  medicine TEXT NOT NULL,     -- medicine id from the site
  kind     TEXT NOT NULL,     -- pbs | private
  cents    INTEGER NOT NULL,  -- amount paid, in cents
  state    TEXT NOT NULL,     -- SA, VIC, ... or ''
  pharmacy TEXT NOT NULL      -- chain | independent | online | ''
);
CREATE INDEX IF NOT EXISTS idx_prices_med ON prices (medicine, created);

-- Patient sightings (v12). Anonymous: medicine, pharmacy name, suburb, what happened.
CREATE TABLE IF NOT EXISTS sightings (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  created  TEXT NOT NULL,
  medicine TEXT NOT NULL,
  pharmacy TEXT NOT NULL,
  region   TEXT NOT NULL,
  status   TEXT NOT NULL,     -- in_stock | limited_qty | out_of_stock
  note     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sightings_created ON sightings (created);
