# Technical Report: FP&A Narrative Reporting Copilot

**Version:** 1.0  
**Date:** May 2026  
**Stack:** Python · Streamlit · ChromaDB · Anthropic Claude (claude-sonnet-4-6)

---

## 1. Executive Summary

This project delivers a working prototype of an AI-powered FP&A narrative reporting assistant. Given monthly P&L data in Excel format, the system computes account-level variances deterministically using Pandas, retrieves relevant financial definitions and style guidance from a local vector database, and uses Claude to draft concise executive commentary — then audits that commentary using a second LLM pass to flag unsupported claims.

The core design philosophy is **separation of concerns between probabilistic and deterministic reasoning**: numbers are never produced by the LLM. Every figure in the output is computed by Python code and can be verified against the source data. The LLM's role is strictly language production and audit — two tasks where it adds irreplaceable value.

The result is a three-tab Streamlit dashboard that an FP&A analyst can use to generate, review, and publish executive-quality variance commentary in under 30 seconds.

---

## 2. Architecture

### 2.1 WAT Framework

The system is structured using the **WAT (Workflows, Agents, Tools)** pattern:

| Layer | Component | Role |
|-------|-----------|------|
| **Workflows** | `MasterPromt.md` | The SOP defining the objective, inputs, stages, and constraints |
| **Agents** | `src/engine.py` | Orchestrates the 4-stage pipeline; makes LLM decisions |
| **Tools** | `src/tools.py`, `src/rag.py` | Deterministic execution: math and retrieval |

This separation is why the system is reliable. When AI tries to handle every step (including arithmetic), compounding errors reduce accuracy quickly. By delegating math to `tools.py` and retrieval to `rag.py`, the LLM only handles what it genuinely does well: language.

### 2.2 Data Flow

```
pnl_actual.xlsx  ──┐
pnl_budget.xlsx  ──┤──► src/tools.py ──► variance_table + top_drivers
pnl_forecast.xlsx ─┘         │
                              │
finance_glossary.md  ─┐       │
accounting_policy.md ─┤──► src/rag.py ──► style_context (retrieved passages)
                       │       │
                       └───────┘
                               │
                               ▼
                       src/engine.py
                    ┌──────────────────────┐
                    │ Stage 1: Planner     │  validate month + baseline
                    │ Stage 2: Compute     │  call tools.get_variance_report()
                    │ Stage 3: Draft       │  RAG query → LLM narrative
                    │ Stage 4: Review      │  LLM auditor → flagged risks
                    └──────────────────────┘
                               │
                               ▼
                           app.py
                   ┌──────┬────────┬───────┐
                   │ Tab 1│ Tab 2  │ Tab 3 │
                   │ Data │Narrative│ Audit │
                   └──────┴────────┴───────┘
```

---

## 3. Component Deep-Dive

### 3.1 Calculation Engine — `src/tools.py`

The calculation engine is the system's single source of numerical truth. It loads P&L files using:

```python
pd.read_excel(filepath, sheet_name='in')
```

**Sign convention** (from `accounting_policy_notes.md`): cost and expense items are stored as negative numbers. Revenue items are positive. The unified variance formula is:

```
variance = actual − target
```

| Scenario | Example | Result | Label |
|----------|---------|--------|-------|
| Revenue beats plan | 500 vs 480 | +20 | Favorable |
| Revenue misses plan | 450 vs 480 | −30 | Unfavorable |
| Expenses under plan | −80 vs −100 | +20 | Favorable |
| Expenses over plan | −120 vs −100 | −20 | Unfavorable |

This unified formula avoids the common trap of applying `target − actual` for costs (which produces the wrong sign when amounts are already negative). The formula's sign directly encodes favorability for all account categories.

Top drivers are sorted by `abs(variance_inr_lakhs)` and limited to the top 3.

### 3.2 Knowledge Store — `src/rag.py`

The RAG layer indexes `finance_glossary.md` and `accounting_policy_notes.md` into a persistent ChromaDB collection:

```python
chromadb.PersistentClient(path="./chroma_db")
```

On first run the documents are chunked (word-level, ~300 words per chunk with 50% overlap) and embedded using ChromaDB's default embedding function. On subsequent runs the existing collection is reused (`list_collections()` check), avoiding redundant re-indexing.

The `query_kb(query)` function returns the top 4 most relevant passages for a given query string. In practice the Draft stage queries with: `"narrative style rules executive summary variance driver"`.

### 3.3 Orchestration Pipeline — `src/engine.py`

`run_pipeline(month, baseline)` executes four sequential stages:

**Stage 1 — Planner:** Validates that `baseline` is `"budget"` or `"forecast"`. Returns a structured error if not.

**Stage 2 — Compute:** Calls `tools.get_variance_report()`. If the month is absent from the data, returns a `"Data Insufficient"` response without calling the LLM — preserving API credits and giving a clean user-facing message.

**Stage 3 — Draft:** Queries the knowledge base for style context, then constructs a two-part prompt (system + user) instructing Claude to write a CFO-audience executive commentary with explicit quantification rules.

**Stage 4 — Review:** Passes the draft and the verified driver data to a second Claude call with a strict auditor persona. The auditor outputs a structured `Review Mode Output` section listing risks and clarifying questions. If the narrative is clean, it outputs `"No issues found."`.

Results are returned as a dict and cached in `st.session_state` to avoid repeat API calls.

### 3.4 Dashboard — `app.py`

The Streamlit app uses three tabs populated from the cached pipeline result:

- **Tab 1** renders the Pandas-computed variance table and summary metrics (net variance, favorable/unfavorable line counts)
- **Tab 2** renders the LLM narrative as formatted Markdown
- **Tab 3** renders the Review Mode audit output

A key design decision: results are stored in `st.session_state` keyed by `(month, baseline)`. Streamlit re-runs the entire script on every interaction — without session state caching, every tab click would trigger a fresh API call at ~$0.003 per run.

### 3.5 Evaluation Framework — `eval.py`

The evaluation script reads `evaluation_prompts.xlsx` (3 rows), extracts the month and baseline from each free-text prompt with regex, runs the full pipeline, and scores the output using an LLM-as-judge prompt with two dimensions:

- **Coverage (1–5):** Does the narrative mention the drivers called out in `expected_focus`?
- **Accuracy (1–5):** Does the narrative avoid inventing figures not present in the verified data?

Scores and reasoning are saved to `eval_results.jsonl`.

---

## 4. Prompting Strategy

### 4.1 Draft Prompt

The Draft stage uses a two-message structure:

**System message (role):**
> "You are an FP&A analyst writing a concise executive commentary for senior leadership. Follow the style rules and definitions below exactly."

The system message includes the RAG-retrieved passages from the knowledge base so style guidance is baked into the model's framing before the task begins.

**User message (task):**
Provides the computed top-driver data in structured text, followed by explicit rules:
- State month and baseline in the opening sentence
- Quantify every driver in INR lakhs and %
- Cover top 2–3 drivers only
- Label each as Favorable or Unfavorable
- Do not invent drivers not in the provided data

The explicit rule list is the critical guardrail. Without it, LLMs reliably add plausible-but-invented context (e.g., "driven by increased market competition") that cannot be verified.

### 4.2 Review Prompt

The Review stage uses a separate LLM call with a different persona:

**System message:**
> "You are a strict financial audit reviewer. Flag unsupported assumptions, invented market claims, missing quantification, or vague language. If a claim cannot be traced back to the provided data, mark it 'Data Insufficient'."

**User message:**
Passes the draft narrative alongside the verified driver data as ground truth. The auditor is explicitly told: "do not accept claims beyond this."

### 4.3 Why Two Separate Calls

A single prompt asking Claude to both write and critique produces weaker results — the draft persona biases the review toward leniency. Separating into two calls with distinct personas creates genuine adversarial tension: the drafter optimizes for quality and completeness; the reviewer optimizes for skepticism. This is the "Constitutional AI" pattern applied at the application layer.

---

## 5. Evaluation Framework & Results

### 5.1 Test Prompts

| ID | Prompt Summary | Expected Focus |
|----|---------------|----------------|
| E01 | Nov 2025 vs Budget | S&M overspend; revenue recovery; 2–3 drivers |
| E02 | Sep 2025 vs Forecast | Product Revenue dip; COGS pressure |
| E03 | Oct 2025 management summary | Cautious language; no unsupported market claims |

### 5.2 Scoring Methodology

The LLM-as-judge receives the full output (narrative + review) and scores on:

- **Coverage:** Did the narrative capture the drivers specified in `expected_focus`?
- **Accuracy:** Were all cited figures verifiable from the source data?

Each dimension scored 1–5. A combined score of ≥8/10 is considered passing for production use.

### 5.3 Known Evaluation Limitation

The judge uses the same model (`claude-sonnet-4-6`) as the system under evaluation. This introduces **self-evaluation bias** — the model may rate its own outputs more favorably than an independent reviewer would. A production-grade evaluation would use a separate, smaller model (e.g., `claude-haiku-4-5`) as judge to reduce this correlation.

---

## 6. Limitations

| Limitation | Impact | Mitigation Path |
|-----------|--------|-----------------|
| Synthetic data only | Cannot validate against real P&L edge cases (multi-currency, restatements, etc.) | Test with anonymised real data before production use |
| Self-evaluation bias in judge | Evaluation scores may be inflated | Use a separate model as judge |
| No multi-month trend analysis | Cannot explain "2-month deterioration in COGS" automatically | Add a `get_trend_report()` function in `tools.py` |
| No user authentication | Anyone with the URL can access the app | Add Streamlit authentication or deploy behind a VPN |
| Small RAG corpus | Only 2 short documents indexed | Add industry-specific dictionaries, prior narratives as examples |

---

## 7. Future Improvements

1. **Multi-month trending** — Surface MoM and YTD trend charts in Tab 1 using Streamlit's `st.line_chart`
2. **Export to Word/PDF** — Allow one-click export of the Tab 2 narrative for distribution
3. **Independent evaluation judge** — Replace self-scoring with `claude-haiku-4-5` to reduce bias
4. **CI/CD pipeline** — Add GitHub Actions workflow running `pytest tests/` on every push to `main`
5. **Prompt versioning** — Store prompt templates as versioned files so A/B testing and rollback are straightforward
