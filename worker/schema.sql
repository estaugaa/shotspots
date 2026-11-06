CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  form TEXT NOT NULL,
  created_at TEXT NOT NULL,
  data TEXT NOT NULL,
  ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_sub_form ON submissions(form, id);
CREATE INDEX IF NOT EXISTS idx_sub_ip ON submissions(ip, created_at);
CREATE TABLE IF NOT EXISTS ticks (at TEXT NOT NULL, job TEXT NOT NULL, result TEXT);
