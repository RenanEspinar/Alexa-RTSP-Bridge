#!/usr/bin/env bash
# v0.6.1: upload reviewed AI preview patch and update SAME Pro Max gateway + AI worker.
# Never re-create a second installation, new volume, or new public hostname.
set -euo pipefail
umask 077
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$HOME/alexa-publicacion-v03.b018az/repo"
ORIGIN='https://github.com/RenanEspinar/Alexa-RTSP-Bridge.git'
APP="${ALEXA_EXISTING_DIR:-$HOME/alexa-promax-test}"
BRIDGE='alexa_rtsp_bridge_pro_beta'
AI='alexa_rtsp_bridge_pro_ai'

FILES=(
  README.md RELEASE_MANIFEST.json alexa_bridge/CHANGELOG.md
  alexa_bridge/config.yaml
  alexa_bridge/promax/ai_engine.py
  alexa_bridge/promax/ai_store.py
  alexa_bridge/promax/service.py
  alexa_bridge/promax/static/app.js
  alexa_bridge/promax/static/app.css
  alexa_bridge/promax/static/index.html
  custom_components/alexa_rtsp_bridge/manifest.json
  docs/AI_VISOR_V061_ES.md
  tests/test_ai_v06.py tests/test_ai_preview_v061.py
  scripts/publicar_v061_desde_ssh.sh
  scripts/restaurar_v061.sh
)
for f in "${FILES[@]}"; do
  [[ -f "$SRC/$f" ]] || { echo "Falta $f en la actualización"; exit 1; }
done
if [[ ! -d "$REPO/.git" ]]; then
  REPO="$HOME/alexa-publicacion-v061/repo"
  [[ ! -e "$REPO" ]] || { echo "Directorio alternativo ya existe: $REPO"; exit 1; }
  mkdir -p "$(dirname "$REPO")"
  git clone --branch main "$ORIGIN" "$REPO"
fi
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || { echo 'No estás en main'; exit 1; }
[[ "$(git remote get-url origin)" == "$ORIGIN" ]] || { echo 'Origen remoto inesperado'; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Cambios locales sin publicar; abortado'; exit 1; }
git pull --ff-only origin main
for f in "${FILES[@]}"; do
  mkdir -p "$(dirname "$REPO/$f")"
  cp -a "$SRC/$f" "$REPO/$f"
done
python3 -m unittest discover -s tests -q
if command -v node >/dev/null 2>&1; then node --check alexa_bridge/promax/static/app.js; fi
bash -n scripts/publicar_v061_desde_ssh.sh scripts/restaurar_v061.sh
git add -- "${FILES[@]}"
git diff --cached --check
git -c core.pager=cat diff --cached --stat
if ! git diff --cached --quiet; then
  read -r -p 'Escribe SUBIR para publicar v0.6.1 en GitHub: ' OK </dev/tty
  [[ "$OK" == SUBIR ]] || { echo 'Cambios preparados, sin publicar'; exit 0; }
  git config user.name >/dev/null 2>&1 || git config user.name RenanEspinar
  git config user.email >/dev/null 2>&1 || git config user.email 43801533+RenanEspinar@users.noreply.github.com
  git commit -m 'feat: on-demand annotated AI preview and optional road detection mode'
  git push origin main </dev/tty
fi
read -r -p 'Escribe ACTUALIZAR para instalar v0.6.1 en nuestro servidor: ' OK </dev/tty
[[ "$OK" == ACTUALIZAR ]] || { echo 'Servidor sin cambios'; exit 0; }
[[ -f "$APP/.env.pro" && -f "$APP/compose.pro.yml" ]] || { echo "No existe la instalación en $APP"; exit 1; }
docker inspect "$BRIDGE" >/dev/null
docker inspect "$AI" >/dev/null
cd "$APP"
docker compose --env-file .env.pro -f compose.pro.yml config -q
PORT="$(sed -n 's/^UI_PORT=//p' .env.pro | tail -1)"
PORT="${PORT:-18099}"
STATE="$(mktemp)";trap 'rm -f "$STATE"' EXIT
curl -fsS --max-time 6 "http://127.0.0.1:$PORT/api/state" -o "$STATE"
read -r VERSION COUNT < <(python3 - "$STATE" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]))
print(s.get('version','unknown'),len(s.get('cameras',[])))
PY
)
[[ "$VERSION" == 0.6.0b1 || "$VERSION" == 0.6.1b1 ]] || { echo "Versión no compatible: $VERSION"; exit 1; }
echo "Versión original: $VERSION · Cámaras: $COUNT"
BACKUP="$HOME/alexa-promax-backups/$(date -u +%Y%m%dT%H%M%SZ)-pre-v061"
mkdir -p "$BACKUP";chmod 700 "$BACKUP"
cp -a "$APP/alexa_bridge" "$BACKUP/alexa_bridge"
cp -a "$APP/compose.pro.yml" "$BACKUP/compose.pro.yml"
cp -a "$APP/.env.pro" "$BACKUP/env.pro.private"
docker cp "$BRIDGE:/data" "$BACKUP/data"
printf '%s\n' "$BACKUP" > "$APP/.last_promax_backup_path"
echo "Respaldo privado: $BACKUP"
rollback(){
  echo 'Fallo; restaurando la versión anterior del puente y del detector.'
  rm -rf "$APP/alexa_bridge"
  cp -a "$BACKUP/alexa_bridge" "$APP/alexa_bridge"
  cp -a "$BACKUP/compose.pro.yml" "$APP/compose.pro.yml"
  cp -a "$BACKUP/env.pro.private" "$APP/.env.pro"
  docker compose --env-file .env.pro -f compose.pro.yml up --build -d --no-deps bridge || true
  docker compose --env-file .env.pro -f compose.pro.yml --profile ai up --build -d --no-deps ai || true
  echo "Datos sin borrar. Respaldo: $BACKUP"
}
for f in "${FILES[@]}"; do
  case "$f" in
    alexa_bridge/*) mkdir -p "$(dirname "$APP/$f")"; cp -a "$SRC/$f" "$APP/$f" || { rollback; exit 1; } ;;
  esac
done
if ! docker compose --env-file .env.pro -f compose.pro.yml up --build -d --no-deps bridge; then rollback; exit 1; fi
OK=0
for i in $(seq 1 30); do
  if curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/state" -o "$STATE" 2>/dev/null; then
    if python3 - "$STATE" "$COUNT" <<'PY'
import json,sys
s=json.load(open(sys.argv[1])); assert s.get('version')=='0.6.1b1',s.get('version')
assert len(s['cameras'])==int(sys.argv[2]),'Camera count changed'
print('Versión:',s['version'],'| Cámaras conservadas:',len(s['cameras']))
PY
    then OK=1;break;fi
  fi
  sleep 2
done
if [[ "$OK" -ne 1 ]]; then rollback; exit 1; fi
if ! docker compose --env-file .env.pro -f compose.pro.yml --profile ai up --build -d --no-deps ai; then rollback; exit 1; fi
if ! docker inspect "$AI" --format '{{.State.Running}}' | grep -qx true; then rollback; exit 1; fi
printf '\nInstalación v0.6.1 confirmada. Worker AI iniciado; cámaras intactas.\n'
printf 'Panel original: https://alexa-pro.chuma.website\n'
printf 'Abre AI Detector > Calle Gladiolos A > View AI boxes.\n'
printf 'Para volver atrás: bash %q\n' "$REPO/scripts/restaurar_v061.sh"
