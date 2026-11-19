#!/usr/bin/env bash
# Ejecutar DESDE EL PAQUETE extraído, en el mismo Ubuntu que guarda el repo Git.
set -euo pipefail
umask 077
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$HOME/alexa-publicacion-v03.b018az/repo"
EXPECTED='https://github.com/RenanEspinar/Alexa-RTSP-Bridge.git'

if [[ ! -d "$REPO/.git" ]]; then
  REPO="$HOME/alexa-publicacion-v05/repo"
  if [[ -e "$REPO" ]]; then echo "Existe $REPO; no se sobrescribió"; exit 1; fi
  mkdir -p "$(dirname "$REPO")"
  git clone --branch main "$EXPECTED" "$REPO"
fi
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || { echo 'La copia de Git no está en main'; exit 1; }
[[ "$(git remote get-url origin)" == "$EXPECTED" ]] || { echo 'El origen Git no coincide'; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Hay cambios locales pendientes. Aborta para no pisarlos.'; exit 1; }
git pull --ff-only origin main

FILES=(
 README.md RELEASE_MANIFEST.json
 alexa_bridge/CHANGELOG.md alexa_bridge/config.yaml
 alexa_bridge/promax/media.py alexa_bridge/promax/diagnostics.py
 alexa_bridge/promax/security.py alexa_bridge/promax/store.py
 alexa_bridge/promax/service.py
 alexa_bridge/promax/static/app.js alexa_bridge/promax/static/index.html
 alexa_bridge/promax/static/app.css
 aws/lambda_function.py
 custom_components/alexa_rtsp_bridge/manifest.json
 docs/AUDIO_DIAGNOSTICOS_ES.md docs/ALEXA_LAMBDA_ES.md
 docs/GUIA_COMPLETA_ES.md docs/MIGRAR_DESDE_V02.md
 docs/WIZARD_DESDE_CERO_ES.md docs/START_FROM_ZERO_EN.md
 scripts/actualizar_existente.sh scripts/publicar_v05_desde_ssh.sh
 tests/test_audio_recovery_diagnostics.py
 .github/workflows/pro-v03-checks.yml
)

echo '=== Copiando únicamente archivos de la versión 0.5 ==='
for file in "${FILES[@]}"; do
  [[ -f "$SRC/$file" ]] || { echo "Falta $file en el ZIP"; exit 1; }
  mkdir -p "$(dirname "$REPO/$file")"
  cp -a "$SRC/$file" "$REPO/$file"
done

echo '=== Pruebas locales ==='
python3 -m unittest discover -s tests -q
bash -n scripts/actualizar_existente.sh
bash -n scripts/publicar_v05_desde_ssh.sh
if command -v node >/dev/null 2>&1; then node --check alexa_bridge/promax/static/app.js; fi

git add -- "${FILES[@]}"
git diff --cached --check
printf '\n=== Archivos del commit ===\n'
git -c core.pager=cat diff --cached --stat
if git diff --cached --quiet; then
  echo 'GitHub ya contiene estos archivos.'
else
  git config user.name >/dev/null 2>&1 || git config user.name RenanEspinar
  git config user.email >/dev/null 2>&1 || git config user.email 43801533+RenanEspinar@users.noreply.github.com
  read -r -p 'Escribe SUBIR para publicar la v0.5 en GitHub: ' OK </dev/tty
  [[ "$OK" == 'SUBIR' ]] || { echo 'Cancelado: no se publicó nada'; exit 0; }
  git commit -m 'feat: opt-in AAC audio, diagnostics and FFmpeg recovery'
  git push origin main </dev/tty
fi
printf '\nGitHub: '
git log -1 --oneline
printf '\nEl despliegue reconstruye brevemente el contenedor actual y conserva el volumen privado.\n'
read -r -p 'Escribe ACTUALIZAR para desplegar en tu servidor actual, o Enter para salir: ' ANSWER </dev/tty
if [[ "$ANSWER" == ACTUALIZAR ]]; then
  bash scripts/actualizar_existente.sh --check
  bash scripts/actualizar_existente.sh --apply
  printf '\n=== Estado ===\n'
  docker inspect alexa_rtsp_bridge_pro_beta --format 'Estado: {{.State.Status}} | Health: {{if .State.Health}}{{.State.Health.Status}}{{end}}'
  echo 'https://alexa-pro.chuma.website'
else
  echo 'Solo publicamos GitHub. Pro Max permanece sin cambios en el servidor.'
fi
