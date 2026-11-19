# AWS Lambda, Home Assistant and Alexa Smart Home integration

**Important distinction:** this package includes `lambda/lambda_function.py`, a proposed public rewrite of the earlier repository Lambda. We did **not** retrieve the Lambda currently deployed to the author's AWS account. Reproduce the v3 Smart Home handshake in a dedicated test skill first; account linking requirements vary by setup.

## Requirements

- Home Assistant with an accessible `/api/alexa/smart_home` endpoint over HTTPS and exposed Alexa-compatible camera entities.
- Amazon Developer account with an Alexa Smart Home skill, correctly configured account linking / OAuth token flow, and an Alexa device/account where the skill is enabled.
- AWS account and Lambda runtime that supports Python 3.13; Lambda permission allowing Alexa Smart Home to invoke the function.
- Public **HTTPS** URL to the signed HLS gateway, such as `https://YOUR_HLS_HOST.example.net`.
- The exact Alexa endpoint IDs used in Home Assistant discovery. Verify them from sanitized discovery results, not from assumptions.

For official details, read [Alexa.CameraStreamController](https://developer.amazon.com/docs/alexaplus/device-apis/alexa-camerastreamcontroller) and the [Home Assistant Alexa Smart Home integration](https://www.home-assistant.io/integrations/alexa.smart_home/). Both HLS and RTSP are supported in the Alexa API; this project specifically provides an HLS conversion pipeline.

## 1. Prepare an isolated test Lambda

Create a Lambda function using Python 3.13, entry point `lambda_function.lambda_handler`, and upload the complete `lambda/lambda_function.py` source. No third-party pip dependency is required. Use a custom test skill first, rather than replacing an existing production skill. Limit IAM permissions and avoid request/response logging that leaks bearer tokens or camera URLs.

## 2. Environment variables

| Name | Example value | Description |
|---|---|---|
| `HOME_ASSISTANT_URL` | `https://ha.example.net` | HTTPS Home Assistant address reachable from Lambda |
| `ALEXA_HLS_BASE` | `https://hls.example.net` | HTTPS hostname for Nginx/Tunnel |
| `CAMERA_ENDPOINT_MAP_JSON` | `{"camera#front_door":"front_door"}` | Alexa endpointId to slug mapping |
| `HLS_SIGNING_KEY` | **private value** | Exact content of the local file `local/secrets/hls_signing_key` |

**Never** commit real values or screenshot `HLS_SIGNING_KEY`. Use AWS encrypted environment configuration and tightly restricted IAM permissions, or AWS Secrets Manager in a hardened deployment. The current reference handler uses an environment variable to minimize dependencies; migrating to Secrets Manager would require corresponding code changes.

Generate a sanitized example map locally:

```bash
python3 - <<'PY'
import json
c=json.load(open('config/cameras.json'))['cameras']
print(json.dumps({x['alexa_endpoint_id']: x['slug'] for x in c}))
PY
```

The local HLS key file contains 64 hex characters created by `openssl rand -hex 32`. Paste exactly those characters into the **private** Lambda configuration, never into a public issue or test transcript.

## 3. Configure the Alexa Smart Home skill

In the Amazon Developer Console, create/configure a Smart Home skill in your region and set its endpoint to the test Lambda ARN as required by Alexa. Configure account linking/OAuth so Alexa supplies the Home Assistant-compatible bearer token in directives; verify skill invocation permission and your Home Assistant manual Smart Home setup. Do not hardcode a long-lived Home Assistant token inside the source or disable TLS verification.

Expose only camera entities that you intend to make reachable by this skill. A sample YAML outline (verify against your Home Assistant version and account-linking choice):

```yaml
alexa:
  smart_home:
    filter:
      include_entities:
        - camera.front_door
        - camera.garage
    entity_config:
      camera.front_door:
        name: Front Door
        display_categories: CAMERA
      camera.garage:
        name: Garage
        display_categories: CAMERA
```

**Camera entity IDs and Alexa endpoint IDs can differ.** Observe a sanitized `Discover.Response` or camera request to confirm `endpointId` before editing the Lambda map. Home Assistant may expose camera entities differently based on platform/integration configuration.

## 4. How signed URLs work

On a recognized `Alexa.CameraStreamController.Response`, Lambda signs `expiry:slug` using HMAC-SHA256. Example path syntax (redacted):

`/s/EXPIRY/SIGNATURE/front_door/index.m3u8`

FFmpeg playlist references `segment_<number>.ts` relative to this path. The controller requires the same signature on every playlist/segment request. The reference Lambda URL expires after 30 minutes; the controller rejects links expired or more than 60 minutes ahead of its clock. Ensure the host time is synchronized by NTP.

The returned `authorizationType: NONE` refers to Alexa's stream authorization mode: **it does not mean the URL is openly accessible**. The signed URL acts as a temporary bearer credential. Do not log or share it. Also note that URL-bearing responses can appear in vendor audit logs; assess your privacy requirements.

## 5. Test sequence

1. Confirm Home Assistant discovery and correct endpoint IDs.
2. Test Lambda invocation with a **sanitized** Smart Home fixture. Never paste live tokens into GitHub.
3. Verify signed HTTPS HLS URL playback in a client over the Internet; confirm segment fetching and expired-link rejection.
4. Enable the test skill on a test Alexa account/device. Say "Alexa, show Front Door" (localized naming depends on skill/device language).
5. Record first-frame time, duration, 30s watchdog behavior after stop, and the camera/hardware/region used.
6. Keep the original live skill unchanged until the new flow passes all tests.

## Common failures

- Unauthorized Home Assistant response: check OAuth account linking, token scope, and HTTPS URL; do not log token values.
- Alexa discovers no cameras: check entity exposure and discovery response, endpoint IDs, account linking.
- Alexa shows a camera but no video: check signed URL, DNS/HTTPS, HLS playlist+segments, codecs and first-frame latency.
- 403: HMAC key mismatch, expired URL, wrong slug or server clock skew.
- 503: FFmpeg fails to start or playlist is not produced in time; inspect container logs privately.
