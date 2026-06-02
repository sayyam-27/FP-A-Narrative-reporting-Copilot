"""Evaluation framework: runs each prompt from evaluation_prompts.xlsx through the pipeline
and scores the output with an LLM-as-judge."""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from dotenv import load_dotenv
import anthropic

from src.engine import run_pipeline

load_dotenv()

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..")
_EVAL_FILE = os.path.join(_DATA_DIR, "evaluation_prompts.xlsx")
_OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "eval_results.jsonl")

_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
_MODEL = "claude-sonnet-4-6"

_MONTH_RE = re.compile(r"\b(2025-\d{2})\b")
_BASELINE_RE = re.compile(r"\b(budget|forecast)\b", re.IGNORECASE)


def _parse_prompt(prompt: str) -> tuple[str, str]:
    """Extract month and baseline from a free-text prompt string."""
    month_match = _MONTH_RE.search(prompt)
    baseline_match = _BASELINE_RE.search(prompt)
    month = month_match.group(1) if month_match else "2025-11"
    baseline = baseline_match.group(1).lower() if baseline_match else "budget"
    return month, baseline


def _judge(prompt: str, expected_focus: str, narrative: str, review: str) -> dict:
    """Use an LLM to score whether the output covers the expected_focus without fabricating."""
    judge_prompt = f"""You are an evaluation judge for an FP&A AI assistant.

ORIGINAL PROMPT: {prompt}
EXPECTED FOCUS: {expected_focus}

GENERATED NARRATIVE:
{narrative}

REVIEW MODE OUTPUT:
{review}

Score the output on two criteria (1-5 each):
1. Coverage: Does the narrative address the expected focus areas without omitting key drivers?
2. Accuracy: Does the narrative avoid fabricating figures or unsupported claims?

Respond in this exact JSON format:
{{
  "coverage_score": <1-5>,
  "accuracy_score": <1-5>,
  "reasoning": "<one sentence>"
}}"""

    response = _client.messages.create(
        model=_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": judge_prompt}],
    )
    raw = response.content[0].text.strip()
    try:
        # Extract JSON block
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(json_match.group()) if json_match else {"raw": raw}
    except Exception:
        return {"raw": raw}


def run_eval():
    eval_df = pd.read_excel(_EVAL_FILE, sheet_name="in")
    results = []

    for _, row in eval_df.iterrows():
        eval_id = str(row["id"])
        prompt = str(row["prompt"])
        expected_focus = str(row["expected_focus"])

        print(f"  [{eval_id}] {prompt[:60]}...")
        month, baseline = _parse_prompt(prompt)

        pipeline_result = run_pipeline(month, baseline)
        scores = _judge(prompt, expected_focus, pipeline_result["narrative"], pipeline_result["review"])

        record = {
            "id":             eval_id,
            "prompt":         prompt,
            "expected_focus": expected_focus,
            "month":          month,
            "baseline":       baseline,
            "narrative":      pipeline_result["narrative"],
            "review":         pipeline_result["review"],
            "scores":         scores,
        }
        results.append(record)
        print(f"       coverage={scores.get('coverage_score','?')} accuracy={scores.get('accuracy_score','?')}")

    with open(_OUTPUT_FILE, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"\nResults saved to {_OUTPUT_FILE}")
    avg_cov = sum(r["scores"].get("coverage_score", 0) for r in results) / len(results)
    avg_acc = sum(r["scores"].get("accuracy_score", 0) for r in results) / len(results)
    print(f"Average coverage: {avg_cov:.2f}/5  |  Average accuracy: {avg_acc:.2f}/5")


if __name__ == "__main__":
    run_eval()
