"""Deterministic detection + evidence compression. Pure Python, zero LLM tokens.
Turns thousands of log lines into ~1 KB of structured evidence."""
from __future__ import annotations
import hashlib, re
from collections import Counter

THRESHOLDS = {"cpu_pct": 90, "mem_pct": 90, "disk_pct": 95, "p99_ms": 2000,
              "err_rate": 0.05, "db_pool_util": 0.9, "restarts": 3}
MIN_ERROR_LINES = 10
_PREFIX = re.compile(r"^\S+\s+(?P<lvl>[A-Z]+)\s+(?P<svc>\S+)\s+(?P<msg>.*)$")
_SUBS = [(re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?Z?"), "<ts>"),
         (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f-]{12,}\b"), "<uuid>"),
         (re.compile(r"\breq-[0-9a-z]+\b"), "<req>"),
         (re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b"), "<ip>"),
         (re.compile(r"\b0x[0-9a-f]+\b|\b[0-9a-f]{10,}\b"), "<hex>"),
         (re.compile(r"\d+"), "<n>")]


def normalize(msg: str) -> str:
    for rx, rep in _SUBS:
        msg = rx.sub(rep, msg)
    return re.sub(r"\s+", " ", msg)[:140]


def breached_metrics(metrics: dict) -> list[dict]:
    return [{"metric": k, "value": metrics[k], "limit": lim} for k, lim in THRESHOLDS.items()
            if k in metrics and metrics[k] >= lim]


def extract_evidence(service: str, logs: list[str], metrics: dict, top_k: int = 4) -> dict:
    counts, errors, deploy = Counter(), 0, ""
    for line in logs:
        m = _PREFIX.match(line)
        if not m:
            continue
        if "deploy" in m["msg"].lower():
            deploy = normalize(m["msg"])
        if m["lvl"] in ("ERROR", "FATAL", "CRITICAL"):
            errors += 1
            counts[normalize(m["msg"])] += 1
    top = [{"t": t, "n": n} for t, n in counts.most_common(top_k)]
    breaches = breached_metrics(metrics)
    fp = hashlib.sha256((service + "|".join(t["t"] for t in top) + "|".join(b["metric"] for b in breaches)).encode()).hexdigest()[:20]
    return {"service": service, "total_lines": len(logs), "error_lines": errors, "top": top,
            "breaches": breaches, "deploy_hint": deploy, "fingerprint": fp}


def is_anomalous(ev: dict) -> bool:
    return bool(ev["breaches"]) or ev["error_lines"] >= MIN_ERROR_LINES
