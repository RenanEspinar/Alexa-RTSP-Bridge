<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/0d4dee5b-a272-4c6c-977d-93b728e92c8b" />What is Alexa RTSP Bridge?


Amazon Alexa officially supports live camera streaming only through the Alexa Smart Home Camera API.
Unfortunately, most IP cameras expose their video through RTSP, while Alexa expects an HTTPS HLS stream delivered by a Smart Home Skill.
As a result, thousands of cameras—including Hikvision, Dahua, Reolink and generic ONVIF devices—cannot be viewed directly from Alexa without proprietary cloud integrations.
Alexa RTSP Bridge solves this problem by acting as an intelligent bridge between Alexa and your cameras.
Instead of exposing RTSP directly, it implements the complete Alexa Smart Home communication flow and dynamically provides an Alexa-compatible HLS stream.

Features
✔ Works with virtually any RTSP camera
✔ Hikvision
✔ Dahua
✔ Reolink
✔ Generic RTSP cameras
✔ DVRs
✔ NVRs
✔ Home Assistant integration
✔ AWS Lambda Smart Home proxy
✔ Cloudflare Tunnel support
✔ HTTPS HLS generation
✔ Docker ready
✔ Raspberry Pi compatible
✔ Intel Mini PC compatible
✔ Multiple cameras
✔ Low latency streaming
✔ Fully open source

Why this project exists
  Many tutorials claim to integrate RTSP cameras with Alexa.
Most of them rely on:
Vendor-specific Alexa Skills
Proprietary cloud services
Unsupported workarounds
Unstable custom integrations

These approaches usually fail because Alexa ultimately requires a valid CameraStreamController response.
Alexa RTSP Bridge implements that communication properly.
Instead of trying to "hack" Alexa, this project speaks Alexa's own Smart Home protocol.
Architecture
                        Amazon Alexa
                              │
                              ▼
                  Alexa Smart Home Directive
                              │
                              ▼
                       AWS Lambda Proxy
                              │
                   Alexa Smart Home API v3
                              │
                              ▼
                       Home Assistant
                              │
                 Camera Entity Resolution
                              │
                              ▼
                  Alexa.CameraStreamController
                              │
            (Intercept Response & Replace Stream)
                              │
                              ▼
                     FFmpeg Transcoder
                              │
                              ▼
                         HTTPS HLS
                              │
                              ▼
                     Cloudflare Tunnel
                              │
                              ▼
                       Amazon Alexa
How it works
The Lambda function receives every Smart Home directive sent by Amazon Alexa.
Instead of generating camera streams itself, it forwards the request to Home Assistant using the official Smart Home endpoint.
Home Assistant performs all the entity resolution and camera management.
Once Home Assistant returns the CameraStreamController response, Alexa RTSP Bridge intercepts the payload before it is sent back to Alexa.
At this point, the stream can be modified in real time.

Typical operations include:
Replacing the HLS URL
Starting FFmpeg dynamically
Optimizing the stream
Selecting a different camera
Injecting compatibility fixes
Returning a completely different video source

This makes the bridge far more powerful than a simple RTSP-to-HLS converter.

It effectively becomes a programmable middleware between Alexa and Home Assistant.

Supported Architecture
RTSP Camera
      │
      ▼
   FFmpeg
      │
      ▼
     HLS
      │
      ▼
    Nginx
      │
      ▼
Cloudflare Tunnel
      │
      ▼
  AWS Lambda
      │
      ▼
 Home Assistant
      │
      ▼
 Amazon Alexa

- Compatible Cameras
        Manufacturer	Status
        Hikvision	
        Dahua	
        Reolink	
        Uniview	Expected
        TP-Link VIGI	Expected
        Generic RTSP	
        ONVIF Cameras	Expected
        DVRs	
        NVRs	
- Compatible Hardware
        Hardware	Status
        Raspberry Pi 3B+	
        Raspberry Pi 4	
        Raspberry Pi 5	
        Intel N100	
        Ubuntu Server	
        Debian	
        Docker	Required

  # Requirements
Before installing Alexa RTSP Bridge, ensure that the following components are available.
## Hardware
- Raspberry Pi 3B+ or newer
- Intel Mini PC (recommended for multiple cameras)
- Any Linux server capable of running Docker
## Operating System
- Ubuntu Server 20.04+
- Debian 11+
- Raspberry Pi OS (64-bit recommended)
## Software
- Docker
- Docker Compose
- Home Assistant
- AWS Account
- Amazon Developer Account
- Cloudflare Account
## Network
- Internet connection
- RTSP-enabled camera
- HTTPS domain (recommended)
- Cloudflare Tunnel (recommended)
## Camera Requirements
Any camera capable of exposing an RTSP stream.
Examples include:
- Hikvision
- Dahua
- Reolink
- ONVIF Cameras
- DVR
- NVR
- Generic RTSP Cameras
## Recommended Knowledge
Although this guide is designed to be beginner-friendly, basic knowledge of the following topics is recommended:
- Docker
- Linux command line
- Home Assistant
- Networking fundamentals
- RTSP video streaming
  
Why not RTSP directly?
Amazon Alexa does not natively support RTSP streams.
Instead, Alexa requires an HTTPS-accessible HLS stream delivered through the Alexa Smart Home Camera API.
Alexa RTSP Bridge performs this translation transparently, allowing virtually any RTSP camera to behave like a native Alexa-compatible camera.
Design Philosophy
Alexa RTSP Bridge is not intended to replace Home Assistant. Instead, it extends the Alexa Smart Home protocol by acting as a programmable middleware between Alexa and Home Assistant, allowing developers to intercept, transform and optimize camera streams before they reach Alexa.
