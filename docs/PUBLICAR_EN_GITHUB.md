# Publicar Alexa RTSP Bridge Pro v0.3 en GitHub

La versión debe estar **extraída en la raíz del repositorio**, con los directorios `alexa_bridge/`, `custom_components/`, `docs/`, `tools/`, `benchmarks/` y el archivo `hacs.json`. Subir únicamente un `.zip` a GitHub permite descargarlo manualmente, **pero Marketplace/HACS no instalará su contenido directamente**.

## Procedimiento recomendado desde Windows

1. Descarga y extrae `Alexa_RTSP_Bridge_PRO_v0.3.0b1_GitHub.zip` en Descargas.
2. Comprueba que Git for Windows esté instalado y tu cuenta tenga acceso de escritura a `RenanEspinar/Alexa-RTSP-Bridge`.
3. En PowerShell, entra en la carpeta extraída y ejecuta `powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_V03_GITHUB.ps1`.
4. El script crea una copia temporal de la rama **main**, copia exclusivamente los archivos públicos del paquete, muestra `git diff --stat` y pide `SUBIR` antes de crear el commit y enviar a GitHub. Si no hay autenticación de GitHub, Git Credential Manager solicitará iniciar sesión.
5. Comprueba en https://github.com/RenanEspinar/Alexa-RTSP-Bridge que aparezcan `hacs.json` y `custom_components/alexa_rtsp_bridge/manifest.json` además de los manuales.
6. Comprueba en GitHub Actions que las pruebas funcionen. No presentes Marketplace/HACS como probado hasta hacer una instalación real.

## Publicación desde terminal Linux con Git autenticado

Clona tu repositorio en otra carpeta, copia los archivos de la distribución **sin secretos ni directorios privados**, ejecuta `git diff --check`, y luego `git add`, `git commit` y `git push origin main` con credenciales propias. No sobreescribas un repositorio remoto con `git push --force`.

## Protección de archivos

No subas `.env.pro`, `.env`, `local/`, `cameras.json`, `metadata.json` local, copias de volumen, `alexa-promax-resultados/` sin anonimizar, ni capturas donde aparezcan claves y tokens. Antes de subir, abre `git status` para ver todos los cambios.

## Estado de la publicación

El paquete entregado **no actualiza por sí solo la cuenta GitHub**. La conexión disponible al repositorio permite verificar su contenido, pero no autoriza escritura (403 para crear ramas). Por ese motivo, la operación de `git push` debe realizarse con tu sesión GitHub.
