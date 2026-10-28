#!/usr/bin/env bash
# Modo Google Meet (sem OBS): exige a extensão em chrome-extension/ carregada no Chrome
exec "$(dirname "$0")/run.sh" --no-vcam --ws "$@"
