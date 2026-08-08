"""
LLM & Heuristic Notes Analyser

Analyses free-text lead notes to extract intent, buying signals, and red flags.

Features:
- Primary mode: OpenAI GPT API (gpt-4o-mini) for rich semantic extraction
- Fallback mode: High-precision regex heuristic analyzer (runs offline if no API key)

Returns structured output per lead:
- llm_intent_score (int: -50 to +25)
- llm_intent_category (str: high_intent | medium_intent | low_intent | partner | job_seeker | student | spam)
- llm_summary_reason (str)
- llm_flags (list[str])
"""

import os
import json
import re
from dataclasses import dataclass
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class NoteAnalysis:
    intent_score: int
    intent_category: str
    summary_reason: str
    flags: list[str]


# ---------------------------------------------------------------------------
# Heuristic Analyser (Offline Fallback)
# ---------------------------------------------------------------------------

def analyze_note_heuristically(note: str | None) -> NoteAnalysis:
    """Fallback analyzer using pattern matching when OpenAI key is not provided."""
    if pd.isna(note) or not str(note).strip():
        return NoteAnalysis(
            intent_score=0,
            intent_category="low_intent",
            summary_reason="No notes provided",
            flags=["missing_notes"]
        )

    text = str(note).strip()
    text_lower = text.lower()
    flags: list[str] = []

    # Check for Spam / Scam
    if re.search(r"won\s+\$\d+|click\ certificate|claim\ now|lottery|prize", text_lower):
        return NoteAnalysis(
            intent_score=-50,
            intent_category="spam",
            summary_reason="Flagged as spam or promotional message",
            flags=["spam"]
        )

    # Check for Job Seekers / Developers looking for roles
    if re.search(r"looking for a role|attaching my cv|resume|developer looking|hiring me", text_lower):
        return NoteAnalysis(
            intent_score=-30,
            intent_category="job_seeker",
            summary_reason="Job seeker or developer looking for employment",
            flags=["job_seeker", "not_buying"]
        )

    # Check for Students / Learning only
    if re.search(r"cs student|not looking to buy|just learning|free template|school project", text_lower):
        return NoteAnalysis(
            intent_score=-30,
            intent_category="student",
            summary_reason="Student seeking free resources/learning material",
            flags=["student", "not_buying"]
        )

    # Check for Investor / VC / Referral Partner
    if re.search(r"vc here|investor|intro you to|portfolio companies|partner intro", text_lower):
        return NoteAnalysis(
            intent_score=0,
            intent_category="partner",
            summary_reason="Investor or partner offering portfolio introductions",
            flags=["investor_partner", "not_direct_buyer"]
        )

    # Check High Intent Signals
    high_signals = []
    if re.search(r"budget approved|ready to pilot|asap|ready to start|decision maker", text_lower):
        high_signals.append("urgent_budget_approved")
        flags.append("urgent")
        flags.append("budget_approved")

    if re.search(r"want it automated|interested in automating|comparing a few options|looking into automating", text_lower):
        high_signals.append("active_automation_need")

    if high_signals:
        score = 25 if "urgent_budget_approved" in high_signals else 15
        cat = "high_intent" if score >= 20 else "medium_intent"
        reason = "Expressed active automation interest with budget/urgency" if score >= 20 else "Exploring automation options"
        return NoteAnalysis(
            intent_score=score,
            intent_category=cat,
            summary_reason=reason,
            flags=flags
        )

    # Default moderate / low intent
    return NoteAnalysis(
        intent_score=5,
        intent_category="low_intent",
        summary_reason="General inquiry or limited note detail",
        flags=[]
    )


# ---------------------------------------------------------------------------
# OpenAI LLM Analyser
# ---------------------------------------------------------------------------

def analyze_note_openai(note: str, client) -> NoteAnalysis:
    """Analyze note using OpenAI API."""
    try:
        prompt = f"""
        You are a B2B sales lead analyst. Analyze the following lead note and evaluate intent, buying signals, and red flags.

        Lead Note: "{note}"

        Respond ONLY with a raw JSON object with these keys:
        - "intent_score": integer between -50 and 25 (-50 for spam, -30 for job seeker/student, 0 for partner, +10 to +25 for active buyers)
        - "intent_category": string ("high_intent", "medium_intent", "low_intent", "partner", "job_seeker", "student", "spam")
        - "summary_reason": 1 sentence explanation of intent and fit
        - "flags": array of string tags (e.g. ["urgent", "budget_approved", "spam", "job_seeker"])
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        data = json.loads(content)

        return NoteAnalysis(
            intent_score=int(data.get("intent_score", 0)),
            intent_category=str(data.get("intent_category", "low_intent")),
            summary_reason=str(data.get("summary_reason", "")),
            flags=list(data.get("flags", []))
        )
    except Exception as err:
        # Fallback if API call fails
        res = analyze_note_heuristically(note)
        res.flags.append(f"api_error_{err}")
        return res


# ---------------------------------------------------------------------------
# Main DataFrame Analysis Function
# ---------------------------------------------------------------------------

def analyze_lead_notes(df: pd.DataFrame, force_heuristic: bool = False) -> pd.DataFrame:
    """
    Applies note analysis to the leads DataFrame.

    Adds columns:
    - llm_intent_score (int)
    - llm_intent_category (str)
    - llm_summary_reason (str)
    - llm_flags (str — JSON list)
    - final_score (rule_score + llm_intent_score)
    - final_recommendation (contact_now | nurture | disqualify)
    """
    df = df.copy()
    api_key = os.getenv("OPENAI_API_KEY")

    client = None
    if api_key and not force_heuristic:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            print("[INFO] Using OpenAI API (gpt-4o-mini) for notes analysis")
        except ImportError:
            print("[INFO] OpenAI package not installed. Falling back to heuristic analyser.")

    if client is None:
        print("[INFO] Using high-precision heuristic analyser (Offline mode)")

    intent_scores: list[int] = []
    categories: list[str] = []
    reasons: list[str] = []
    flags_list: list[str] = []
    final_scores: list[int] = []
    final_recs: list[str] = []

    for _, row in df.iterrows():
        note_text = row.get("notes")
        if client:
            res = analyze_note_openai(str(note_text), client)
        else:
            res = analyze_note_heuristically(note_text)

        rule_score = int(row.get("rule_score", 0))
        final_score = rule_score + res.intent_score

        # Determine final recommendation
        if res.intent_category in ("spam", "job_seeker", "student"):
            final_rec = "disqualify"
        elif final_score >= 70:
            final_rec = "contact_now"
        elif final_score >= 40:
            final_rec = "nurture"
        else:
            final_rec = "disqualify"

        intent_scores.append(res.intent_score)
        categories.append(res.intent_category)
        reasons.append(res.summary_reason)
        flags_list.append(json.dumps(res.flags))
        final_scores.append(final_score)
        final_recs.append(final_rec)

    df["llm_intent_score"] = intent_scores
    df["llm_intent_category"] = categories
    df["llm_summary_reason"] = reasons
    df["llm_flags"] = flags_list
    df["final_score"] = final_scores
    df["final_recommendation"] = final_recs

    return df


# ---------------------------------------------------------------------------
# Sanity Check Script
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from loader import load_leads
    from scorer import calculate_rule_scores

    csv_path = Path("data/leads_raw.csv")
    df_raw = load_leads(csv_path)
    df_scored = calculate_rule_scores(df_raw)
    df_analyzed = analyze_lead_notes(df_scored, force_heuristic=True)

    print("\n[OK] Notes Analysis Complete")
    print(f"\n[INTENT CATEGORY BREAKDOWN]:\n{df_analyzed['llm_intent_category'].value_counts()}")
    print(f"\n[FINAL RECOMMENDATIONS BREAKDOWN]:\n{df_analyzed['final_recommendation'].value_counts()}")
    
    print("\n[SAMPLE DISQUALIFIED BY NOTES]:")
    disq_notes = df_analyzed[df_analyzed["llm_intent_category"].isin(["spam", "job_seeker", "student"])]
    print(disq_notes[["lead_id", "name", "title", "llm_intent_category", "llm_summary_reason"]].head(5).to_string())
