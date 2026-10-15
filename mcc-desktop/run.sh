#!/usr/bin/env bash
# Abre o MCC desktop (Python + PySide6)
cd "$(dirname "$0")" && exec .venv/bin/python -m mcc "$@"
