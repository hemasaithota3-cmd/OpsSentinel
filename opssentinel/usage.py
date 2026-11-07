"""Usage ledger + budget guard. Every LLM call, Hindsight op, cache hit and error is recorded."""
from __future__ import annotations
from collections import defaultdict
from .config import Settings
from .db import DB, now

LOCAL_FREE = {"ollama", "offline", "replay"}


class Usage:
    def __init__(self, db: DB, s: Settings):
        self.db, self.s = db, s
        self.session_calls = 0
        self.session_reflects = 0
        self.incident_calls: dict[str, int] = defaultdict(int)

    def est_cost(self, provider, tin, tout) -> float:
        if provider in LOCAL_FREE:
            return 0.0
        return (tin * self.s.price_in_per_m + tout * self.s.price_out_per_m) / 1e6

    def record(self, kind, *, provider="", model="", tin=0, tout=0, ok=True, incident="", detail=""):
        cost = self.est_cost(provider, tin, tout) if kind == "llm" else 0.0
        self.db.execute(
            "INSERT INTO usage_events(ts,kind,provider,model,tokens_in,tokens_out,cost_usd,ok,incident_id,detail)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (now(), kind, provider, model, tin, tout, cost, 1 if ok else 0, incident, detail[:200]))
        if kind == "llm":
            self.session_calls += 1
            self.incident_calls[incident] += 1

    def tokens_today(self) -> int:
        r = self.db.query("SELECT COALESCE(SUM(tokens_in+tokens_out),0) AS t FROM usage_events "
                          "WHERE kind='llm' AND ts>=?", (now()[:10],))
        return int(r[0]["t"])

    def allow_llm(self, incident: str):
        if self.incident_calls[incident] >= self.s.max_calls_per_incident:
            return False, "per-incident call limit"
        if self.session_calls >= self.s.max_calls_per_session:
            return False, "per-session call limit"
        if self.tokens_today() >= self.s.max_tokens_per_day:
            return False, "daily token limit"
        return True, "ok"

    def incident_stats(self, incident: str):
        r = self.db.query("SELECT COUNT(*) AS n, COALESCE(SUM(tokens_in+tokens_out),0) AS t FROM usage_events "
                          "WHERE kind='llm' AND incident_id=?", (incident,))
        return int(r[0]["n"]), int(r[0]["t"])

    def summary(self) -> dict:
        rows = self.db.query("SELECT kind, COUNT(*) AS n, COALESCE(SUM(tokens_in),0) AS tin, "
                             "COALESCE(SUM(tokens_out),0) AS tout, COALESCE(SUM(cost_usd),0) AS cost "
                             "FROM usage_events GROUP BY kind")
        by = {r["kind"]: r for r in rows}
        g = lambda k, f="n": (by.get(k) or {}).get(f, 0) or 0
        return {
            "llm_requests": g("llm"), "tokens_in": g("llm", "tin"), "tokens_out": g("llm", "tout"),
            "est_cost_usd": round(float(g("llm", "cost")), 5),
            "hindsight_retain": g("hs_retain"), "hindsight_recall": g("hs_recall"),
            "hindsight_reflect": g("hs_reflect"),
            "recall_dedup_saved": g("recall_dedup") + g("recall_cache"),
            "llm_cache_hits": g("cache_hit"), "budget_blocks": g("budget_block"), "errors": g("error"),
            "tokens_today": self.tokens_today(), "daily_token_cap": self.s.max_tokens_per_day,
        }
