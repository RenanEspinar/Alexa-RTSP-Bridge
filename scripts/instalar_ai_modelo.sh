#!/usr/bin/env bash
# Download and pin official upstream YOLOX-Nano. No model is bundled in the repository.
set -euo pipefail
umask 077
APP="${ALEXA_EXISTING_DIR:-$HOME/alexa-promax-test}"
cd "$APP"
[[ -f .env.pro ]] || { echo 'Falta .env.pro'; exit 1; }
docker inspect alexa_rtsp_bridge_pro_beta >/dev/null 2>&1 || { echo 'Bridge no está instalado'; exit 1; }
URL='https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx'
SHA='c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d'
MODEL="$(mktemp)";trap 'rm -f "$MODEL"' EXIT
printf '%s\n' '=== DESCARGANDO MODELO OFICIAL YOLOX-NANO ==='
curl --proto '=https' --tlsv1.2 -fL --retry 3 --max-time 180 "$URL" -o "$MODEL"
echo "$SHA  $MODEL" | sha256sum -c -
echo 'Checksum correcto. Instalando pesos en el volumen privado...'
docker exec alexa_rtsp_bridge_pro_beta sh -c 'umask 077; mkdir -p /data/ai/models; chmod 700 /data/ai/models'
docker cp "$MODEL" alexa_rtsp_bridge_pro_beta:/data/ai/models/yolox_nano.onnx
docker exec alexa_rtsp_bridge_pro_beta chmod 600 /data/ai/models/yolox_nano.onnx
echo '=== CONSTRUYENDO ÚNICAMENTE EL CONTENEDOR AI ==='
docker compose --env-file .env.pro -f compose.pro.yml --profile ai up --build -d --no-deps ai
# The AI process is safe at idle until the user explicitly enables AI in the dashboard.
echo '=== VERIFICACIÓN DEL MODELO ONNX EN EL CONTENEDOR ==='
docker exec alexa_rtsp_bridge_pro_ai python -c 'from promax.ai_engine import YOLOXNano; import numpy as np; m=YOLOXNano("/data/ai/models/yolox_nano.onnx"); z=np.zeros((1,3,416,416),dtype=np.float32); out=m.session.run(None,{m.input_name:z})[0]; assert out.shape==(1,3549,85),out.shape; print("YOLOX Nano ONNX OK:",out.shape)'
echo 'Modelo probado. Abre AI Detector, activa Solario y luego Enable AI detector.'
