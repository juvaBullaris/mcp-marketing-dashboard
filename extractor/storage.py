"""SQLite storage. One row per day per channel/campaign; re-runs overwrite."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS ga4_daily (
    date        TEXT NOT NULL,
    property_id TEXT NOT NULL,
    channel     TEXT NOT NULL,
    sessions    INTEGER,
    users       INTEGER,
    new_users   INTEGER,
    key_events  REAL,
    revenue     REAL,
    PRIMARY KEY (date, property_id, channel)
);
CREATE TABLE IF NOT EXISTS meta_daily (
    date           TEXT NOT NULL,
    account_id     TEXT NOT NULL,
    campaign_id    TEXT NOT NULL,
    campaign_name  TEXT,
    spend          REAL,
    impressions    INTEGER,
    clicks         INTEGER,
    purchases      REAL,
    purchase_value REAL,
    PRIMARY KEY (date, account_id, campaign_id)
);
CREATE TABLE IF NOT EXISTS extract_runs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at   TEXT DEFAULT (datetime('now')),
    source   TEXT,
    rows     INTEGER,
    status   TEXT,
    message  TEXT
);
"""


def db_path() -> str:
    return os.environ.get("DB_PATH", "./data/marketing.db")


def connect() -> sqlite3.Connection:
    path = db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0])
    sql = (
        f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' for _ in cols)})"
    )
    conn.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
    conn.commit()
    return len(rows)


def log_run(conn, source: str, rows: int, status: str, message: str = ""):
    conn.execute(
        "INSERT INTO extract_runs (source, rows, status, message) VALUES (?, ?, ?, ?)",
        (source, rows, status, message),
    )
    conn.commit()
