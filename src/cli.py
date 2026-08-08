"""
Lead Triage System — Command Line Interface (CLI)

Usage:
  # Interactive mode
  uv run python main.py --interactive

  # Standard CLI execution
  uv run python main.py --input "data/leads_raw.csv"

  # Cloud URL execution
  uv run python main.py --input "https://example.com/.../leads.csv"
"""

import sys
from pathlib import Path
import click

from loader import load_leads, is_url, SUPPORTED_EXTENSIONS
from scorer import calculate_rule_scores
from analyser import analyze_lead_notes
from reporter import export_scored_csv, generate_html_report


def prompt_interactive_menu() -> str:
    """Presents an interactive terminal menu for selecting input datasets."""
    click.echo("==================================================")
    click.echo("LEAD TRIAGE SYSTEM - INTERACTIVE MENU")
    click.echo("==================================================")
    click.echo("Supported formats: " + ", ".join(sorted(SUPPORTED_EXTENSIONS)))
    click.echo("--------------------------------------------------")
    click.echo("  [1] Provide a Cloud Dataset URL")
    click.echo("  [2] Provide a local dataset file path")
    click.echo("  [3] Use default dataset (data/leads_raw.csv)")
    click.echo("  [4] Exit")
    click.echo("--------------------------------------------------")

    choice = click.prompt("Select option", type=click.Choice(["1", "2", "3", "4"]), default="3")

    if choice == "1":
        return click.prompt("Enter Cloud Dataset URL").strip()
    elif choice == "2":
        return click.prompt("Enter relative or absolute file path").strip()
    elif choice == "3":
        default_path = "data/leads_raw.csv"
        click.echo(f"Using default dataset: {default_path}")
        return default_path
    else:
        click.echo("Exiting pipeline.")
        sys.exit(0)


def execute_pipeline(df_clean, output: str, report: str, force_heuristic: bool):
    """Executes rule scoring, notes analysis, CSV export, and HTML report generation."""
    # Rule-based Scoring
    click.echo("\n[RULES] Running Rule Scoring Engine...")
    df_scored = calculate_rule_scores(df_clean)
    click.echo("  * Rule scoring complete")

    # Notes Intent Analysis
    click.echo("\n[ANALYSIS] Analyzing Notes Intent & Buying Signals...")
    df_analyzed = analyze_lead_notes(df_scored, force_heuristic=force_heuristic)
    click.echo("  * Notes analysis complete")

    # Export CSV & Generate HTML Report
    click.echo("\n[EXPORT] Exporting Scored CSV & Generating HTML Report...")
    out_csv = export_scored_csv(df_analyzed, output)
    out_report = generate_html_report(df_analyzed, report)

    # Summary Statistics
    counts = df_analyzed["final_recommendation"].value_counts()
    click.echo("\n==================================================")
    click.echo("[SUCCESS] PIPELINE EXECUTION COMPLETED SUCCESSFULLY!")
    click.echo("==================================================")
    click.echo(f"  * Contact Now  : {counts.get('contact_now', 0)}")
    click.echo(f"  * Nurture      : {counts.get('nurture', 0)}")
    click.echo(f"  * Disqualify   : {counts.get('disqualify', 0)}")
    click.echo(f"\nScored CSV : {out_csv.resolve()}")
    click.echo(f"HTML Report: {out_report.resolve()}")


@click.command()
@click.option("--input", "-i", default=None, help="Path or Cloud URL to lead dataset file.")
@click.option("--output", "-o", default="output/leads_scored.csv", help="Path where scored CSV will be saved.")
@click.option("--report", "-r", default="output/report.html", help="Path where HTML summary report will be saved.")
@click.option("--force-heuristic", is_flag=True, help="Force heuristic notes analysis (offline mode).")
@click.option("--interactive", is_flag=True, help="Run in interactive CLI mode with prompts.")
def run_cli(input: str | None, output: str, report: str, force_heuristic: bool, interactive: bool):
    """Automated Lead Triage & Qualification CLI."""

    is_interactive_mode = interactive or (input is None)

    if is_interactive_mode:
        while True:
            target_input = prompt_interactive_menu()

            click.echo("\n==================================================")
            click.echo("STARTING LEAD TRIAGE & QUALIFICATION PIPELINE")
            click.echo("==================================================")

            if not is_url(target_input):
                input_path = Path(target_input)
                if not input_path.exists():
                    click.echo(f"\n[ERROR] Local input file not found at: {input_path.resolve()}", err=True)
                    click.echo("Please try again with a valid file path.\n")
                    continue

            click.echo(f"\n[VALIDATION] Ingesting & Validating dataset from: {target_input}")
            try:
                df_clean = load_leads(target_input)
            except ValueError as val_err:
                click.echo("\n[ERROR] DATASET VALIDATION FAILED!", err=True)
                click.echo(f"{val_err}", err=True)
                click.echo("Please select a supported dataset format.\n")
                continue
            except Exception as err:
                click.echo(f"\n[ERROR] Failed to load dataset: {err}", err=True)
                click.echo("Please try again.\n")
                continue

            click.echo(f"  * Successfully validated and loaded {len(df_clean)} leads ({df_clean['email_valid'].sum()} valid emails)")
            execute_pipeline(df_clean, output, report, force_heuristic)
            break
    else:
        target_input = input.strip()

        click.echo("\n==================================================")
        click.echo("STARTING LEAD TRIAGE & QUALIFICATION PIPELINE")
        click.echo("==================================================")

        if not is_url(target_input):
            input_path = Path(target_input)
            if not input_path.exists():
                click.echo(f"[ERROR] Local input file not found at: {input_path.resolve()}", err=True)
                sys.exit(1)

        click.echo(f"\n[VALIDATION] Ingesting & Validating dataset from: {target_input}")
        try:
            df_clean = load_leads(target_input)
        except ValueError as val_err:
            click.echo("\n[ERROR] DATASET VALIDATION FAILED!", err=True)
            click.echo(f"{val_err}", err=True)
            sys.exit(1)
        except Exception as err:
            click.echo(f"\n[ERROR] Failed to load dataset: {err}", err=True)
            sys.exit(1)

        click.echo(f"  * Successfully validated and loaded {len(df_clean)} leads ({df_clean['email_valid'].sum()} valid emails)")
        execute_pipeline(df_clean, output, report, force_heuristic)


if __name__ == "__main__":
    run_cli()
