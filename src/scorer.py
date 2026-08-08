"""
Lead Scoring Engine

Calculates a rule-based qualification score for each lead based on:
1. Job Title / Role authority (0-30 pts)
2. Monthly Budget (0-30 pts)
3. Lead Source (0-25 pts)
4. Company Size / Employee count (0-15 pts)
5. Recency / Creation date (0-10 pts)
6. Data Quality penalties (e.g. invalid email -20 pts)

Categorises leads into:
- contact_now  (Score >= 70)
- nurture      (Score 40 - 69)
- disqualify   (Score < 40)
"""

import json
from dataclasses import dataclass
import pandas as pd
from pathlib import Path


# ---------------------------------------------------------------------------
# Scoring Rules & Data Structures (Strongly Typed to avoid IDE warnings)
# ---------------------------------------------------------------------------

@dataclass
class TitleTier:
    keywords: list[str]
    score: int
    label: str


TIER_1 = TitleTier(
    keywords=["ceo", "founder", "owner", "co-founder", "president", "managing director", "managing partner", "cto", "coo"],
    score=30,
    label="Executive decision maker"
)

TIER_2 = TitleTier(
    keywords=["vp", "vice president", "head of", "director"],
    score=20,
    label="Senior leadership"
)

TIER_3 = TitleTier(
    keywords=["manager", "lead", "consultant", "partner", "strategist"],
    score=10,
    label="Manager/Consultant"
)

DISQUALIFY_TITLES = TitleTier(
    keywords=["student", "freelancer", "recruiter", "developer", "intern"],
    score=-10,
    label="Low authority role"
)

SOURCE_SCORES: dict[str, int] = {
    "referral": 25,
    "event": 20,
    "linkedin": 15,
    "webform": 10,
    "cold reply": 5
}


def score_title(title: str | None) -> tuple[int, str]:
    if pd.isna(title) or not str(title).strip():
        return 0, "Missing title"

    t = str(title).lower().strip()

    for kw in DISQUALIFY_TITLES.keywords:
        if kw in t:
            return DISQUALIFY_TITLES.score, f"{DISQUALIFY_TITLES.label} ({title})"

    for tier in (TIER_1, TIER_2, TIER_3):
        for kw in tier.keywords:
            if kw in t:
                return tier.score, f"{tier.label} ({title})"

    return 5, f"Other role ({title})"


def score_budget(budget: float | int | None) -> tuple[int, str]:
    if pd.isna(budget) or budget is None:
        return 0, "No budget specified"

    val = float(budget)
    if val >= 10000:
        return 30, f"High budget (${val:,.0f}/mo)"
    elif val >= 5000:
        return 20, f"Mid-high budget (${val:,.0f}/mo)"
    elif val >= 1000:
        return 10, f"Moderate budget (${val:,.0f}/mo)"
    elif val > 0:
        return 5, f"Low budget (${val:,.0f}/mo)"
    else:
        return 0, "Zero budget ($0)"


def score_source(source: str | None) -> tuple[int, str]:
    if pd.isna(source) or not source:
        return 0, "Unknown source"

    src = str(source).lower().strip()
    score = SOURCE_SCORES.get(src, 0)
    return score, f"Source: {src}"


def score_company_size(employees: float | int | None) -> tuple[int, str]:
    if pd.isna(employees) or employees is None:
        return 0, "Unknown company size"

    emp = int(employees)
    if emp >= 50:
        return 15, f"Large team ({emp}+ employees)"
    elif emp >= 10:
        return 10, f"Mid-sized team ({emp} employees)"
    elif emp >= 1:
        return 5, f"Small team ({emp} employees)"
    return 0, "Micro/Solo team"


def score_recency(created_date: pd.Timestamp | None, reference_date: pd.Timestamp) -> tuple[int, str]:
    if pd.isna(created_date) or created_date is None:
        return 0, "Unknown creation date"

    days_old = (reference_date - created_date).days
    if days_old <= 30:
        return 10, f"Recent lead ({days_old} days old)"
    elif days_old <= 90:
        return 5, f"Moderate recency ({days_old} days old)"
    return 0, f"Older lead ({days_old} days old)"


def score_quality_penalties(row) -> tuple[int, list[str]]:
    penalty = 0
    reasons: list[str] = []

    if not row.get("email_valid", True):
        penalty -= 20
        reasons.append("Invalid email address (-20)")

    flags = str(row.get("data_quality_flag", ""))
    if "missing_lead_id" in flags:
        penalty -= 5
        reasons.append("Missing lead ID (-5)")

    return penalty, reasons


# ---------------------------------------------------------------------------
# Scoring Function for DataFrame
# ---------------------------------------------------------------------------

def calculate_rule_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies rule-based scoring to the cleaned leads DataFrame.

    Adds columns:
    - rule_score (int)
    - scoring_breakdown (JSON string)
    - initial_recommendation (str: contact_now | nurture | disqualify)
    """
    df = df.copy()

    # Determine reference date for recency (max date in dataset)
    valid_dates = df["created_date"].dropna()
    ref_date = valid_dates.max() if not valid_dates.empty else pd.Timestamp.now()

    rule_scores: list[int] = []
    breakdowns: list[str] = []
    recommendations: list[str] = []

    for _, row in df.iterrows():
        t_pts, t_msg = score_title(row.get("title"))
        b_pts, b_msg = score_budget(row.get("budget_usd"))
        s_pts, s_msg = score_source(row.get("source_clean"))
        e_pts, e_msg = score_company_size(row.get("employees_clean"))
        r_pts, r_msg = score_recency(row.get("created_date"), ref_date)
        p_pts, p_msgs = score_quality_penalties(row)

        total = t_pts + b_pts + s_pts + e_pts + r_pts + p_pts

        # Determine recommendation based on score thresholds
        if total >= 70:
            rec = "contact_now"
        elif total >= 40:
            rec = "nurture"
        else:
            rec = "disqualify"

        # Special automatic disqualifications (e.g. Student role)
        title_str = str(row.get("title", "")).lower()
        if "student" in title_str or "recruiter" in title_str:
            rec = "disqualify"

        breakdown = {
            "title": {"points": t_pts, "reason": t_msg},
            "budget": {"points": b_pts, "reason": b_msg},
            "source": {"points": s_pts, "reason": s_msg},
            "company_size": {"points": e_pts, "reason": e_msg},
            "recency": {"points": r_pts, "reason": r_msg},
            "penalties": {"points": p_pts, "reasons": p_msgs}
        }

        rule_scores.append(total)
        breakdowns.append(json.dumps(breakdown))
        recommendations.append(rec)

    df["rule_score"] = rule_scores
    df["scoring_breakdown"] = breakdowns
    df["initial_recommendation"] = recommendations

    return df


if __name__ == "__main__":
    from loader import load_leads

    csv_path = Path("data/leads_raw.csv")
    cleaned_df = load_leads(csv_path)
    scored_df = calculate_rule_scores(cleaned_df)

    print("[OK] Scored leads successfully extracted without warnings")
    print(f"\n[RECOMMENDATION SUMMARY]:\n{scored_df['initial_recommendation'].value_counts()}")
