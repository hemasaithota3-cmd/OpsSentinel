"""Central settings. Three modes keep spending predictable:
  dev  : real Hindsight + real LLM, but under hard budgets
  demo : real Hindsight, LLM is REPLAY-ONLY (cache fixtures) unless OPS_DEMO_LIVE=1
  test : in-process fakes + sqlite, zero network, zero cost
"""
from __future__ import annotations
import os
from dataclasses import dataclass, replace
from dotenv import load_dotenv

load_dotenv()
MODES = ("dev", "test", "demo")


def _i(k, d): return int(os.getenv(k, str(d)) or d)
def _f(k, d): return float(os.getenv(k, str(d)) or d)
def _b(k, d=False): return os.getenv(k, "1" if d else "0").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    mode: str
    database_url: str
    hindsight_url: str
    hindsight_api_key: str
    bank_id: str
    llm_provider: str
    llm_model: str
    llm_base_url: str
    llm_api_key: str
    allow_paid: bool
    max_calls_per_incident: int
    max_calls_per_session: int
    max_output_tokens: int
    max_tokens_per_day: int
    max_retries: int
    max_graph_iterations: int
    max_reflects_per_session: int
    recall_max_tokens: int
    quota_cooldown_s: int
    price_in_per_m: float
    price_out_per_m: float
    loki_url: str
    prometheus_url: str


def get_settings(mode: str | None = None, **overrides) -> Settings:
    mode = mode or os.getenv("OPS_MODE", "dev")
    if mode not in MODES:
        raise ValueError(f"OPS_MODE must be one of {MODES}")
    env_provider = os.getenv("LLM_PROVIDER", "groq")
    provider = {"dev": env_provider, "test": "offline",
                "demo": env_provider if _b("OPS_DEMO_LIVE") else "replay"}[mode]
    db = "sqlite:///:memory:" if mode == "test" else os.getenv(
        "DATABASE_URL", "postgresql://ops:ops@localhost:5432/opssentinel")
    s = Settings(
        mode=mode, database_url=db,
        hindsight_url=os.getenv("HINDSIGHT_URL", "http://localhost:8888"),
        hindsight_api_key=os.getenv("HINDSIGHT_API_KEY", ""),
        bank_id=os.getenv("HINDSIGHT_BANK", "opssentinel") + ("" if mode != "test" else "-test"),
        llm_provider=provider,
        llm_model=os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        allow_paid=_b("ALLOW_PAID_PROVIDER"),
        max_calls_per_incident=_i("MAX_LLM_CALLS_PER_INCIDENT", 2),
        max_calls_per_session=_i("MAX_LLM_CALLS_PER_SESSION", 30),
        max_output_tokens=_i("MAX_OUTPUT_TOKENS", 400),
        max_tokens_per_day=_i("MAX_LLM_TOKENS_PER_DAY", 40000),
        max_retries=_i("MAX_LLM_RETRIES", 1),
        max_graph_iterations=_i("MAX_GRAPH_ITERATIONS", 3),
        max_reflects_per_session=_i("MAX_REFLECTS_PER_SESSION", 1),
        recall_max_tokens=_i("RECALL_MAX_TOKENS", 800),
        quota_cooldown_s=_i("QUOTA_COOLDOWN_S", 300),
        price_in_per_m=_f("PRICE_IN_PER_M", 0.15),
        price_out_per_m=_f("PRICE_OUT_PER_M", 0.60),
        loki_url=os.getenv("LOKI_URL", "http://localhost:3100"),
        prometheus_url=os.getenv("PROMETHEUS_URL", "http://localhost:9090"),
    )
    return replace(s, **overrides) if overrides else s
