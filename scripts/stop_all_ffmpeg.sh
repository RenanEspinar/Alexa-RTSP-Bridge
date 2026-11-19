#!/usr/bin/env bash
# Parar solo los contenedores ffmpeg_* creados con start_camera_example.sh.
# No toca alexa_ondemand ni los contenedores alexa_* de la instalación real.
set -euo pipefail

mapfile -t cams < <(docker ps --filter 'name=^/ffmpeg_' --format '{{.Names}}')
if ((${#cams[@]} == 0)); then
  echo 'No hay contenedores ffmpeg_* encendidos.'
  exit 0
fi
printf 'Se detendrán:\n'
printf '  %s\n' "${cams[@]}"
read -r -p 'Escribe SI para continuar: ' ok
[[ "$ok" == SI ]] || { echo 'Cancelado.'; exit 0; }
docker stop "${cams[@]}"
