<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/0d4dee5b-a272-4c6c-977d-93b728e92c8b" />What is Alexa RTSP Bridge?

# Alexa RTSP Bridge

> Bridge any RTSP camera to Amazon Alexa using AWS Lambda, Home Assistant, FFmpeg, HLS, Docker and Cloudflare Tunnel.

<p align="center">
  <img src="images/alexa-rtsp-bridge-demo.png" alt="Alexa RTSP Bridge demo" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue" />
  <img src="https://img.shields.io/badge/AWS-Lambda-orange" />
  <img src="https://img.shields.io/badge/Home%20Assistant-Compatible-41BDF5" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED" />
  <img src="https://img.shields.io/badge/Cloudflare-Tunnel-F38020" />
  <img src="https://img.shields.io/badge/RTSP-Supported-success" />
  <img src="https://img.shields.io/badge/HLS-Compatible-success" />
  <img src="https://img.shields.io/badge/License-MIT-green" />
</p>

---

## What is Alexa RTSP Bridge?

Amazon Alexa officially supports live camera streaming through the **Alexa Smart Home Camera API**.

Unfortunately, most IP cameras expose their video through **RTSP**, while Alexa expects an HTTPS-accessible **HLS** stream returned by a Smart Home Skill.

As a result, thousands of cameras, DVRs and NVRs cannot be viewed directly from Alexa without proprietary cloud integrations.

**Alexa RTSP Bridge** solves this problem by acting as an intelligent bridge between Alexa, Home Assistant and your RTSP cameras.

It does not expose RTSP directly.

Instead, it implements the Alexa Smart Home communication flow, forwards Alexa directives to Home Assistant, intercepts camera stream responses, and replaces them with Alexa-compatible HLS streams generated from RTSP sources.

---

## Why this project exists

Many tutorials claim to integrate RTSP cameras with Alexa.

Most of them rely on:

- Vendor-specific Alexa Skills
- Proprietary cloud services
- Unsupported workarounds
- Unstable custom integrations
- Direct RTSP exposure
- Browser-only streams
- HLS streams that Alexa rejects

These approaches often fail because Alexa requires a valid `Alexa.CameraStreamController` response.

Alexa RTSP Bridge speaks Alexa's own Smart Home protocol.

Instead of trying to force Alexa to understand RTSP, this project converts RTSP into a format Alexa expects.

---

## Features

| Feature | Status |
|--------|--------|
| Generic RTSP camera support | ✅ |
| Hikvision support | ✅ |
| Dahua support | ✅ |
| Reolink support | ✅ |
| DVR/NVR support | ✅ |
| Multiple cameras | ✅ |
| Home Assistant integration | ✅ |
| AWS Lambda Smart Home proxy | ✅ |
| FFmpeg transcoding | ✅ |
| HLS generation | ✅ |
| Nginx HLS serving | ✅ |
| Cloudflare Tunnel support | ✅ |
| Docker-based deployment | ✅ |
| Raspberry Pi compatible | ✅ |
| Intel Mini PC compatible | ✅ |
| Open source | ✅ |

---

## Table of Contents

- [What is Alexa RTSP Bridge?](#what-is-alexa-rtsp-bridge)
- [Why this project exists](#why-this-project-exists)
- [Features](#features)
- [Architecture](#architecture)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Supported Cameras](#supported-cameras)
- [Supported Hardware](#supported-hardware)
- [Quick Start](#quick-start)
- [FFmpeg HLS Stream](#ffmpeg-hls-stream)
- [Nginx HLS Server](#nginx-hls-server)
- [Cloudflare Tunnel](#cloudflare-tunnel)
- [AWS Lambda](#aws-lambda)
- [Home Assistant](#home-assistant)
- [Multiple Cameras](#multiple-cameras)
- [Performance Notes](#performance-notes)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)
- [Roadmap](#roadmap)
- [License](#license)

---

## Architecture

```text
                        ┌────────────────────┐
                        │    Amazon Alexa    │
                        └─────────┬──────────┘
                                  │
                                  │ Smart Home Directive
                                  ▼
                        ┌────────────────────┐
                        │     AWS Lambda     │
                        │  Smart Home Proxy  │
                        └─────────┬──────────┘
                                  │
                                  │ POST /api/alexa/smart_home
                                  ▼
                        ┌────────────────────┐
                        │  Home Assistant    │
                        │ Entity Resolution  │
                        └─────────┬──────────┘
                                  │
                                  │ CameraStreamController Response
                                  ▼
                        ┌────────────────────┐
                        │ Lambda Interceptor │
                        │ Replace Stream URI │
                        └─────────┬──────────┘
                                  │
                                  │ HTTPS HLS URL
                                  ▼
                        ┌────────────────────┐
                        │      Alexa         │
                        │  Plays HLS Stream  │
                        └────────────────────┘
The video pipeline runs separately:

                        ┌────────────────────┐
                        │    RTSP Camera     │
                        └─────────┬──────────┘
                                  │
                                  │ rtsp://user:pass@camera
                                  ▼
                        ┌────────────────────┐
                        │      FFmpeg        │
                        │ RTSP → HLS Encode  │
                        └─────────┬──────────┘
                                  │
                                  │ index.m3u8 + .ts segments
                                  ▼
                        ┌────────────────────┐
                        │       Nginx        │
                        │   HLS Web Server   │
                        └─────────┬──────────┘
                                  │
                                  │ HTTPS via Tunnel
                                  ▼
                        ┌────────────────────┐
                        │ Cloudflare Tunnel  │
                        └─────────┬──────────┘
                                  │
                                  ▼
                        ┌────────────────────┐
                        │    Amazon Alexa    │
                        └────────────────────┘

How it works

The Lambda function receives Alexa Smart Home directives.

For normal devices such as lights, sensors or switches, the Lambda forwards the directive to Home Assistant and returns the Home Assistant response unchanged.

For cameras, the flow is different.

Alexa requests a camera stream.
Lambda forwards the request to Home Assistant.
Home Assistant resolves the camera entity.
Home Assistant returns a CameraStreamController response.
Lambda intercepts that response.
Lambda replaces the Home Assistant HLS URL with an optimized HLS URL generated by FFmpeg.
Alexa receives a valid HLS stream and displays the camera.

This makes Alexa RTSP Bridge more powerful than a simple RTSP-to-HLS converter.

It is programmable middleware between Alexa and Home Assistant.

Typical operations include:

Replacing the HLS URL
Returning a different stream per camera
Adjusting reported resolution
Removing unsupported audio declarations
Starting FFmpeg dynamically
Optimizing the stream for Alexa
Supporting multiple RTSP cameras
Why not RTSP directly?

Alexa does not natively support RTSP.

RTSP is widely used by IP cameras, DVRs and NVRs, but Alexa expects camera streams to be delivered through the Alexa Smart Home Camera API.

In practice, Alexa expects:

HTTPS URL
HLS playlist
H.264 video
Compatible profile and level
Proper segmentation
Valid CameraStreamController response

Alexa RTSP Bridge performs this translation.

Design Philosophy

Alexa RTSP Bridge is not intended to replace Home Assistant.

It extends Home Assistant by providing a programmable Alexa camera bridge.

Home Assistant continues to manage entities, authentication and Smart Home discovery.

Alexa RTSP Bridge handles the parts that Alexa is strict about:

Camera stream compatibility
HLS delivery
FFmpeg transcoding
Cloud-accessible stream URLs
Response rewriting

The goal is to make RTSP cameras behave like native Alexa-compatible cameras.

Requirements

Before installing Alexa RTSP Bridge, make sure the following components are available.

Hardware
Raspberry Pi 3B+ or newer
Raspberry Pi 4 or Raspberry Pi 5 recommended
Intel N100 mini PC recommended for multiple cameras
Any Linux server capable of running Docker
Operating System
Ubuntu Server 20.04+
Debian 11+
Raspberry Pi OS 64-bit
Any Linux distribution with Docker support
Software
Docker
Docker Compose
Home Assistant
AWS Account
Amazon Developer Account
Cloudflare Account
FFmpeg container
Nginx container
Network
Internet connection
RTSP-enabled camera
HTTPS domain
Cloudflare Tunnel recommended
Home Assistant reachable from AWS Lambda
HLS server reachable by Alexa
Camera Requirements

Any camera capable of exposing an RTSP stream.

Examples:

Hikvision
Dahua
Reolink
Generic IP camera
ONVIF camera
DVR
NVR

Example RTSP URL:

rtsp://username:password@192.168.1.100:554/Streaming/Channels/101
Recommended Knowledge

This guide is designed to be practical, but basic knowledge of the following topics is recommended:

Linux command line
Docker
Home Assistant
AWS Lambda
Alexa Smart Home Skills
RTSP
HLS
Basic networking
Cloudflare Tunnel
Supported Cameras
Manufacturer	Status
Hikvision	✅ Tested
Dahua	✅ Expected
Reolink	✅ Expected
Generic RTSP	✅
ONVIF Cameras	✅ Expected
DVRs	✅
NVRs	✅
TP-Link VIGI	Expected
Uniview	Expected

[!NOTE]
If your camera exposes a working RTSP stream, it can probably work with this project.

Supported Hardware
Hardware	Status	Notes
Raspberry Pi 3B+	✅ Tested	Works with one camera at a time
Raspberry Pi 4	✅	Better for multiple streams
Raspberry Pi 5	✅	Recommended ARM option
Intel N100 Mini PC	✅	Recommended for many cameras
Ubuntu Server	✅	Tested target
Debian	✅	Expected
Docker host	✅	Required
Performance Notes

FFmpeg transcoding is CPU-intensive.

A single camera requires:

RTSP decode
    ↓
Scale
    ↓
H.264 encode
    ↓
HLS segment generation

Recommended hardware:

Use Case	Recommended Hardware
1 camera on demand	Raspberry Pi 3B+
1–3 cameras	Raspberry Pi 4
3–5 cameras	Raspberry Pi 5
5–10 cameras	Intel N100
10+ cameras	Intel i5/i7 or server

[!WARNING]
Running many FFmpeg containers permanently on a Raspberry Pi 3B+ is not recommended.

For small devices, use on-demand streaming.

Quick Start

The basic workflow is:

Create an HLS folder.
Start FFmpeg to convert RTSP to HLS.
Serve the HLS folder using Nginx.
Publish the HLS server using Cloudflare Tunnel.
Configure Lambda to replace the Home Assistant camera stream with the HLS URL.
Ask Alexa to show the camera.

Example:

mkdir -p ~/alexa_hls/solario
chmod -R 777 ~/alexa_hls

Start FFmpeg:

docker run -d \
  --name ffmpeg_solario \
  --restart unless-stopped \
  -v ~/alexa_hls:/hls \
  linuxserver/ffmpeg:latest \
  -rtsp_transport tcp \
  -fflags nobuffer \
  -flags low_delay \
  -i "rtsp://USERNAME:PASSWORD@192.168.1.100:554/Streaming/Channels/101" \
  -an \
  -c:v libx264 \
  -profile:v baseline \
  -level 3.1 \
  -pix_fmt yuv420p \
  -preset ultrafast \
  -tune zerolatency \
  -vf "scale=960:540,fps=15" \
  -r 15 \
  -g 15 \
  -keyint_min 15 \
  -sc_threshold 0 \
  -b:v 1000k \
  -maxrate 1000k \
  -bufsize 1000k \
  -f hls \
  -hls_time 1 \
  -hls_list_size 6 \
  -hls_flags delete_segments+omit_endlist \
  -hls_segment_filename "/hls/solario/segment_%06d.ts" \
  "/hls/solario/index.m3u8"

Serve with Nginx:

docker run -d \
  --name alexa_hls_nginx \
  --restart unless-stopped \
  -p 8090:80 \
  -v ~/alexa_hls:/usr/share/nginx/html:ro \
  nginx:alpine

Test locally:

curl http://192.168.1.10:8090/solario/index.m3u8

Expected output:

#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:1
#EXTINF:1.000000,
segment_000001.ts
FFmpeg HLS Stream

The FFmpeg command converts the RTSP camera stream into Alexa-compatible HLS.

Important parameters:

Parameter	Purpose
-rtsp_transport tcp	More stable RTSP transport
-fflags nobuffer	Reduces buffering
-flags low_delay	Attempts lower latency
-an	Removes audio
-c:v libx264	Encodes video as H.264
-profile:v baseline	Improves Alexa compatibility
-level 3.1	Compatible H.264 level
-pix_fmt yuv420p	Widely compatible pixel format
-preset ultrafast	Lower CPU latency
-tune zerolatency	Optimized for real-time streaming
-vf scale=960:540,fps=15	Reduces load and bandwidth
-g 15	Keyframe every 1 second at 15 fps
-hls_time 1	1-second HLS segments
-hls_list_size 6	Short live window
delete_segments	Removes old segments
Recommended FFmpeg Profiles
Stable low-load profile
-vf "scale=960:540,fps=15" \
-b:v 1000k \
-maxrate 1000k \
-bufsize 1000k \
-hls_time 1 \
-hls_list_size 6
Higher quality profile
-vf "scale=960:540,fps=15" \
-b:v 1500k \
-maxrate 1500k \
-bufsize 3000k \
-hls_time 1 \
-hls_list_size 6
720p profile
-vf "scale=1280:720,fps=15" \
-b:v 1800k \
-maxrate 1800k \
-bufsize 3600k \
-hls_time 2 \
-hls_list_size 10

[!TIP]
If Alexa opens the camera but closes after a few seconds, reduce bitrate or resolution.

Nginx HLS Server

Nginx serves the generated HLS files.

Example structure:

~/alexa_hls/
├── solario/
│   ├── index.m3u8
│   ├── segment_000001.ts
│   ├── segment_000002.ts
│   └── ...
├── jardin/
│   ├── index.m3u8
│   └── ...
└── pasillo/
    ├── index.m3u8
    └── ...

Run Nginx:

docker run -d \
  --name alexa_hls_nginx \
  --restart unless-stopped \
  -p 8090:80 \
  -v ~/alexa_hls:/usr/share/nginx/html:ro \
  nginx:alpine

Test:

curl http://SERVER_IP:8090/solario/index.m3u8
Cloudflare Tunnel

Alexa requires HTTPS-accessible stream URLs.

Cloudflare Tunnel allows exposing the HLS server securely without opening router ports.

Example public hostname:

alexa-hls.example.com

Service:

http://192.168.1.10:8090

Final HLS URL:

https://alexa-hls.example.com/solario/index.m3u8

[!NOTE]
Cloudflare Tunnel avoids exposing your local server directly to the internet.

AWS Lambda

The Lambda function acts as an Alexa Smart Home proxy.

It forwards directives to Home Assistant and modifies camera stream responses.

Example stream mapping:

ALEXA_HLS_URLS = {
    "camera#solario": "https://alexa-hls.example.com/solario/index.m3u8",
    "camera#jardin": "https://alexa-hls.example.com/jardin/index.m3u8",
}

When Alexa asks for camera#solario, Lambda returns:

https://alexa-hls.example.com/solario/index.m3u8
Lambda Environment Variables
Variable	Required	Description
BASE_URL	✅	Home Assistant public URL
DEBUG	Optional	Enables debug logging
NOT_VERIFY_SSL	Optional	Disable SSL verification for testing
CAMERA_RESPONSE_DELAY_SECONDS	Optional	Wait before returning HLS URL

Example:

BASE_URL=https://home.example.com
DEBUG=true
CAMERA_RESPONSE_DELAY_SECONDS=1
Home Assistant

Home Assistant is responsible for:

Alexa Smart Home integration
Entity discovery
Camera entity naming
Smart Home API responses
Normal device control

Example camera exposure:

alexa:
  smart_home:
    filter:
      include_entities:
        - camera.solario
        - camera.jardin
    entity_config:
      camera.solario:
        name: Solario
        display_categories: CAMERA
      camera.jardin:
        name: Jardin
        display_categories: CAMERA
Multiple Cameras

Each camera should have:

A Home Assistant camera entity.
An FFmpeg container.
A dedicated HLS folder.
A public HLS URL.
A Lambda mapping entry.

Example:

Camera	RTSP Channel	HLS Path	Lambda Endpoint
Solario	801	/solario/index.m3u8	camera#solario
Jardin	301	/jardin/index.m3u8	camera#jardin
Pasillo	401	/pasillo/index.m3u8	camera#pasillo
Estacionamiento	601	/estacionamiento/index.m3u8	camera#estacionamiento

Example Lambda mapping:

ALEXA_HLS_URLS = {
    "camera#solario": "https://alexa-hls.example.com/solario/index.m3u8",
    "camera#jardin": "https://alexa-hls.example.com/jardin/index.m3u8",
    "camera#pasillo": "https://alexa-hls.example.com/pasillo/index.m3u8",
    "camera#estacionamiento": "https://alexa-hls.example.com/estacionamiento/index.m3u8",
}
On-Demand Streaming

Running FFmpeg permanently can overload small devices.

A better approach is on-demand streaming:

Alexa requests camera
        ↓
Lambda receives directive
        ↓
Lambda starts FFmpeg container
        ↓
Wait a few seconds
        ↓
Return HLS URL
        ↓
Alexa plays stream
        ↓
Container stops after timeout

This is recommended for:

Raspberry Pi 3B+
Raspberry Pi 4
Low-power servers
Many cameras
Troubleshooting
Alexa says "I can't connect to the camera"

Possible causes:

HLS URL is not public
Lambda returned the wrong URL
HLS playlist exists but segments return 404
FFmpeg is not running
Cloudflare Tunnel route is incorrect
Alexa rejected the H.264 profile

Check:

curl https://alexa-hls.example.com/solario/index.m3u8

Then test a segment from the playlist:

curl -I https://alexa-hls.example.com/solario/segment_000001.ts
HLS playlist works but segments return 404

This usually means the segment was deleted before the client requested it.

Increase the list size:

-hls_list_size 10

or disable immediate deletion:

-hls_flags omit_endlist
Camera works in browser but not Alexa

Browsers and Alexa behave differently.

A browser may accept streams that Alexa rejects.

Check:

H.264 profile
HLS segment duration
Audio codec declaration
Public HTTPS access
Segment availability

Recommended Alexa-compatible settings:

-profile:v baseline
-level 3.1
-pix_fmt yuv420p
-hls_time 1
-hls_list_size 6
-an
Alexa opens the stream and immediately closes

Reduce stream complexity:

-vf "scale=960:540,fps=15"
-b:v 1000k
-maxrate 1000k

Avoid high-profile H.264.

Cloudflare shows 502 Bad Gateway

This means Cloudflare is working, but the origin service is not reachable.

Check:

docker ps
curl http://127.0.0.1:8090
curl http://SERVER_IP:8090

Verify the Cloudflare Tunnel route points to the correct internal service.

FFmpeg container exits immediately

Check logs:

docker logs ffmpeg_solario --tail 80

Common causes:

Wrong RTSP URL
Wrong username or password
Camera offline
Unsupported Docker image architecture
Network issue
exec format error

The Docker image architecture does not match your device.

For Raspberry Pi or ARM64 devices, use a multi-architecture image such as:

linuxserver/ffmpeg:latest
High latency

Alexa HLS will never be as low latency as WebRTC.

Expected latency:

Pipeline	Typical Latency
WebRTC	< 1 second
RTSP local	1–3 seconds
HLS through Alexa	7–15 seconds

To reduce latency:

-hls_time 1
-hls_list_size 4
-preset ultrafast
-tune zerolatency
Security Notes

Do not expose RTSP directly to the internet.

Recommended:

Use Cloudflare Tunnel.
Protect admin services with Cloudflare Access.
Use strong Home Assistant tokens.
Do not commit camera passwords.
Use environment variables or secrets.
Keep Lambda logs free of sensitive tokens.
Use private repositories while testing sensitive configurations.

[!WARNING]
Never publish real RTSP credentials in GitHub.

Suggested Repository Structure
Alexa-RTSP-Bridge/
├── README.md
├── LICENSE
├── .gitignore
├── lambda/
│   ├── lambda.py
│   └── requirements.txt
├── ffmpeg/
│   ├── start_solario.sh
│   ├── start_jardin.sh
│   └── README.md
├── nginx/
│   └── docker-compose.yml
├── docs/
│   ├── architecture.md
│   ├── installation.md
│   ├── cloudflare.md
│   ├── lambda.md
│   ├── ffmpeg.md
│   ├── troubleshooting.md
│   └── performance.md
├── examples/
│   ├── hikvision.md
│   ├── dahua.md
│   ├── reolink.md
│   └── generic_rtsp.md
└── images/
    └── alexa-rtsp-bridge-demo.png
Roadmap
v0.1
Manual FFmpeg HLS pipeline
Lambda stream URL replacement
Home Assistant camera integration
Cloudflare Tunnel support
v0.2
Multi-camera examples
Improved documentation
Docker Compose templates
v0.3
On-demand FFmpeg container start
Portainer API support
Home Assistant webhook support
v1.0
Automated installer
Camera configuration wizard
Multi-platform examples
Production deployment guide
v2.0
WebRTC support
go2rtc integration
Hardware acceleration profiles
Frigate integration examples
FAQ
Does Alexa RTSP Bridge replace Home Assistant?

No.

Home Assistant remains responsible for Alexa entity discovery and Smart Home integration.

Alexa RTSP Bridge extends the camera streaming pipeline.

Can I use this without Cloudflare?

Yes, but Alexa needs a public HTTPS URL.

Cloudflare Tunnel is recommended because it avoids opening router ports.

Can I use this with any RTSP camera?

Usually yes.

If FFmpeg can read your RTSP stream, this project can likely convert it into Alexa-compatible HLS.

Why does the stream have latency?

Alexa consumes HLS, and HLS buffers segments before playback.

Typical latency is between 7 and 15 seconds.

Can this run on a Raspberry Pi 3B+?

Yes, but only with limited workloads.

One camera on demand is realistic.

Multiple permanent FFmpeg transcodes are not recommended.

Can I improve quality?

Yes.

Increase bitrate or resolution, but watch CPU load and Alexa stability.

Example:

-b:v 1500k
-maxrate 1500k
-bufsize 3000k
Can I use audio?

Currently this project recommends video-only streams.

Alexa can be strict with audio codec declarations.

For maximum compatibility, use:

-an

and return:

"audioCodec": "NONE"
Credits

This project was born after extensive debugging of RTSP streams, Home Assistant camera entities, AWS Lambda responses, Alexa Smart Home directives, HLS playlists, Cloudflare Tunnel routing and FFmpeg transcoding.

The goal is simple:

Make RTSP cameras work reliably with Amazon Alexa, regardless of the camera manufacturer.

Contributing

Contributions are welcome.

Useful contributions include:

Camera-specific RTSP examples
FFmpeg profiles
Cloudflare Tunnel guides
Lambda improvements
Home Assistant examples
Documentation fixes
Performance benchmarks
New hardware tests
License

This project is licensed under the MIT License.

See LICENSE for details.

Disclaimer

This project is not affiliated with Amazon, Alexa, Home Assistant, Cloudflare, Hikvision, Dahua, Reolink or any camera manufacturer.

Use it at your own risk.

Always secure your camera streams and avoid exposing private video feeds publicly.
