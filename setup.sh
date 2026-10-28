#!/usr/bin/env bash
# Instala o Meetportation (macOS / Linux)
set -e
cd "$(dirname "$0")"
PY=""
for c in python3.12 python3.13 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -z "$PY" ] && { echo "Python 3.10-3.13 não encontrado."; exit 1; }
echo "Usando $($PY --version)"
[ -x venv/bin/python ] || "$PY" -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
echo "Pronto! Rode ./run.sh (OBS) ou ./run-meet.sh (Google Meet)"
