# FP&A Narrative Reporting Copilot

An AI-powered prototype that ingests monthly P&L data, computes variances deterministically, and generates executive-ready narrative commentary — grounded in a local knowledge base and audited by a built-in Review Mode.

Built for FP&A analysts and finance leaders who need consistent, data-backed commentary at speed.

---

## Architecture

```
P&L Excel Files          Reference Docs
(actual/budget/forecast) (glossary + policy notes)
        │                        │
        ▼                        ▼
  src/tools.py             src/rag.py
  (Pandas variance         (ChromaDB
   engine)                  knowledge store)
        │                        │
        └──────────┬─────────────┘
                   ▼
            src/engine.py  ←── 4-stage pipeline
            ┌──────────────────────────────────┐
            │ 1. Planner   → validate inputs   │
            │ 2. Compute   → variance tables   │
            │ 3. Draft     → Claude narrative  │
            │ 4. Review    → Claude auditor    │
            └──────────────────────────────────┘
                   │
                   ▼
              app.py (Streamlit)
         ┌─────┬──────────┬────────┐
         │Tab 1│  Tab 2   │ Tab 3  │
         │Data │Narrative │ Audit  │
         └─────┴──────────┴────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| UI | Streamlit |
| Data | Pandas + openpyxl |
| Vector DB | ChromaDB (PersistentClient) |
| LLM | Anthropic SDK — `claude-sonnet-4-6` |
| Testing | pytest |
| Env | python-dotenv |

---

## Prerequisites

- Python 3.10 or higher
- An Anthropic API key ([get one here](https://console.anthropic.com))
- The source data files in the parent directory (`BIAproject/`):
  - `pnl_actual.xlsx`, `pnl_budget.xlsx`, `pnl_forecast.xlsx`
  - `finance_glossary.md`, `accounting_policy_notes.md`
  - `evaluation_prompts.xlsx`

---

## Installation

**1. Navigate to the project directory**
```bash
cd fpa_copilot
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure your API key**

Create a `.env` file inside `fpa_copilot/`:
```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

Or create it manually with the content:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

---

## Running the App

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501**.

**What each tab shows:**

| Tab | Contents |
|-----|----------|
| Calculated Insights | Variance table + top 2–3 drivers computed by Pandas (no LLM) |
| Copilot Narrative Draft | AI-generated executive commentary grounded in RAG context |
| Review Mode Audit Trail | AI auditor flags unsupported claims, asks clarifying questions |

**Usage:** Select a reporting month (2025-07 through 2025-11) and a baseline (Budget or Forecast) from the sidebar, then click **Generate Report**. Results are cached per `(month, baseline)` pair — switching tabs does not trigger extra API calls.

---

## Running Tests

```bash
pytest tests/ -v
```

The suite covers 7 cases:
- Revenue Favorable and Unfavorable variance
- Expense Favorable and Unfavorable variance (sign-convention correctness)
- Top driver list sorted by absolute INR lakhs impact
- `ValueError` raised for unknown month
- `ValueError` raised for invalid baseline string

---

## Running Evaluation

```bash
python eval.py
```

Reads the 3 prompts from `evaluation_prompts.xlsx`, runs each through the full pipeline, and scores output with an LLM-as-judge (coverage + accuracy, 1–5 each). Results saved to `eval_results.jsonl`.

---

## Generating the Presentation Deck

```bash
python generate_deck.py
```

Produces `FPA_Copilot_Presentation.pptx` (10 slides) using `Capstone PPT Template.pptx` as the base theme.

---

## File Structure

```
fpa_copilot/
├── src/
│   ├── __init__.py
│   ├── tools.py          # Pandas variance engine
│   ├── rag.py            # ChromaDB knowledge store
│   └── engine.py         # 4-stage LLM orchestration pipeline
├── tests/
│   └── test_tools.py     # 7 pytest cases for variance math
├── app.py                # Streamlit 3-tab dashboard
├── eval.py               # Evaluation framework (LLM-as-judge)
├── generate_deck.py      # PowerPoint deck generator
├── requirements.txt
├── .env                  # API key (not committed)
├── .gitignore
├── TECHNICAL_REPORT.md
└── README.md
```

---

## Sign Convention

All amounts are in **INR lakhs**. Expenses and costs are stored as **negative numbers**.

Variance formula: `variance = actual − target` (unified for all categories)

| Result | Meaning |
|--------|---------|
| Positive variance | Favorable — revenue exceeded plan, or costs came in under plan |
| Negative variance | Unfavorable — revenue missed plan, or costs exceeded plan |

---

## .gitignore

The following should not be committed:
```
.env
chroma_db/
__pycache__/
*.pyc
.pytest_cache/
eval_results.jsonl
FPA_Copilot_Presentation.pptx
```
