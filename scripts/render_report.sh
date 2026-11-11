#!/usr/bin/env bash
# Render the report twice: a self-contained HTML file, then GitHub markdown.
# The HTML render deletes report_files/, so the markdown render must come last.
set -euo pipefail
cd "$(dirname "$0")/.."
# Use this project's Jupyter kernel even if the user has another "python3" kernel.
export JUPYTER_PREFER_ENV_PATH=1
uv run quarto render report/report.qmd --to html
uv run quarto render report/report.qmd --to gfm
