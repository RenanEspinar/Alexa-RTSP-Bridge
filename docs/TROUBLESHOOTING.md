# Troubleshooting

| Symptom | First check | Typical corrective action |
|---|---|---|
| `configure.py` reports missing URL | `local/secrets/<slug>.url` | Create file with a full RTSP URL and `chmod 600` |
| `compose ... config` fails | Generated JSON/YAML and `.env` | Rerun `python3 tools/configure.py`; inspect Compose error |
| Camera container not found | `docker compose -f compose.generated.yml ps -a` | Run `--profile camera create`; do **not** start all with `up` |
| HTTP 403 HLS URL | Time, signature, secret or slug | Check NTP and that Lambda and controller use identical signing-key contents |
| HTTP 404 for TS segment | FFmpeg may have deleted segment | Increase list length after measuring stream delay; check if playlist is stale |
| HTTP 503 for first playlist | RTSP URL, camera, FFmpeg, container permissions | Private `docker logs alexa_cam_<slug>` and `STARTUP_TIMEOUT` |
| Container starts then exits | Camera URL wrong, codec inaccessible, encoding errors | Inspect FFmpeg logs and source RTSP stream |
| Nginx 502 | Controller not reachable | Check `controller` and `nginx` services, their common `media` network |
| Domain 502 / HTTPS error | Cloudflare origin target or connector status | Verify origin `127.0.0.1:8090` from host network only |
| Alexa discovers but cannot view camera | Lambda endpoint mapping, Smart Home response, cloud HTTPS HLS | Verify end-to-end signed URI with test client and device compatibility |
| Camera continues running | Player still polls playlist, watchdog not yet elapsed | Inspect playlist requests privately; wait at least 35–45 seconds with no polls |
| CPU too high | Realtime x264 at 960×540 | Reduce camera count, framerate/resolution, or test hardware acceleration |

## Suggested private diagnostics

```bash
# Safe commands to run on the isolated TEST host, not production:
docker compose -f compose.generated.yml ps -a
docker compose -f compose.generated.yml logs --tail 50 controller
# Replace with your own slug:
docker logs --tail 50 alexa_cam_front_door
```

**Do not share raw logs before reviewing them.** FFmpeg and reverse proxies may expose private RTSP URLs, signed links, endpoint identifiers or location names.

## Recovery

- If a secret leaked, rotate it. HLS signing key rotation instantly invalidates existing signed URLs and requires updating Lambda and restarting the controller; schedule this as a coordinated change.
- If camera doesn't stop, ensure the controller can reach Docker proxy and that the container's actual name matches `local/camera-map.json`.
- If all services are broken, use a separate test installation; never replace the author's production volume/container names while debugging this release candidate.
