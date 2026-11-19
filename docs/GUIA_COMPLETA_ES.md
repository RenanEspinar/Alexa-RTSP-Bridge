# Manual completo — Alexa RTSP Bridge Pro 0.3 Beta

**Ámbito:** Home Assistant Container sobre Ubuntu y Home Assistant OS. **Estado:** versión candidata; el wizard y la integración todavía requieren pruebas de aceptación en Home Assistant real.

## 1. ¿Qué instala cada componente?

| Componente | Responsabilidad |
|---|---|
| Gateway `alexa_bridge` (Docker) | Guarda las cámaras en volumen privado, ejecuta FFmpeg bajo demanda, entrega JPEG y HLS firmado |
| Dashboard/wizard (incluido en gateway) | Alta de cámaras, diagnóstico, configuración y orientación sobre los siguientes pasos |
| Integración `custom_components/alexa_rtsp_bridge` | Presenta sensores y estado del gateway dentro de Home Assistant |
| Smart Home Skill (Amazon) y AWS Lambda | Enlaza peticiones de Alexa con Home Assistant y sustituye las URL de video |
| HTTPS / Cloudflare Tunnel | Expone únicamente el tráfico HLS firmado que Alexa necesita; protege la administración separadamente |

**Importante:** Home Assistant Container no dispone de tienda de apps/add-ons. La instalación tipo Marketplace/HACS de una integración **no instala contenedores Docker**, ni crea habilidades Alexa automáticamente.

## 2. Requisitos

- Ubuntu/Linux x86_64 o ARM64, Docker Engine con `docker compose`, acceso a Internet para descargar las imágenes, y Python 3 para comprobaciones opcionales.
- Home Assistant en funcionamiento si deseas integrarlo con Alexa; para uso HLS local no es indispensable.
- Al menos una URL RTSP de cámara propia/NVR; acceso de red desde el contenedor al puerto RTSP (normalmente 554).
- Una IP/hostname del gateway accesible **desde Home Assistant**, no necesariamente desde tu navegador.
- Una cuenta Amazon Developer y AWS solamente para Alexa; dominio HTTPS y túnel/proxy para acceder desde la nube.

La máquina de ensayo tenía **4 CPU lógicas y 7,1 GiB RAM**; esto describe la máquina medida, **no constituye requisito mínimo**. El número de cámaras y la necesidad de transcodificar determinan el consumo.

## 3. Instalación Docker desde GitHub

```bash
git clone https://github.com/RenanEspinar/Alexa-RTSP-Bridge.git
cd Alexa-RTSP-Bridge
cp .env.pro.example .env.pro
# Ajustar UI_PORT / HLS_PORT si están ocupados
sudo ss -H -lnt | grep -E ':(18099|18090)[[:space:]]' || true
docker compose --env-file .env.pro -f compose.pro.yml config -q
docker compose --env-file .env.pro -f compose.pro.yml up --build -d
docker compose --env-file .env.pro -f compose.pro.yml ps
curl -fsS http://127.0.0.1:18099/api/state | python3 -m json.tool
```

Los valores de `.env.pro.example` corresponden a **puertos del host**, `18099` (panel) y `18090` (HLS), reenviados a `8099` y `8090` dentro del contenedor. El panel y el servidor HLS se enlazan solo a `127.0.0.1` por defecto. **No edites el archivo Compose para publicar el panel en `0.0.0.0`.**

Abre `http://127.0.0.1:18099` desde el propio Ubuntu o mediante túnel SSH. La aplicación web no implementa un login propio: su seguridad depende de que el puerto administrativo sea privado. Desde fuera de casa, puedes reutilizar un túnel de Cloudflare *con Access*; no necesitas uno nuevo si ya tienes el panel protegido.

### Si ya tienes la beta anterior

No clones el proyecto encima de la carpeta en producción. Utiliza [el procedimiento de actualización](MIGRAR_DESDE_V02.md), que preserva `compose.pro.yml`, `.env.pro`, los puertos y el volumen Docker de configuración.

## 4. Asistente de instalación — 4 pasos

**Paso 1 — Bienvenida y arquitectura.** Comprueba que el gateway se está ejecutando y comprende qué partes son locales y cuáles viven en AWS/Cloudflare.

**Paso 2 — Cámaras.** Pulsa *Add a camera* y configura: Camera ID (`[a-z][a-z0-9_]*`), nombre visible, URL `rtsp://usuario:clave@IP:554/ruta`, Alexa endpoint ID (solo si conoces el identificador exacto), `Video mode: Auto`, FPS, tamaño y bitrate. Un ejemplo de perfil de transcodificación es 960 × 540, 15 FPS y 1000 kbit/s.

**Paso 3 — Diagnóstico.** Pulsa *Probe* para obtener códec/perfil, *Snapshot* para una imagen JPEG y *Test HLS* para un enlace HMAC temporal. El diagnóstico de conectividad no garantiza reproducción en Alexa.

**Paso 4 — Alexa y HTTPS.** Sigue las instrucciones para configurar una ruta HTTPS accesible al relay de Amazon y preparar la Lambda de una **skill de prueba**. El wizard **no crea la skill ni configura tu AWS**.

Si ya tienes cámaras, abre **Setup wizard** en el menú lateral. Puedes continuar utilizando las cámaras existentes.

## 5. Configuración de video

- **Auto:** ejecuta `ffprobe`; usa `copy` solamente cuando el H.264 es compatible con el criterio implementado. En el ensayo de ocho canales todas las fuentes se transcodificaron (`transcode`), porque el origen era H.264 High.
- **Copy:** reempaqueta H.264 sin recodificar y normalmente usa menos CPU; solo úsalo si tu cámara tiene parámetros H.264, GOP e interoperabilidad adecuados. Su compatibilidad con Alexa no está validada automáticamente.
- **Transcode:** genera H.264 Baseline con parámetros controlados; consume más CPU, pero reduce la dependencia del perfil de entrada.
- **Snapshots:** imágenes JPEG capturadas por solicitud con una caché configurada; la disponibilidad de JPEG no garantiza miniaturas automáticas en Fire TV.
- **On-demand:** solo solicita RTSP cuando un cliente pide la playlist; se detiene tras la inactividad (`IDLE_TIMEOUT`, por defecto 30 s).

## 6. Integración en Home Assistant

**Home Assistant 2026.11 o superior:** ve a **Settings → Marketplace → Add from link**, introduce `https://github.com/RenanEspinar/Alexa-RTSP-Bridge`, elige el tipo *Integration* cuando se te pida y descarga. Como el repositorio también incluye la definición de una app para HA OS, Marketplace podría pedirte seleccionar explícitamente *Integration*; valida la instalación en tu versión. Después abre **Settings → Devices & services → Add integration → Alexa RTSP Bridge Pro**.

**Home Assistant anterior con HACS:** abre HACS → menú → *Custom repositories* → URL del repositorio → tipo *Integration*; descarga y reinicia Home Assistant cuando lo solicite. Consulta la documentación oficial de tu versión.

La integración solicita **Gateway URL**: la dirección desde la que **el contenedor Home Assistant** puede acceder a `/api/state`. `http://127.0.0.1:18099` solo funcionará si HA comparte red con el host (`network_mode: host`). Puedes comprobarlo con:

```bash
docker inspect homeassistant --format '{{.HostConfig.NetworkMode}}'
```

Si Home Assistant está en una red Docker separada, usa una red privada y el nombre de servicio/host adecuado, sin publicar la administración en Internet. La integración expone sensores de cámaras configuradas, streams activos y uptime. **No importa claves RTSP ni configura automáticamente las cámaras de Home Assistant.**

La integración suministrada es una beta y necesita validación funcional en una instalación real de HA; instalarla en Marketplace/HACS no prueba su funcionamiento por sí solo.

## 7. Home Assistant OS

Si utilizas HA OS, puedes probar la app contenida en `alexa_bridge/` desde un repositorio de apps compatible, **después** de verificar el empaquetado en HA OS. En este repositorio, `repository.yaml` identifica la colección y `alexa_bridge/config.yaml` define la app. El dashboard se diseña para Home Assistant Ingress y sirve por 8099; HLS firmado se sirve por 8090. HACS/Marketplace no instalan apps del Supervisor.

## 8. Alexa / Lambda / Cloudflare

Lee [ALEXA_LAMBDA_ES.md](ALEXA_LAMBDA_ES.md). Distingue dos rutas:

- **Administración:** URL protegida con Cloudflare Access; no debe estar disponible anónimamente.
- **HLS firmado:** ruta HTTPS accesible por el relay de Amazon sin login interactivo. Las rutas de video incluyen firma y vencimiento; evita exponer cualquier otra ruta administrativa por ese hostname.

No reemplaces la Lambda de tu instalación original hasta verificar la nueva versión de extremo a extremo.

## 9. Operaciones frecuentes

```bash
cd ~/alexa-promax-test  # o la carpeta real del clone
docker compose --env-file .env.pro -f compose.pro.yml ps
docker logs --tail 80 alexa_rtsp_bridge_pro_beta
docker stats --no-stream alexa_rtsp_bridge_pro_beta
# Detener sin eliminar volumen:
docker compose --env-file .env.pro -f compose.pro.yml down
# Arrancar nuevamente:
docker compose --env-file .env.pro -f compose.pro.yml up --build -d
```

**Nota:** `docker compose down` sin `-v` conserva el volumen de las cámaras. No ejecutes `down -v` salvo que quieras eliminar intencionalmente los datos. Antes de actualizar, respalda el volumen y la configuración. Ver [MIGRAR_DESDE_V02.md](MIGRAR_DESDE_V02.md).

## 10. Diagnóstico de errores

| Síntoma | Comprobar |
|---|---|
| Panel no responde inmediatamente tras `up` | Estado `health: starting`, logs y volver a consultar `/api/state` |
| No aparece imagen JPEG | Credenciales RTSP, canal y perfil, `Probe`, conectividad contenedor→NVR |
| `Probe` devuelve H.264 High / transcode | Normal; el modo automático prioriza formato de salida compatible |
| `Test HLS` copia URL pero no reproduce | El enlace tiene que ser solicitado desde donde la dirección base sea accesible. `127.0.0.1` no apunta a tu servidor desde otra PC |
| HLS 403 | URL firmada vencida o alterada, secreto no coincidente, reloj/NTP incorrecto |
| HLS 503 | FFmpeg no arrancó o no generó segmentos a tiempo |
| UI accesible sin login desde fuera | Verifica Cloudflare Access con `curl -sSI https://TU_HOST/`: debería redirigir al login |
| Error Cloudflare 1043 | Revisar asociación de aplicación Access/hostname/túnel, sin desactivar protección |
| Entidades HA no aparecen | Revisar Marketplace/HACS, recarga y ruta interna al gateway desde HA |
| Video negro en Alexa | Verificar HTTPS, HLS MPEG-TS, perfil H.264, firma, segmento y skill de prueba |

## 11. Datos y evaluación reproducible

Consulta [RENDIMIENTO_EXPERIMENTAL.md](RENDIMIENTO_EXPERIMENTAL.md). Los CSV anonimizados y el script que reproduce las gráficas están en `benchmarks/2026-11-19/`. La herramienta de ensayo está en `tools/benchmark_sostenido.py` y se ejecuta **solamente de forma controlada**:

```bash
python3 tools/benchmark_sostenido.py --concurrency all --duration 60   --admin http://127.0.0.1:18099 --hls http://127.0.0.1:18090
```

Realiza ensayos de carga solo en cámaras propias, comprobando antes capacidad de CPU/RAM. Los datos publicados son una única repetición por condición: no permiten afirmar superioridad frente a otros proyectos.

## 12. Seguridad y privacidad

No publiques `.env.pro`, `local/`, `metadata.json`, las URLs RTSP, claves HLS o logs que contengan tokens. Restringe `alexa-pro.chuma.website` con Access. Por riesgo de exposición previa, **rota credenciales de cámaras y tokens del túnel antes de una publicación masiva**. Ver [SEGURIDAD_ES.md](SEGURIDAD_ES.md).
