"""
main.py
Lead Triage System — Main Entry Point

Delegates execution to src/cli.py for command-line usage.
For web application mode, run app.py instead.
"""

import sys
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from cli import run_cli

if __name__ == "__main__":
    run_cli()
