# Validation matrix — do not mark passed without evidence

## Evidence currently available

| ID | Requirement | Current evidence | Verdict |
|---|---|---|---|
| V01 | Original HLS Nginx config syntactically valid | `nginx -T` succeeded in original server audit | Confirmed original setup |
| V02 | Original on-demand controller present and running | Container status and source captured | Confirmed original setup |
| V03 | Original eight FFmpeg containers exist | Docker inspect | Confirmed existence only; all stopped at snapshot |
| V04 | RC generator accepts camera list | Local unit tests | Static pass |
| V05 | RC HMAC URL validity, expiry and tampering | Local unit tests | Static pass |
| V06 | RC Lambda rewrites only matching camera response | Local unit tests | Static pass |
| V07 | Docker pulls/builds on fresh Ubuntu | Not executed against a Docker daemon | Pending |
| V08 | RTSP → HLS on new install | Not measured | Pending |
| V09 | First request starts FFmpeg | Not executed on new deployment | Pending |
| V10 | No playlist request for 30 sec stops stream | Not executed on new deployment | Pending |
| V11 | Camera 1 and camera 2 independently controlled | Not executed | Pending |
| V12 | Alexa Skill + AWS Lambda + HA + Echo Show | Live AWS account/device not tested | Pending |
| V13 | HLS URLs/segments never accessible with wrong signature | Unit-tested URL validator, not end-to-end | Partial |
| V14 | Signed links never appear in logs | Code inspection, not cloud logs | Partial |
| V15 | CPU/RAM/latency under real camera load | Not measured | Pending |

## Manual acceptance protocol

1. Use an isolated test host, one camera, valid RTSP credentials and no sensitive rooms.
2. Record Docker Engine/Compose version, CPU model, architecture and FFmpeg image digest.
3. Confirm `docker compose -f compose.generated.yml config -q` succeeds.
4. `--profile camera create`: verify camera container is created but not running.
5. Generate a signed HLS URL; play it with a local client; observe `alexa_cam_front_door` moves to running.
6. Verify playlist contains references to segments; retrieve at least one segment over the same signed path.
7. Stop the player and wait 35–45 seconds with no playlist requests; verify container is stopped.
8. Request again and verify restart; repeat 3 times.
9. With 2 cameras, request camera A and verify camera B remains stopped, then test both simultaneously.
10. Change one signature digit, send an expired timestamp, and try a guessed unsigned URL; all must fail (403 or 404).
11. Confirm invalid slug is rejected and neither controller nor Docker socket is published publicly.
12. Move to AWS/Alexa: verify discovery, command, signed URI playback, stop behavior, and repeat.
13. Measure per-camera first-frame delay (seconds), sustained CPU (%), RAM (MiB), outbound traffic (Mb/s) and any stream dropouts (count/hour).
14. Record source observations and signed-off environment; retain sanitized logs (never bearer tokens or real camera images in public issue).

## Known functional edge cases

- Slow RTSP startup may cause 503 after `STARTUP_TIMEOUT=12` seconds. Test with different cameras and reconnect times.
- FFmpeg `-hls_flags delete_segments` may delete a segment requested by a slow viewer; increase playlist length and expiration only after measurements.
- Background clients may continue requesting playlists even when the visible viewer closes, delaying shutdown.
- Concurrent requests can race on disk files and process state. The RC uses camera locks, but concurrency and failover require integration testing.
- Multi-architecture image availability varies by FFmpeg tag. Reconfirm compatibility on Raspberry Pi.

## Publication criterion

Do **not** call it one-command production-ready until V07–V15 are independently verified, and at least one external tester follows the install from scratch without private configuration. Publish it initially as an **experimental release candidate** with open test-matrix entries.
