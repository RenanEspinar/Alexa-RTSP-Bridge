#!/usr/bin/env bash
# Restore v0.6.0 code without modifying the persistent private data volume.
set -euo pipefail
APP="${ALEXA_EXISTING_DIR:-$HOME/alexa-promax-test}"
[[ -f "$APP/.last_promax_backup_path" ]] || { echo 'No hay respaldo registrado'; exit 1; }
BACKUP="$(cat "$APP/.last_promax_backup_path")"
case "$BACKUP" in "$HOME"/alexa-promax-backups/*-pre-v061) ;; *) echo 'Ruta de respaldo inesperada'; exit 1;; esac
for x in "$BACKUP/alexa_bridge" "$BACKUP/compose.pro.yml" "$BACKUP/env.pro.private"; do
 [[ -e "$x" ]] || { echo "Falta: $x"; exit 1; }
done
read -r -p 'Escribe RESTAURAR para regresar al código previo: ' ANSWER </dev/tty
[[ "$ANSWER" == RESTAURAR ]] || exit 0
cd "$APP"
rm -rf "$APP/alexa_bridge"
cp -a "$BACKUP/alexa_bridge" "$APP/alexa_bridge"
cp -a "$BACKUP/compose.pro.yml" "$APP/compose.pro.yml"
cp -a "$BACKUP/env.pro.private" "$APP/.env.pro"
docker compose --env-file .env.pro -f compose.pro.yml up --build -d --no-deps bridge
docker compose --env-file .env.pro -f compose.pro.yml --profile ai up --build -d --no-deps ai
printf 'Código anterior restaurado; volumen de cámaras y eventos conservado.\n'
