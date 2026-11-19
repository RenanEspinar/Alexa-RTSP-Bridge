## v0.5.0b1 — Opt-in audio, diagnostics and recovery (preview)

- AAC microphone audio can be switched on per camera; OFF remains the default.
- Alexa Lambda maps AAC or NONE per camera (old string mappings still work).
- Diagnostics show video/audio probe, local HLS decoding, container CPU/RAM, retry state and sanitized events.
- Watchdog checks HLS segment freshness, restarts failed streams after bounded backoff, without affecting other cameras.
- Manual restart for active streams; idle cameras remain stopped.
- Data volume format is backward-compatible with 0.4.
- This release has automated tests but has not yet been validated with real Fire TV audio playback or a multi-day endurance run.

# Changes

## v0.4.0b1 (preview)

- Guided installation from scratch with 11 stages, bilingual links/instructions, non-secret browser-local progress and copyable AWS/OAuth values.
- Private `/api/check-hls/<slug>` endpoint to check an RTSP-derived MPEG-TS segment locally, requiring CSRF header.
- First-time setup manuals in ES and EN and updated migration/rollback version detection.
- Video pipeline and existing volume layout preserved; Alexa end-to-end wizard setup requires live testing.

# Changelog

## 0.2.0b1 — experimental

- Home Assistant add-on with Ingress admin panel and persistent camera settings.
- Standalone Docker deployment using the same application.
- Per-camera copy / transcode / auto selection and ffprobe diagnostics.
- Signed HLS playlists, segments and on-request cached JPEG snapshots.
- Per-camera idle timeout, stream status and watchdog with retry cooldown.
- Initial tests for configuration, validation, security and media command generation.
