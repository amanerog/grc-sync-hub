#!/bin/bash
set -euo pipefail

export PYTHONPATH="${APP_HOME}/src:${PYTHONPATH:-}"

exec uvicorn sinc_amn.main:app --host "${SINC_AMN_HOST:-0.0.0.0}" --port "${SINC_AMN_PORT:-8080}"
