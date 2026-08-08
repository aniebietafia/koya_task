"""
Data Ingestion & Cleaning

Responsible for:
- Loading raw CSV/Excel files from local paths OR Cloud URLs
- Validating supported file formats (.csv, .xlsx, .xls)
- Validating expected dataset columns & schema
- Normalising messy columns (budget, employees, dates, source)
- Flagging invalid/suspicious rows
"""

import re
from pathlib import Path
import pandas as pd

# ---------------------------------------------------------------------------
# Constants & Validation Rules
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
VALID_SOURCES = {"webform", "referral", "linkedin", "event", "cold reply"}

# Expected lead dataset schema
EXPECTED_COLUMNS = [
    "lead_id", "created", "name", "email", "company",
    "employees", "website", "title", "source", "monthly_budget", "notes"
]

# Essential columns required to run qualification & scoring logic
REQUIRED_CORE_COLUMNS = {"email", "title", "monthly_budget", "notes"}

DATE_FORMATS = [
    "%m/%d/%Y",   # 06/28/2024
    "%Y-%m-%d",   # 2024-06-08
    "%b %d %Y",   # Jun 7 2024
    "%d-%m-%Y",   # 19-06-2024
    "%m/%d/%y",   # 6/1/24
    "%d-%m-%y",   # 04-06-24
]


def is_url(path_str: str) -> bool:
    """Check if the provided path string is a cloud HTTP/HTTPS URL."""
    return path_str.startswith("http://") or path_str.startswith("https://")


def normalize_github_url(url: str) -> str:
    """Auto-convert GitHub HTML view URLs into raw content URLs."""
    if "github.com/" in url and "/blob/" in url:
        raw_url = url.replace("github.com/", "raw.githubusercontent.com/").replace("/blob/", "/")
        print(f"[INFO] Auto-converted GitHub view URL to Raw URL:\n  * {raw_url}")
        return raw_url
    return url


def validate_file_format(source_str: str) -> str:
    """
    Validates that the input source has a supported extension (.csv, .xlsx, .xls).
    Raises ValueError with supported formats if invalid.
    """
    clean_path = source_str.split("?")[0]  # Strip query parameters if URL
    ext = Path(clean_path).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        supported_str = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported file format '{ext if ext else 'unknown'}'. "
            f"Supported file formats are: {supported_str}"
        )
    return ext


def validate_columns(df: pd.DataFrame) -> None:
    """
    Validates that the dataset contains necessary columns for scoring and triage.
    Raises ValueError detailing missing columns if validation fails.
    """
    df_cols = {col.strip().lower() for col in df.columns}
    missing_core = REQUIRED_CORE_COLUMNS - df_cols

    if missing_core:
        missing_list = ", ".join(sorted(missing_core))
        expected_list = ", ".join(EXPECTED_COLUMNS)
        raise ValueError(
            f"Unsupported / Invalid dataset schema. Missing required columns: [{missing_list}].\n"
            f"  Expected schema columns: [{expected_list}]\n"
            f"  Columns found in dataset: [{', '.join(df.columns.tolist())}]"
        )


# ---------------------------------------------------------------------------
# Value Cleaners
# ---------------------------------------------------------------------------

def parse_budget(value) -> int | None:
    """Convert messy budget strings to a plain monthly integer (USD)."""
    if pd.isna(value):
        return None

    raw = str(value).strip().lower()

    if raw in ("tbd", "n/a", "-", ""):
        return None

    raw = re.sub(r"[\$,\s]", "", raw)
    raw = re.sub(r"/mo(nth)?", "", raw)

    range_match = re.match(r"([\d.]+)k?-([\d.]+)k?", raw)
    if range_match:
        lo = float(range_match.group(1))
        hi = float(range_match.group(2))
        if "k" in raw:
            lo *= 1000
            hi *= 1000
        return int((lo + hi) / 2)

    k_match = re.match(r"([\d.]+)k$", raw)
    if k_match:
        return int(float(k_match.group(1)) * 1000)

    plain_match = re.match(r"^[\d.]+$", raw)
    if plain_match:
        return int(float(raw))

    return None


def parse_employees(value) -> int | None:
    """Convert messy employee counts to a single integer."""
    if pd.isna(value):
        return None

    raw = str(value).strip().lower().replace(",", "")

    range_match = re.match(r"(\d+)-(\d+)", raw)
    if range_match:
        lo, hi = int(range_match.group(1)), int(range_match.group(2))
        return (lo + hi) // 2

    approx_match = re.match(r"[~]?(\d+)\+?$", raw)
    if approx_match:
        return int(approx_match.group(1))

    return None


def parse_date(value) -> pd.Timestamp | None:
    """Try each known date format in turn; return NaT-safe Timestamp or None."""
    if pd.isna(value):
        return None

    raw = str(value).strip()

    for fmt in DATE_FORMATS:
        try:
            return pd.to_datetime(raw, format=fmt)
        except ValueError:
            continue

    try:
        return pd.to_datetime(raw, dayfirst=True)
    except Exception:
        return None


def normalise_source(value) -> str | None:
    """Lower-case and validate the source field."""
    if pd.isna(value):
        return None

    cleaned = str(value).strip().lower()

    if cleaned in VALID_SOURCES:
        return cleaned

    return None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def is_valid_email(value) -> bool:
    if pd.isna(value):
        return False
    return bool(EMAIL_RE.match(str(value).strip()))


# ---------------------------------------------------------------------------
# Main loader (Supports Local Paths, Cloud URLs, Excel & Format Validation)
# ---------------------------------------------------------------------------

def load_leads(source: str | Path) -> pd.DataFrame:
    """
    Load and clean the raw leads dataset.

    Validates file formats (.csv, .xlsx, .xls) and dataset column schemas.
    """
    source_str = str(source).strip()

    # Validate File Format Extension
    ext = validate_file_format(source_str)

    # Ingest Data (Local or URL)
    if is_url(source_str):
        source_str = normalize_github_url(source_str)
        print(f"[INFO] Fetching cloud dataset from URL: {source_str}")
        try:
            if ext in (".xlsx", ".xls"):
                df = pd.read_excel(source_str, dtype=str)
            else:
                df = pd.read_csv(source_str, dtype=str, encoding="utf-8")
        except Exception as err:
            raise RuntimeError(f"Failed to read dataset from URL ({source_str}): {err}")
    else:
        filepath = Path(source_str)
        if not filepath.exists():
            raise FileNotFoundError(f"Local dataset file not found: {filepath.resolve()}")

        try:
            if ext in (".xlsx", ".xls"):
                df = pd.read_excel(filepath, dtype=str)
            else:
                df = pd.read_csv(filepath, dtype=str, encoding="utf-8")
        except Exception as err:
            raise RuntimeError(f"Failed to read file ({filepath.name}): {err}")

    # Validate Column Schema
    validate_columns(df)

    # Data Cleaning Pipeline
    df = df.drop_duplicates()

    # Remove header-row artefacts
    if "lead_id" in df.columns:
        df = df[df["lead_id"].astype(str).str.strip().str.lower() != "lead_id"].copy()

    # Strip whitespace from string columns
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()

    # Derived / cleaned columns
    df["budget_usd"] = df["monthly_budget"].apply(parse_budget) if "monthly_budget" in df.columns else None
    df["employees_clean"] = df["employees"].apply(parse_employees) if "employees" in df.columns else None
    df["created_date"] = df["created"].apply(parse_date) if "created" in df.columns else None
    df["source_clean"] = df["source"].apply(normalise_source) if "source" in df.columns else None
    df["email_valid"] = df["email"].apply(is_valid_email) if "email" in df.columns else False

    # Data quality flags
    def quality_flags(row) -> str:
        issues = []
        if pd.isna(row.get("lead_id")) or str(row.get("lead_id", "")).strip() in ("", "nan"):
            issues.append("missing_lead_id")
        if not row.get("email_valid", False):
            issues.append("invalid_email")
        if pd.isna(row.get("name")) or str(row.get("name", "")).strip() in ("", "nan"):
            issues.append("missing_name")
        if row.get("created_date") is None:
            issues.append("unparseable_date")
        if row.get("source_clean") is None:
            issues.append("unknown_source")
        if pd.isna(row.get("notes")) or str(row.get("notes", "")).strip() in ("", "nan"):
            issues.append("missing_notes")
        return ",".join(issues)

    df["data_quality_flag"] = df.apply(quality_flags, axis=1)

    return df
