# Pro Max AI v0.7.0b1 — Recuadros sobre Alexa / Fire TV (BETA)

Esta versión añade una salida **HLS con recuadros de YOLOX incrustados** en los fotogramas H.264. Se activa por cámara y viene **apagada por defecto**. No se reemplaza Lambda, Skill, firma HLS, puertos ni dominio. Está probada localmente con video sintético MPEG-TS; **todavía NO se ha validado con un dispositivo Alexa real ni con el NVR del autor**.

## 1. Qué cambió y cuánto consume

- OpenCV llama `grab()` por fotograma RTSP y `retrieve()` cuando toca inferir. Evita crear un fotograma BGR completo en cada iteración, pero **sigue decodificando RTSP**.
- En **Road mode**, YOLOX-Nano analiza un fotograma por segundo aproximadamente. No hay inferencia a 15 FPS ni seguimiento óptico por fotograma.
- FFmpeg toma las últimas cajas almacenadas en el volumen privado y actualiza hasta **4 rectángulos** mediante `zmq` + `drawbox` en su propio transcodificador H.264. No se abre un segundo pipeline FFmpeg para la salida HLS.
- Los fotogramas HLS continúan a la tasa configurada en la cámara (normalmente 15 FPS); **las cajas cambian aproximadamente cada segundo** y pueden tener retraso espacial respecto al vehículo. El HLS añade latencia por su segmentación y búfer en Fire TV.
- **Las cajas quemadas en video requieren transcodificación**. Esta versión usa el preset de menor consumo de CPU `ultrafast` cuando el overlay está activado, a costa de menor eficiencia de compresión. No podemos garantizar menor consumo total sin medirlo.
- Máximo **una cámara con overlay HLS** configurada en esta beta para proteger el servidor de 4 CPU lógicas. Las otras siete siguen funcionando como antes.

## 2. Activación en Calle Gladiolos B

1. Abre `https://alexa-pro.chuma.website` y entra en **AI Detector**. Verifica que `Worker: running`, `Model: loaded` y **Calle Gladiolos B** tenga `Analyze this camera` + `Road mode` activados y guardados. Elige B porque los primeros eventos confirmados aparecieron en esa cámara. Si prefieres A, habilita la IA en A y deja B sin overlay.
2. En el panel principal, busca la cámara **Calle Gladiolos B** y pulsa **Edit**.
3. En el campo **AI boxes on Alexa / Fire TV (experimental)**, selecciona **On — burn detected boxes into HLS** y guarda. Si otra cámara tiene activado el overlay, primero desactívalo en la otra.
4. Espera a que acabe la sesión HLS existente (inactividad predeterminada 30 segundos), o reinicia **únicamente** esa cámara desde Diagnostics.
5. Abre esa cámara desde Alexa / Fire TV usando el mismo comando de voz y Skill de siempre. La imagen debería llevar cajas **verdes para personas** y **cian para vehículos/animales** cuando existan detecciones recientes. La salida HLS **no incluye rótulos de texto**; la interfaz AI Detector conserva etiquetas y porcentaje de confianza.
6. Si no salen cajas, pero sí video: comprueba que el AI Worker esté activo para la **misma cámara**, el Road mode y que `Model: loaded`. Si no sale video, desactiva el overlay en Edit y restablece la transmisión normal; consulta logs sin compartir URLs RTSP.

## 3. Diagnóstico y límites

```bash
# Estado y versión del mismo gateway
a=$(curl -fsS http://127.0.0.1:18099/api/state)
python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); print(d["version"], len(d["cameras"]))' <<< "$a"

# CPU y RAM durante la reproducción de Gladiolos en Alexa
docker stats --no-stream alexa_rtsp_bridge_pro_beta alexa_rtsp_bridge_pro_ai

# Solo las últimas líneas, sin URLs ni secretos
docker logs --tail 50 alexa_rtsp_bridge_pro_beta
docker logs --tail 50 alexa_rtsp_bridge_pro_ai

# Verifica el soporte de filtros FFmpeg en el contenedor
docker exec alexa_rtsp_bridge_pro_beta sh -c "ffmpeg -hide_banner -filters 2>/dev/null | grep -E ' zmq | drawbox '"
```

El ZMQ del controlador se limita a `127.0.0.1` **dentro del contenedor**, sin publicar ningún puerto nuevo. La metadata del detector se guarda en el volumen privado del bridge y caduca a los 2,5 segundos en Road mode (y según el intervalo en modo normal). No incorpora URLs RTSP ni claves.

## 4. Si no funciona

En **Edit** deja `AI boxes on Alexa = Off` y espera a la siguiente conexión HLS; así se vuelve a la ruta anterior.

Para restaurar todo el código anterior, ejecuta desde el clon GitHub en Ubuntu:

```bash
bash "$HOME/alexa-publicacion-v03.b018az/repo/scripts/restaurar_v07.sh"
```

Escribe `RESTAURAR` cuando lo solicite. Se conservan el volumen y las ocho cámaras. Como alternativa usa la ruta real de tu clon si el script se publicó desde el directorio alternativo.

## 5. Pruebas pendientes antes de afirmar compatibilidad

- Reproducir 10–30 minutos en Fire TV y registrar CPU, latencia primer segmento, pérdida de frames y recuperación de FFmpeg.
- Comparar overlay OFF y ON en la misma cámara con iguales fps, resolución y bitrate.
- Verificar recuadros en movimiento rápido y comprobar si se desfasan por la baja frecuencia de inferencia.
- Detectar GPU/VA-API/Quick Sync del host antes de prometer aceleración hardware.

**Esta beta no garantiza cuadros perfectamente sincronizados con cada fotograma, ni 25/30 FPS de inferencia.** La velocidad de la vista de Alexa y la de YOLOX son parámetros independientes.
