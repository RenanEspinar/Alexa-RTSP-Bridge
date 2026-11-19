#!/usr/bin/env bash
# Restore source code and Docker images (leave private data volume untouched).
set -euo pipefail
APP="${ALEXA_EXISTING_DIR:-$HOME/alexa-promax-test}"
[[ -f "$APP/.last_promax_backup_path" ]] || { echo 'Respaldo no registrado'; exit 1; }
BACKUP="$(cat "$APP/.last_promax_backup_path")"
case "$BACKUP" in "$HOME"/alexa-promax-backups/*-pre-v07) ;; *) echo "Respaldo no es de v0.7";exit 1;; esac
for f in "$BACKUP/alexa_bridge" "$BACKUP/compose.pro.yml" "$BACKUP/env.pro.private";do
 [[ -e "$f" ]] || { echo "No existe $f";exit 1; }
done
read -r -p 'Escribe RESTAURAR para volver a la versión anterior sin borrar cámaras: ' OK </dev/tty
[[ "$OK" == RESTAURAR ]] || exit 0
cd "$APP"
rm -rf "$APP/alexa_bridge"
cp -a "$BACKUP/alexa_bridge" "$APP/alexa_bridge"
cp -a "$BACKUP/compose.pro.yml" "$APP/compose.pro.yml"
cp -a "$BACKUP/env.pro.private" "$APP/.env.pro"
docker compose --env-file .env.pro -f compose.pro.yml --profile ai up --build -d --no-deps bridge ai
printf 'Código y contenedores restaurados. Volumen privado y cámaras conservados.\n'
