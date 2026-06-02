"""FP&A Narrative Reporting Copilot — Streamlit dashboard."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
from src.engine import run_pipeline
from src.tools import _load

st.set_page_config(
    page_title="FP&A Narrative Copilot",
    page_icon="📊",
    layout="wide",
)

st.title("FP&A Narrative Reporting Copilot")
st.caption("Variance analysis · Executive narrative · Review mode audit")

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Report Parameters")

    actual_df = _load("actual")
    available_months = sorted(actual_df["month"].astype(str).unique().tolist())

    month = st.selectbox("Reporting Month", available_months, index=len(available_months) - 1)
    baseline = st.radio("Comparison Baseline", ["Budget", "Forecast"])

    run_btn = st.button("Generate Report", type="primary", use_container_width=True)

# ── Session state cache ───────────────────────────────────────────────────────
cache_key = (month, baseline.lower())

if run_btn:
    with st.spinner("Running pipeline… this may take 15–30 seconds."):
        result = run_pipeline(month, baseline.lower())
    st.session_state["result"] = result
    st.session_state["cache_key"] = cache_key

result = st.session_state.get("result") if st.session_state.get("cache_key") == cache_key else None

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Calculated Insights", "Copilot Narrative Draft", "Review Mode Audit Trail"])

with tab1:
    st.subheader(f"Variance: {month} Actual vs {baseline}")
    if result is None:
        st.info("Select parameters and click **Generate Report** to see results.")
    elif result.get("variance_table") is None:
        st.error(result.get("narrative", "Unknown error."))
    else:
        vt: pd.DataFrame = result["variance_table"]

        # Summary metrics
        total_variance = vt["variance_inr_lakhs"].sum()
        fav_count = (vt["direction"] == "Favorable").sum()
        unfav_count = (vt["direction"] == "Unfavorable").sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Net Variance (INR Lakhs)", f"{total_variance:+.2f}")
        c2.metric("Favorable Lines", fav_count)
        c3.metric("Unfavorable Lines", unfav_count)

        st.markdown("#### Top Variance Drivers")
        for d in result["top_drivers"]:
            pct = f"{d['variance_pct']:.1f}%" if d["variance_pct"] is not None else "N/A"
            color = "green" if d["direction"] == "Favorable" else "red"
            st.markdown(
                f"**{d['account']}** ({d['category']}) — "
                f":{color}[{d['direction']} {d['variance_inr_lakhs']:+.2f} INR lakhs ({pct})]"
            )

        st.markdown("#### Full Variance Table")
        display_df = vt[["category", "account", "actual", "target", "variance_inr_lakhs", "variance_pct", "direction"]].copy()
        display_df.columns = ["Category", "Account", "Actual", "Target", "Variance (INR L)", "Variance %", "Direction"]
        display_df["Variance %"] = display_df["Variance %"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Executive Commentary")
    if result is None:
        st.info("Run a report to see the AI-generated narrative.")
    else:
        st.markdown(result["narrative"])

with tab3:
    st.subheader("Review Mode — Audit Trail")
    if result is None:
        st.info("Run a report to see the audit output.")
    else:
        st.markdown(result["review"])
