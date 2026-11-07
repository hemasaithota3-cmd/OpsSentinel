"""Exposes the usage ledger to Prometheus (:9102) so Grafana can chart LLM/Hindsight spend."""
import time
from prometheus_client import Gauge, start_http_server

G = Gauge("opssentinel_usage", "OpsSentinel usage ledger", ["name"])


def serve(ctx, port=9102):
    start_http_server(port)
    print(f"usage metrics on :{port}")
    while True:
        for k, v in ctx.usage.summary().items():
            G.labels(k).set(v)
        time.sleep(5)
