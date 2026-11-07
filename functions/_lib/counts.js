// v19.5 (7 Nov 2026): privacy-safe daily totals. One row per day, kind and key (a file path or an outreach tag)
// holding only a number. No IP address, user agent, cookie, referrer or anything else about the visitor is stored.
// Every caller treats a failure here as "not counted": nothing a visitor asked for ever waits on or fails because of it.
const CREATE = "CREATE TABLE IF NOT EXISTS counts (day TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, " +
  "n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, kind, key))";
let ready = null;

// Adds 1 to today's total for (kind, key). Past `cap` different keys of this kind today, only existing rows count up.
export async function addCount(env, kind, key, cap = 300) {
  if (!env || !env.DB) return;
  if (!ready) ready = env.DB.prepare(CREATE).run().catch((e) => { ready = null; throw e; });
  await ready;
  const day = new Date().toISOString().slice(0, 10);
  const r = await env.DB.prepare("SELECT COUNT(*) AS c FROM counts WHERE day = ?1 AND kind = ?2").bind(day, kind).first();
  const sql = r && r.c >= cap
    ? "UPDATE counts SET n = n + 1 WHERE day = ?1 AND kind = ?2 AND key = ?3"
    : "INSERT INTO counts (day, kind, key, n) VALUES (?1, ?2, ?3, 1) ON CONFLICT (day, kind, key) DO UPDATE SET n = n + 1";
  await env.DB.prepare(sql).bind(day, kind, key).run();
}
