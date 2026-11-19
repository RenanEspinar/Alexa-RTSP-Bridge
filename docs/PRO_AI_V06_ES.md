# Alexa RTSP Bridge Pro AI v0.6 — manual de instalación y verificación

**Estado:** beta experimental. No activa IA automáticamente; las cámaras, la Skill/Lambda, el HLS, el audio y Cloudflare anteriores permanecen sin cambios. Este manual se redactó para una instalación Ubuntu con Docker Compose ya operativa.

## 1. Qué hace y qué todavía no hace

La función **AI Detector** detecta personas, bicicletas, automóviles, motocicletas, autobuses, camiones, gatos y perros mediante un modelo [YOLOX-Nano](https://github.com/Megvii-BaseDetection/YOLOX) preentrenado en COCO. Los fotogramas se procesan localmente con OpenCV y ONNX Runtime. Norfair ayuda a seguir objetos en el tiempo. La primera inferencia tiene umbral configurable y la emisión de eventos exige observaciones repetidas y un período de enfriamiento.

Cada evento conserva hora UTC, cámara, clase, confianza y una fotografía JPG anotada. El usuario puede marcar **Correcto**, **Falsa alarma** o **Deshacer**. Los comentarios humanos no reentrenan automáticamente el modelo.

Limitaciones: **no** identifica personas, matrículas ni comportamientos complejos; no distingue un auto entrando de uno estacionado sin una zona/regla adicional; no garantiza detección de todos los objetos. **No genera por sí solo anuncios de voz dentro del flujo de Alexa**. El Fire TV seguirá reproduciendo video mediante el puente existente. Los resultados se deben validar contra imágenes reales.

## 2. Arquitectura y seguridad

```text
RTSP fuente principal ─→ contenedor bridge ─→ HLS firmado ─→ Alexa / Fire TV
           │
           └─→ (substream opcional) contenedor pro-ai ─→ OpenCV + YOLOX + Norfair
                                                   ├─→ /data/ai/events.sqlite3
                                                   ├─→ /data/ai/snapshots/ (privado)
                                                   └─→ HA event bus (opcional)
Panel privado ─→ /api/ai/* ─→ listado / confirmación / fotos
```

El contenedor `alexa_rtsp_bridge_pro_ai` no publica puertos. Se instala con el perfil Docker `ai` y tiene límite inicial de **0,75 CPU** y **768 MiB RAM**. Permite hasta dos cámaras, pero **se recomienda empezar con una sola**. Utiliza preferentemente un *substream* RTSP de ~640 × 360 píxeles: el stream principal puede consumir bastante CPU al decodificarse.

La API de fotos y configuración solo vive en el puerto administrativo ya protegido por Cloudflare Access. No existe ruta AI pública en el puerto HLS. No se exponen ni tokens ni contraseñas RTSP en JSON de administración. Las capturas se conservan 7 días por defecto (configurable de 1 a 30 días).

## 3. Actualización sin romper Alexa

En un teléfono, descarga el ZIP de la versión 0.6 y súbelo a la raíz `main` en [GitHub](https://github.com/RenanEspinar/Alexa-RTSP-Bridge/upload/main), usando Chrome > Sitio para computadoras > Choose your files > Commit changes. Después ejecuta el instalador SSH suministrado en la conversación. El instalador verifica SHA-256, publica cambios de código después de pedir `SUBIR`, respalda la instalación existente y pide `ACTUALIZAR` antes de reconstruir el gateway.

Para recuperar el sistema, el instalador mantiene un respaldo privado con el código, Compose, `.env.pro` y una copia de `/data`. La activación de IA es independiente del funcionamiento de Alexa.

## 4. Descargar el modelo preentrenado

El ZIP no redistribuye pesos. El instalador ofrece `INICIAR_AI`, lo cual descarga **únicamente desde el release oficial de YOLOX**:

[Modelo YOLOX-Nano oficial](https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx) (ONNX, entrada 416 × 416, clases COCO).

La descarga se verifica mediante SHA-256:

```text
c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d
```

Si el hash no coincide, el script **detiene el proceso**. Documentación upstream: https://github.com/Megvii-BaseDetection/YOLOX/blob/main/demo/ONNXRuntime/README.md . Código y pesos YOLOX: licencia Apache 2.0. Consulta los avisos oficiales de licencia.

## 5. Configuración en el panel web

1. Entra a https://alexa-pro.chuma.website y verifica que la versión sea `0.6.0b1`.
2. Abre **AI Detector**. El trabajador debe mostrar `disabled` o `waiting_for_camera`, con latido saludable. Si aparece `not_started`, todavía no se inició el perfil Docker.
3. En **Solario**, activa **Analyze this camera** y pulsa **Save camera AI**. No cambia su configuración RTSP de Alexa.
4. Si dispones de un substream RTSP, introdúcelo en el campo privado y guarda de nuevo. Si no, deja el campo vacío; el detector probará la URL RTSP existente y puede gastar más CPU.
5. En la parte superior marca **Enable AI detector**, define intervalo inicial `3 s`, confianza `0.45`, y pulsa **Save AI settings**.
6. Pulsa **Refresh**: estado `running` / `model loaded` cuando la fuente haya entregado fotogramas. Un `camera_offline` implica revisar RTSP, la dirección y credenciales. Si el escenario está estático es normal que no existan eventos.
7. Haz que una persona camine en la escena; espera dos o más inferencias y comprueba que aparezca captura con la etiqueta `PERSON`. Prueba después con un vehículo.
8. Pulsa **Correct** o **False positive**. Recarga la página: la etiqueta debe mantenerse en SQLite.
9. Abre la cámara **Solario** con Alexa, como siempre. Verifica que el video continúe fluyendo y que no aumenten anormalmente CPU o retardo HLS. **Esto verifica coexistencia con Alexa, no la voz TTS.**

## 6. Comandos de diagnóstico

Desde la carpeta de instalación existente `~/alexa-promax-test`:

```bash
# Estados (no imprime secretos)
docker compose --env-file .env.pro -f compose.pro.yml --profile ai ps

docker logs --tail=40 alexa_rtsp_bridge_pro_ai

# Datos básicos del bridge: versión y cantidad de cámaras
curl -fsS http://127.0.0.1:18099/api/state | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["version"],len(d["cameras"]))'

# Consumo de recursos por contenedor
docker stats --no-stream alexa_rtsp_bridge_pro_beta alexa_rtsp_bridge_pro_ai

# Apagar únicamente la IA; Alexa no se reinicia
docker compose --env-file .env.pro -f compose.pro.yml --profile ai stop ai

# Volver a encender únicamente la IA
docker compose --env-file .env.pro -f compose.pro.yml --profile ai start ai
```

Los eventos AI se guardan en el volumen del proyecto, no en un directorio expuesto al público. No publiques capturas que identifiquen a terceros ni logs con tokens.

## 7. Eventos de Home Assistant y notificaciones opcionales

El motor puede publicar un evento en Home Assistant llamado `alexa_rtsp_ai_detection`, con los campos `event_id`, `camera`, `category` y `confidence`. **No envía la imagen**. Esta función está desactivada si no configuras el endpoint y el token privado.

Agrega estos tres valores a tu `.env.pro` (sin publicarlos en GitHub):

```ini
AI_HA_URL=http://IP_PRIVADA_O_DNS_DE_HOME_ASSISTANT:8123
AI_HA_TOKEN=TOKEN_PRIVADO_DE_LARGA_DURACION
AI_HA_NOTIFY_SERVICE=mobile_app_NOMBRE_EXACTO_DEL_TELEFONO
```

`AI_HA_NOTIFY_SERVICE` es opcional. Es el identificador de servicio de notificación registrado en tu Home Assistant, sin el prefijo `notify.`. Al configurarlo y reiniciar **solo el contenedor AI**, el teléfono recibe un aviso informativo. La confirmación se hace en el dashboard Pro Max, protegido por Access.

Revisa [eventos de Home Assistant](https://www.home-assistant.io/docs/configuration/events/) y [notificaciones accionables](https://companion.home-assistant.io/docs/notifications/actionable-notifications/). Los botones de confirmación **desde la propia notificación** y la voz TTS mezclada en HLS son mejoras futuras; esta beta no los implementa.

## 8. Limitaciones y criterios de aceptación

* El detector está limitado por software a **dos cámaras** y por Docker a 0,75 CPU; puede analizar imágenes a intervalos mayores al configurado si la inferencia o decodificación son lentas.
* No se ha ejecutado un test real con los pesos y las cámaras del usuario en este entorno: se necesitan las pruebas indicadas arriba.
* Las 41 pruebas automáticas de la reconstrucción del repositorio son de integridad del software, seguridad de API, decodificación sintética y regresión de FFmpeg. No constituyen una validación estadística de precisión de detección.
* El nombre del contenedor Alexa, el volumen Docker, la ruta administrativa, la Skill y la Lambda no cambian.
* Para producción, evaluar mAP, *precision*, *recall*, falsas alarmas/día, capturas perdidas, consumo de CPU y latencia Alexa durante al menos 24 h. Priorizar precisión de eventos sobre cantidad de mensajes.
