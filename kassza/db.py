"""SQLite ledger. One table of transactions; receipts and bank rows both land here."""
import json
import os
import sqlite3
from pathlib import Path

# Vercel functions can only write to /tmp
DB = (Path("/tmp") if os.getenv("VERCEL") else Path(__file__).resolve().parent.parent / "data") / "ledger.db"
DB.parent.mkdir(exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tx (
  id INTEGER PRIMARY KEY,
  owner TEXT NOT NULL DEFAULT '',  -- random id kept in the visitor's browser
  source TEXT NOT NULL,          -- 'receipt' or 'bank'
  date TEXT NOT NULL,
  merchant TEXT NOT NULL,
  amount REAL NOT NULL,          -- negative = money out
  currency TEXT NOT NULL,
  category TEXT NOT NULL,
  detail TEXT,                   -- receipt JSON or raw bank row
  dedup TEXT,
  UNIQUE (owner, dedup)
);
"""


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def add(owner, source, date, merchant, amount, currency, category, detail=None, dedup=None) -> int | None:
    with conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO tx (owner, source, date, merchant, amount, currency, category, detail, dedup)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (owner, source, date, merchant, amount, currency, category,
             json.dumps(detail, ensure_ascii=False) if detail is not None else None, dedup))
        return cur.lastrowid if cur.rowcount else None


def all_tx(owner: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM tx WHERE owner = ? ORDER BY date DESC, id DESC", (owner,))]


def clear(owner: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM tx WHERE owner = ?", (owner,))
