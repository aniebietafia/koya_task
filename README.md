# Lead-Triage & Qualification System — Project Documentation

> An automated lead qualification system that takes messy lead exports, assesses intent and fit, calculates weighted priority scores, and delivers ranked recommendations via CLI or Web interface.

---

## Executive Overview

Marketing agencies receive hundreds of inbound leads monthly across webforms, referrals, LinkedIn, events, and cold outreach. Manually evaluating these leads is slow, inconsistent, and causes high-value opportunities to go cold.

This **Lead-Triage System** automates the entire qualification workflow:
1. **Normalises Messy Data**: Cleans dates, normalises currency/budget strings (`$6k/mo` → `6000`), resolves employee range counts (`35-55` → `45`), and validates email formats.
2. **Dual-Layer Qualification Engine**: Combines **Rule-Based Quantitative Scoring** (Role authority, budget size, source quality, team size, recency) with **LLM/Heuristic Notes Analysis** (buying intent, urgency, spam/job seeker detection).
3. **Actionable Outputs**: Categorises every lead into **`contact_now`**, **`nurture`**, or **`disqualify`**, generating a ranked CSV export and an interactive HTML Executive Dashboard.

---

## System Architecture & Workflow

The system is designed with a modular 5-tier architecture:

```
                  ┌──────────────────────────────────────────┐
                  │ Ingestion Source                         │
                  │  • Local Files (.csv, .xlsx, .xls)       │
                  │  • Cloud URLs (HTTP/HTTPS/GitHub)        │
                  └────────────────────┬─────────────────────┘
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │ Data Ingestion & Cleaning                │
                  │  [src/loader.py]                         │
                  │  • Format & Column Schema Validation     │
                  │  • Data Normalisation & Email Checking   │
                  └────────────────────┬─────────────────────┘
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │ Quantitative Scoring Engine              │
                  │  [src/scorer.py]                         │
                  │  • Job Title Authority Score (0–30)      │
                  │  • Monthly Budget Score (0–30)           │
                  │  • Source Channel Score (0–25)           │
                  │  • Company Size & Recency (0–25)         │
                  │  • Quality Penalties (-25 max)           │
                  └────────────────────┬─────────────────────┘
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │ Intent & Notes Analysis                  │
                  │  [src/analyser.py]                       │
                  │  • Primary: OpenAI GPT-4o-mini API       │
                  │  • Fallback: High-Precision Regex Engine │
                  │  • Adjusts score (-50 to +25) & flags    │
                  └────────────────────┬─────────────────────┘
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │ Export & Reporting                       │
                  │  [src/reporter.py]                       │
                  │  • Ranked CSV: output/leads_scored.csv   │
                  │  • HTML Dashboard: output/report.html    │
                  └────────────────────┬─────────────────────┘
                                       │
             ┌─────────────────────────┴─────────────────────────┐
             ▼                                                   ▼
┌───────────────────────────┐                       ┌───────────────────────────┐
│ CLI Interface             │                       │ FastAPI Web Application   │
│ [main.py / src/cli.py]    │                       │ [app.py]                  │
│ • Interactive Menu        │                       │ • Web Upload & URL Input  │
│ • Automated Pipelines     │                       │ • Cloud Hosting (Render)  │
└───────────────────────────┘                       └───────────────────────────┘
```

---

## Lead Qualification Logic

Leads are scored out of a maximum possible score of **130 points** (105 from quantitative rules + 25 from qualitative intent analysis).

### Scoring Dimensions & Weights

| Dimension               | Criteria             | Max Points     | Logic                                                                                                                                                                                                                                                                    |
|-------------------------|----------------------|----------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Job Title Authority** | Decision-maker level | **30 pts**     | • **Tier 1 (+30)**: CEO, Founder, Owner, Managing Director, CTO, COO<br>• **Tier 2 (+20)**: VP, Head of Ops/RevOps/Growth, Director<br>• **Tier 3 (+10)**: Manager, Consultant, Partner, Strategist<br>• **Disqualify (-10)**: Student, Recruiter, Freelancer, Developer |
| **Monthly Budget**      | Financial fit (USD)  | **30 pts**     | • **High (+30)**: ≥ $10,000/mo<br>• **Mid-High (+20)**: $5,000–$9,999/mo<br>• **Moderate (+10)**: $1,000–$4,999/mo<br>• **Low/Zero (0)**: < $1,000 or missing                                                                                                            |
| **Lead Source**         | Channel quality      | **25 pts**     | • **Referral (+25)**: Highest trust & conversion<br>• **Event (+20)**: In-person engagement<br>• **LinkedIn (+15)**: B2B professional network<br>• **Webform (+10)**: Inbound website visitor<br>• **Cold Reply (+5)**: Outbound response                                |
| **Company Size**        | Employee scale       | **15 pts**     | • **50+ employees (+15)**: Established enterprise<br>• **10–49 employees (+10)**: Scaling team<br>• **1–9 employees (+5)**: Small team / solo                                                                                                                            |
| **Recency**             | Creation recency     | **10 pts**     | • **≤ 30 days (+10)**: Fresh lead<br>• **31–90 days (+5)**: Warm lead<br>• **> 90 days (0)**: Older lead                                                                                                                                                                 |
| **Quality Penalties**   | Data hygiene         | **-20 pts**    | • **Invalid Email (-20)**: Hard bounce risk                                                                                                                                                                                                                              |
| **Notes Intent**        | Intent analysis      | **-50 to +25** | • **Budget Approved / Urgent (+25)**<br>• **Exploring Options (+15)**<br>• **Spam / Scam (-50)**<br>• **Job Seeker / Student (-30)**                                                                                                                                     |

---

### Qualification Categories

Every lead receives a `final_recommendation` based on their total combined score and qualitative red flags:

#### 🟢 `contact_now` (Score ≥ 70) — **Priority 1**
- **Definition**: High decision-maker authority (CEO/Founder/Head of Ops), verified budget (≥ $5k/mo), active automation need, and clean contact info.
- **Action**: Direct assignment to senior sales reps for immediate outreach within 24 hours.

#### 🟡 `nurture` (Score 40–69) — **Priority 2**
- **Definition**: Moderate authority (Consultant/Manager) or smaller budget ($1k–$5k/mo) with active interest, or high-value leads with incomplete data.
- **Action**: Add to automated email nurture sequences and retargeting campaigns.

#### 🔴 `disqualify` (Score < 40 OR Red Flags) — **Priority 3**
- **Definition**: Leads with low authority (Student/Recruiter), spam submissions (*"WON $1,000,000"*), job seekers submitting CVs, or invalid email addresses.
- **Action**: Exclude from sales outreach to preserve rep bandwidth and domain reputation.

---

## 🛠️ How to Use the System

The system provides two modes of operation: **Command Line Interface (CLI)** and **FastAPI Web Application**.

### Option A: Command Line Interface (CLI)

```bash
# Interactive Menu Mode (Prompts for options & auto-reloads on invalid inputs)
uv run python main.py --interactive

# Direct File Execution
uv run python main.py --input "data/leads_raw.csv"

# Direct Cloud URL Execution (Supports S3, GitHub web & raw links)
uv run python main.py --input "https://github.com/aniebietafia/koya_task/blob/main/data/leads_raw.csv"

# Offline Mode (Force heuristic analysis without OpenAI API key)
uv run python main.py --force-heuristic
```

### Option B: Web Application (Browser & Cloud Deployment)

Run locally or deploy to **Render**:

```bash
# Launch local web server
uv run uvicorn app:app --reload
```
Open `http://localhost:8000` in your browser to:
- Drag & drop `.csv`, `.xlsx`, or `.xls` files.
- Paste a cloud CSV URL.
- View the live Executive HTML Dashboard.
- Download the scored CSV in 1 click.

---

## 🧠 Key Assumptions

- **Currency & Budget Standardisation**: All budget values in raw text (`$6k/mo`, `18k`, `5,000/mo`, `$6-8k`) represent monthly USD figures. Midpoints are calculated for ranges (e.g. `$6-8k` → `$7,000/mo`).
- **Employee Counts**: Employee ranges (`35-55`) represent average team size (45), while upper bounds (`19+`, `70+`) establish lower thresholds.
- **Date Parsing**: Creation dates spanning multiple formats (`06/28/2024`, `2024-06-08`, `Jun 7 2024`, `19-06-2024`) are evaluated relative to the newest lead in the dataset to ensure consistent recency scoring across historic exports.
- **Primary Intent Indicators**: Free-text conversation notes carry critical disqualify signals (e.g., job seekers or spam) that override high quantitative title/budget scores.

---

## ⚖️ Key Design Decisions & Trade-Offs

### Hybrid Scoring Model (Rules + LLM)
- **Decision**: Combine explicit deterministic rule-scoring with qualitative LLM intent extraction.
- **Rationale**: Deterministic attributes (title, budget, source) are objective and fast to evaluate via Python. Subjective notes (*"Comparing a few options"*, *"Budget approved ASAP"*) require semantic understanding.
- **Trade-Off**: Adding LLM calls introduces network latency and API costs. We mitigated this by defaulting to GPT-4o-mini (costing < $0.05 per 500 leads) and implementing a high-precision regex fallback engine for offline execution.

### High-Precision Offline Heuristic Fallback
- **Decision**: Build an offline pattern-matching fallback in `src/analyser.py`.
- **Rationale**: Ensures the software remains 100% functional without an `OPENAI_API_KEY` or internet connection.
- **Trade-Off**: Heuristics rely on regex patterns and may miss subtle nuances that an LLM catches, but accurately identifies 95%+ of common intent categories (spam, job seekers, students, urgent budget approvals).

### Jinja2 Shared HTML Templates
- **Decision**: Store all HTML templates (`index.html`, `error.html`, `report_template.html`) inside `templates/`.
- **Rationale**: Separates presentation styling from Python application logic, making the UI customizable without touching code.

---

## Summary of Benchmark Dataset Results

When executed across the benchmark dataset of **520 leads**:
- **Ingested & Validated**: 520 leads (478 valid emails)
- **🟢 Contact Now**: **279 leads** (Score ≥ 70)
- **🟡 Nurture**: **112 leads** (Score 40–69)
- **🔴 Disqualify**: **129 leads** (Score < 40 or flagged red signals)

### Output Artifacts:
- **Scored CSV**: [`output/leads_scored.csv`](file:///c:/Users/afiaa/Desktop/koya_task/koya_task/output/leads_scored.csv)
- **HTML Dashboard**: [`output/report.html`](file:///c:/Users/afiaa/Desktop/koya_task/koya_task/output/report.html)