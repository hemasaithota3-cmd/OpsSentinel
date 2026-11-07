"""Budget-guarded, cache-first, provider-configurable LLM client.

Rules enforced here (never in prompts):
  * cache first (Postgres llm_cache) -> identical prompts never cost twice
  * offline / replay providers never touch the network
  * per-incident, per-session and per-day limits; bounded retries
  * HTTP 429 => cooldown, then deterministic fallback. NEVER auto-switches to another (paid) provider.
  * JSON-mode output validated by the caller; only VALID responses are cached.
"""
from __future__ import annotations
import hashlib, json, re, time
from dataclasses import dataclass
import requests
from .config import Settings
from .db import DB, now
from .usage import Usage

PROVIDERS = {
    "groq": {"base": "https://api.groq.com/openai/v1"},
    "ollama": {"base": "http://localhost:11434/v1"},          # local, free
    "openai_compat": {"base": None},                          # any endpoint; needs ALLOW_PAID_PROVIDER=1
}
NO_NETWORK = {"offline", "replay"}


class QuotaError(Exception): ...


@dataclass
class LLMResult:
    data: dict | None
    source: str   # cache | llm | none
    reason: str   # ok | offline | replay_miss | budget | quota | error


class LLMClient:
    def __init__(self, s: Settings, db: DB, usage: Usage):
        self.s, self.db, self.usage = s, db, usage
        self._quota_until = 0.0
        p = s.llm_provider
        if p not in PROVIDERS and p not in NO_NETWORK:
            raise ValueError(f"Unknown LLM_PROVIDER '{p}'. Use one of {list(PROVIDERS) + sorted(NO_NETWORK)}")
        if p == "openai_compat" and not s.allow_paid:
            raise ValueError("openai_compat may be a paid endpoint: set ALLOW_PAID_PROVIDER=1 to opt in explicitly.")

    @staticmethod
    def key(model, system, user):
        return hashlib.sha256(f"{model}|{system}|{user}".encode()).hexdigest()

    def complete_json(self, system, user, validator, incident_id="") -> LLMResult:
        k = self.key(self.s.llm_model, system, user)
        row = self.db.query("SELECT response FROM llm_cache WHERE key=?", (k,))
        if row:
            data = json.loads(row[0]["response"])
            if validator(data):
                self.usage.record("cache_hit", incident=incident_id, detail="llm")
                return LLMResult(data, "cache", "ok")
        p = self.s.llm_provider
        if p == "offline":
            return LLMResult(None, "none", "offline")
        if p == "replay":
            return LLMResult(None, "none", "replay_miss")
        if time.time() < self._quota_until:
            return LLMResult(None, "none", "quota")
        for attempt in range(self.s.max_retries + 1):
            ok, why = self.usage.allow_llm(incident_id)
            if not ok:
                self.usage.record("budget_block", incident=incident_id, detail=why)
                return LLMResult(None, "none", "budget")
            try:
                data, tin, tout = self._call(system, user)
            except QuotaError:
                self._quota_until = time.time() + self.s.quota_cooldown_s
                self.usage.record("error", provider=p, ok=False, incident=incident_id, detail="quota/429")
                return LLMResult(None, "none", "quota")
            except Exception as e:  # network, 5xx, bad JSON
                self.usage.record("error", provider=p, ok=False, incident=incident_id, detail=str(e))
                time.sleep(min(2 ** attempt, 4))
                continue
            self.usage.record("llm", provider=p, model=self.s.llm_model, tin=tin, tout=tout, incident=incident_id)
            if validator(data):
                self.db.execute("INSERT INTO llm_cache(key,response,created_at) VALUES(?,?,?) "
                                "ON CONFLICT(key) DO NOTHING", (k, json.dumps(data), now()))
                return LLMResult(data, "llm", "ok")
            self.usage.record("error", provider=p, ok=False, incident=incident_id, detail="schema_invalid")
        return LLMResult(None, "none", "error")

    def _call(self, system, user):
        p = self.s.llm_provider
        base = self.s.llm_base_url or PROVIDERS[p]["base"]
        if not base:
            raise ValueError("LLM_BASE_URL required")
        body = {"model": self.s.llm_model, "temperature": 0, "max_tokens": self.s.max_output_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if "gpt-oss" in self.s.llm_model:
            body["reasoning_effort"] = "low"   # fewer hidden reasoning tokens
        r = requests.post(f"{base}/chat/completions", json=body, timeout=30,
                          headers={"Authorization": f"Bearer {self.s.llm_api_key}"})
        if r.status_code == 429:
            raise QuotaError()
        r.raise_for_status()
        j = r.json()
        text = j["choices"][0]["message"]["content"] or ""
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0) if m else text)
        u = j.get("usage", {})
        return data, int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))

    # --- fixtures so the demo can replay real answers with zero API spend
    def export_cache(self, path):
        rows = self.db.query("SELECT key, response FROM llm_cache")
        json.dump(rows, open(path, "w"), indent=1)
        return len(rows)

    def import_cache(self, path):
        rows = json.load(open(path))
        for r in rows:
            self.db.execute("INSERT INTO llm_cache(key,response,created_at) VALUES(?,?,?) "
                            "ON CONFLICT(key) DO NOTHING", (r["key"], r["response"], now()))
        return len(rows)
