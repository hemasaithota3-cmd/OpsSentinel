"""Tiny DB layer: PostgreSQL in dev/demo, sqlite in tests. No ORM, no paid services."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_DDL = [
    "CREATE TABLE IF NOT EXISTS usage_events(id {pk}, ts TEXT, kind TEXT, provider TEXT, model TEXT,"
    " tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, ok INTEGER, incident_id TEXT, detail TEXT)",
    "CREATE TABLE IF NOT EXISTS llm_cache(key TEXT PRIMARY KEY, response TEXT, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)",
    "CREATE TABLE IF NOT EXISTS pending_retains(id {pk}, content TEXT, context TEXT, ts TEXT)",
    "CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY, ts TEXT, service TEXT, cause_id TEXT,"
    " root_cause TEXT, resolution TEXT, confidence REAL, source TEXT, memory_hits INTEGER, degraded INTEGER,"
    " llm_calls INTEGER, llm_tokens INTEGER, cause_ok INTEGER, fix_specific INTEGER, retained TEXT, report TEXT)",
]


class DB:
    def __init__(self, url: str):
        self.url = url
        if url.startswith("sqlite"):
            self.kind = "sqlite"
            path = url.split("///", 1)[1] if "///" in url else ":memory:"
            self.conn = sqlite3.connect(path or ":memory:", check_same_thread=False, isolation_level=None)
            self.conn.row_factory = sqlite3.Row
        else:
            import psycopg2  # lazy: not needed in test mode
            self.kind = "pg"
            self.conn = psycopg2.connect(url)
            self.conn.autocommit = True
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if self.kind == "sqlite" else "BIGSERIAL PRIMARY KEY"
        for stmt in _DDL:
            self.execute(stmt.format(pk=pk))

    def _q(self, sql): return sql.replace("?", "%s") if self.kind == "pg" else sql

    def execute(self, sql, params=()):
        if self.kind == "pg":
            with self.conn.cursor() as cur:
                cur.execute(self._q(sql), params)
        else:
            self.conn.execute(sql, params)

    def query(self, sql, params=()):
        if self.kind == "pg":
            import psycopg2.extras
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(self._q(sql), params)
                return [dict(r) for r in cur.fetchall()]
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def kv_get(self, k, default=None):
        r = self.query("SELECT v FROM kv WHERE k=?", (k,))
        return r[0]["v"] if r else default

    def kv_set(self, k, v):
        self.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))

    def kv_prefix(self, prefix):
        return self.query("SELECT k, v FROM kv WHERE k LIKE ?", (prefix + "%",))

    def reset_demo_state(self):
        """Wipe incident history + memory-derived caches (keeps llm_cache and the usage ledger)."""
        for t in ("incidents", "pending_retains", "kv"):
            self.execute(f"DELETE FROM {t}")
