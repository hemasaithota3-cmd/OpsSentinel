"""Streamlit dashboard: usage/cost ledger + the memory learning curve. Run: streamlit run dashboard/app.py"""
import pandas as pd, streamlit as st
from opssentinel.config import get_settings
from opssentinel.db import DB
from opssentinel.usage import Usage

s = get_settings(); db = DB(s.database_url); u = Usage(db, s).summary()
st.set_page_config(page_title="OpsSentinel", layout="wide")
st.title("OpsSentinel: incident agent with Hindsight memory")
st.caption(f"mode={s.mode} | llm={s.llm_provider} | bank={s.bank_id}")

t1, t2, t3 = st.tabs(["Learning curve", "Usage & cost", "Incidents"])
inc = pd.DataFrame(db.query("SELECT id,ts,service,cause_id,source,confidence,memory_hits,llm_calls,llm_tokens,"
                            "cause_ok,fix_specific,retained,resolution FROM incidents ORDER BY ts, id"))
with t1:
    if inc.empty:
        st.info("Run `python -m opssentinel.cli demo` first.")
    else:
        inc["n"] = range(1, len(inc) + 1)
        inc["team_fix_found"] = inc["fix_specific"].fillna(0).astype(float).expanding().mean()
        c1, c2 = st.columns(2)
        c1.subheader("Team-specific fix found (running rate)"); c1.line_chart(inc.set_index("n")["team_fix_found"])
        c2.subheader("LLM tokens per incident"); c2.bar_chart(inc.set_index("n")["llm_tokens"])
        st.subheader("Diagnosis source"); st.bar_chart(inc["source"].value_counts())
        st.subheader("Latest Hindsight reflect"); st.write(db.kv_get("last_reflect", "(none yet)"))
with t2:
    a, b, c, d = st.columns(4)
    a.metric("LLM requests", u["llm_requests"]); b.metric("Tokens (in/out)", f"{u['tokens_in']}/{u['tokens_out']}")
    c.metric("Est. API cost (USD)", u["est_cost_usd"]); d.metric("Errors", u["errors"])
    e, f, g, h = st.columns(4)
    e.metric("Hindsight retain", u["hindsight_retain"]); f.metric("Hindsight recall", u["hindsight_recall"])
    g.metric("Hindsight reflect", u["hindsight_reflect"]); h.metric("Recalls saved (cache/dedup)", u["recall_dedup_saved"])
    st.progress(min(1.0, u["tokens_today"] / max(1, u["daily_token_cap"])),
                text=f"Daily LLM token budget: {u['tokens_today']}/{u['daily_token_cap']}")
    st.write({"llm_cache_hits": u["llm_cache_hits"], "budget_blocks": u["budget_blocks"]})
    st.dataframe(pd.DataFrame(db.query("SELECT ts,kind,provider,tokens_in,tokens_out,ok,detail FROM usage_events "
                                       "ORDER BY id DESC LIMIT 100")))
with t3:
    st.dataframe(inc)
