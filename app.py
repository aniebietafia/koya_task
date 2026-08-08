"""
Lead Triage System — FastAPI Web Application for Cloud Deployment (Render)

Features:
- In-place form validation error messages on index page
- Sleek card-based HTML error rendering via templates/error.html
- Dynamic CSV/Excel dataset processing & HTML dashboard reporting
"""

import sys
import tempfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from jinja2 import Environment, FileSystemLoader

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loader import load_leads
from scorer import calculate_rule_scores
from analyser import analyze_lead_notes
from reporter import export_scored_csv, generate_html_report

app = FastAPI(title="Lead Triage & Qualification Web System")

# Configure Jinja2 Environment with templates/ directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

# Ensure output directory exists
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
def index():
    template = jinja_env.get_template("index.html")
    return template.render()


@app.post("/triage", response_class=HTMLResponse)
async def triage_leads(url: str = Form(None), file: UploadFile = File(None)):
    target_source = None

    if url and url.strip():
        target_source = url.strip()
    elif file and file.filename:
        # Save temporary file preserving extension
        temp_dir = tempfile.mkdtemp()
        temp_file_path = Path(temp_dir) / file.filename
        content = await file.read()
        temp_file_path.write_bytes(content)
        target_source = str(temp_file_path)

    # In-place validation when no data is provided
    if not target_source:
        template = jinja_env.get_template("index.html")
        return HTMLResponse(
            content=template.render(
                error_message="Please provide a dataset URL or upload a file (.csv, .xlsx, .xls).",
                url_value=url
            ),
            status_code=200
        )

    try:
        # Pipeline execution with validation
        df_clean = load_leads(target_source)
        df_scored = calculate_rule_scores(df_clean)
        df_analyzed = analyze_lead_notes(df_scored, force_heuristic=True)

        # Generate outputs
        export_scored_csv(df_analyzed, OUTPUT_DIR / "leads_scored.csv")
        report_path = generate_html_report(df_analyzed, OUTPUT_DIR / "report.html", template_dir=TEMPLATES_DIR)

        # Inject top action bar into rendered report HTML
        html_text = report_path.read_text(encoding="utf-8")
        download_bar = """
        <div style="background: #1e293b; border-bottom: 1px solid #334155; padding: 12px 20px; text-align: right;">
            <a href="/download-csv" style="background: #10b981; color: white; padding: 8px 16px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 0.85rem;">⬇Download Scored CSV</a>
            <a href="/" style="background: #334155; color: white; padding: 8px 16px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 0.85rem; margin-left: 10px;">Analyze Another Dataset</a>
        </div>
        """
        body_index = html_text.find("<body>") + 6
        final_html = html_text[:body_index] + download_bar + html_text[body_index:]

        return HTMLResponse(content=final_html)

    except ValueError as val_err:
        # User validation error (unsupported file format or schema error)
        template = jinja_env.get_template("error.html")
        error_html = template.render(error_details=str(val_err))
        return HTMLResponse(content=error_html, status_code=400)

    except Exception as err:
        template = jinja_env.get_template("error.html")
        error_html = template.render(error_details=f"Lead Triage Failed: {err}")
        return HTMLResponse(content=error_html, status_code=500)


@app.get("/download-csv")
def download_csv():
    csv_file = OUTPUT_DIR / "leads_scored.csv"
    if not csv_file.exists():
        raise HTTPException(status_code=404, detail="No scored CSV available.")
    return FileResponse(csv_file, media_type="text/csv", filename="leads_scored.csv")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
