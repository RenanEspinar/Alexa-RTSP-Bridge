# Alexa RTSP Bridge Pro Max — análisis experimental verificable

**Fecha de ensayo:** 19 de noviembre de 2026 (timestamps UTC).
**Build:** v0.2.0b1.
**Fuente de datos:** salida de siete archivos CSV originales copiados del servidor Ubuntu, `run_20261119T134355Z`; extracción y normalización documental el 19/11/2026.
**Tamaño experimental:** un ensayo por nivel de concurrencia (1, 4 y 8 canales), 60 s sostenidos por nivel; 30 muestras de recursos en la fase sostenida por nivel.

## Resumen

Con ocho canales RTSP concurrentes en modo **transcode**, el cliente de prueba descargó **511 segmentos MPEG-TS distintos**, sin errores HTTP ni excepciones registradas, y observó el apagado de los ocho procesos al finalizar. El contenedor usó una media de **190,26 % de CPU Docker** (aproximadamente 1,90 de las cuatro CPU lógicas de la máquina), pico **240,52 %**, y memoria máxima **678,7 MiB**. El tiempo medio hasta el primer segmento fue **11,474 s** (mínimo 4,484 s; máximo 18,081 s).

No obstante, cuatro canales tuvieron un intervalo máximo superior a cinco segundos sin detectar un segmento nuevo; el mayor intervalo fue **11,343 s**. Sin inspección de PTS, fotogramas decodificados o imagen de salida, no se puede afirmar reproducción audiovisual continua, ausencia de congelamientos ni compatibilidad integral con Alexa.

## Mediciones por condición

| Canales | CPU media (%) | CPU pico (%) | Memoria pico (MiB) | Media primer TS (s) | TS distintos | Errores HTTP | Otros errores | Apagado |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 42,90 | 82,31 | 104,1 | 4,224 | 61 | 0 | 0 | Sí |
| 4 | 146,47 | 164,12 | 338,6 | 6,599 | 253 | 0 | 0 | Sí |
| 8 | 190,26 | 240,52 | 678,7 | 11,474 | 511 | 0 | 0 | Sí |

La desviación estándar **temporal** de las 30 muestras de CPU fue, respectivamente, **8,91**, **8,74** y **12,01 puntos porcentuales**. No representa variabilidad entre ensayos independientes: no hay repeticiones por condición.

![CPU por concurrencia](../figuras/cpu_vs_concurrencia.png)

![CPU temporal](../figuras/cpu_serie_temporal.png)

![Memoria temporal](../figuras/memoria_serie_temporal.png)

## Resultados individualizados: 8 canales

| Cámara anonimizada | Primer TS (s) | TS distintos | Volumen TS (bytes) | Mayor intervalo sin TS nuevo (s) |
|---|---:|---:|---:|---:|
| camera_01 | 12.495 | 64 | 8,396,644 | 3.337 |
| camera_02 | 12.950 | 65 | 8,556,820 | 2.883 |
| camera_03 | 8.488 | 65 | 8,446,840 | 7.342 |
| camera_04 | 18.081 | 61 | 8,064,260 | 1.612 |
| camera_05 | 10.483 | 64 | 8,376,340 | 5.346 |
| camera_06 | 16.264 | 63 | 8,313,548 | 1.607 |
| camera_07 | 8.546 | 65 | 8,480,492 | 7.287 |
| camera_08 | 4.484 | 64 | 8,364,496 | 11.343 |

![Tiempo hasta primer TS](../figuras/arranque_8_camaras.png)

![Brechas entre TS nuevos](../figuras/intervalos_maximos_8_camaras.png)

**Interpretación:** el indicador `max_gap_new_ts_s` caracteriza la mayor separación temporal entre descubrimientos de nuevos segmentos por el cliente de benchmark; no equivale automáticamente al intervalo real entre fotogramas, ni prueba por sí solo que el reproductor se congeló. El umbral de cinco segundos es un criterio de auditoría, no un requisito oficial de Alexa.

## Recursos y escalabilidad: límites de interpretación

- CPU Docker por encima de 100 % es admisible en contenedores multinúcleo: ~100 % representa una CPU lógica, y este host informó cuatro CPU lógicas. A ocho canales, la media fue equivalente al 47,57 % de su capacidad nominal total y el pico al 60,13 %. Esto **no prueba** que el procesador completo tenga holgura en todas las condiciones: otras aplicaciones también usan CPU y el hardware puede limitarse por temperatura o I/O.
- En ocho canales, la memoria creció de **627,0** a **675,9 MiB** entre la primera y última muestra sostenida, diferencia de **+48,9 MiB**, con pico de **678,7 MiB**. En 60 segundos no se puede determinar si es calentamiento de buffers, caché o una fuga de memoria. Repetir durante 10–30 min y revisar el estado posterior.
- El volumen total descargado y contado como TS distintos fue **66.999.440 bytes** para ocho cámaras. Si se divide por 60 s, equivale a aproximadamente **8,93 Mbit/s de datos TS entregados**, sin incluir HTTP y sin que ello demuestre el bitrate nominal por cámara.
- Los datos pertenecen a un **solo grabador/NVR multicanal**; las ocho fuentes no son muestras independientes de ocho dispositivos o fabricantes.
- Las ventanas de 60 s se realizaron **una única vez por concurrencia**. Un muestreo de CPU cada ~2 s genera 30 observaciones temporales correlacionadas, no 30 replicaciones experimentales.

## Método y definición de variables

- **Variable independiente:** número de canales RTSP solicitados concurrentemente: 1, 4, 8.
- **Variables dependientes:** demora al primer playlist y primer segmento TS, segmentos TS distintos descargados, errores, CPU Docker, memoria del contenedor y apagado por inactividad.
- **Modo de video:** `transcode` para todos los canales; no se ha probado `copy` en este conjunto.
- **Ventana sostenida:** 60 s después de que todos los canales entregan un primer segmento válido, según el script de benchmark.
- **CPU:** porcentaje agregado de Docker, no porcentaje normalizado a toda la máquina; 100 % ≈ una CPU lógica.
- **Memoria:** memoria contabilizada para el contenedor (MiB), no RAM total consumida por el sistema.
- **Errores:** códigos HTTP y errores capturados por el cliente; no representa métricas de decodificación, UDP, pérdidas de paquetes, o calidad de imagen.
- **Timestamps:** datos de adquisición en UTC; omitir nombre de host, datos personales, IP locales y credenciales de la publicación.

## Validaciones pendientes para un artículo original

1. **Tres o más ejecuciones independientes** para cada condición (1, 4 y 8); alternar el orden para limitar efectos de calentamiento y carga cruzada. Publicar media, desviación estándar entre repeticiones e intervalos de confianza si corresponde.
2. **Comparación controlada `copy` vs `transcode`** con el mismo conjunto de canales y configuración compatible, incluyendo el comportamiento de Alexa/Fire TV.
3. **Prueba larga (≥10 min)** y trazas HLS/PTS para investigar las cuatro brechas >5 s y si hay discontinuidades de reproducción.
4. **Validación extremo a extremo** Alexa/Fire TV: tiempo hasta primer cuadro decodificado, duración efectiva sin congelamientos y tasa de éxito con repeticiones.
5. **Línea base independiente** de la integración competidora en el mismo hardware, perfil de salida, RTSP, número de canales y entorno. No se puede afirmar superioridad sin ella.
6. **Reproducibilidad de entorno:** CPU concreta, SO/kernel, Docker, versión de FFmpeg, configuración de codificación, NVR y conectividad, en metadatos redactados antes de subirlos públicamente.

## Procedencia y privacidad

Los CSV normalizados en `datos/` preservan los valores obtenidos de la salida de terminal compartida. `resumen_derivado.csv` y las gráficas se recalcularon a partir de ellos. Los archivos originales del servidor se conservaron en `/home/renan/alexa-promax-resultados/run_20261119T134355Z` según el registro compartido; este paquete no incluye `metadata.json` porque no se revisó para detectar información de infraestructura privada.

Este documento representa **resultados preliminares de un único ensayo por condición**, adecuados para documentación transparente de GitHub y como material inicial para un manuscrito, no una validación comparativa concluyente. Para una revista, comprobar previamente su política sobre divulgación pública de resultados y preprints.
