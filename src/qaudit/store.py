from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .common import canonical


class ScoreStore:
    """Transactional, append-only score cache. One immutable identity per cell."""
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS cells (cell TEXT PRIMARY KEY, identity TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS scores (cell TEXT, question TEXT, payload TEXT NOT NULL, PRIMARY KEY(cell,question))")
        self.db.commit()

    def register(self, cell, identity):
        encoded = canonical(identity)
        existing = self.db.execute("SELECT identity FROM cells WHERE cell=?", (cell,)).fetchone()
        if existing and existing[0] != encoded:
            raise ValueError(f"Run identity changed for {cell}; use a new workspace")
        self.db.execute("INSERT OR IGNORE INTO cells VALUES (?,?)", (cell,encoded))
        self.db.commit()

    def insert(self, cell, record):
        key, payload = record["key"], canonical(record)
        previous = self.db.execute("SELECT payload FROM scores WHERE cell=? AND question=?",(cell,key)).fetchone()
        if previous:
            if previous[0] != payload:
                raise ValueError(f"Refusing to replace completed score: {cell}/{key}")
            return
        if not self.db.execute("SELECT 1 FROM cells WHERE cell=?", (cell,)).fetchone():
            raise ValueError("Register cell identity first")
        self.db.execute("INSERT INTO scores VALUES (?,?,?)",(cell,key,payload))
        self.db.commit()

    def records(self, cell):
        return [json.loads(x[0]) for x in self.db.execute("SELECT payload FROM scores WHERE cell=? ORDER BY question",(cell,))]

    def cells(self):
        return [r[0] for r in self.db.execute("SELECT cell FROM cells ORDER BY cell")]

    def identity(self, cell):
        row = self.db.execute("SELECT identity FROM cells WHERE cell=?",(cell,)).fetchone()
        if not row:
            raise ValueError(f"Missing cell: {cell}")
        return json.loads(row[0])

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def cell_name(role, bits, dataset, stage):
    return f"{role}/{bits}/{dataset}/{stage}"


def aligned_records(store, cell, rows):
    records = store.records(cell)
    index = {r["key"]: r for r in records}
    expected = {r["key"] for r in rows}
    if len(index) != len(rows) or set(index) != expected:
        raise ValueError(f"Incomplete or unexpected questions in {cell}: {len(index)}/{len(rows)}")
    return [index[r["key"]] for r in rows]
