"""OpsSentinel CLI.  python -m opssentinel.cli <command>"""
from __future__ import annotations
import argparse, json, os, sys, time
from dataclasses import replace
from .config import get_settings
from .pipeline import (build_graph, make_ctx, retain_recurrence_summary, run_graph, run_linear)
from .sources import fetch_loki, fetch_prometheus
from sim.scenarios import DEMO_SEQUENCE, SCENARIOS, make_incident

FIXTURE = "fixtures/demo_llm_cache.json"
REFLECT_Q = ("What recurring failure patterns have we seen, which services are most affected, "
             "and which fixes worked best? Answer in 3 short bullets.")


def runner(ctx, engine):
    if engine == "linear" or ctx.s.mode == "test":
        return lambda inc, res=None: run_linear(inc, ctx, res)
    try:
        app = build_graph(ctx)
        return lambda inc, res=None: run_graph(app, ctx, inc, res)
    except ImportError:
        print("[warn] langgraph not installed -> using the equivalent linear runner", file=sys.stderr)
        return lambda inc, res=None: run_linear(inc, ctx, res)


def print_usage(ctx):
    u = ctx.usage.summary()
    print("\n=== Usage ===")
    print(f"LLM requests {u['llm_requests']} | tokens in/out {u['tokens_in']}/{u['tokens_out']} | est. cost ${u['est_cost_usd']}")
    print(f"Hindsight: retain {u['hindsight_retain']}  recall {u['hindsight_recall']}  reflect {u['hindsight_reflect']}"
          f"  (recall calls saved by cache/dedup: {u['recall_dedup_saved']})")
    print(f"LLM cache hits {u['llm_cache_hits']} | budget blocks {u['budget_blocks']} | errors {u['errors']}")
    print(f"Daily token budget: {u['tokens_today']}/{u['daily_token_cap']}")


def cmd_demo(a):
    s = get_settings()
    if a.fresh:
        s = replace(s, bank_id=f"{s.bank_id}-{int(time.time())}")
    ctx = make_ctx(s)
    if a.fresh:
        ctx.db.reset_demo_state()
    if os.path.exists(FIXTURE):
        ctx.llm.import_cache(FIXTURE)
    run = runner(ctx, a.engine)
    print(f"mode={s.mode} llm={s.llm_provider} bank={s.bank_id}\n")
    print(f"{'#':>2} {'scenario':<24}{'service':<14}{'source':<9}{'cause':<6}{'fix':<9}{'llm':<4}{'mem':<4}")
    for i, sc in enumerate(DEMO_SEQUENCE[:a.n]):
        inc = make_incident(sc, a.seed, i)
        r = run(inc, inc["expected_fix"])
        print(f"{i+1:>2} {sc:<24}{r['service']:<14}{r['source']:<9}{'ok' if r.get('cause_ok') else 'X':<6}"
              f"{'ok' if r.get('fix_specific') else 'generic':<9}{r['llm_calls']:<4}{r['memory_hits']:<4}")
    retain_recurrence_summary(ctx)
    if not a.no_reflect:
        print("\n=== Hindsight reflect ===")
        print(ctx.mem.reflect(REFLECT_Q) or "(reflect unavailable / budget-limited)")
    print_usage(ctx)


def cmd_investigate(a):
    ctx = make_ctx()
    inc = make_incident(a.scenario, a.seed, a.idx)
    rep = runner(ctx, a.engine)(inc, inc["expected_fix"] if a.auto_resolve else None)
    print(json.dumps(rep, indent=2))
    print_usage(ctx)


def cmd_live(a):
    s = get_settings(); ctx = make_ctx(s)
    inc = {"id": f"LIVE-{int(time.time())}", "service": a.service,
           "logs": fetch_loki(s, a.service), "metrics": fetch_prometheus(s, a.service)}
    print(json.dumps(runner(ctx, a.engine)(inc, None), indent=2))


def cmd_usage(a): print_usage(make_ctx())
def cmd_flush(a): print("flushed", make_ctx().mem.flush_pending(), "pending retains")
def cmd_export(a): print("exported", make_ctx().llm.export_cache(FIXTURE), "->", FIXTURE)
def cmd_import(a): print("imported", make_ctx().llm.import_cache(FIXTURE))


def cmd_metrics(a):
    from .metrics_server import serve
    serve(make_ctx(), a.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="opssentinel")
    p.add_argument("--engine", choices=["langgraph", "linear"], default="langgraph")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo"); d.set_defaults(f=cmd_demo)
    d.add_argument("--n", type=int, default=len(DEMO_SEQUENCE)); d.add_argument("--seed", type=int, default=7)
    d.add_argument("--fresh", action="store_true", help="new Hindsight bank + clean local history")
    d.add_argument("--no-reflect", action="store_true")
    i = sub.add_parser("investigate"); i.set_defaults(f=cmd_investigate)
    i.add_argument("--scenario", choices=list(SCENARIOS), required=True)
    i.add_argument("--seed", type=int, default=7); i.add_argument("--idx", type=int, default=0)
    i.add_argument("--auto-resolve", action="store_true", help="simulate the team's fix so it is retained")
    l = sub.add_parser("live"); l.set_defaults(f=cmd_live); l.add_argument("--service", required=True)
    for n, f in (("usage", cmd_usage), ("flush-retains", cmd_flush), ("export-cache", cmd_export), ("import-cache", cmd_import)):
        sub.add_parser(n).set_defaults(f=f)
    m = sub.add_parser("metrics"); m.set_defaults(f=cmd_metrics); m.add_argument("--port", type=int, default=9102)
    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
