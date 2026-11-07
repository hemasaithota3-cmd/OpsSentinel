"""Deterministic failure taxonomy + generic runbooks (the 'no-memory' baseline).
Pure Python: classification costs 0 tokens."""
from __future__ import annotations
import re

CAUSES = {
    "db_pool_exhausted": {
        "title": "Database connection pool exhausted",
        "kw": ["queuepool", "connection slots", "acquire database connection", "pool"],
        "mem_kw": ["pool", "connection", "database"], "metrics": ["db_pool_util"],
        "generic": "Check active DB connections and long-running queries; consider raising the pool size."},
    "memory_leak_oom": {
        "title": "Memory leak causing OutOfMemory kills",
        "kw": ["outofmemory", "heap space", "oomkilled", "gc overhead"],
        "mem_kw": ["memory", "oom", "heap", "leak"], "metrics": ["mem_pct", "restarts"],
        "generic": "Inspect memory growth and recent releases; restart as a stopgap and capture a heap dump."},
    "bad_deploy_regression": {
        "title": "Regression introduced by a recent deploy",
        "kw": ["nullpointerexception", "unhandled exception", "regression", "deploy"],
        "mem_kw": ["deploy", "regression", "rolled back", "rollback", "exception", "feature flag"],
        "metrics": [], "generic": "Compare errors with the last deploy; consider rollback or disabling new feature flags."},
    "disk_full": {
        "title": "Disk full on the service host",
        "kw": ["no space left", "errno 28", "write checkpoint"],
        "mem_kw": ["disk", "space", "logrotate", "log"], "metrics": ["disk_pct"],
        "generic": "Free disk space (old logs/temp files) and review log rotation and disk alerts."},
    "dns_resolution_failure": {
        "title": "DNS / service discovery failure",
        "kw": ["name resolution", "getaddrinfo", "enotfound", "upstream"],
        "mem_kw": ["dns", "name resolution", "coredns", "ndots"], "metrics": [],
        "generic": "Check cluster DNS health and the upstream service's discovery records."},
}
_FIX = re.compile(r"Resolution[^:]*:\s*(.*?)(?:\s*Time to resolve.*)?$", re.S)
ACTION = re.compile(r"\b(rolled back|raised|restarted|purged|set|disabled|enabled|killed|fixed|resolved|increased|added)\b", re.I)


def evidence_text(ev: dict) -> str:
    return " ".join(t["t"] for t in ev["top"]).lower() + " " + (ev.get("deploy_hint") or "").lower()


def classify(ev: dict):
    """-> (cause_id, score, confidence). Generic baseline: confidence capped low on purpose."""
    txt = evidence_text(ev)
    names = {b["metric"] for b in ev["breaches"]}
    best, best_s = None, -1
    for cid, c in CAUSES.items():
        sc = sum(2 for k in c["kw"] if k in txt) + sum(1 for m in c["metrics"] if m in names)
        if cid == "bad_deploy_regression" and ev.get("deploy_hint"):
            sc += 1
        if sc > best_s:
            best, best_s = cid, sc
    conf = min(0.45, 0.15 + 0.07 * max(best_s, 0)) if best_s > 0 else 0.1
    return best, best_s, conf


def memory_match(recalled: list[str], ev: dict, cause_id: str):
    """Deterministically decide whether Hindsight's recalled facts contain a usable past fix.
    Returns {text, hits} or None. No LLM involved."""
    c = CAUSES[cause_id]
    scored = []
    for r in recalled:
        rl = r.lower()
        rel = cause_id in rl or sum(1 for k in c["mem_kw"] if k in rl) >= 2
        if rel and ACTION.search(r):
            scored.append((int(ev["service"] in rl), sum(1 for k in c["mem_kw"] if k in rl), r))
    if not scored:
        return None
    scored.sort(reverse=True)
    fixes = []
    for _, _, t in scored[:2]:
        m = _FIX.search(t)           # our own post-mortem format; paraphrased facts fall back to the whole text
        f = (m.group(1) if m else t).strip()
        if f not in fixes:
            fixes.append(f)
    return {"text": " ".join(fixes)[:360], "hits": len(scored)}
