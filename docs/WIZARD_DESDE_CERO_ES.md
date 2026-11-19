# Alexa RTSP Bridge Pro — instalación desde cero para principiantes

**Versión:** 0.5.0b1, candidata a pruebas. **Objetivo:** abrir una cámara RTSP en Fire TV o Echo Show con la orden «Alexa, muéstrame [nombre]».

Esta guía **no presupone** que tengas una Skill, AWS Lambda, Cloudflare Tunnel o conocimientos de programación. Separa los pasos que la aplicación puede ejecutar de aquellos en los que debes iniciar sesión y autorizar cambios en servicios externos. Los nombres de menús pueden cambiar; los enlaces oficiales se verificaron el **19 de noviembre de 2026**.

**Importante:** el motor Pro 0.2 ya procesó ocho canales RTSP de un NVR durante 60 segundos por condición y mostró arranque/apagado automático. **La v0.4 y su instalación desde cero no están aún validadas de extremo a extremo con Alexa.** Un resultado positivo en RTSP/HLS no equivale a reproducción en Fire TV.

## 0. Qué necesitas y qué significa cada cosa

| Pieza | Qué hace | ¿Necesaria? |
|---|---|---|
| Cámara IP o NVR con RTSP | Entrega video local | Sí |
| Home Assistant | Descubre la cámara como entidad y enlaza Alexa | Sí para este flujo Alexa |
| Docker / HA OS | Ejecuta el gateway y FFmpeg | Sí |
| Alexa RTSP Bridge Pro | Convierte RTSP a HLS y protege segmentos con firmas | Sí |
| Dominio y HTTPS | Amazon necesita entrar desde Internet | Sí |
| Cloudflare Tunnel | Publica los servicios sin abrir el router; opción recomendada | Recomendado, sustituible por proxy seguro |
| Amazon Developer Console | Registra tu Skill Smart Home privada | Sí |
| AWS Lambda | Recibe las órdenes de Alexa y devuelve el HLS firmado | Sí |
| Marketplace/HACS | Instala sensores opcionales del gateway en HA | No sustituye Docker, Alexa ni AWS |

Enlaces: [Home Assistant](https://www.home-assistant.io/installation/), [Docker Engine](https://docs.docker.com/engine/install/), [Integración oficial Alexa Smart Home](https://www.home-assistant.io/integrations/alexa.smart_home/), [Amazon Developer Console](https://developer.amazon.com/alexa/console/ask), [AWS Lambda](https://console.aws.amazon.com/lambda/), [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/get-started/).

### Si todavía no tienes Home Assistant

Elige primero un método de instalación en https://www.home-assistant.io/installation/. En Home Assistant Container, necesitarás Docker y ejecutar el gateway como **otro servicio**. En Home Assistant OS puede probarse el empaquetado tipo app/add-on, que sigue siendo experimental: no lo presentamos todavía como instalador verificado de un clic.

### Si todavía no tienes una cámara agregada a Home Assistant

Conecta la cámara o NVR a tu red local y confirma que su URL `rtsp://...` reproduce video desde el servidor. Agrega su entidad de cámara a Home Assistant con una integración compatible (consulta [integraciones de cámaras y FFmpeg](https://www.home-assistant.io/integrations/ffmpeg/)). **No publiques la contraseña RTSP.**

## 1. Instala el gateway de video desde GitHub

Desde la terminal del equipo Linux que ejecuta Docker:

```bash
git clone https://github.com/RenanEspinar/Alexa-RTSP-Bridge.git
cd Alexa-RTSP-Bridge
cp .env.pro.example .env.pro
docker compose --env-file .env.pro -f compose.pro.yml config -q
docker compose --env-file .env.pro -f compose.pro.yml up --build -d
curl -fsS http://127.0.0.1:18099/api/state
```

El panel usa por defecto `127.0.0.1:18099` y HLS `127.0.0.1:18090` **en el host** (internamente 8099 y 8090). Es normal que una consulta inicial tarde en responder mientras el contenedor arranca. `docker compose ps` debe terminar indicando estado saludable. El código no necesita las claves de AWS ni de Cloudflare para iniciar.

**No cambies la publicación del panel a `0.0.0.0`.** No tiene autenticación de usuario propia. Accede con SSH o con Cloudflare Access autenticado. Para una instalación ya existente usa [el actualizador](MIGRAR_DESDE_V02.md), nunca `down -v`.

## 2. Abre Setup Wizard y agrega la primera cámara

En el panel selecciona **Install wizard → Agregar cámaras → + Agregar cámara**. Rellena:

- **Camera ID:** un identificador corto, por ejemplo `entrada`. Solo minúsculas, números y guion bajo.
- **Friendly name:** el nombre visible que usarás después en Alexa, por ejemplo `Entrada`.
- **RTSP URL:** dirección de tu cámara o NVR, con usuario, contraseña, IP privada y ruta del canal.
- **Video mode:** Auto.
- **FPS / Width / Height / Bitrate:** comienza con los valores propuestos; ajústalos según CPU y cámaras.
- **Alexa endpoint ID:** si aún no sabes el valor **déjalo vacío**. No inventes `camera#entrada`: no siempre coincide con Alexa.

Guarda. La aplicación almacena las credenciales en un volumen Docker privado y **no las devuelve en `/api/state`**.

## 3. Ejecuta tres verificaciones reales desde el wizard

**Detect codec:** conecta con RTSP y muestra códec, perfil y resolución de la fuente. **Capture JPEG:** solicita una imagen actual. **Check HLS:** pone en marcha FFmpeg, espera una playlist y comprueba que exista un segmento MPEG-TS no vacío con cabecera adecuada; muestra bytes y tiempo.

Si falla:

- **RTSP:** verifica IP privada, conectividad del contenedor al NVR, contraseña, ruta y puerto 554.
- **Snapshot:** la cámara puede tardar en iniciar o bloquear conexiones RTSP simultáneas.
- **HLS:** revisa `docker logs --tail 80 alexa_rtsp_bridge_pro_beta`. Un perfil H.264 High puede requerir transcodificación a Baseline.

**Esas comprobaciones no validan el reproductor de Alexa.** Se realizará una prueba final en el dispositivo.

## 4. Prepara Home Assistant para la Skill

Home Assistant tiene que ser accesible mediante un HTTPS **público con certificado válido** desde Lambda y desde el navegador de autorización OAuth. Confírmalo con datos móviles, sin conectarte a tu Wi-Fi.

Si Home Assistant no tiene habilitado Alexa Smart Home, agrega a `configuration.yaml` (adaptando el identificador de una cámara real):

```yaml
alexa:
  smart_home:
    filter:
      include_entities:
        - camera.entrada
```

**Si ya existe `alexa:` en el YAML, edita ese bloque en lugar de duplicarlo.** Valida la configuración, guarda y reinicia Home Assistant si hace falta. Para exponer más cámaras, amplía `include_entities`. La UI «Developer Tools → States» permite comprobar los IDs reales. Consulta la [guía oficial](https://www.home-assistant.io/integrations/alexa.smart_home/).

En el wizard introduce la dirección base, por ejemplo `https://ha.ejemplo.com`. Se generan las URL de OAuth más adelante, sin que tengas que escribirlas manualmente.

## 5. Crea Cloudflare y publica solo los servicios necesarios

1. Entra en [Cloudflare](https://dash.cloudflare.com/). Crea tu cuenta y agrega un dominio que controles. Para usar un hostname personalizado de Tunnel necesitas un dominio configurado en Cloudflare.
2. Abre [Cloudflare One → Tunnels](https://one.dash.cloudflare.com/), selecciona **Create Tunnel**, ponle un nombre e instala `cloudflared` siguiendo el comando mostrado para tu sistema operativo. Espera al estado **Healthy**.
3. En **Networking → Tunnels → tu túnel → Routes**, agrega una ruta tipo **Published application** para el **panel** (ejemplo: `admin.ejemplo.com` → `http://127.0.0.1:18099` si cloudflared corre en el mismo Ubuntu). **Configura Cloudflare Access antes de publicarla**, con una política Allow limitada a tu correo electrónico. Comprueba en incógnito que obliga a autenticarte. [Guía Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/).
4. Agrega **otro hostname solo para HLS** (`hls.ejemplo.com`) que apunte al puerto de medios del host `http://127.0.0.1:18090`, siempre que cloudflared esté instalado directamente en el mismo Ubuntu. **No protejas esta URL de medios con login interactivo de Access** porque el relay de Alexa no puede usarlo. El gateway rechaza URLs sin firma temporal.
5. Nunca crees una ruta HLS que apunte al puerto de administración `18099`. Si cloudflared corre dentro de otro contenedor, `127.0.0.1` se refiere a ese contenedor: necesitas una ruta privada de red adecuada.

Comprueba que `https://hls.ejemplo.com/s/test` devuelve **403** sin firma. Un **302** hacia Cloudflare Access bloqueará Alexa. Si ves **200** sin firma, detén la publicación y revisa la seguridad. [Manual oficial Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/get-started/).

## 6. Crea tu Smart Home Skill privada

1. Abre [Amazon Developer Console](https://developer.amazon.com/alexa/console/ask) con **la misma cuenta Amazon** de tu Fire TV / Echo Show.
2. Pulsa **Create Skill**.
3. Escoge un nombre como `Mis cámaras RTSP` y el idioma correspondiente a tu cuenta/dispositivo.
4. Elige el tipo **Smart Home**, NO Custom. En hosting elige **Provision your own**.
5. Finaliza la creación. En la pantalla Smart Home comprueba **Payload version 3** y copia tu **Skill ID** (comienza por `amzn1.ask.skill.`).

Deja esta pestaña abierta. Todavía no habrá respuesta hasta completar Lambda y account linking. [Documentación Smart Home oficial](https://developer.amazon.com/en-US/alexa/devices/connected-devices/development-resources/smart-home-skills).

## 7. Crea Lambda con el código que ya viene listo

1. Entra a [AWS Console](https://console.aws.amazon.com/) y comprueba que tienes una cuenta con acceso a AWS Lambda. Revisa [tarifas](https://aws.amazon.com/lambda/pricing/) y crea un [presupuesto/alerta](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html). La cuenta de AWS puede generar cargos según el uso.
2. Abre [IAM](https://console.aws.amazon.com/iam/) → Roles → Create role → AWS service → Lambda. Asigna la política `AWSLambdaBasicExecutionRole` para CloudWatch Logs. No concedas permisos administrativos globales.
3. Abre [Lambda](https://console.aws.amazon.com/lambda/) → Create function → **Author from scratch**. Ponle nombre `alexa-rtsp-bridge`, elige Python 3.13 u otra versión Python 3.x soportada y asigna el rol anterior.
4. **Región:** depende del locale Alexa. La documentación Home Assistant señala `us-east-1` (N. Virginia) para EE. UU./Canadá/Brasil, `eu-west-1` (Irlanda) para Europa/India y `us-west-2` (Oregón) para Japón/Australia. **Verifica la tabla oficial para tu idioma/cuenta**, no el país físico.
5. En Code source abre `lambda_function.py`, sustituye el ejemplo por el código completo del proyecto: [aws/lambda_function.py](https://github.com/RenanEspinar/Alexa-RTSP-Bridge/blob/main/aws/lambda_function.py). Pulsa **Deploy**. Handler: `lambda_function.lambda_handler`.
6. En el overview de Lambda: **Add trigger → Alexa Smart Home**; limita el permiso de invocación al **Skill ID** de tu Skill. AWS puede mostrar el ARN completo de la función; cópialo.
7. Vuelve a Amazon Developer Console → Skill → **Smart Home service endpoint** → **Default endpoint**. Pega el **Lambda ARN** y guarda.

**No instales la función original de Home Assistant sin adaptar**, porque nuestro gateway necesita que Lambda cambie el URI a una URL HLS firmada. El archivo incluido ya implementa ese intercambio. AWS autentica el trigger para la Skill específica. Guía oficial: [Lambda Python](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html).

## 8. Completa las cuatro variables de Lambda

AWS Lambda → tu función → **Configuration → Environment variables → Edit → Add environment variable**. Introduce:

| Nombre | Valor que debes usar |
|---|---|
| `HOME_ASSISTANT_URL` | `https://ha.ejemplo.com` (sin `/api` ni `/` final) |
| `ALEXA_HLS_BASE` | `https://hls.ejemplo.com` (hostname SOLO para medios) |
| `HLS_SIGNING_KEY` | Clave privada que genera el gateway, copiada con **Copy secret** del wizard |
| `CAMERA_ENDPOINT_MAP_JSON` | Mapa JSON de `endpointId` Alexa → ID de cámara local. El wizard puede copiarlo si tus cámaras tienen el ID exacto. |

Para el **primer descubrimiento de dispositivos**, puedes empezar con `CAMERA_ENDPOINT_MAP_JSON={}`: Lambda enviará las solicitudes de descubrimiento a Home Assistant sin modificar sus datos. Después de que Alexa descubra las cámaras, toma los `endpointId` reales de la respuesta `Alexa.Discovery.Discover` y completa el mapa. **No se deben deducir los endpointId** a partir de `camera.entrada` sin comprobarlos. Puedes consultar logs de Home Assistant/Alexa en un entorno privado y sin difundir el token OAuth; [guía de descubrimiento Home Assistant](https://www.home-assistant.io/integrations/alexa.smart_home/).

**La clave de firma no es el Client Secret de OAuth.** El gateway no guarda credenciales AWS. La Lambda incluida usa un secreto en variable de entorno: en un despliegue endurecido considera AWS Secrets Manager. [Variables en AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html).

## 9. Account linking: unir tu cuenta Alexa y Home Assistant

Dentro de tu Skill en Amazon Developer Console abre **ACCOUNT LINKING** y configura **Authorization Code Grant**, con `Credentials in request body` (no HTTP Basic). Los valores son:

| Campo | Valor |
|---|---|
| Authorization URI | `https://ha.ejemplo.com/auth/authorize` |
| Access Token URI | `https://ha.ejemplo.com/auth/token` |
| Client ID (Alexa US/BR) | `https://pitangui.amazon.com/` |
| Client ID (Alexa Europa) | `https://layla.amazon.com/` |
| Client ID (Japón/Australia, verificar) | `https://alexa.amazon.co.jp/` |
| Client Secret | Un valor privado configurado según la guía de Home Assistant; ese proveedor no lo valida como un secreto compartido convencional |
| Scope | `smart_home` |

**La barra final `/` del Client ID importa.** El wizard genera las URLs de los dos primeros campos y el Client ID según la región seleccionada. No pegues aquí secretos ni tokens. Lee atentamente la [sección oficial Account linking de Home Assistant](https://www.home-assistant.io/integrations/alexa.smart_home/), especialmente si la consola muestra campos nuevos.

## 10. Habilita la Skill y prueba una cámara en Alexa

1. Abre la app Alexa en tu teléfono, con la misma cuenta que usaste en Amazon Developer Console.
2. **Más → Skills y juegos → Tus Skills → Dev** (el nombre puede variar por región).
3. Abre la Skill que creaste y pulsa **Enable to use / Habilitar**.
4. Se abrirá el login de Home Assistant: entra con tu cuenta y autoriza la vinculación. No compartas el token.
5. Ordena «Alexa, descubre dispositivos». Confirma que aparece la cámara. Si falta el mapeo de endpoints, complétalo en Lambda y vuelve a guardar las variables.
6. En Fire TV o Echo Show di **«Alexa, muéstrame Entrada»** (usa el nombre real).
7. **Resultado satisfactorio:** aparece video **en movimiento**, no solamente una miniatura. Si no, comprueba la URL HLS firmada, permiso del túnel, Cloudflare WAF, perfil H.264 MPEG-TS, IDs y logs de Lambda.

Los usuarios nuevos no necesitan publicar su Skill en la tienda pública para probarla con su cuenta de desarrollador; verifica que la cuenta y la región sean compatibles.

## 11. Diagnóstico: por dónde empezar si falla

| Mensaje o síntoma | Primera acción |
|---|---|
| «No camera found» en la lista | RTSP mal configurado o entidad sin exponer en Home Assistant |
| JPEG OK, HLS no | FFmpeg, CPU, perfil H.264, puertos y timeout; revisa logs del contenedor |
| `HTTP 403` en URL sin firma | Comportamiento previsto |
| `HTTP 403` con firma vigente | Clave HMAC distinta entre gateway/Lambda, reloj, ruta modificada o TTL expirado |
| `HTTP 302` hacia login Access al pedir HLS | Has protegido erróneamente el hostname de medios con login interactivo |
| `HTTP 503` HLS | FFmpeg no obtuvo segmentos a tiempo o RTSP no responde |
| Alexa descubre pero muestra negro | Valida HTTPS, resolución de dominio, AWS relay/WAF, H.264 MPEG-TS, URI de Lambda y segmentos |
| Error al vincular cuenta | HTTPS de HA, Authorization URI, Client ID/región, Client Secret, grant type y token URL |
| No se pueden descubrir cámaras | Confirma `alexa.smart_home`, entidades expuestas y que la Lambda reenvía descubrimiento |
| Home Assistant Container sin «Add-ons» | Normal; utiliza Docker Compose para el gateway e instala solo la integración opcional vía Marketplace/HACS |

Consulta también los [issues del proyecto](https://github.com/RenanEspinar/Alexa-RTSP-Bridge/issues) y el [manual oficial de Home Assistant](https://www.home-assistant.io/integrations/alexa.smart_home/).

## 12. Mantenimiento y seguridad

- Administra el panel **solo desde localhost/SSH o Access**, nunca por un hostname abierto.
- Mantén una ruta independiente de HLS HTTPS sin login interactivo, donde la seguridad dependa de la firma temporal, su caducidad y controles de red adecuados.
- No subas `configuration.yaml`, `.env.pro`, los registros con tokens, URLs RTSP privadas ni los archivos del volumen a GitHub.
- Conserva respaldo del volumen de cámaras y el `.env.pro`. `docker compose down` conserva el volumen; `down -v` **lo borra**.
- Revisa el [informe de rendimiento](RENDIMIENTO_EXPERIMENTAL.md): la v0.2 midió 1, 4 y 8 canales del mismo NVR, con CPU pico 240,52 % y RAM pico 678,7 MiB en ocho; **no son requisitos mínimos ni garantía de Alexa**.
- Si se compartieron credenciales RTSP o tokens del túnel, cámbialos.

## Enlaces oficiales usados en el asistente

- https://www.home-assistant.io/integrations/alexa.smart_home/
- https://www.home-assistant.io/installation/
- https://www.home-assistant.io/integrations/marketplace/
- https://developer.amazon.com/alexa/console/ask
- https://developer.amazon.com/en-US/alexa/devices/connected-devices/development-resources/smart-home-skills
- https://console.aws.amazon.com/lambda/
- https://console.aws.amazon.com/iam/
- https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html
- https://developers.cloudflare.com/tunnel/get-started/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/


## Opcional: micrófono de cámara y diagnósticos

De manera predeterminada el sistema transmite **solo video**. En *Cameras → Edit* puedes cambiar a **AAC** cuando tu RTSP incluya audio. Prueba la cámara desde *Diagnostics → Probe A/V*, comprueba HLS y actualiza el mapa de Lambda. Para detectar problemas, *Diagnostics* muestra CPU/RAM, recuperaciones y un reinicio manual limitado a cámaras activas. Lee [Audio y diagnósticos](AUDIO_DIAGNOSTICOS_ES.md).
