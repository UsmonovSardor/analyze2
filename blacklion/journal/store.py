"""Journal — durable record of signals, executions and outcomes (SRS doc 04).

SQLite for the single-server v1 (swap to PostgreSQL/TimescaleDB later behind the
same interface — pragmatic-path decision). Every signal the Rule Engine emits is
recorded, whether or not it is traded, so the AI/Probability engines (docs 16–17)
have a clean, labelled history to train on once enough outcomes accumulate.

Deterministic and self-contained: the DB path comes from config, the schema is
created on first open, and all writes go through typed methods.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Literal

from pydantic import BaseModel

from ..core import config
from ..engines.rule_engine import Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    INTEGER NOT NULL,
    symbol        TEXT NOT NULL,
    timeframe     TEXT NOT NULL DEFAULT 'H1',   -- entry TF the signal fired on
    direction     TEXT NOT NULL,
    entry         REAL, stop_loss REAL, tp1 REAL, tp2 REAL, tp3 REAL,
    rr            REAL,
    confidence    INTEGER,
    confluence    INTEGER,
    reasons       TEXT,                       -- json array
    status        TEXT NOT NULL DEFAULT 'open',-- open|tp1|tp2|tp3|stopped|breakeven
    ticket        TEXT,                        -- broker ticket once executed
    volume        REAL,
    fill_price    REAL,
    result_r      REAL,
    closed_at     INTEGER,
    features      TEXT                         -- json feature vector (doc 09 → AI)
);
CREATE INDEX IF NOT EXISTS idx_signals_status  ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
"""

# idempotent column adds for DBs created before a column existed
_MIGRATIONS = [("features", "TEXT"), ("timeframe", "TEXT NOT NULL DEFAULT 'H1'")]


class TradeRow(BaseModel):
    id: int
    symbol: str
    timeframe: str = "H1"
    direction: Literal["BUY", "SELL"]
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    status: str
    ticket: str | None = None
    volume: float | None = None
    result_r: float | None = None
    created_at: int | None = None
    closed_at: int | None = None


class Journal:
    def __init__(self, db_path: str | None = None) -> None:
        self.path = db_path or config.env(
            "DB_PATH", os.path.join(os.getcwd(), "data", "journal.db"))
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            existing = {r[1] for r in c.execute("PRAGMA table_info(signals)")}
            for col, decl in _MIGRATIONS:
                if col not in existing:
                    c.execute(f"ALTER TABLE signals ADD COLUMN {col} {decl}")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    # ── writes ────────────────────────────────────────────────────────────
    def record_signal(self, sig: Signal, timeframe: str = "H1") -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO signals(created_at,symbol,timeframe,direction,entry,stop_loss,"
                "tp1,tp2,tp3,rr,confidence,confluence,reasons) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (int(time.time()), sig.symbol, timeframe, sig.direction, sig.entry,
                 sig.stop_loss, sig.tp1, sig.tp2, sig.tp3, sig.rr, sig.confidence,
                 sig.confluence_score, json.dumps(sig.reasons)))
            return int(cur.lastrowid)

    def record_features(self, signal_id: int, features: dict) -> None:
        with self._conn() as c:
            c.execute("UPDATE signals SET features=? WHERE id=?",
                      (json.dumps(features), signal_id))

    def features_dataset(self) -> list[tuple[dict, str, float]]:
        """(features, status, result_r) for every CLOSED signal that has features —
        the labelled training set for the AI/Probability engines (docs 16-17).
        Keyed on closed_at so partially scaled-out (tp1/tp2) trades, which carry a
        running result_r but are not yet resolved, are excluded until they close."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT features, status, result_r FROM signals "
                "WHERE features IS NOT NULL AND closed_at IS NOT NULL").fetchall()
        return [(json.loads(r["features"]), r["status"], r["result_r"]) for r in rows]

    def record_execution(self, signal_id: int, ticket: str, volume: float,
                         fill_price: float) -> None:
        with self._conn() as c:
            c.execute("UPDATE signals SET ticket=?, volume=?, fill_price=? WHERE id=?",
                      (ticket, volume, fill_price, signal_id))

    def close_signal(self, signal_id: int, status: str, result_r: float) -> None:
        with self._conn() as c:
            c.execute("UPDATE signals SET status=?, result_r=?, closed_at=? WHERE id=?",
                      (status, result_r, int(time.time()), signal_id))

    def advance(self, signal_id: int, status: str, result_r: float) -> None:
        """Record a partial scale-out (tp1/tp2): store the new status and the R
        booked so far, but leave closed_at NULL so the trade stays live for its
        remaining runner. Only close_signal() finalises a trade."""
        with self._conn() as c:
            c.execute("UPDATE signals SET status=?, result_r=? WHERE id=?",
                      (status, result_r, signal_id))

    def update_status(self, signal_id: int, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE signals SET status=? WHERE id=?", (status, signal_id))

    # ── reads ─────────────────────────────────────────────────────────────
    def get(self, signal_id: int) -> TradeRow | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
        return self._row(row) if row else None

    def get_signal(self, signal_id: int):
        """Rebuild the full Signal from the stored row so a manual trade can be
        executed later from the Telegram button (all fields were journalled)."""
        from ..engines.rule_engine import Signal
        with self._conn() as c:
            r = c.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
        if r is None:
            return None
        return Signal(
            symbol=r["symbol"], direction=r["direction"], entry=r["entry"],
            stop_loss=r["stop_loss"], tp1=r["tp1"], tp2=r["tp2"], tp3=r["tp3"],
            rr=r["rr"] or 0.0, confidence=r["confidence"] or 0,
            confluence_score=r["confluence"] or 0,
            reasons=json.loads(r["reasons"]) if r["reasons"] else [])

    def open_trades(self) -> list[TradeRow]:
        """Every unresolved signal — tracked for its forward outcome whether or not
        it was executed. In dry-run this shadow-tracks EVERY signal so the AI layer
        (docs 16-17) gets a labelled TP/SL history; the ticket, when present, also
        closes the real broker position on resolution."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM signals WHERE status IN ('open','tp1','tp2')").fetchall()
        return [self._row(r) for r in rows]

    def signals_today(self) -> int:
        cutoff = int(time.time()) - 86400
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM signals WHERE created_at>?",
                             (cutoff,)).fetchone()[0]

    def realized_r(self, since_seconds: int, executed_only: bool = False) -> float:
        """Sum of closed-trade R over the window. In trade modes pass
        executed_only=True so only trades that carried a real broker ticket count
        toward the loss locks — the never-filled shadow signals we track for the
        AI history must not veto live risk (see Runtime._account_state)."""
        cutoff = int(time.time()) - since_seconds
        q = ("SELECT result_r FROM signals WHERE closed_at>? "
             "AND result_r IS NOT NULL")
        if executed_only:
            q += " AND ticket IS NOT NULL"
        with self._conn() as c:
            rows = c.execute(q, (cutoff,)).fetchall()
        return round(sum(r[0] for r in rows), 4)

    def recent_signal_for(self, symbol: str, hours: int,
                          timeframe: str | None = None) -> bool:
        cutoff = int(time.time()) - hours * 3600
        q = "SELECT COUNT(*) FROM signals WHERE symbol=? AND created_at>?"
        params: list = [symbol, cutoff]
        if timeframe is not None:            # per-(symbol,TF) cooldown for multi-TF scans
            q += " AND timeframe=?"
            params.append(timeframe)
        with self._conn() as c:
            n = c.execute(q, params).fetchone()[0]
        return n > 0

    def stats(self, days: int = 7) -> dict:
        cutoff = int(time.time()) - days * 86400
        with self._conn() as c:
            rows = c.execute("SELECT result_r FROM signals WHERE closed_at>? "
                             "AND result_r IS NOT NULL", (cutoff,)).fetchall()
        rs = [r[0] for r in rows]
        wins = [r for r in rs if r > 0]
        return {
            "closed": len(rs),
            "wins": len(wins),
            "win_rate": round(100 * len(wins) / len(rs), 1) if rs else 0.0,
            "total_r": round(sum(rs), 2),
            "open": len(self.open_trades()),
        }

    @staticmethod
    def _row(r: sqlite3.Row) -> TradeRow:
        return TradeRow(
            id=r["id"], symbol=r["symbol"], timeframe=r["timeframe"],
            direction=r["direction"], entry=r["entry"], stop_loss=r["stop_loss"],
            tp1=r["tp1"], tp2=r["tp2"], tp3=r["tp3"], status=r["status"],
            ticket=r["ticket"], volume=r["volume"], result_r=r["result_r"],
            created_at=r["created_at"], closed_at=r["closed_at"])
