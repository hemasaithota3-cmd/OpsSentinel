"""Offline, zero-cost tests (mode=test: sqlite + FakeHindsight + offline LLM). Run: python -m unittest -v"""
import unittest
from opssentinel.config import get_settings
from opssentinel.detect import extract_evidence
from opssentinel.llm import LLMClient
from opssentinel.pipeline import make_ctx, run_linear, retain_recurrence_summary
from opssentinel.taxonomy import classify
from sim.scenarios import DEMO_SEQUENCE, SCENARIOS, make_incident


class T(unittest.TestCase):
    def ctx(self, **kw): return make_ctx(get_settings("test", **kw))

    def test_evidence_is_compact_and_classification_deterministic(self):
        for sc in SCENARIOS:
            inc = make_incident(sc, 1, 0)
            ev = extract_evidence(inc["service"], inc["logs"], inc["metrics"])
            self.assertLess(len(str(ev)), 1600)
            self.assertEqual(classify(ev)[0], sc, sc)
            self.assertEqual(make_incident(sc, 1, 0)["logs"], inc["logs"])

    def test_memory_improves_and_llm_never_called_offline(self):
        ctx, rows = self.ctx(), []
        for i, sc in enumerate(DEMO_SEQUENCE):
            inc = make_incident(sc, 7, i)
            rows.append(run_linear(inc, ctx, inc["expected_fix"]))
        first_seen = {}
        for i, (sc, r) in enumerate(zip(DEMO_SEQUENCE, rows)):
            if sc not in first_seen:
                first_seen[sc] = i
                self.assertEqual(r["fix_specific"], 0)          # no memory yet -> generic
            else:
                self.assertEqual(r["source"], "memory")
                self.assertEqual(r["fix_specific"], 1)          # recalled the team's real fix
        self.assertEqual(ctx.usage.summary()["llm_requests"], 0)
        self.assertEqual(sum(r["cause_ok"] for r in rows), len(rows))

    def test_retain_only_novel_and_recurrence_batch(self):
        ctx = self.ctx()
        for i, sc in enumerate(DEMO_SEQUENCE):
            inc = make_incident(sc, 7, i); run_linear(inc, ctx, inc["expected_fix"])
        n_novel = len(set(DEMO_SEQUENCE))
        self.assertEqual(ctx.usage.summary()["hindsight_retain"], n_novel)
        self.assertTrue(retain_recurrence_summary(ctx))
        self.assertEqual(ctx.usage.summary()["hindsight_retain"], n_novel + 1)

    def test_recall_dedup_and_investigation_cache(self):
        ctx = self.ctx()
        inc = make_incident("disk_full", 3, 0)
        run_linear(inc, ctx)                                    # no resolution => no retain => version stable
        recalls = ctx.usage.summary()["hindsight_recall"]
        inc2 = dict(inc, id="INC-again")
        run_linear(inc2, ctx)
        s = ctx.usage.summary()
        self.assertEqual(s["hindsight_recall"], recalls)        # nothing recalled twice

    def test_budget_blocks_and_degrades(self):
        ctx = self.ctx(llm_provider="ollama", max_calls_per_session=0)
        ctx.llm = LLMClient(ctx.s, ctx.db, ctx.usage)
        r = run_linear(make_incident("db_pool_exhausted", 2, 0), ctx)
        self.assertTrue(r["degraded"])
        self.assertEqual(ctx.usage.summary()["llm_requests"], 0)
        self.assertGreaterEqual(ctx.usage.summary()["budget_blocks"], 1)

    def test_paid_provider_requires_opt_in(self):
        with self.assertRaises(ValueError):
            self.ctx(llm_provider="openai_compat")

    def test_normal_traffic_not_flagged(self):
        ctx = self.ctx()
        inc = make_incident("disk_full", 1, 0)
        inc["logs"] = [l for l in inc["logs"] if " INFO " in l]
        inc["metrics"] = {"cpu_pct": 30, "mem_pct": 50, "disk_pct": 50, "p99_ms": 200, "err_rate": 0.0}
        self.assertEqual(run_linear(inc, ctx)["outcome"], "no_incident")


if __name__ == "__main__":
    unittest.main()
