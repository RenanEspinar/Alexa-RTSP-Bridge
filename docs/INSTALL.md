# Installation manual — isolated reference deployment

**Status: release candidate.** These instructions create a separate deployment; **do not execute them on the original live homeserver** until validation and backups are complete. Tested commands should be executed on Ubuntu/Debian with Python 3, Docker Engine, Docker Compose and `openssl` already installed.

## 1. Prepare the host

1. Verify Docker Engine (`docker version`) and Compose (`docker compose version`). Ensure the operator is authorized to access Docker. Docker privileges are approximately root privileges.
2. Ensure the RTSP camera is reachable from the Docker host, ideally over a trusted local LAN/VLAN.
3. Keep cameras and Docker services off publicly exposed ports. Reserve TCP port 8090 on **localhost** for local HLS.
4. Install/enable Home Assistant. Confirm the camera entity works locally in Home Assistant before setting up Alexa.
5. Copy the existing GitHub repository to a **test location** and overlay this release-candidate package. Keep the repo's original `images/` and `LICENSE` directory/file.

## 2. Create local camera configuration

From the repository root:

```bash
cp config/cameras.example.json config/cameras.json
cp .env.example .env
mkdir -p local/secrets local/hls
chmod 700 local/secrets
openssl rand -hex 32 > local/secrets/hls_signing_key
chmod 600 local/secrets/hls_signing_key
```

Edit `config/cameras.json` and set one row for each camera. Example:

```json
{
  "cameras": [
    {"slug": "front_door", "alexa_endpoint_id": "camera#front_door"},
    {"slug": "garage", "alexa_endpoint_id": "camera#garage"}
  ]
}
```

The `alexa_endpoint_id` value **must match** the ID in your real Home Assistant Alexa camera response; do not guess from the entity name. One endpoint ID maps to exactly one slug. Slugs must be lowercase letters, digits and underscores, starting with a letter.

For each slug, create a **private** text file containing only its full RTSP URL (one line). Example:

```bash
umask 077
nano local/secrets/front_door.url
nano local/secrets/garage.url
chmod 600 local/secrets/*.url
```

Illustrative URL format: `rtsp://USERNAME:PASSWORD@CAMERA_IP:554/Streaming/Channels/101`. Do **not** put credentials in JSON, Git history, screenshots, public log files, shell commands or issues.

## 3. Generate files and test syntax

```bash
python3 tools/configure.py
python3 -m unittest discover -s tests -v
```

`configure.py` validates secret-file permissions and creates `compose.generated.yml` plus `local/camera-map.json`; it **does not** contact Docker or upload credentials.

Review generated Compose and run `docker compose -f compose.generated.yml config -q`. If the image cannot be pulled on your architecture, stop here and verify a compatible LinuxServer FFmpeg image.

## 4. Create the camera containers without running them

```bash
docker compose -f compose.generated.yml --profile camera create
# Starts controller, Docker API proxy, Nginx; leaves camera containers stopped.
docker compose -f compose.generated.yml up -d dockerproxy controller nginx

docker compose -f compose.generated.yml ps -a
```

The pre-created FFmpeg containers are named `alexa_cam_<slug>`. **Do not run `docker compose --profile camera up -d`**: that would start all cameras continuously, defeating on-demand streaming.

**Important:** the Docker socket proxy is available only on a Docker internal network; it is not a complete security boundary. Use a dedicated test host or virtual machine and never expose the proxy to users.

## 5. Verify HLS on the private host

The generated controller accepts **signed** paths, not the original `/front_door/index.m3u8` URL. Use the local test helper, which reads the HLS key but never prints the key itself:

```bash
python3 tools/sign_url.py front_door
```

A URL resembling `http://127.0.0.1:8090/s/<expiry>/<signature>/front_door/index.m3u8` will appear. This **URL is itself a temporary credential**; use it privately and do not post it in issues or screenshots.

Open the URL in VLC or use `curl` from the server. The first request may wait while FFmpeg initializes. Check the camera container state and files:

```bash
docker compose -f compose.generated.yml ps -a
find local/hls -name index.m3u8
```

After stopping the viewer, do not make additional playlist requests. The container should stop in approximately 30–35 seconds. This measures playlist inactivity, not user inactivity.

## 6. Configure HTTPS ingress

An Alexa device needs to retrieve the returned HLS URL. In Cloudflare Zero Trust, create a Tunnel, install/connect your own `cloudflared` connector, and route a dedicated HTTPS hostname to `http://127.0.0.1:8090` **only if cloudflared runs on the host network**. For a normal bridge-networked cloudflared container, `127.0.0.1` refers to that container, not the host. Use the correct Docker network service URL instead.

Do not publicly expose controller port 8080 or the Docker proxy port 2375. Do not publish HLS outside HTTPS. The release candidate uses HMAC-signed URLs, but a valid captured URL can still be used until it expires.

Test the signed HTTPS URL from a separate network. Confirm playlist *and referenced MPEG-TS segments* work. Test invalid signatures and expired URLs: both must return 403.

## 7. Install/configure AWS Lambda and Alexa

Follow [ALEXA_AWS.md](ALEXA_AWS.md). The installed Lambda must use the **same secret bytes** from `local/secrets/hls_signing_key` as `HLS_SIGNING_KEY`; it must map Alexa endpoint IDs to camera slugs. Configure the Home Assistant Alexa Smart Home integration and Amazon Smart Home skill/account linking. This final stage cannot be validated without the user's accounts and an Alexa device.

## 8. Verify and record the result

Follow [VALIDATION.md](VALIDATION.md), capture sanitized logs, record first-frame time, average CPU and RAM use with one active camera, and test repeat starts, stoppage and concurrent camera requests. No success claim should be published before this stage.

## 9. Uninstall test instance

From the isolated test repository, run `docker compose -f compose.generated.yml --profile camera down` after ensuring it targets only the test project. This intentionally removes the test containers and network, not your camera/HA data. Do not delete `local/` unless you intend to delete the test credentials and temporary HLS files.
