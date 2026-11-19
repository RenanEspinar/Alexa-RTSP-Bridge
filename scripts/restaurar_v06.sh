#!/usr/bin/env bash
set -euo pipefail
umask 077
APP="${ALEXA_EXISTING_DIR:-$HOME/alexa-promax-test}"
[[ -f "$APP/.last_promax_backup_path" ]] || { echo 'No hay respaldo registrado'; exit 1; }
BACKUP="$(cat "$APP/.last_promax_backup_path")"
case "$BACKUP" in "$HOME"/alexa-promax-backups/*-pre-v06) ;; *) echo 'Ruta de backup inesperada'; exit 1;; esac
for path in "$BACKUP/alexa_bridge" "$BACKUP/compose.pro.yml" "$BACKUP/env.pro.private"; do
  [[ -e "$path" ]] || { echo "No existe: $path"; exit 1; }
done
read -r -p 'Escribe RESTAURAR para recuperar el código previo (no borra cámaras): ' ANSWER </dev/tty
[[ "$ANSWER" == RESTAURAR ]] || exit 0
cd "$APP"
docker compose --env-file .env.pro -f compose.pro.yml --profile ai stop ai || true
rm -rf "$APP/alexa_bridge"
cp -a "$BACKUP/alexa_bridge" "$APP/alexa_bridge"
cp -a "$BACKUP/compose.pro.yml" "$APP/compose.pro.yml"
cp -a "$BACKUP/env.pro.private" "$APP/.env.pro"
docker compose --env-file .env.pro -f compose.pro.yml up --build -d --no-deps bridge
echo 'Versión previa restaurada. El volumen privado no fue eliminado.'
