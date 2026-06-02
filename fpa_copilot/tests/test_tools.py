"""Pytest suite for src/tools.py variance calculation logic."""

import os
import sys
import pytest
import pandas as pd

# Make src importable when running pytest from fpa_copilot/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_df(rows):
    """Helper: build a minimal P&L DataFrame from row dicts."""
    return pd.DataFrame(rows, columns=["month", "category", "account", "amount_inr_lakhs"])


ACTUAL_DATA = _make_df([
    {"month": "2025-09", "category": "Revenue",  "account": "Product Revenue", "amount_inr_lakhs":  500.0},
    {"month": "2025-09", "category": "COGS",     "account": "Cost of Goods Sold", "amount_inr_lakhs": -310.0},
    {"month": "2025-09", "category": "OPEX",     "account": "Sales & Marketing",  "amount_inr_lakhs": -120.0},
])

BUDGET_DATA = _make_df([
    {"month": "2025-09", "category": "Revenue",  "account": "Product Revenue",    "amount_inr_lakhs":  480.0},
    {"month": "2025-09", "category": "COGS",     "account": "Cost of Goods Sold", "amount_inr_lakhs": -290.0},
    {"month": "2025-09", "category": "OPEX",     "account": "Sales & Marketing",  "amount_inr_lakhs": -100.0},
])


@pytest.fixture(autouse=True)
def patch_loaders():
    """Patch _load() so tests never hit the real Excel files."""
    def fake_load(key):
        if key == "actual":
            return ACTUAL_DATA.copy()
        return BUDGET_DATA.copy()

    with patch("src.tools._load", side_effect=fake_load):
        yield


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_revenue_favorable():
    """Actual revenue > budget → Favorable variance."""
    from src.tools import get_variance_report
    result = get_variance_report("2025-09", "budget")
    rev_row = next(r for r in result["variance_table"].to_dict("records") if r["account"] == "Product Revenue")
    # 500 - 480 = +20
    assert abs(rev_row["variance_inr_lakhs"] - 20.0) < 0.01
    assert rev_row["direction"] == "Favorable"


def test_revenue_unfavorable():
    """Actual revenue < budget → Unfavorable variance."""
    from src.tools import get_variance_report, _load
    # Patch actual to have lower revenue
    low_actual = _make_df([
        {"month": "2025-09", "category": "Revenue", "account": "Product Revenue", "amount_inr_lakhs": 450.0},
        {"month": "2025-09", "category": "COGS",    "account": "Cost of Goods Sold", "amount_inr_lakhs": -290.0},
        {"month": "2025-09", "category": "OPEX",    "account": "Sales & Marketing",  "amount_inr_lakhs": -100.0},
    ])

    def fake_load_low(key):
        return low_actual.copy() if key == "actual" else BUDGET_DATA.copy()

    with patch("src.tools._load", side_effect=fake_load_low):
        result = get_variance_report("2025-09", "budget")
    rev_row = next(r for r in result["variance_table"].to_dict("records") if r["account"] == "Product Revenue")
    # 450 - 480 = -30
    assert abs(rev_row["variance_inr_lakhs"] - (-30.0)) < 0.01
    assert rev_row["direction"] == "Unfavorable"


def test_expense_favorable():
    """Actual spend less than budget (less negative) → Favorable."""
    from src.tools import get_variance_report
    # Use patched data where S&M actual (-80) < budget (-100) → underspend
    low_sm_actual = _make_df([
        {"month": "2025-09", "category": "Revenue", "account": "Product Revenue",    "amount_inr_lakhs":  480.0},
        {"month": "2025-09", "category": "COGS",    "account": "Cost of Goods Sold", "amount_inr_lakhs": -290.0},
        {"month": "2025-09", "category": "OPEX",    "account": "Sales & Marketing",  "amount_inr_lakhs":  -80.0},
    ])

    def fake_load_low_sm(key):
        return low_sm_actual.copy() if key == "actual" else BUDGET_DATA.copy()

    with patch("src.tools._load", side_effect=fake_load_low_sm):
        result = get_variance_report("2025-09", "budget")
    sm_row = next(r for r in result["variance_table"].to_dict("records") if r["account"] == "Sales & Marketing")
    # actual - target = -80 - (-100) = +20 → Favorable (underspent)
    assert abs(sm_row["variance_inr_lakhs"] - 20.0) < 0.01
    assert sm_row["direction"] == "Favorable"


def test_expense_unfavorable():
    """Actual spend more than budget (more negative) → Unfavorable."""
    from src.tools import get_variance_report
    result = get_variance_report("2025-09", "budget")
    sm_row = next(r for r in result["variance_table"].to_dict("records") if r["account"] == "Sales & Marketing")
    # actual - target = -120 - (-100) = -20 → Unfavorable (overspent)
    assert abs(sm_row["variance_inr_lakhs"] - (-20.0)) < 0.01
    assert sm_row["direction"] == "Unfavorable"


def test_top_drivers_sorted_by_absolute_magnitude():
    """Top drivers list must be sorted largest absolute variance first."""
    from src.tools import get_variance_report
    result = get_variance_report("2025-09", "budget")
    drivers = result["top_drivers"]
    variances = [abs(d["variance_inr_lakhs"]) for d in drivers]
    assert variances == sorted(variances, reverse=True)


def test_unknown_month_raises():
    """Requesting a month not in the data raises ValueError."""
    from src.tools import get_variance_report
    with pytest.raises(ValueError, match="not found"):
        get_variance_report("2099-01", "budget")


def test_invalid_baseline_raises():
    """Requesting an invalid baseline raises ValueError."""
    from src.tools import get_variance_report
    with pytest.raises(ValueError, match="baseline must be"):
        get_variance_report("2025-09", "actuals")
