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
