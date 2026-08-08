"""
Output & Report Generator

Exports:
1. Cleaned & Scored CSV output (`output/leads_scored.csv`) sorted by final_score
2. Executive HTML Report (`output/report.html`) generated using templates/report_template.html
"""

from pathlib import Path
import pandas as pd
from jinja2 import Environment, FileSystemLoader


# ---------------------------------------------------------------------------
# Export Scored Leads CSV
# ---------------------------------------------------------------------------

def export_scored_csv(df: pd.DataFrame, output_path: str | Path) -> Path:
    """Exports the fully analyzed DataFrame to a sorted CSV file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort leads by final_score descending
    df_sorted = df.sort_values(by="final_score", ascending=False).copy()

    # Reorder columns for optimal readability
    primary_cols = [
        "lead_id", "final_recommendation", "final_score", "rule_score", "llm_intent_score",
        "name", "email", "company", "title", "monthly_budget", "budget_usd",
        "employees_clean", "source_clean", "llm_intent_category", "llm_summary_reason"
    ]
    other_cols = [c for c in df_sorted.columns if c not in primary_cols]
    final_cols = primary_cols + other_cols

    df_sorted[final_cols].to_csv(output_path, index=False, encoding="utf-8")
    print(f"[OK] Exported {len(df_sorted)} scored leads to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Generate HTML Executive Summary Report
# ---------------------------------------------------------------------------

def generate_html_report(df: pd.DataFrame, report_path: str | Path, template_dir: str | Path = "templates") -> Path:
    """Generates an executive HTML report from templates/report_template.html using Jinja2."""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    t_dir = Path(template_dir)
    if not t_dir.exists():
        t_dir = Path(__file__).parent.parent / "templates"

    env = Environment(loader=FileSystemLoader(str(t_dir)))
    template = env.get_template("report_template.html")

    total_leads = len(df)
    counts = df["final_recommendation"].value_counts()
    contact_now_count = int(counts.get("contact_now", 0))
    nurture_count = int(counts.get("nurture", 0))
    disqualify_count = int(counts.get("disqualify", 0))

    top_leads = df.sort_values(by="final_score", ascending=False).head(15).to_dict(orient="records")
    disqualified_leads = df[df["final_recommendation"] == "disqualify"].head(10).to_dict(orient="records")

    html_content = template.render(
        total_leads=total_leads,
        contact_now_count=contact_now_count,
        nurture_count=nurture_count,
        disqualify_count=disqualify_count,
        top_leads=top_leads,
        disqualified_leads=disqualified_leads
    )

    report_path.write_text(html_content, encoding="utf-8")
    print(f"[OK] Generated HTML report at {report_path}")
    return report_path


# ---------------------------------------------------------------------------
# Sanity Check Script
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from loader import load_leads
    from scorer import calculate_rule_scores
    from analyser import analyze_lead_notes

    csv_path = Path("data/leads_raw.csv")
    df_raw = load_leads(csv_path)
    df_scored = calculate_rule_scores(df_raw)
    df_analyzed = analyze_lead_notes(df_scored, force_heuristic=True)

    export_scored_csv(df_analyzed, "output/leads_scored.csv")
    generate_html_report(df_analyzed, "output/report.html")
