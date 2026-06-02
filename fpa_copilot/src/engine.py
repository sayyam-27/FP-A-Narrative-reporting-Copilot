"""4-stage FP&A narrative pipeline: Planner → Compute → Draft → Review."""

import os
from dotenv import load_dotenv
import anthropic

from .tools import get_variance_report
from .rag import query_kb

load_dotenv()

_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
_MODEL = "claude-sonnet-4-6"


def _llm(system: str, user: str) -> str:
    response = _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text.strip()


def _format_drivers(top_drivers: list[dict]) -> str:
    lines = []
    for d in top_drivers:
        pct = f"{d['variance_pct']:.1f}%" if d["variance_pct"] is not None else "N/A"
        lines.append(
            f"- {d['account']} ({d['category']}): Actual {d['actual']:.2f} vs Target {d['target']:.2f} | "
            f"Variance {d['variance_inr_lakhs']:+.2f} INR lakhs ({pct}) — {d['direction']}"
        )
    return "\n".join(lines)


def run_pipeline(month: str, baseline: str) -> dict:
    """
    Execute the 4-stage pipeline and return a results dict with keys:
      variance_table, top_drivers, narrative, review
    """

    # ── Stage 1: Planner ──────────────────────────────────────────────────────
    baseline = baseline.lower().strip()
    available_baselines = ["budget", "forecast"]
    if baseline not in available_baselines:
        return {
            "month": month,
            "baseline": baseline,
            "variance_table": None,
            "top_drivers": [],
            "narrative": f"Error: baseline must be one of {available_baselines}.",
            "review": "",
        }

    # ── Stage 2: Compute ──────────────────────────────────────────────────────
    try:
        report = get_variance_report(month, baseline)
    except ValueError as e:
        return {
            "month": month,
            "baseline": baseline,
            "variance_table": None,
            "top_drivers": [],
            "narrative": f"Data Insufficient — {e}",
            "review": "No data available for the requested period.",
        }

    drivers_text = _format_drivers(report["top_drivers"])
    variance_table = report["variance_table"]

    # ── Stage 3: Draft ────────────────────────────────────────────────────────
    style_context = query_kb("narrative style rules executive summary variance driver")

    draft_system = (
        "You are an FP&A analyst writing a concise executive commentary for senior leadership. "
        "Follow the style rules and definitions below exactly.\n\n"
        f"KNOWLEDGE BASE CONTEXT:\n{style_context}"
    )

    draft_user = f"""Write an executive commentary for {month} (Actual vs {baseline.capitalize()}).

TOP VARIANCE DRIVERS:
{drivers_text}

Rules:
- State the month and comparison baseline in the opening sentence.
- Quantify each driver explicitly with INR lakhs and % variance.
- Cover top 2–3 drivers only.
- Label each driver as Favorable or Unfavorable.
- Do NOT invent drivers or figures not present in the data above.
- Use professional, concise language suitable for a CFO audience.
- Output formatted Markdown."""

    narrative = _llm(draft_system, draft_user)

    # ── Stage 4: Review ───────────────────────────────────────────────────────
    review_system = (
        "You are a strict financial audit reviewer. Your job is to identify weaknesses in the "
        "narrative draft below. Flag any unsupported assumptions, invented market claims, "
        "missing quantification, or vague language. If a claim cannot be traced back to the "
        "provided data, mark it 'Data Insufficient'. Output a 'Review Mode Output' section "
        "with bullet-pointed risks and clarifying questions."
    )

    review_user = f"""NARRATIVE DRAFT:
{narrative}

VERIFIED DATA (top drivers only, do not accept claims beyond this):
{drivers_text}

Audit the narrative and produce a 'Review Mode Output' section listing:
1. Any unsupported assumptions or invented drivers.
2. Any figures that cannot be verified from the data above.
3. Clarifying questions the analyst should answer before publishing.
If the narrative is fully grounded, state "No issues found." """

    review = _llm(review_system, review_user)

    return {
        "month":          month,
        "baseline":       baseline,
        "variance_table": variance_table,
        "top_drivers":    report["top_drivers"],
        "narrative":      narrative,
        "review":         review,
    }
