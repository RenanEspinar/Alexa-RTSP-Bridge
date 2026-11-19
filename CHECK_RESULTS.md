# RC1 test notes

This is the current state of the **experimental** branch, not a compatibility certificate.

## What we've checked

- Python unit tests: camera configuration, HLS signatures and expiry, Lambda's camera response rewrite, playlist/segment HTTP access.
- Syntax: Python modules and Bash FFmpeg launcher.
- Compose generator: two camera entries produce three control/HTTP services plus two camera services. RTSP URLs stay in private files, not in the generated Compose data.
- GitHub Actions: the static-checks workflow has passed in the RC1 branch. Run the workflow again after making changes.
- Original setup: Nginx configuration and Docker container state were inspected; real Fire TV playback has been recorded.

## Still open

Fresh Docker install, FFmpeg image availability on different CPUs, actual Alexa playback with RC1, load tests, camera compatibility, network security review and third-party reproduction.

The original server and RC1 **are not identical**. The video shows the original working setup, while RC1's signed URL and socket-proxy path still need a real end-to-end test.

The previous infrastructure audit exposed a Cloudflare Tunnel token. Rotate that token and don't publish raw diagnostic logs from the server.
