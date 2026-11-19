# Actualizar la instalación existente de Pro Max 0.2 a 0.3

Este procedimiento actualiza **el mismo contenedor** `alexa_rtsp_bridge_pro_beta` sobre `~/alexa-promax-test` sin abrir un nuevo panel, sin crear un subdominio y sin cambiar la política de Cloudflare Access.

- Administración sigue en `alexa-pro.chuma.website`, que debe estar protegida por Cloudflare Access.
- Puertos del host `18099` (UI) / `18090` (HLS), mediante la `.env.pro` existente.
- Docker Compose conserva su proyecto, nombre de contenedor y volumen `alexa-promax-test_bridge_pro_data`.
- No se modifica la Lambda original ni Home Assistant.

## Paso a paso

1. Publicar **el código fuente extraído**, no solo un ZIP, en la rama principal de GitHub. Consultar [PUBLICAR_EN_GITHUB.md](PUBLICAR_EN_GITHUB.md).
2. Desde Ubuntu, obtener una copia temporal del repositorio:

```bash
mkdir -p ~/alexa-actualizacion
cd ~/alexa-actualizacion
git clone --depth 1 https://github.com/RenanEspinar/Alexa-RTSP-Bridge.git fuente
```

3. Examinar el script de actualización y ejecutarlo con confirmación:

```bash
cd ~/alexa-actualizacion/fuente
bash scripts/actualizar_existente.sh --check
bash scripts/actualizar_existente.sh --apply
```

El script realiza respaldo del código original y del volumen del contenedor, conserva `.env.pro`, valida el Compose, reconstruye la imagen y revisa `GET /api/state` hasta que informe `0.3.0b1`. No ejecuta `down -v`.

4. Abre **https://alexa-pro.chuma.website** y actualiza con Ctrl+F5. Aparecerá **Setup wizard** en el menú lateral, aun si ya había cámaras configuradas. Comprueba cámaras, `Probe`, `Snapshot`, y que `docker stats` vuelva a reposo tras la prueba.

## Deshacer una actualización

Si el script falla, mostrará la ruta de respaldo. La reversión necesita revisar primero logs; no se borrarán datos automáticamente. En caso necesario se restaura el código `alexa_bridge` y se reconstruye la imagen de la versión anterior usando `docker compose ... up --build -d`. No ejecutes `docker compose down -v`.

**No hay garantía de compatibilidad de esquemas a futuro**, por eso se respalda el volumen aunque en esta versión el modelo de almacenamiento del gateway no cambió.
