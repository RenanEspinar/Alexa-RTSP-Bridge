#!/usr/bin/env bash
set -euo pipefail
umask 077
MODE="${1:---check}"
if [[ "$MODE" != '--check' && "$MODE" != '--apply' ]]; then echo 'Uso: actualizar_existente.sh --check|--apply'; exit 2; fi
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${ALEXA_EXISTING_DIR:-$HOME/alexa-promax-test}"
CONTAINER='alexa_rtsp_bridge_pro_beta'
if [[ ! -d "$APP/alexa_bridge" || ! -f "$APP/compose.pro.yml" || ! -f "$APP/.env.pro" ]]; then
  echo "No está la instalación existente en $APP"; exit 1
fi
if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then echo "Contenedor $CONTAINER no encontrado"; exit 1; fi
cd "$APP"
echo '=== INSTALACIÓN ACTUAL ==='
docker inspect "$CONTAINER" --format 'Imagen: {{.Image}} | Estado: {{.State.Status}}'
docker compose --env-file .env.pro -f compose.pro.yml config -q
echo '=== PUERTOS EXISTENTES ==='
grep -E '^(UI_PORT|HLS_PORT|IDLE_TIMEOUT|SNAPSHOT_TTL)=' .env.pro | sed -E 's/(KEY|TOKEN|PASSWORD|SECRET)=.*/\1=<REDACTED>/' || true
if [[ "$MODE" == '--check' ]]; then echo 'Diagnóstico correcto. Repite con --apply para actualizar.'; exit 0; fi
BACKUP="$HOME/alexa-promax-backups/$(date -u +%Y%m%dT%H%M%SZ)-pre-v04"
mkdir -p "$BACKUP"; chmod 700 "$BACKUP"
cp -a "$APP/alexa_bridge" "$BACKUP/alexa_bridge"
cp -a "$APP/compose.pro.yml" "$BACKUP/compose.pro.yml"
cp -a "$APP/.env.pro" "$BACKUP/env.pro.private"
# Docker cp preserva los datos sin mostrar credenciales.
docker cp "$CONTAINER:/data" "$BACKUP/data"
printf '%s\n' "$BACKUP" > "$APP/.last_promax_backup_path"
echo "Respaldo privado: $BACKUP"
# Instalación de código, sin cambiar .env.pro ni el volumen de Docker.
cp -a "$SRC/alexa_bridge/." "$APP/alexa_bridge/"
cp -a "$SRC/compose.pro.yml" "$APP/compose.pro.yml"
(cd "$SRC" && python3 -m unittest discover -s tests -q)
docker compose --env-file .env.pro -f compose.pro.yml config -q
docker compose --env-file .env.pro -f compose.pro.yml up --build -d --no-deps bridge
OK=0
for i in $(seq 1 30); do
  if curl -fsS --max-time 3 'http://127.0.0.1:'"$(sed -n 's/^UI_PORT=//p' .env.pro | tail -1)"'/api/state' -o "$BACKUP/state-after.json" 2>/dev/null; then
     if python3 - "$BACKUP/state-after.json" <<'PY2'
import json,sys
with open(sys.argv[1]) as fh: j=json.load(fh)
assert j.get('version') == '0.4.0b1', j.get('version')
print('Versión:', j['version'], '| Cámaras conservadas:', len(j.get('cameras', [])))
PY2
     then OK=1; break; fi
  fi
  sleep 2
done
if [[ "$OK" -ne 1 ]]; then
  echo 'La versión nueva no respondió. Restaurando el código anterior.'
  rm -rf "$APP/alexa_bridge"
  cp -a "$BACKUP/alexa_bridge" "$APP/alexa_bridge"
  cp -a "$BACKUP/compose.pro.yml" "$APP/compose.pro.yml"
  docker compose --env-file .env.pro -f compose.pro.yml up --build -d --no-deps bridge || true
  echo "Respaldo de datos en $BACKUP/data. Revisa los logs."; exit 1
fi
echo 'Actualización confirmada; nombre del contenedor, puertos y volumen conservados.'
echo "Respaldo privado: $BACKUP"
