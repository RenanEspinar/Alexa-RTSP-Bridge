#!/usr/bin/env bash
# Publish v0.7 experimental Alexa boxes, then safely update SAME bridge + AI sidecar.
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
 alexa_bridge/Dockerfile
 alexa_bridge/promax/security.py alexa_bridge/promax/store.py
 alexa_bridge/promax/overlay.py alexa_bridge/promax/media.py
 alexa_bridge/promax/ai_engine.py alexa_bridge/promax/ai_store.py
 alexa_bridge/promax/service.py
 alexa_bridge/promax/static/app.js alexa_bridge/promax/static/index.html
 docs/AI_OVERLAY_V07_ES.md
 tests/test_ai_v06.py tests/test_alexa_overlay_v07.py
 scripts/publicar_v07_desde_ssh.sh scripts/restaurar_v07.sh
)
for f in "${FILES[@]}"; do
 [[ -f "$SRC/$f" ]] || { echo "Falta archivo en paquete: $f"; exit 1; }
done
if [[ ! -d "$REPO/.git" ]]; then
 REPO="$HOME/alexa-publicacion-v07/repo"
 [[ ! -e "$REPO" ]] || { echo "Directorio alternativo ocupado: $REPO"; exit 1; }
 mkdir -p "$(dirname "$REPO")"
 git clone --branch main "$ORIGIN" "$REPO"
fi
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || { echo 'El clon debe estar en main'; exit 1; }
[[ "$(git remote get-url origin)" == "$ORIGIN" ]] || { echo 'Origen GitHub no esperado'; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Hay cambios locales pendientes; abortado'; exit 1; }
git pull --ff-only origin main
for f in "${FILES[@]}"; do
 mkdir -p "$(dirname "$REPO/$f")"
 cp -a "$SRC/$f" "$REPO/$f"
done
python3 -m unittest discover -s tests -q
if command -v node >/dev/null 2>&1; then node --check alexa_bridge/promax/static/app.js; fi
for script in scripts/publicar_v07_desde_ssh.sh scripts/restaurar_v07.sh; do bash -n "$script"; done
git add -- "${FILES[@]}"
git diff --cached --check
git -c core.pager=cat diff --cached --stat
if ! git diff --cached --quiet; then
 read -r -p 'Escribe SUBIR para publicar v0.7 en GitHub: ' OK </dev/tty
 [[ "$OK" == SUBIR ]] || { echo 'Sin publicación';exit 0; }
 git config user.name >/dev/null 2>&1 || git config user.name RenanEspinar
 git config user.email >/dev/null 2>&1 || git config user.email 43801533+RenanEspinar@users.noreply.github.com
 git commit -m 'feat: optional private YOLOX bounding boxes burned into Alexa HLS'
 git push origin main </dev/tty
fi
read -r -p 'Escribe ACTUALIZAR para instalar v0.7 en los DOS contenedores existentes: ' OK </dev/tty
[[ "$OK" == ACTUALIZAR ]] || { echo 'Servidor sin cambios'; exit 0; }
[[ -f "$APP/.env.pro" && -f "$APP/compose.pro.yml" ]] || { echo "Instalación anterior no encontrada: $APP"; exit 1; }
docker inspect "$BRIDGE" >/dev/null
docker inspect "$AI" >/dev/null
cd "$APP"
docker compose --env-file .env.pro -f compose.pro.yml config -q
PORT="$(sed -n 's/^UI_PORT=//p' .env.pro | tail -1)";PORT="${PORT:-18099}"
STATE="$(mktemp)";trap 'rm -f "$STATE"' EXIT
curl -fsS --max-time 6 "http://127.0.0.1:$PORT/api/state" -o "$STATE"
read -r VERSION COUNT < <(python3 - "$STATE" <<'PY'
import json,sys
v=json.load(open(sys.argv[1]));print(v.get('version','unknown'),len(v.get('cameras',[])))
PY
)
[[ "$VERSION" == 0.6.1b1 || "$VERSION" == 0.7.0b1 ]] || { echo "Versión de origen inesperada: $VERSION"; exit 1; }
echo "Instalación actual: $VERSION; cámaras conservadas esperadas: $COUNT"
BACKUP="$HOME/alexa-promax-backups/$(date -u +%Y%m%dT%H%M%SZ)-pre-v07"
mkdir -p "$BACKUP"; chmod 700 "$BACKUP"
cp -a "$APP/alexa_bridge" "$BACKUP/alexa_bridge"
cp -a "$APP/compose.pro.yml" "$BACKUP/compose.pro.yml"
cp -a "$APP/.env.pro" "$BACKUP/env.pro.private"
docker cp "$BRIDGE:/data" "$BACKUP/data"
printf '%s\n' "$BACKUP" > "$APP/.last_promax_backup_path"
echo "Respaldo privado: $BACKUP"
rollback() {
 echo 'Error: restaurando el puente y el worker AI anterior.'
 rm -rf "$APP/alexa_bridge"
 cp -a "$BACKUP/alexa_bridge" "$APP/alexa_bridge"
 cp -a "$BACKUP/compose.pro.yml" "$APP/compose.pro.yml"
 cp -a "$BACKUP/env.pro.private" "$APP/.env.pro"
 docker compose --env-file .env.pro -f compose.pro.yml --profile ai up --build -d --no-deps bridge ai || true
 echo "Respaldo disponible: $BACKUP"
}
for f in "${FILES[@]}"; do
 case "$f" in
  alexa_bridge/*) mkdir -p "$(dirname "$APP/$f")";cp -a "$SRC/$f" "$APP/$f" || { rollback;exit 1; }; ;;
 esac
done
# Build images and run in-place; existing named volume, Cloudflare, ports, cameras preserved.
if ! docker compose --env-file .env.pro -f compose.pro.yml --profile ai up --build -d --no-deps bridge ai; then
 rollback;exit 1
fi
OK=0
for i in $(seq 1 36);do
 if curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/state" -o "$STATE" 2>/dev/null; then
  if python3 - "$STATE" "$COUNT" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]))
assert s.get('version')=='0.7.0b1',s.get('version')
assert len(s.get('cameras',[]))==int(sys.argv[2]),'Number of cameras changed'
print('Versión:',s['version'],'| Cámaras:',len(s['cameras']))
PY
  then OK=1;break;fi
 fi
 sleep 2
done
if [[ "$OK" != 1 ]]; then rollback; exit 1; fi
if ! docker inspect "$AI" --format '{{.State.Running}}' | grep -qx true; then rollback;exit 1;fi
if ! docker exec "$BRIDGE" sh -c "ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' zmq '"; then
 rollback;echo 'FFmpeg no soporta ZMQ; no se activó overlay';exit 1
fi
printf '\n=== V0.7 INSTALADA CORRECTAMENTE ===\n'
echo 'Overlay OFF por defecto. Habilítalo SOLO en una cámara desde Edit.'
echo 'Panel original: https://alexa-pro.chuma.website'
echo 'Lee docs/AI_OVERLAY_V07_ES.md antes de activar.'
printf 'Rollback: bash %q\n' "$REPO/scripts/restaurar_v07.sh"
