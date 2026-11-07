"""Live data sources (local Docker stack): Loki for logs, Prometheus for metrics. Free + local."""
from __future__ import annotations
import time, requests
from .config import Settings


def fetch_loki(s: Settings, service: str, minutes: int = 15, limit: int = 500) -> list[str]:
    end = int(time.time() * 1e9)
    r = requests.get(f"{s.loki_url}/loki/api/v1/query_range", timeout=10, params={
        "query": f'{{filename=~".*/{service}.log"}}', "start": end - minutes * 60 * 10**9,
        "end": end, "limit": limit, "direction": "forward"})
    r.raise_for_status()
    return [v[1] for st in r.json()["data"]["result"] for v in st["values"]]


def fetch_prometheus(s: Settings, service: str) -> dict:
    r = requests.get(f"{s.prometheus_url}/api/v1/query", timeout=10,
                     params={"query": f'ops_service_metric{{service="{service}"}}'})
    r.raise_for_status()
    return {x["metric"]["metric"]: float(x["value"][1]) for x in r.json()["data"]["result"]}
