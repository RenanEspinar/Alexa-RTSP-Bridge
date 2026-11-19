# Images, demonstrations and Reddit media checklist

**Do not fabricate screenshots.** The original GitHub repository already has `images/logo.png`, `images/banner.png`, `images/1000175247.jpg` and a GitHub-hosted demo image linked from its original README. This overlay preserves references to the existing original assets; it does not copy the image binaries.

## Materials to capture from the actual system

1. Real photo of an Echo Show displaying a **non-sensitive** camera feed, with any recognizable persons/addresses blurred.
2. Before/after `docker ps` showing one named camera stopped, then started by the HLS playlist request, then stopped after 30s playlist inactivity. Redact hosts, public URLs and credentials.
3. Nginx and Docker Compose architecture diagram, showing that raw camera credentials never leave the private host.
4. Optional short demonstration video (30–60 seconds): voice request → camera display → server container state; **measure and show actual timings**, not invented figures.
5. A redacted benchmark table: camera make/model, CPU, FFmpeg build/digest, width×height, fps, first-frame delay, CPU/RAM, success/failure count.

Do not publish live RTSP URLs, private home footage, Cloudflare tunnel token, signed HLS links, Home Assistant tokens or identifiable property addresses. For Reddit, avoid implying official Amazon/Home Assistant certification.
