# Reddit post draft — publish only after the full validation checklist

**Title**: I built an on-demand RTSP-to-HLS bridge for Alexa + Home Assistant, using Docker and FFmpeg

I wanted to view my existing RTSP cameras on an Alexa display without replacing my cameras or relying on each manufacturer's cloud integration. My setup uses an Alexa Smart Home Lambda proxy, Home Assistant, FFmpeg and Nginx behind HTTPS.

The interesting bit is on-demand streaming: requesting the HLS playlist starts the camera's FFmpeg container. A watchdog stops it after 30 seconds without playlist requests. In my reference installation I configured eight independent camera containers. This is a playlist-idle heuristic, not a device-disconnect callback.

I've published the installation guide, Docker Compose generator, camera configuration examples, security notes and a reproducibility test matrix here: [GitHub repository](https://github.com/RenanEspinar/Alexa-RTSP-Bridge).

The release candidate has per-camera RTSP secret files and expiring signed HLS links; **the new distribution still needs independent deployment testing**. If you've used Alexa CameraStreamController, Home Assistant, or FFmpeg on ARM/x86 hosts, I'd welcome technical feedback and reproducible tests. I'm especially interested in reported first-frame delay, HLS segment behavior and CPU use.

[Insert only verified screenshots, measured results and a demo video after tests. Do not share signed URLs, private video or credentials.]
