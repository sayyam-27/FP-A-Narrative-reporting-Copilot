"""Deterministic Pandas engine for financial variance calculations."""

import os
import pandas as pd

# Resolve data directory relative to this file (../.. from src/tools.py → BIAproject/)
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..")

_FILES = {
    "actual":   os.path.join(_DATA_DIR, "pnl_actual.xlsx"),
    "budget":   os.path.join(_DATA_DIR, "pnl_budget.xlsx"),
    "forecast": os.path.join(_DATA_DIR, "pnl_forecast.xlsx"),
}

_BASELINE_MAP = {
    "budget":   "budget",
    "forecast": "forecast",
}


def _load(key: str) -> pd.DataFrame:
    return pd.read_excel(_FILES[key], sheet_name="in")


def _label(variance: float, category: str) -> str:
    """Positive variance = Favorable for all categories (unified actual - target formula)."""
    return "Favorable" if variance >= 0 else "Unfavorable"


def get_variance_report(month: str, baseline: str) -> dict:
    """
    Calculate account-level variances for *month* vs *baseline* (budget|forecast).

    Returns:
        {
            "month": str,
            "baseline": str,
            "variance_table": pd.DataFrame,   # account-level detail
            "top_drivers": list[dict],         # top 2-3 by absolute INR lakhs impact
        }
    Raises ValueError for unknown month or baseline.
    """
    baseline = baseline.lower().strip()
    if baseline not in _BASELINE_MAP:
        raise ValueError(f"baseline must be 'budget' or 'forecast', got '{baseline}'")

    actual_df   = _load("actual")
    baseline_df = _load(_BASELINE_MAP[baseline])

    # Filter to requested month
    actual_m   = actual_df[actual_df["month"].astype(str) == month]
    baseline_m = baseline_df[baseline_df["month"].astype(str) == month]

    if actual_m.empty:
        raise ValueError(f"Month '{month}' not found in actuals. Available: {sorted(actual_df['month'].astype(str).unique().tolist())}")
    if baseline_m.empty:
        raise ValueError(f"Month '{month}' not found in {baseline}. Available: {sorted(baseline_df['month'].astype(str).unique().tolist())}")

    merged = pd.merge(
        actual_m[["category", "account", "amount_inr_lakhs"]].rename(columns={"amount_inr_lakhs": "actual"}),
        baseline_m[["account", "amount_inr_lakhs"]].rename(columns={"amount_inr_lakhs": "target"}),
        on="account",
        how="outer",
    ).fillna(0)

    # Unified formula: actual - target for all categories.
    # Positive variance → Favorable (more revenue OR less cost than plan).
    # Negative variance → Unfavorable (less revenue OR more cost than plan).
    # This correctly handles negative expense amounts: e.g. actual -150 vs budget -100
    # gives -150 - (-100) = -50 (Unfavorable overspend), matching the spec's example.
    merged["variance_inr_lakhs"] = merged["actual"] - merged["target"]

    # Percentage variance relative to absolute target (avoid div-by-zero)
    merged["variance_pct"] = merged.apply(
        lambda r: (r["variance_inr_lakhs"] / abs(r["target"]) * 100) if r["target"] != 0 else None,
        axis=1,
    )

    merged["direction"] = merged.apply(lambda r: _label(r["variance_inr_lakhs"], r["category"]), axis=1)

    # Top drivers by absolute INR lakhs impact
    top_drivers = (
        merged.reindex(merged["variance_inr_lakhs"].abs().sort_values(ascending=False).index)
        .head(3)[["account", "category", "actual", "target", "variance_inr_lakhs", "variance_pct", "direction"]]
        .to_dict(orient="records")
    )

    return {
        "month":          month,
        "baseline":       baseline,
        "variance_table": merged,
        "top_drivers":    top_drivers,
    }
