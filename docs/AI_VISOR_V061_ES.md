# Pro Max AI v0.6.1 — visor de recuadros y modo carretera

**Alcance:** actualización incremental desde v0.6.0b1. Mantiene el mismo contenedor, dominio, ocho cámaras y clave HLS. Este parche no añade cajas al HLS de Alexa.

## Lo que cambia

- En **AI Detector**, cada cámara tiene **View AI boxes**. Al abrirlo, el worker publica durante la sesión una imagen JPEG de la cámara con **todos los recuadros reales** y etiquetas (`car`, `truck`, `person`, etc.). El texto indica la antigüedad del fotograma, el tiempo de inferencia y los objetos. Actualización aproximadamente cada cuatro segundos; el muestreo del motor depende de la configuración.
- Las imágenes del visor se guardan temporalmente en el volumen privado y se borran al cerrar el visor. Una solicitud de visualización vence automáticamente si el usuario abandona la página. La interfaz administrativa requiere la misma protección actual (Cloudflare Access / Ingress). La ruta pública HLS **no** sirve las capturas.
- **Road mode** es opcional por cámara: analiza una muestra aproximadamente cada segundo, aunque la detección de movimiento no se dispare, y acepta un evento de vehículo en una sola observación cuando la confianza es **≥0,72**. Usa el cooldown general de 90 s por clase, salvo que ya se hubiese cambiado por API.
- Las cámaras sin Road mode conservan su configuración de detección existente. El contenedor AI sigue limitado por Compose a **0,75 CPU** y **768 MiB RAM**.

## Prueba concreta: Calle Gladiolos A

1. Abre `https://alexa-pro.chuma.website` y entra en **AI Detector**.
2. En **Calle Gladiolos A**, marca **Analyze this camera** y **Road mode (1s sampling; high-confidence traffic alerts)**. Guarda con **Save camera AI**.
3. Activa **Enable AI detector** (si todavía no está activado). Pulsa **Save AI settings**.
4. Pulsa **View AI boxes**. El primer fotograma puede tardar en llegar mientras se abre RTSP.
5. Cuando pase un vehículo, observa si aparecen cajas `car` / `truck` / `bus` en la vista. Un vehículo puede ser reconocido sin convertirse en evento si queda por debajo del umbral del modo carretera o dentro del cooldown.
6. Comprueba el rendimiento con `docker stats --no-stream alexa_rtsp_bridge_pro_beta alexa_rtsp_bridge_pro_ai` y solicita **«Alexa, muéstrame Gladiolos»** para comprobar que el HLS original sigue funcionando.
7. Si el procesador se satura, desactiva **Road mode**. Si no detecta nada, compara un fotograma del visor con el escenario y ajusta `Confidence` gradualmente (por ejemplo 0,35), anotando falsas alarmas.

## Limitaciones importantes

**No es un video fluido:** es una sucesión de muestras JPEG del procesamiento de OpenCV, pensada para calibración. No se garantiza detección de todo camión en carretera con una muestra por segundo ni que el modelo reconozca objetos pequeños/lejanos.

**Alexa/Fire TV:** su HLS entrega video H.264; el navegador dibuja o muestra cajas de forma independiente. Para que Alexa vea las cajas tenemos que incrustarlas en el video, con sincronización entre inferencia y FFmpeg, y una nueva prueba de compatibilidad y uso de CPU. Todavía no se ha implementado ni validado; anunciarlo antes sería incorrecto.

**Seguridad:** imágenes y etiquetas no se exponen en Internet anónimamente; el worker sigue sin puertos públicos. El navegador activa el visor mediante solicitudes autenticadas con CSRF y solo de cámaras configuradas.

**Precisión:** COCO/YOLOX-Nano no es un detector específico para el ángulo de tu NVR. Cuida reflejos, vehículos alejados, visibilidad nocturna, lluvia, resolución, movimiento y tamaño del objeto.

## Reversión

Si falla la versión del bridge o del worker, el instalador intenta restaurar ambos. Para volver manualmente al código anterior tras la instalación, ejecuta `bash ~/alexa-publicacion-v03.b018az/repo/scripts/restaurar_v061.sh` si esa es la carpeta del repositorio usada en el servidor. Nunca ejecutes `docker compose down -v` porque borraría el volumen de datos.
