"""Local simulator: writes incident logs to data/logs/<service>.log (shipped to Loki by Promtail)
and exposes metrics for Prometheus on :9101. Run: python -m sim.exporter --interval 30"""
import argparse, os, time
from prometheus_client import Gauge, start_http_server
from sim.scenarios import DEMO_SEQUENCE, make_incident

G = Gauge("ops_service_metric", "Simulated service metric", ["service", "metric"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--port", type=int, default=9101)
    a = ap.parse_args()
    os.makedirs("data/logs", exist_ok=True)
    start_http_server(a.port)
    i = 0
    while True:
        inc = make_incident(DEMO_SEQUENCE[i % len(DEMO_SEQUENCE)], a.seed, i)
        with open(f"data/logs/{inc['service']}.log", "a") as f:
            f.write("\n".join(inc["logs"]) + "\n")
        for k, v in inc["metrics"].items():
            G.labels(inc["service"], k).set(v)
        print(f"[sim] {inc['id']} {inc['scenario']} on {inc['service']}", flush=True)
        i += 1
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
