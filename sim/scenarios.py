"""Seeded, realistic-looking incident generator (no cloud, no cost). Same seed => same data."""
from __future__ import annotations
import random
from datetime import datetime, timedelta

BASE = {"cpu_pct": (30, 55), "mem_pct": (45, 65), "disk_pct": (40, 60), "p99_ms": (120, 400),
        "err_rate": (0.0, 0.02), "db_pool_util": (0.2, 0.5), "restarts": (0, 0)}

SCENARIOS = {
    "db_pool_exhausted": {
        "services": ["payments-api", "orders-api", "billing-api"],
        "metrics": {"db_pool_util": (0.96, 1.0), "p99_ms": (3000, 6000), "err_rate": (0.08, 0.2)},
        "errors": ["QueuePool limit of size {a} overflow {b} reached, connection timed out, timeout {t}.00",
                   "FATAL: remaining connection slots are reserved for non-replication superuser connections",
                   "POST /v1/charge failed: could not acquire database connection in {t}s"],
        "fix": "Raised DB_POOL_SIZE from 10 to 40 and restarted {svc}; killed the long-running analytics report query holding connections.",
        "fix_kw": ["pool_size", "40"]},
    "memory_leak_oom": {
        "services": ["search-api", "catalog-api", "recs-api"],
        "metrics": {"mem_pct": (96, 99.5), "restarts": (4, 9), "p99_ms": (1500, 4000), "err_rate": (0.05, 0.15)},
        "errors": ["java.lang.OutOfMemoryError: Java heap space",
                   "Container killed: OOMKilled exit code 137",
                   "GC overhead limit exceeded after {t} ms"],
        "fix": "Rolled back {svc} to v2.14.1 (leak in session cache added in v2.14.2) and set -Xmx2g as a stopgap.",
        "fix_kw": ["v2.14.1", "xmx2g"]},
    "bad_deploy_regression": {
        "services": ["checkout-api", "cart-api", "promo-api"],
        "metrics": {"err_rate": (0.25, 0.6), "p99_ms": (800, 2500)},
        "errors": ["Unhandled exception NullPointerException at CheckoutController.applyCoupon line {a}",
                   "HTTP 500 on POST /v1/checkout after deploy version 3.8.0"],
        "deploy": "deploy completed version 3.8.0 by ci-bot",
        "fix": "Rolled back {svc} to v3.7.4 and disabled feature flag coupon_v2.",
        "fix_kw": ["coupon_v2", "v3.7.4"]},
    "disk_full": {
        "services": ["ingest-worker", "audit-svc", "report-svc"],
        "metrics": {"disk_pct": (97, 99.9), "err_rate": (0.05, 0.12)},
        "errors": ["OSError: [Errno 28] No space left on device: '/var/log/app/{svc}.log'",
                   "Failed to write checkpoint: no space left on device"],
        "fix": "Purged rotated logs under /var/log/app and enabled compress in the logrotate config; added an 85% disk alert.",
        "fix_kw": ["logrotate", "compress"]},
    "dns_resolution_failure": {
        "services": ["gateway-api", "pricing-api", "cart-api"],
        "metrics": {"p99_ms": (2500, 7000), "err_rate": (0.1, 0.3)},
        "errors": ["Temporary failure in name resolution while calling inventory-svc",
                   "getaddrinfo ENOTFOUND inventory-svc.internal",
                   "upstream inventory-svc timed out after {t}ms"],
        "fix": "Restarted the coredns pods and set ndots to 2 in the {svc} deployment dnsConfig.",
        "fix_kw": ["coredns", "ndots"]},
}

_INFO = ["GET /health 200 {ms}ms req-{h}", "GET /v1/items 200 {ms}ms req-{h}", "cache hit ratio {ms}%",
         "POST /v1/session 201 {ms}ms req-{h}"]
_DECOY = "rate limiter rejected request from 10.{a}.{b}.{t}"


def make_incident(scenario: str, seed: int = 7, idx: int = 0, n_lines: int = 240) -> dict:
    sc = SCENARIOS[scenario]
    rnd = random.Random(f"{scenario}-{seed}-{idx}")
    svc = rnd.choice(sc["services"])
    t0 = datetime(2026, 11, 7, 9, 0, 0) + timedelta(minutes=idx * 17)
    fill = lambda m: m.format(a=rnd.randint(5, 250), b=rnd.randint(1, 250), t=rnd.randint(5, 60),
                              ms=rnd.randint(8, 90), h=f"{rnd.getrandbits(32):08x}", svc=svc)
    lines = []
    if sc.get("deploy"):
        lines.append(f"{t0.isoformat()}Z INFO {svc} {sc['deploy']}")
    for i in range(n_lines):
        ts = (t0 + timedelta(seconds=i * 2 + 1)).isoformat() + "Z"
        r = rnd.random()
        if r < 0.38:
            lines.append(f"{ts} ERROR {svc} {fill(rnd.choice(sc['errors']))}")
        elif r < 0.41:
            lines.append(f"{ts} ERROR {svc} {fill(_DECOY)}")
        else:
            lines.append(f"{ts} INFO {svc} {fill(rnd.choice(_INFO))}")
    metrics = {k: round(rnd.uniform(*sc["metrics"].get(k, v)), 3) for k, v in BASE.items()}
    return {"id": f"INC-{seed}-{idx:03d}", "scenario": scenario, "service": svc, "logs": lines,
            "metrics": metrics, "ts": t0.isoformat() + "Z",
            "expected_fix": sc["fix"].format(svc=svc), "fix_kw": sc["fix_kw"], "mttr_min": rnd.randint(18, 55)}


DEMO_SEQUENCE = ["db_pool_exhausted", "memory_leak_oom", "db_pool_exhausted", "bad_deploy_regression",
                 "disk_full", "db_pool_exhausted", "dns_resolution_failure", "memory_leak_oom",
                 "bad_deploy_regression", "db_pool_exhausted", "disk_full", "dns_resolution_failure"]
