# Notes for a community demo

I built Alexa RTSP Bridge because I wanted to open my existing RTSP cameras on Fire TV without relying on each camera vendor's Alexa skill.

The working system uses Home Assistant and AWS Lambda to return an HLS stream to Alexa. A small Python controller starts FFmpeg for whichever camera was requested and stops it after 30 seconds without playlist requests.

The [Fire TV demo](https://github.com/RenanEspinar/Alexa-RTSP-Bridge/blob/main/Alexa_RTSP_Bridge_FireTV_README_1080p.mp4) shows my original installation. I also put together an [experimental RC1](https://github.com/RenanEspinar/Alexa-RTSP-Bridge/tree/review/reproducible-rc1-20261118) with configurable cameras, signed URLs and setup notes. The new version still needs full device testing.

If anyone has tried something similar with different camera codecs or Echo/Fire TV hardware, I'm interested in what worked and what didn't.
