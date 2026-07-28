#!/bin/bash
set -euo pipefail

# No usamos $APP_HOME aqui: es solo una convencion de nombre (ENV APP_HOME
# /opt en el Dockerfile), no garantiza coincidir con el WORKDIR real de la
# imagen base (el Dockerfile no declara WORKDIR explicitamente). `pwd` si
# coincide siempre con el destino de `COPY . .`, sea cual sea ese WORKDIR.
export PYTHONPATH="$(pwd)/grc:${PYTHONPATH:-}"

exec uvicorn sinc_amn.main:app --host "${SINC_AMN_HOST:-0.0.0.0}" --port "${SINC_AMN_PORT:-8080}"
