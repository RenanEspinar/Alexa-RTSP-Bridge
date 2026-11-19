# Architecture: original server vs public reference candidate

## Facts recovered from the running server (November 18, 2026)

- Host `homeserverv2`: Ubuntu 26.04.1 LTS, x86-64, four logical CPUs, 7.1 GiB RAM.
- Home Assistant and Cloudflare Tunnel were running. `alexa_ondemand` (`python:3.13-alpine`) was running on host port 8080; `alexa_hls_nginx` was serving on host port 8090.
- Eight per-camera FFmpeg containers existed and were stopped at the time of the snapshot. Their stopped state alone does not imply failure, because the original controller is designed to start on demand.
- `alexa_ondemand:/app/controller.py` uses the Docker Unix socket to call `GET /containers/{id}/json`, `POST /containers/{id}/start`, and `POST /containers/{id}/stop`.
- The controller serves only `/slug/index.m3u8`. It starts FFmpeg on first access, waits up to ten seconds for HLS to exist, and stops FFmpeg 30 seconds after its last playlist request. It has a five-second watchdog loop.
- Nginx proxies eight explicitly named playlists to the controller and serves MPEG-TS segments directly. `nginx -T` succeeded.
- Actual FFmpeg script: `/docker/alexa-bridge/start-camera.sh` searches the host's Home Assistant `configuration.yaml` using `awk`, extracts the configured RTSP URL, and transcodes H.264 baseline Level 3.1, 960×540, 15 fps, 1000 kb/s, one-second HLS segments, six-segment list.
- The live Lambda configuration **was not captured**. The public GitHub Lambda code is therefore only a repository reference, not proof of the Lambda currently deployed in AWS.

## Reproducibility problems found during the initial audit

1. Server's `start-camera.sh`, controller, multi-camera Nginx routes, and container creation workflow were not fully published.
2. The original FFmpeg launcher tightly couples to the author's Home Assistant YAML text and exact camera names.
3. The original controller connects directly to unrestricted `/var/run/docker.sock` and publishes HTTP port 8080 on all host interfaces.
4. Original HLS access has no signed-URL protection in the recovered Nginx/controller code, so a publicly shared playlist could reveal private video.
5. At the first review, `scripts/stop_all_ffmpeg.sh` contained Docker Compose YAML instead of a Bash script; this has been fixed in the cleanup package for `main`.
6. Installation, AWS account-linking, credentials handling, and device-specific tests are incomplete.

## What's changed in this package

- `config/cameras.json` defines camera slugs and Alexa endpoint IDs, without camera passwords.
- Each RTSP URL sits in `local/secrets/<slug>.url` (owner-only, gitignored) rather than being scraped from Home Assistant YAML.
- A Compose generator defines a stopped FFmpeg service per camera, plus Nginx, controller and Docker API proxy.
- Nginx listens only on localhost:8090; controller and Docker API proxy do not publish a host port.
- Lambda signs per-camera HLS URLs with HMAC-SHA256, and controller checks signature and time before serving playlists/segments.
- Nginx proxies both playlist and segments through the authenticated controller (the original server served TS segments directly from disk).
- The controller's watchdog continues to use **last playlist access**, not the last segment access or a definitive Alexa session signal.

## Deliberate limitations

- The Docker socket proxy reduces the number of available API endpoints but **still offers high-impact access to container lifecycle actions**. Treat this deployment as privileged infrastructure. Do not let untrusted clients reach its port.
- The signed URLs are temporary bearer credentials, not user accounts. Anyone holding a valid URL can view that stream until expiration (default Lambda 30 minutes). They must remain out of access logs and screenshots.
- On-demand startup is tested statically; actual first-frame latency, CPU load, signed stream compatibility with specific Alexa devices and clock skew remain unverified.
- FFmpeg images and upstream APIs can change; pin tested image digests before a reproducible stable release.
