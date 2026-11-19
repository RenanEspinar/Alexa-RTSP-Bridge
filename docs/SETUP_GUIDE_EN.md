# Alexa RTSP Bridge Pro — setup guide

This is a beta release. It includes a Docker RTSP/HLS gateway, browser setup wizard, Home Assistant integration, a Home Assistant OS app candidate, and a reference AWS Lambda handler. These are **separate** components.

## Docker gateway

1. Install Docker Engine and Docker Compose on a Linux host that can reach your RTSP cameras.
2. Clone the repository, copy `.env.pro.example` to `.env.pro`, and choose unused `UI_PORT` / `HLS_PORT`.
3. Run `docker compose --env-file .env.pro -f compose.pro.yml config -q` and `docker compose --env-file .env.pro -f compose.pro.yml up --build -d`.
4. Open the admin UI locally on `http://127.0.0.1:18099`, using an SSH tunnel or **authenticated** Cloudflare Access for remote viewing. The admin UI has no own login.
5. Run the four-step wizard: add a camera URL, test `Probe`, test `Snapshot`, test signed HLS, and review Alexa setup.

**Existing users:** see [in-place migration](MIGRAR_DESDE_V02.md); this updates the current Docker project and preserves its volumes and ports.

## Home Assistant

Home Assistant **2026.11 and later**: Settings → Marketplace → Add from link → paste this repo URL → select Integration → install → Devices & services → Add integration. Older installations: HACS custom integration repository. The integration reads metadata from the gateway and does **not** install Docker or Alexa.

Gateway URL must be reachable **from Home Assistant**, which is not necessarily the same URL as your browser. `127.0.0.1` works only when Home Assistant uses the host network namespace.

## Alexa / AWS

Create a test Alexa Smart Home skill, account-link it to Home Assistant, deploy `aws/lambda_function.py` as a test AWS Lambda, configure `HOME_ASSISTANT_URL`, `ALEXA_HLS_BASE`, `HLS_SIGNING_KEY`, and `CAMERA_ENDPOINT_MAP_JSON`. Add an HTTPS endpoint for signed HLS; Alexa's relay cannot complete interactive Cloudflare Access login. Do not replace your production skill until end-to-end playback is tested.

See [full Spanish documentation](GUIA_COMPLETA_ES.md) and [Lambda step-by-step](ALEXA_LAMBDA_ES.md) for precise instructions. No setup wizard can create AWS resources from your Home Assistant account by itself.

## Evidence

The Pro **0.2.0b1** engine handled eight NVR channels for a 60-second test window with mean 190.26% Docker CPU, peak 240.52%, 678.7 MiB peak memory, and 0 reported HTTP/client errors. The new 0.3 wizard/HA integration has not yet been independently field-tested. See [data and limitations](RENDIMIENTO_EXPERIMENTAL.md).
