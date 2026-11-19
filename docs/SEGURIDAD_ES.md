# Seguridad y privacidad

## Superficies de red

1. **Administración (8099 interno; 18099 por defecto en host):** puede agregar cámaras, leer metadatos, generar enlaces firmados y revelar la clave HMAC. **No tiene login propio.** Publicarla directamente sería inseguro. Debe permanecer en loopback, SSH, Home Assistant Ingress o detrás de Cloudflare Access con política restrictiva.
2. **Medios firmados (8090 interno; 18090 en host):** genera playlist/segmentos/snapshot con HMAC y vencimiento. El relay de Alexa requiere HTTPS y no puede usar un login web interactivo. El acceso al medio debe limitarse al token de duración finita y al proxy configurado para ese fin.
3. **RTSP (NVR/cámaras):** la aplicación guarda URLs con credenciales en el volumen privado del contenedor. No copies esas URLs a tickets, README, vídeos o capturas.

## Reglas

- No commits de `.env.pro`, `cameras.json`, `metadata.json`, URLs RTSP, HMAC, tokens de Cloudflare, Amazon OAuth o AWS.
- Al publicar datos de rendimiento, utiliza solo IDs anónimos y elimina IP locales y nombre de host; los CSV anonimizados de este repo no contienen URLs RTSP.
- Revisa la política Cloudflare Access con solicitud anónima (`curl -sSI https://TU_UI/`), verificando redirección a `/cdn-cgi/access/login/`.
- No uses el hostname de administración como HLS si exige login de Cloudflare Access: el relay Alexa no puede completarlo.
- Si alguna credencial real ya se expuso en una conversación, captura o archivo, cámbiala en el NVR/servicio y actualiza las copias locales; evita confiar en que borrar un mensaje restaure el secreto.
- Respaldos del volumen: permisos `0700`, ubicación fuera del repositorio, y protección del disco/host.
- Las rutas HLS firmadas son credenciales temporales: no subirlas a GitHub ni capturarlas en herramientas de analítica o logs HTTP.

## Límites conocidos

La CSRF actual es un mecanismo contra peticiones no deseadas, **no equivale a autenticación**. Cualquier cliente que pueda acceder libremente al puerto de administración puede recuperar su estado y operar el gateway. El bloqueo de la interfaz mediante Access o Ingress no es opcional si se habilita acceso remoto.

El modo `copy` no garantiza decodificación por Alexa si el NVR produce GOP/PTS/SPS/PPS no compatibles. Mantén la skill original hasta comprobarlo.
