"""Investigation pipeline. Nodes are plain functions so the same logic runs under LangGraph
(build_graph) or the dependency-free linear runner used by tests.

detect -> [cached? report | none? END | recall] -> diagnose -> (low confidence & budget left? recall(widened))
       -> report -> [resolution known? learn | END]

Loop safety: `iterations` is capped by MAX_GRAPH_ITERATIONS, widening happens at most once, and LangGraph
also gets a hard recursion_limit.
"""
from __future__ import annotations
import json, re
from dataclasses import dataclass
from typing import TypedDict
from .config import Settings, get_settings
from .db import DB, now
from .detect import extract_evidence, is_anomalous
from .llm import LLMClient
from .memory import HindsightMemory
from .taxonomy import CAUSES, classify, memory_match
from .usage import Usage


@dataclass
class Ctx:
    s: Settings
    db: DB
    usage: Usage
    llm: LLMClient
    mem: HindsightMemory


def make_ctx(s: Settings | None = None) -> Ctx:
    s = s or get_settings()
    db = DB(s.database_url)
    usage = Usage(db, s)
    return Ctx(s, db, usage, LLMClient(s, db, usage), HindsightMemory(s, db, usage))


class State(TypedDict, total=False):
    incident: dict
    resolution: str
    evidence: dict
    recalled: list
    diagnosis: dict
    iterations: int
    widened: bool
    outcome: str
    report: dict


# ------------------------------------------------------------------ nodes
def n_detect(st: State, ctx: Ctx) -> State:
    inc = st["incident"]
    ev = extract_evidence(inc["service"], inc["logs"], inc["metrics"])
    st.update(evidence=ev, iterations=0, widened=False, recalled=[])
    if not is_anomalous(ev):
        st["outcome"] = "no_incident"
        return st
    hit = ctx.db.kv_get(f"inv:{ctx.mem.bank_version()}:{ev['fingerprint']}")
    if hit:   # identical situation, memory unchanged since => zero recall, zero LLM
        d = json.loads(hit); d["source"] = "cache"
        st.update(diagnosis=d, outcome="cached")
        ctx.usage.record("cache_hit", incident=inc["id"], detail="investigation")
    return st


def route_detect(st: State) -> str:
    return {"no_incident": "end", "cached": "report"}.get(st.get("outcome", ""), "recall")


def build_query(ev: dict, widened: bool) -> str:
    cid, _, _ = classify(ev)
    if widened:
        return f"{ev['service']} {CAUSES[cid]['title']} root cause resolution fix"
    top = ev["top"][0]["t"] if ev["top"] else ""
    return f"{ev['service']} {top} " + " ".join(b["metric"] for b in ev["breaches"])


def n_recall(st: State, ctx: Ctx) -> State:
    q = build_query(st["evidence"], st["widened"])
    merged = list(dict.fromkeys(st["recalled"] + ctx.mem.recall(q, st["incident"]["id"])))
    st["recalled"] = merged
    return st


_SYSTEM = ("You are an SRE assistant. Reply ONLY with JSON: "
           '{"cause_id": <one of %s>, "root_cause": <=160 chars, "resolution": <=240 chars, "confidence": 0..1}. '
           "If past incidents are given, reuse the fix this team applied.")


def _valid(d) -> bool:
    return (isinstance(d, dict) and d.get("cause_id") in CAUSES and isinstance(d.get("root_cause"), str)
            and isinstance(d.get("resolution"), str) and d["root_cause"] and d["resolution"]
            and isinstance(d.get("confidence"), (int, float)) and 0 <= d["confidence"] <= 1)


def n_diagnose(st: State, ctx: Ctx) -> State:
    st["iterations"] += 1
    ev, inc_id = st["evidence"], st["incident"]["id"]
    cid, _, base_conf = classify(ev)
    mm = memory_match(st["recalled"], ev, cid)
    if mm:   # memory-first: Python decides, no LLM tokens spent
        st["diagnosis"] = {"cause_id": cid, "root_cause": CAUSES[cid]["title"], "resolution": mm["text"],
                           "confidence": 0.9, "source": "memory", "memory_hits": mm["hits"], "degraded": False}
        return st
    user = json.dumps({"evidence": {k: ev[k] for k in ("service", "error_lines", "top", "breaches", "deploy_hint")},
                       "past": [r[:250] for r in st["recalled"][:3]]}, separators=(",", ":"))
    res = ctx.llm.complete_json(_SYSTEM % list(CAUSES), user, _valid, inc_id)
    if res.data:
        d = res.data
        st["diagnosis"] = {**d, "source": "llm" if res.source == "llm" else "cache", "memory_hits": len(st["recalled"]),
                           "degraded": False}
    else:    # deterministic generic baseline
        st["diagnosis"] = {"cause_id": cid, "root_cause": CAUSES[cid]["title"], "resolution": CAUSES[cid]["generic"],
                           "confidence": base_conf, "source": "fallback", "memory_hits": len(st["recalled"]),
                           "degraded": res.reason in ("budget", "quota", "error"), "reason": res.reason}
    return st


def make_route_diagnose(ctx: Ctx):
    def route(st: State) -> str:
        if (st["diagnosis"]["confidence"] < 0.5 and not st["widened"]
                and st["iterations"] < ctx.s.max_graph_iterations):
            st["widened"] = True
            return "recall"
        return "report"
    return route


def n_report(st: State, ctx: Ctx) -> State:
    inc, ev, d = st["incident"], st["evidence"], st["diagnosis"]
    calls, toks = ctx.usage.incident_stats(inc["id"])
    rep = {"incident_id": inc["id"], "service": inc["service"], "cause_id": d["cause_id"],
           "root_cause": d["root_cause"], "resolution": d["resolution"], "confidence": round(float(d["confidence"]), 2),
           "source": d["source"], "memory_hits": d.get("memory_hits", 0), "degraded": bool(d.get("degraded")),
           "llm_calls": calls, "llm_tokens": toks, "top_errors": ev["top"][:2], "breaches": ev["breaches"]}
    if d["source"] in ("memory", "llm") and st.get("outcome") != "cached":
        ctx.db.kv_set(f"inv:{ctx.mem.bank_version()}:{ev['fingerprint']}", json.dumps(d))
    ok = None
    if "expected_fix" in inc:   # simulator ground truth (demo/test only)
        rep["cause_ok"] = int(d["cause_id"] == inc["scenario"])
        rep["fix_specific"] = int(all(k in d["resolution"].lower() for k in inc["fix_kw"]))
    ctx.db.execute("INSERT INTO incidents(id,ts,service,cause_id,root_cause,resolution,confidence,source,memory_hits,"
                   "degraded,llm_calls,llm_tokens,cause_ok,fix_specific,retained,report) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET report=excluded.report",
                   (rep["incident_id"], now(), rep["service"], rep["cause_id"], rep["root_cause"], rep["resolution"],
                    rep["confidence"], rep["source"], rep["memory_hits"], int(rep["degraded"]), calls, toks,
                    rep.get("cause_ok"), rep.get("fix_specific"), "no", json.dumps(rep)))
    st["report"] = rep
    return st


def route_report(st: State) -> str:
    return "learn" if st.get("resolution") else "end"


def _similar(proposed: str, actual: str) -> float:
    """Share of the team's actual fix already contained in what memory proposed (service names ignored)."""
    ta, tb = set(re.findall(r"\w+", proposed.lower())), set(re.findall(r"\w+", actual.lower()))
    return len(ta & tb) / max(1, len(tb))


def postmortem(rep: dict, resolution: str, mttr: int | None) -> str:
    err = rep["top_errors"][0]["t"] if rep["top_errors"] else "n/a"
    sym = ", ".join(f"{b['metric']}={b['value']}" for b in rep["breaches"]) or "no metric breach"
    return (f"Incident {rep['incident_id']} on service {rep['service']}. Symptoms: {sym}; top error: {err}. "
            f"Root cause: {rep['root_cause']} [cause: {rep['cause_id']}]. "
            f"Resolution applied by the team: {resolution} "
            + (f"Time to resolve: {mttr} minutes." if mttr else ""))


def n_learn(st: State, ctx: Ctx) -> State:
    """Retain only NOVEL knowledge. Confirmed repeats are counted in Postgres and batched later."""
    rep, resolution = st["report"], st["resolution"]
    dup = rep["source"] in ("memory", "cache") and _similar(rep["resolution"], resolution) >= 0.7
    if dup:
        k = f"recur:{rep['cause_id']}:{rep['service']}"
        ctx.db.kv_set(k, str(int(ctx.db.kv_get(k, "0")) + 1))
        rep["retained"] = "recurrence_counted"
    else:
        ok = ctx.mem.retain(postmortem(rep, resolution, st["incident"].get("mttr_min")),
                            "incident post-mortem", rep["incident_id"])
        rep["retained"] = "retained" if ok else "queued"
    ctx.db.execute("UPDATE incidents SET retained=? WHERE id=?", (rep["retained"], rep["incident_id"]))
    return st


def retain_recurrence_summary(ctx: Ctx) -> bool:
    rows = ctx.db.kv_prefix("recur:")
    if not rows:
        return False
    parts = [f"{r['k'].split(':')[2]} had {int(r['v'])} repeat(s) of {r['k'].split(':')[1]}" for r in rows]
    ok = ctx.mem.retain("Recurrence summary: " + "; ".join(parts) + ". Known fixes worked on each repeat.",
                        "recurrence summary")
    if ok:
        for r in rows:
            ctx.db.execute("DELETE FROM kv WHERE k=?", (r["k"],))
    return ok


# ------------------------------------------------------------------ runners
def run_linear(incident: dict, ctx: Ctx, resolution: str | None = None) -> dict:
    """Same nodes + routers as the graph, no LangGraph dependency (used by tests and as a safe fallback)."""
    st: State = {"incident": incident}
    if resolution:
        st["resolution"] = resolution
    n_detect(st, ctx)
    nxt = route_detect(st)
    if nxt == "end":
        return {"incident_id": incident["id"], "outcome": "no_incident"}
    if nxt == "recall":
        rd = make_route_diagnose(ctx)
        for _ in range(ctx.s.max_graph_iterations + 1):   # hard bound, mirrors recursion_limit
            n_recall(st, ctx); n_diagnose(st, ctx)
            if rd(st) == "report":
                break
    n_report(st, ctx)
    if route_report(st) == "learn":
        n_learn(st, ctx)
    return st["report"]


def build_graph(ctx: Ctx):
    from langgraph.graph import StateGraph, END
    g = StateGraph(State)
    g.add_node("detect", lambda s: n_detect(s, ctx))
    g.add_node("recall", lambda s: n_recall(s, ctx))
    g.add_node("diagnose", lambda s: n_diagnose(s, ctx))
    g.add_node("report", lambda s: n_report(s, ctx))
    g.add_node("learn", lambda s: n_learn(s, ctx))
    g.set_entry_point("detect")
    g.add_conditional_edges("detect", route_detect, {"end": END, "report": "report", "recall": "recall"})
    g.add_edge("recall", "diagnose")
    g.add_conditional_edges("diagnose", make_route_diagnose(ctx), {"recall": "recall", "report": "report"})
    g.add_conditional_edges("report", route_report, {"learn": "learn", "end": END})
    g.add_edge("learn", END)
    return g.compile()


def run_graph(app, ctx: Ctx, incident: dict, resolution: str | None = None) -> dict:
    st: State = {"incident": incident}
    if resolution:
        st["resolution"] = resolution
    out = app.invoke(st, config={"recursion_limit": 4 * ctx.s.max_graph_iterations + 8})
    return out.get("report") or {"incident_id": incident["id"], "outcome": out.get("outcome", "no_incident")}
