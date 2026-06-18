from __future__ import annotations
import os
import sqlite3

# How strongly a stored decision counts as a signal (1.0 = certain).
DECISION_WEIGHT = {"human": 1.0, "propagated-dup": 0.95, "propagated-style": 0.9}


def _avg_to_text(avg):
    return ",".join(str(int(x)) for x in avg) if avg else ""


def _avg_from_text(t):
    if not t:
        return None
    try:
        return tuple(int(x) for x in t.split(","))
    except ValueError:
        return None


class Decisions:
    """Persistent store of artist labels you (or propagation) have assigned,
    keyed by perceptual hash so they survive re-runs and apply to copies.
    Stores a mean colour too, to guard against phash collisions on flat images."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS decisions ("
            " phash TEXT PRIMARY KEY, artist TEXT NOT NULL, source TEXT NOT NULL,"
            " note TEXT, avg TEXT)")
        self.conn.commit()

    def get(self, phash):
        if not phash:
            return None
        row = self.conn.execute(
            "SELECT artist, source, note, avg FROM decisions WHERE phash=?", (phash,)).fetchone()
        if not row:
            return None
        return {"artist": row[0], "source": row[1], "note": row[2], "avg": _avg_from_text(row[3])}

    def set(self, phash, artist, source="human", note="", avg=None):
        if not phash or not artist:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO decisions (phash, artist, source, note, avg) VALUES (?,?,?,?,?)",
            (phash, artist, source, note, _avg_to_text(avg)))
        self.conn.commit()

    def delete(self, phash):
        self.conn.execute("DELETE FROM decisions WHERE phash=?", (phash,))
        self.conn.commit()

    def all(self):
        return [{"phash": r[0], "artist": r[1], "source": r[2], "note": r[3], "avg": _avg_from_text(r[4])}
                for r in self.conn.execute(
                    "SELECT phash, artist, source, note, avg FROM decisions").fetchall()]

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

    def close(self):
        self.conn.close()
