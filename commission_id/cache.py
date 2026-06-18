from __future__ import annotations
import json
import os
import sqlite3


class Cache:
    """Caches reverse-search results keyed by perceptual hash, so re-runs don't
    re-hit the (rate-limited) APIs."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS reverse_cache ("
            " phash TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL,"
            " PRIMARY KEY (phash, source))")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS descriptor_cache ("
            " phash TEXT PRIMARY KEY, vec TEXT NOT NULL)")
        self.conn.commit()

    def get(self, phash, source):
        if not phash:
            return None
        row = self.conn.execute(
            "SELECT payload FROM reverse_cache WHERE phash=? AND source=?",
            (phash, source)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, phash, source, payload):
        if not phash:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO reverse_cache (phash, source, payload) VALUES (?,?,?)",
            (phash, source, json.dumps(payload)))
        self.conn.commit()

    def get_descriptor(self, phash):
        if not phash:
            return None
        row = self.conn.execute(
            "SELECT vec FROM descriptor_cache WHERE phash=?", (phash,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_descriptor(self, phash, vec):
        if not phash:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO descriptor_cache (phash, vec) VALUES (?,?)",
            (phash, json.dumps(vec)))
        self.conn.commit()

    def close(self):
        self.conn.close()
