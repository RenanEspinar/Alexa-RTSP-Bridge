# Security and privacy audit

## Immediate action from original audit

The historical server audit showed a Cloudflare Tunnel bearer token in a container command line. **Treat that token as disclosed**. Rotate/revoke it in Cloudflare and update the running connector before sharing the audit. Verify the new connector is healthy. Redact old reports and avoid sending `docker inspect` command arrays unfiltered.

## Security model of this candidate

- Camera RTSP credentials live in ignored `local/secrets/<slug>.url` files with owner-only mode, not source code or Compose environment variables.
- Signing secret is a different owner-only file and in private AWS configuration. **Never reuse camera passwords as a signing key.**
- Nginx publishes only `127.0.0.1:8090` on the Docker test host. Controller and Docker proxy have no host ports.
- All HLS responses require a valid HMAC-SHA256 URL and time-window check. Playlist and MPEG-TS segments are both checked.
- HTTP access logs are disabled at Nginx and controller to reduce leakage of signed URLs. Cloudflare/host/enterprise edge logs may require independent configuration.
- RTSP streams are still accessible to the FFmpeg container over the camera network. Treat the camera network as sensitive.

## Residual risks — do not claim production hardened

1. **Docker control:** the controller talks through a Docker socket proxy with container lifecycle operations enabled. If the proxy/controller is compromised, an attacker may affect other containers. A `:ro` Docker socket mount does not make Docker API operations read-only. Stronger separation requires a dedicated Docker daemon/VM, rootless controls, or a very narrow custom broker authorizing only predefined containers and operations.
2. **Signed URLs are bearer tokens:** a leaked valid URL provides video access until expiry. Default 30-minute expiration and one-hour max future lifetime are convenience limits, not permanent authorization. A production implementation may need access scopes, revocation and shorter TTL.
3. **No viewer identity:** this reference signs by camera slug, not authenticated user; anyone possessing the signed URL can reuse it.
4. **Camera passwords in process arguments:** FFmpeg takes `-i rtsp://...` as a command argument internally. Avoid collecting process arguments or exposing Docker administration to untrusted users. The secret file prevents committing or showing secrets in the generated Compose file but does not prevent all runtime disclosure.
5. **HTTP origin security:** Cloudflare-to-host/connector routing must be properly restricted. Bind local Nginx to loopback; do not expose the origin service or tunnel connector admin APIs publicly.
6. **Upstream updates:** `latest` FFmpeg tag was selected to match the real setup, but is not reproducible by digest. Pin a tested digest for a stable release.

## Safe review checklist

- [ ] Rotate compromised Cloudflare token and remove it from any shared snapshots.
- [ ] Never upload real Home Assistant configuration, RTSP credentials, cloud API keys, signed HLS URIs or Alexa OAuth tokens.
- [ ] Use separate cameras or prerecorded non-sensitive video for public demos; blur identifying background details.
- [ ] Use a dedicated non-production Docker host for initial RC tests.
- [ ] Keep Docker proxy on internal network with no published port.
- [ ] Block broad inbound ports 8080/2375/8090 in firewall (8090 is loopback-only in the reference).
- [ ] Test invalid/expired HLS signatures result in 403 for playlists AND segments.
- [ ] Verify the cloud hostname serves ONLY intended paths.
- [ ] Remove default cameras/metadata that identify private locations from demos.
- [ ] Run a credential scanner before committing (e.g. `gitleaks`), and review `git diff --cached`.
