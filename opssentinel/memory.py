"""Hindsight integration: genuine retain / recall / reflect, with spend guards.

Cost notes (Hindsight runs its own LLM server-side):
  recall  -> retrieval only (no generation); we de-duplicate and cache it
  retain  -> 1 server-side LLM extraction per call; we retain only NOVEL knowledge
  reflect -> 1 server-side LLM generation; capped per session and cached per bank version
"""
from __future__ import annotations
import hashlib, json, re
from .config import Settings
from .db import DB, now
from .usage import Usage


class _Hit:  # shape-compatible with hindsight_client recall results
    def __init__(self, text): self.text = text


class FakeHindsight:
    """TEST MODE ONLY. Token-overlap store so unit tests run offline. Never used in dev/demo."""
    def __init__(self): self.docs = []
    def retain(self, bank_id, content, context=None, timestamp=None): self.docs.append(content)
    def recall(self, bank_id, query, **kw):
        q = set(re.findall(r"\w+", query.lower()))
        scored = sorted(((len(q & set(re.findall(r"\w+", d.lower()))), d) for d in self.docs), reverse=True)
        res = type("R", (), {})()
        res.results = [_Hit(d) for n, d in scored if n > 0][:5]
        return res
    def reflect(self, bank_id, query, **kw):
        return type("A", (), {"text": f"[fake reflect over {len(self.docs)} memories]"})()


def _h(s): return hashlib.sha256(s.encode()).hexdigest()[:16]


class HindsightMemory:
    def __init__(self, s: Settings, db: DB, usage: Usage):
        self.s, self.db, self.usage = s, db, usage
        self.is_fake = s.mode == "test"
        if self.is_fake:
            self.client = FakeHindsight()
        else:
            from hindsight_client import Hindsight  # real client, required outside tests
            try:
                self.client = Hindsight(base_url=s.hindsight_url, api_key=s.hindsight_api_key) \
                    if s.hindsight_api_key else Hindsight(base_url=s.hindsight_url)
            except TypeError:
                self.client = Hindsight(base_url=s.hindsight_url)
            try:  # optional: give the bank a mission so reflect is on-topic (ignored if API differs)
                self.client.create_bank(bank_id=s.bank_id, name="OpsSentinel incident memory",
                                        mission="Remember production incidents, root causes and the fixes "
                                                "this team actually applied, so future incidents resolve faster.")
            except Exception:
                pass
        self._memo: dict[str, list[str]] = {}   # in-process de-dup (same investigation)

    # ---------- versioning: every retain invalidates recall/investigation caches
    def bank_version(self) -> int:
        return int(self.db.kv_get("bank_version", "0"))

    def _bump(self): self.db.kv_set("bank_version", str(self.bank_version() + 1))

    # ---------- RECALL
    def recall(self, query: str, incident_id: str = "") -> list[str]:
        q = query[:400]
        key = f"{self.bank_version()}:{_h(q)}"
        if key in self._memo:
            self.usage.record("recall_dedup", incident=incident_id)
            return self._memo[key]
        cached = self.db.kv_get("recall:" + key)
        if cached:
            self.usage.record("recall_cache", incident=incident_id)
            self._memo[key] = json.loads(cached)
            return self._memo[key]
        try:
            try:
                res = self.client.recall(bank_id=self.s.bank_id, query=q, max_tokens=self.s.recall_max_tokens)
            except TypeError:
                res = self.client.recall(bank_id=self.s.bank_id, query=q)
            texts = [r.text[:700] for r in res.results][:8]
            self.usage.record("hs_recall", incident=incident_id, detail=f"{len(texts)} hits")
        except Exception as e:
            self.usage.record("error", ok=False, incident=incident_id, detail=f"recall: {e}")
            texts = []
        self._memo[key] = texts
        self.db.kv_set("recall:" + key, json.dumps(texts))
        return texts

    # ---------- RETAIN
    def retain(self, content: str, context: str, incident_id: str = "") -> bool:
        try:
            self.client.retain(bank_id=self.s.bank_id, content=content, context=context, timestamp=now())
            self.usage.record("hs_retain", incident=incident_id, detail=context)
            self._bump()
            return True
        except Exception as e:  # e.g. Hindsight's own LLM quota exhausted -> queue, never lose the lesson
            self.usage.record("error", ok=False, incident=incident_id, detail=f"retain: {e}")
            self.db.execute("INSERT INTO pending_retains(content,context,ts) VALUES(?,?,?)", (content, context, now()))
            return False

    def flush_pending(self) -> int:
        n = 0
        for r in self.db.query("SELECT id, content, context FROM pending_retains ORDER BY id"):
            if self.retain(r["content"], r["context"]):
                self.db.execute("DELETE FROM pending_retains WHERE id=?", (r["id"],)); n += 1
            else:  # retain() re-queued a duplicate; drop it and stop to avoid hammering a dead quota
                self.db.execute("DELETE FROM pending_retains WHERE id=(SELECT MAX(id) FROM pending_retains)")
                break
        return n

    # ---------- REFLECT
    def reflect(self, query: str, force: bool = False) -> str | None:
        key = f"reflect:{self.bank_version()}:{_h(query)}"
        cached = self.db.kv_get(key)
        if cached and not force:
            self.usage.record("recall_cache", detail="reflect")
            return cached
        if self.usage.session_reflects >= self.s.max_reflects_per_session:
            self.usage.record("budget_block", detail="reflect limit")
            return cached
        try:
            ans = self.client.reflect(bank_id=self.s.bank_id, query=query)
            text = getattr(ans, "text", None) or str(ans)
            self.usage.session_reflects += 1
            self.usage.record("hs_reflect", detail=query[:80])
            self.db.kv_set(key, text)
            self.db.kv_set("last_reflect", text)
            return text
        except Exception as e:
            self.usage.record("error", ok=False, detail=f"reflect: {e}")
            return cached
