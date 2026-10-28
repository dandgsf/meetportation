#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -x venv/bin/python ] || { echo "Rode ./setup.sh primeiro."; exit 1; }
exec venv/bin/python run.py "$@"
