# Alexa / AWS Lambda — guía de integración

**Advertencia:** esta parte requiere acceso a tus cuentas de Amazon Developer y AWS. El wizard solo orienta; no crea credenciales, no conecta cuentas ni despliega Lambda automáticamente. Haz primero una **skill de prueba** sin afectar la integración que ya funciona.

## Arquitectura

1. El usuario pide a Alexa mostrar una cámara expuesta por Home Assistant.
2. Alexa envía una directiva Smart Home a AWS Lambda.
3. Lambda reenvía a `https://TU_HOME_ASSISTANT/api/alexa/smart_home` con el token OAuth de la directiva.
4. La respuesta de cámara se modifica para apuntar a `https://TU_GATEWAY_HLS/s/.../.../slug/index.m3u8`.
5. El gateway verifica la firma, inicia FFmpeg bajo demanda y entrega playlist `.m3u8` y segmentos MPEG-TS `.ts`.
6. Tras el tiempo de inactividad configurado, se detiene el proceso FFmpeg.

## Requisitos de Alexa

- Integración Smart Home de Home Assistant configurada y cámaras expuestas.
- Alexa Smart Home skill en Amazon Developer Console, con *account linking* a Home Assistant.
- Función AWS Lambda autorizada a recibir invocaciones de la skill; handler `lambda_function.lambda_handler` y runtime compatible con Python 3.13.
- Endpoint HTTPS público de Home Assistant accesible desde Lambda y endpoint HTTPS de **HLS** accesible desde el relay de Alexa, sin desafío de login interactivo.
- Nombres de endpoint exactos (`endpointId`) descubiertos por Alexa; no inferirlos a partir de `camera.solario`.

Documentación oficial: [Home Assistant Alexa Smart Home](https://www.home-assistant.io/integrations/alexa.smart_home/), [Amazon Smart Home Skill](https://developer.amazon.com/en-US/alexa/devices/connected-devices/development-resources/smart-home-skills).

## Implementación de prueba

1. En **Amazon Developer Console**, crea una skill Smart Home de prueba y configura *account linking* siguiendo la documentación de Home Assistant para tu región; no publiques tokens en repositorios.
2. Crea una función Lambda de prueba en AWS (Python 3.13 si está disponible), copia `aws/lambda_function.py`, establece el handler `lambda_function.lambda_handler` y concede el permiso de invocación a la Smart Home skill.
3. Añade variables privadas a Lambda:

| Variable | Contenido |
|---|---|
| `HOME_ASSISTANT_URL` | URL HTTPS base de Home Assistant, sin `/api/...` |
| `ALEXA_HLS_BASE` | URL HTTPS base del gateway firmado, sin ruta `/s/...` |
| `HLS_SIGNING_KEY` | Misma clave HMAC privada que usa el gateway; no publicarla |
| `CAMERA_ENDPOINT_MAP_JSON` | Objeto JSON `endpointId` → slug, por ejemplo `{"camera#ejemplo":"camara"}` solamente si coincide con tu descubrimiento real |

4. En la UI de Pro Max, **Copy endpoint map** proporciona los pares configurados. Si el mapeo está vacío, confirma en la respuesta de descubrimiento Alexa los identificadores exactos y completa las cámaras. No confundir ID de Home Assistant con `endpointId`.
5. En el panel, el botón **Reveal signing key** copia una credencial privada. Hazlo solo desde una sesión segura. La cadena de firma no debe aparecer en capturas ni en logs.
6. Antes de vincular la skill, verifica desde una red externa que una URL firmada del gateway entregue playlist y segmentos MPEG-TS; comprueba que una URL vencida devuelve 403. No publiques la URL firmada: es un token temporal.
7. Activa la skill de prueba con tu cuenta de Alexa, descubre las cámaras y solicita una en Fire TV/Echo Show.
8. Registra hora de petición, primer frame visible, funcionamiento continuo, detecciones de error, timeout y consumo del servidor. Solo después evalúa migrar la skill original.

## Separación de acceso

- `alexa-pro.chuma.website` puede servir el panel de administración **solo si está detrás de Cloudflare Access**. Una prueba anónima con `curl -I` debe ser redirigida al login.
- El relay de Alexa **no puede iniciar sesión en Cloudflare Access**. La ruta HLS necesita HTTPS y acceso basado en la propia URL temporal firmada; publica solo el puerto de medios (8090 dentro del contenedor), con reglas adecuadas para no exponer administración.
- Asegura clocks/NTP para evitar expiraciones incorrectas; no desactives verificación TLS.

## Problemas comunes

| Síntoma | Posible causa |
|---|---|
| Alexa muestra la cámara pero no video | HTTPS, segmento vacío/incorrecto, códec/perfil, tokens HMAC, WAF |
| 403 en medios | Firma vencida o distinta, slug erróneo, desfase horario |
| 503 en medios | Arranque RTSP o transcodificación falla/no produce segmento |
| Cuenta no vincula | Configuración OAuth / endpoints Amazon / token Home Assistant |
| Skill no descubre cámara | No está expuesta o `endpointId` no corresponde |

La Lambda incluida es un punto de partida verificable para una **skill propia**; los ajustes de account linking e IAM dependen de la región y de la consola de AWS, por lo que requieren validación actual antes de producción.
