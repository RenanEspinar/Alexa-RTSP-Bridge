#!/usr/bin/env bash
# v0.6 in-place bridge updater. AI is an opt-in separate Docker profile.
set -euo pipefail
umask 077
MODE="${1:---check}"
[[ "$MODE" == '--check' || "$MODE" == '--apply' ]] || { echo 'Uso: actualizar_existente.sh --check|--apply'; exit 2; }
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${ALEXA_EXISTING_DIR:-$HOME/alexa-promax-test}"
CONTAINER='alexa_rtsp_bridge_pro_beta'
[[ -f "$APP/.env.pro" && -f "$APP/compose.pro.yml" && -d "$APP/alexa_bridge" ]] || { echo "Instalación no encontrada en $APP"; exit 1; }
docker inspect "$CONTAINER" >/dev/null 2>&1 || { echo "No existe el contenedor $CONTAINER"; exit 1; }
cd "$APP"
echo '=== DIAGNÓSTICO ANTES DE ACTUALIZAR ==='
docker compose --env-file .env.pro -f compose.pro.yml config -q
# The existing API is an authoritative read-only camera-count check.
PORT="$(sed -n 's/^UI_PORT=//p' .env.pro | tail -1)"
PORT="${PORT:-18099}"
STATE="$(mktemp)"; trap 'rm -f "$STATE"' EXIT
curl -fsS --max-time 6 "http://127.0.0.1:${PORT}/api/state" > "$STATE"
COUNT="$(python3 - "$STATE" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]));print(len(s['cameras']))
PY
)"
VERSION="$(python3 - "$STATE" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]));print(s.get('version','unknown'))
PY
)"
echo "Versión actual: $VERSION | cámaras existentes: $COUNT"
if [[ "$MODE" == '--check' ]]; then
  echo 'Listo para actualizar; no se modificó nada.'
  exit 0
fi
BACKUP="$HOME/alexa-promax-backups/$(date -u +%Y%m%dT%H%M%SZ)-pre-v06"
mkdir -p "$BACKUP"; chmod 700 "$BACKUP"
cp -a "$APP/alexa_bridge" "$BACKUP/alexa_bridge"
cp -a "$APP/compose.pro.yml" "$BACKUP/compose.pro.yml"
cp -a "$APP/.env.pro" "$BACKUP/env.pro.private"
docker cp "$CONTAINER:/data" "$BACKUP/data"
printf '%s\n' "$BACKUP" > "$APP/.last_promax_backup_path"
echo "Respaldo privado: $BACKUP"
rollback() {
  echo 'Error durante la actualización. Restaurando el código anterior...'
  rm -rf "$APP/alexa_bridge"
  cp -a "$BACKUP/alexa_bridge" "$APP/alexa_bridge"
  cp -a "$BACKUP/compose.pro.yml" "$APP/compose.pro.yml"
  cp -a "$BACKUP/env.pro.private" "$APP/.env.pro"
  docker compose --env-file .env.pro -f compose.pro.yml up --build -d --no-deps bridge || true
  echo "Respaldo original disponible: $BACKUP"
}
if ! cp -a "$SRC/alexa_bridge/." "$APP/alexa_bridge/"; then rollback; exit 1; fi
if ! cp -a "$SRC/compose.pro.yml" "$APP/compose.pro.yml"; then rollback; exit 1; fi
docker compose --env-file .env.pro -f compose.pro.yml config -q || { rollback; exit 1; }
if ! docker compose --env-file .env.pro -f compose.pro.yml up --build -d --no-deps bridge; then
  rollback; exit 1
fi
OK=0
for i in $(seq 1 30); do
  if curl -fsS --max-time 4 "http://127.0.0.1:${PORT}/api/state" -o "$STATE" 2>/dev/null; then
    if python3 - "$STATE" "$COUNT" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]))
assert s.get('version')=='0.6.0b1', s.get('version')
assert len(s['cameras'])==int(sys.argv[2]), 'Camera count changed'
print('Versión:',s['version'],'| cámaras conservadas:',len(s['cameras']))
PY
    then OK=1; break; fi
  fi
  sleep 2
done
if [[ "$OK" -ne 1 ]]; then rollback; exit 1; fi
echo '=== INSTALACIÓN CORRECTA ==='
echo "Contenedor Alexa: $CONTAINER | puerto: $PORT | respaldo: $BACKUP"
echo 'La IA permanece desactivada hasta que la habilites por cámara.'
