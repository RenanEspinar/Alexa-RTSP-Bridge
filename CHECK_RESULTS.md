# Technical review — 2026-11-18

## What this package contains

Proposed public overlay for `RenanEspinar/Alexa-RTSP-Bridge`, constructed after reading the author's original `start-camera.sh`, `controller.py`, both Nginx configuration files and original server audit. It is **not** a copy of the author's private camera configuration or AWS Lambda deployment.

## Completed checks

- **9 Python unittest cases:** pass (camera configuration, validation, URL signing, expiry, Lambda rewriting, HTTP playlist and MPEG-TS access).
- **Python syntax:** compilation passed for controller, Lambda, generator and URL-signing helper.
- **Bash syntax:** `bash -n ffmpeg/start-camera.sh` passed.
- **Compose generator smoke test:** created 5 services (2 camera + 3 runtime), parsed as valid YAML/JSON, no RTSP password embedded.
- **Public package secret scan (patterns only):** no original Cloudflare token or real RTSP URLs copied.

## Not checked

- Docker Engine/Compose real deployment and image pulls (Docker CLI unavailable in the authoring container).
- AWS account linking, Lambda IAM permissions and actual deployed Lambda code.
- Home Assistant Alexa camera discovery identifiers in the author's live environment.
- Cloudflare Tunnel route and device compatibility.
- Camera models, 30-second shutdown under load, 1st frame delay, CPU/RAM, failover and long-term stability.
- GH Actions workflow on GitHub (not pushed).

## Security findings

- Previous original audit contained a Cloudflare Tunnel bearer token: rotate/revoke it before sharing the audit.
- Original controller had raw Docker socket access and host port 8080 exposed.
- Original repository Lambda logged whole directives and Smart Home responses; the proposed Lambda avoids logging sensitive payloads.
- Candidate still exposes Docker control through restricted proxy internally; this is a remaining privilege risk, not a complete sandbox.
- Signed video access is a new function and must be verified with the cloud/device under actual conditions.

## Delivery status

Ready **for review and isolated testing**, **not** ready to claim production-grade reproducibility or merge stable. The authenticated GitHub connection previously returned HTTP 403 on branch creation; the actual public repository remains untouched.
