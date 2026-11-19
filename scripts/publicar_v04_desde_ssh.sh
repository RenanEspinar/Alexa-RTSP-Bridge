#!/usr/bin/env bash
# Publicar la actualización v0.4 desde Ubuntu y, opcionalmente, aplicarla.
set -euo pipefail
umask 077
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$HOME/alexa-publicacion-v03.b018az/repo"
if [[ ! -d "$REPO/.git" ]]; then
  REPO="$HOME/alexa-publicacion-v04/repo"
  if [[ -e "$REPO" ]]; then echo "Existe $REPO sin repositorio .git. No se sobrescribe."; exit 1; fi
  mkdir -p "$(dirname "$REPO")"
  git clone --branch main https://github.com/RenanEspinar/Alexa-RTSP-Bridge.git "$REPO"
fi
cd "$REPO"
echo '=== Verificando origen y rama ==='
git remote -v | head -2
[[ "$(git branch --show-current)" == 'main' ]] || { echo 'Selecciona main antes de publicar.'; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'El repositorio tiene cambios locales. No se modificó.'; exit 1; }
git pull --ff-only origin main

FILES=(
  README.md RELEASE_MANIFEST.json
  alexa_bridge/CHANGELOG.md alexa_bridge/config.yaml
  alexa_bridge/promax/service.py
  alexa_bridge/promax/static/app.js
  alexa_bridge/promax/static/index.html
  alexa_bridge/promax/static/app.css
  custom_components/alexa_rtsp_bridge/manifest.json
  docs/GUIA_COMPLETA_ES.md docs/ALEXA_LAMBDA_ES.md docs/MIGRAR_DESDE_V02.md
  docs/WIZARD_DESDE_CERO_ES.md docs/START_FROM_ZERO_EN.md
  scripts/actualizar_existente.sh scripts/publicar_v04_desde_ssh.sh
  tests/test_hacs_package.py tests/test_install_wizard.py
  .github/workflows/pro-v03-checks.yml
)
echo '=== Instalando solo los archivos modificados ==='
for file in "${FILES[@]}"; do
  [[ -f "$SRC/$file" ]] || { echo "Falta archivo $file"; exit 1; }
  mkdir -p "$(dirname "$REPO/$file")"
  cp -a "$SRC/$file" "$REPO/$file"
done

echo '=== Pruebas de la nueva versión ==='
python3 -m unittest discover -s tests -q
bash -n scripts/actualizar_existente.sh
bash -n scripts/publicar_v04_desde_ssh.sh
if command -v node >/dev/null 2>&1; then node --check alexa_bridge/promax/static/app.js; fi

git add -- "${FILES[@]}"
git diff --cached --check
echo '=== Archivos modificados ==='
git -c core.pager=cat diff --cached --stat
if git diff --cached --quiet; then
  echo 'No había cambios pendientes de publicación.'
else
  git config user.name >/dev/null 2>&1 || git config user.name RenanEspinar
  git config user.email >/dev/null 2>&1 || git config user.email 43801533+RenanEspinar@users.noreply.github.com
  read -r -p 'Escribe SUBIR para publicar el código fuente en main: ' OK </dev/tty
  [[ "$OK" == 'SUBIR' ]] || { echo 'Cancelado antes del commit.'; exit 0; }
  git commit -m 'feat: add complete beginner Alexa installation wizard v0.4'
  git push origin main </dev/tty
fi

echo '=== Commit publicado ==='
git log -1 --oneline
printf '\nEl despliegue usará el contenedor actual, puertos 18099/18090 y su volumen.\n'
read -r -p 'Escribe ACTUALIZAR para desplegar v0.4 en el servidor, o Enter para salir: ' ANSWER </dev/tty
if [[ "$ANSWER" == 'ACTUALIZAR' ]]; then
  bash scripts/actualizar_existente.sh --check
  bash scripts/actualizar_existente.sh --apply
  echo '=== Estado tras actualización ==='
  docker inspect alexa_rtsp_bridge_pro_beta --format 'Estado: {{.State.Status}} | Salud: {{if .State.Health}}{{.State.Health.Status}}{{end}}'
else
  echo 'Solo se publicó GitHub. El servidor permanece intacto.'
fi
