# Alexa RTSP Bridge Pro — Home Assistant add-on

**Beta: test separately before relying on it for security monitoring.**

Home Assistant OS and Home Assistant Supervised support add-ons (now called apps). A plain Home Assistant Container installation does **not** expose the add-on store. Use the standalone Docker deployment in [PRO_MAX.md](../docs/PRO_MAX.md) instead.

## Install

In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**. Add:

`https://github.com/RenanEspinar/Alexa-RTSP-Bridge`

Install **Alexa RTSP Bridge Pro (Beta)**, start it, and open the Ingress panel.

In the panel, click **Add camera**. Enter a friendly name, unique lowercase ID, RTSP URL and optionally the exact Home Assistant Alexa endpoint ID (`camera#...`). Use **Probe** to inspect the codec, **Snapshot** to confirm access and view status.

The HLS server listens on port 8090; this port needs HTTPS ingress for the Alexa relay. The admin UI is separate on port 8099 and is protected by Home Assistant Ingress. Do **not** expose port 8099 directly.

The URL for each camera uses `/s/expiry/hmac/slug/index.m3u8`, signed with a secret generated privately on first boot. Use **Copy endpoint map** and **Reveal signing key** in the panel to configure the *experimental* Lambda from RC1. The signing key must match exactly. Use the same hostname and allow the returned URLs through your HTTPS tunnel; do not expose credentials in logs.

**Note:** the existing `aws/lambda_function.py` in the RC1 branch handles Smart Home camera playback. It is not a Home Assistant integration, and you still need to configure the Alexa Skill/AWS Lambda and OAuth correctly. See [ALEXA_AWS.md](../docs/ALEXA_AWS.md).

## Video behavior

- `auto`: runs ffprobe on startup; remuxes H.264 Baseline/Main with yuv420p when possible, otherwise transcodes.
- `copy`: refuses incompatible source codecs/profiles (no silent black screen).
- `transcode`: creates H.264 Baseline, yuv420p, 15 fps and 960×540 by default.
- Snapshots: generated **when requested**, then cached for 120 seconds. There is no permanent background snapshot polling.
- Watchdog: stops inactive streams after 30 seconds; attempts recovery after failed/stalled streams with backoff when recently requested.

**This add-on has not yet been validated on a fresh HA OS installation or an Echo Show.** Static tests do not prove universal compatibility.
