#!/usr/bin/env bash
# Publish selected v0.6 code changes, then optionally update SAME docker service.
set -euo pipefail
umask 077
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED='https://github.com/RenanEspinar/Alexa-RTSP-Bridge.git'
REPO="$HOME/alexa-publicacion-v03.b018az/repo"
if [[ ! -d "$REPO/.git" ]]; then
  REPO="$HOME/alexa-publicacion-v06/repo"
  [[ ! -e "$REPO" ]] || { echo 'Existe directorio v06 previo, no lo sobrescribo'; exit 1; }
  mkdir -p "$(dirname "$REPO")"
  git clone --branch main "$EXPECTED" "$REPO"
fi
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || { echo 'Se requiere rama main'; exit 1; }
[[ "$(git remote get-url origin)" == "$EXPECTED" ]] || { echo 'Origen Git inesperado'; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Cambios locales pendientes; abortando sin sobrescribir'; exit 1; }
git pull --ff-only origin main
FILES=(
 README.md RELEASE_MANIFEST.json compose.pro.yml .env.pro.example
 alexa_bridge/CHANGELOG.md alexa_bridge/config.yaml
 alexa_bridge/Dockerfile.ai alexa_bridge/requirements-ai.txt
 alexa_bridge/promax/ai_store.py alexa_bridge/promax/ai_engine.py
 alexa_bridge/promax/service.py
 alexa_bridge/promax/static/app.js alexa_bridge/promax/static/index.html
 alexa_bridge/promax/static/app.css
 custom_components/alexa_rtsp_bridge/manifest.json
 docs/PRO_AI_V06_ES.md
 scripts/actualizar_existente.sh scripts/instalar_ai_modelo.sh
 scripts/restaurar_v06.sh scripts/publicar_v06_desde_ssh.sh
 tests/test_ai_v06.py tests/test_hacs_package.py
 .github/workflows/pro-v03-checks.yml
)
for f in "${FILES[@]}"; do
  [[ -f "$SRC/$f" ]] || { echo "Falta $f en el paquete v06"; exit 1; }
  mkdir -p "$(dirname "$REPO/$f")"
  cp -a "$SRC/$f" "$REPO/$f"
done
python3 -m unittest discover -s tests -q
bash -n scripts/actualizar_existente.sh
bash -n scripts/instalar_ai_modelo.sh
bash -n scripts/restaurar_v06.sh
bash -n scripts/publicar_v06_desde_ssh.sh
if command -v node >/dev/null; then node --check alexa_bridge/promax/static/app.js; fi
git add -- "${FILES[@]}"
git diff --cached --check
git -c core.pager=cat diff --cached --stat
if ! git diff --cached --quiet; then
  read -r -p 'Escribe SUBIR para publicar v0.6 en GitHub: ' ANSWER </dev/tty
  [[ "$ANSWER" == SUBIR ]] || { echo 'No se publicó nada'; exit 0; }
  git config user.name >/dev/null 2>&1 || git config user.name RenanEspinar
  git config user.email >/dev/null 2>&1 || git config user.email 43801533+RenanEspinar@users.noreply.github.com
  git commit -m 'feat: optional local AI detection with events and feedback'
  git push origin main </dev/tty
fi
read -r -p 'Escribe ACTUALIZAR para instalar v0.6 sobre tu Pro Max actual: ' ANSWER </dev/tty
if [[ "$ANSWER" != ACTUALIZAR ]]; then echo 'Solo se publicó GitHub. Servidor intacto.'; exit 0; fi
bash scripts/actualizar_existente.sh --check
bash scripts/actualizar_existente.sh --apply
printf '\nAlexa permanece operativa; AI queda apagada por defecto.\n'
read -r -p 'Escribe INICIAR_AI para descargar el modelo verificado y arrancar el contenedor AI opcional: ' ANSWER </dev/tty
if [[ "$ANSWER" == INICIAR_AI ]]; then
  bash scripts/instalar_ai_modelo.sh
else
  echo 'Motor AI no instalado. Puedes instalarlo después con scripts/instalar_ai_modelo.sh.'
fi
printf '\nPanel: https://alexa-pro.chuma.website\n'
