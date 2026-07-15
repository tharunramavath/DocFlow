#!/usr/bin/env bash
# Convenience launcher for Certificate Studio.
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing dependencies…"
pip install -q -r requirements.txt

echo "Launching Certificate Studio…"
streamlit run app.py
