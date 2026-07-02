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
