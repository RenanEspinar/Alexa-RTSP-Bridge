# Audio opcional, diagnóstico y recuperación automática — Pro 0.5

**Estado:** beta. Probado mediante 31 pruebas locales, que incluyen generación real de segmentos MPEG-TS con video solamente y con audio AAC. Falta comprobar audio en Fire TV/Echo Show y estabilidad del recuperador con cámaras desconectadas en el servidor real.

## 1. ¿La música puede seguir sonando mientras se abre la cámara?

**No se puede garantizar.** El ajuste **Audio OFF** quita el audio de la cámara del archivo HLS; no controla el foco de audio de Alexa ni del sistema operativo Fire TV. Abrir la pantalla de una cámara puede pausar o suspender aplicaciones musicales aun cuando el HLS no contenga audio. Esta diferencia debe explicarse al usuario.

Referencia Amazon: [CameraStreamController](https://developer.amazon.com/docs/alexaplus/device-apis/alexa-camerastreamcontroller) acepta `AAC`, `G711` y `NONE`; [Fire TV audio focus](https://developer.amazon.com/docs/fire-tv/managing-audio-focus.html) describe la gestión de reproducción y foco.

## 2. Configuración por cámara

En **Cameras → Edit**, elige:

| Ajuste | Efecto | Recomendación |
|---|---|---|
| **OFF — video only** | `FFmpeg -an`, sin pista de audio. Lambda declara `audioCodec: NONE`. | Predeterminado, menor complejidad. |
| **ON — AAC** | Requiere audio RTSP y lo codifica en AAC mono, 48 kHz, 64 kbit/s. Lambda declara `audioCodec: AAC`. | Solo si deseas oír el micrófono de la cámara. |

**No usamos audio bidireccional** ni mezclamos avisos TTS en la pista. Para que un aviso de Alexa no interrumpa su música sería necesaria una validación específica de su comportamiento, no basta con insertar audio en HLS.

Si se activa AAC y el RTSP carece de pista de audio, el sistema genera un error de diagnóstico, no anuncia una pista inexistente. Usa **Diagnostics → Probe A/V** para comprobarlo. Los cambios se guardan en el mismo volumen privado de Pro Max.

## 3. Lambda: declaración compatible con el flujo

Después de cambiar la configuración de audio, abre **Copy endpoint map**. El resultado es JSON. Para una cámara con audio OFF se conserva el formato de antes:

```json
{"camera#sin_audio":"pasillo"}
```

Con AAC habilitado se genera un objeto:

```json
{"camera#con_audio":{"slug":"solario","audioCodec":"AAC"}}
```

Los ID son ilustrativos: usa los `endpointId` reales de la respuesta de descubrimiento de Alexa. Sustituye **únicamente** la variable privada `CAMERA_ENDPOINT_MAP_JSON` en la Lambda de prueba; el gateway y AWS deben coincidir. Verifica primero que FFmpeg produce una pista AAC real. No compartas el mapa completo si revela nombres de cámaras privadas ni copies claves HLS en incidencias públicas.

## 4. Diagnóstico

Abre **Diagnostics** en el menú lateral:

- **CPU/RAM:** el porcentaje de CPU del cgroup se expresa por núcleo lógico (100 % ≈ un núcleo); los valores pueden ser `—` si el host no expone métricas cgroup.
- **Probe A/V:** consulta los códecs y resolución del RTSP, sin mostrar usuario ni contraseña.
- **Test local HLS:** inicia FFmpeg, espera el primer segmento MPEG-TS y prueba que FFprobe lo reconozca y que FFmpeg decodifique el video. **No es una prueba de Alexa** ni de acceso HTTPS externo.
- **Restart if active:** reinicia solo esa cámara si está transmitiendo. Una cámara en reposo no arranca.
- **Eventos:** inicio, detención, fallos y recuperaciones sin URLs RTSP ni enlaces HLS temporales.

**Rutas de la API administrativa (solo local/Cloudflare Access):**

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/api/diagnostics` | CPU, RAM, estado, eventos |
| `GET` | `/api/events` | Últimos eventos |
| `POST` | `/api/diagnostics/camera/{slug}` | RTSP video/audio |
| `POST` | `/api/diagnostics/hls/{slug}` | Primer segmento HLS y decodificación |
| `POST` | `/api/restart/{slug}` | Reinicio manual, solo si activo |

Estas rutas exigen el valor CSRF obtenido a través de la sesión protegida del panel. **No son autenticación independiente**: el puerto administrativo debe permanecer privado.

## 5. Autorreparación y límites

Cada cámara tiene su propio proceso FFmpeg y un watchdog que se ejecuta aproximadamente cada 5 segundos:

1. Se inicia solo cuando un cliente solicita su playlist.
2. Si FFmpeg sale o la playlist/segmentos dejan de avanzar, registra el fallo.
3. Después de un tiempo de enfriamiento exponencial de **3, 6, 12, 24, 48 y hasta 60 segundos** puede reintentar **si siguen llegando peticiones recientes**.
4. No reinicia las otras cámaras. Si dejan de solicitar la playlist, se apaga después de `IDLE_TIMEOUT` (30 s por defecto).

Para evitar falsos positivos, no se considera estancamiento durante los primeros 20 segundos de arranque. Después, 15 segundos sin segmentos nuevos pueden activar la recuperación. Estas cifras son parámetros iniciales, no tiempos garantizados de disponibilidad ni SLA.

**Límites:** no puede arreglar fallos de red, contraseñas incorrectas, NVR apagado, pérdida del túnel o restricciones de AWS. El backoff protege el NVR frente a reintentos excesivos.

## 6. Prueba recomendada antes de activar AAC en Alexa

1. Confirma que las ocho cámaras siguen en Audio OFF; realiza una prueba HLS local con Solario.
2. Activa AAC **solo en una cámara que tenga micrófono**.
3. Ejecuta Probe A/V y Test local HLS. Comprueba que la pista AAC se genere (el primer TS puede incluir video y audio).
4. Copia la correspondencia `endpointId` desde la UI; actualiza la Lambda de prueba con `audioCodec: AAC`.
5. En Fire TV: compara apertura de cámara con/sin audio mientras Spotify u otra aplicación reproduce música. Registra modelo de Fire TV, versión de software, aplicación musical, si la música se pausa y si vuelve al cerrar la cámara.
6. Solo después de pasar las pruebas, habilita AAC en otras cámaras.

## 7. Resultados de rendimiento publicados

Las mediciones de 1, 4 y 8 cámaras en `benchmarks/2026-11-19` corresponden a **Pro 0.2, sin audio**, con un ensayo sostenido de 60 segundos por condición. La v0.5 añade funciones que pueden incrementar CPU/memoria, especialmente AAC. No atribuir el benchmark anterior a esta versión ni publicar superioridad no medida sobre otras soluciones.

## 8. Actualización y reversión

Ejecuta `scripts/actualizar_existente.sh --check` y luego `--apply` desde una copia del repositorio. Genera respaldo del volumen y del código original, conserva el mismo dominio, puertos y ocho cámaras. En caso de fallo al obtener la versión nueva, el script restaura el código anterior y reconstruye el contenedor. Verifica siempre `docker logs` y `/api/state` antes de activar audio.

No compartas el directorio de respaldo: contiene claves RTSP y la clave HLS.
