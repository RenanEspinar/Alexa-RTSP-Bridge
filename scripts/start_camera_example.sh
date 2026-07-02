#!/bin/bash

################################################################################
#
# Alexa RTSP Bridge
#
# Example FFmpeg launcher
#
# Replace the variables below with your own camera information.
#
################################################################################

CAMERA_NAME="solario"

RTSP_URL="rtsp://USERNAME:PASSWORD@192.168.1.100:554/Streaming/Channels/101"

WIDTH=960
HEIGHT=540

FPS=15

BITRATE=1000k

################################################################################

mkdir -p ~/alexa_hls/${CAMERA_NAME}

docker rm -f ffmpeg_${CAMERA_NAME} 2>/dev/null

docker run -d \
  --name ffmpeg_${CAMERA_NAME} \
  --restart unless-stopped \
  -v ~/alexa_hls:/hls \
  linuxserver/ffmpeg:latest \
  -rtsp_transport tcp \
  -fflags nobuffer \
  -flags low_delay \
  -i "${RTSP_URL}" \
  -an \
  -c:v libx264 \
  -profile:v baseline \
  -level 3.1 \
  -pix_fmt yuv420p \
  -preset ultrafast \
  -tune zerolatency \
  -vf "scale=${WIDTH}:${HEIGHT},fps=${FPS}" \
  -r ${FPS} \
  -g ${FPS} \
  -keyint_min ${FPS} \
  -sc_threshold 0 \
  -b:v ${BITRATE} \
  -maxrate ${BITRATE} \
  -bufsize ${BITRATE} \
  -f hls \
  -hls_time 1 \
  -hls_list_size 6 \
  -hls_flags delete_segments+omit_endlist \
  -hls_segment_filename "/hls/${CAMERA_NAME}/segment_%06d.ts" \
  "/hls/${CAMERA_NAME}/index.m3u8"

echo ""
echo "========================================="
echo "Camera started successfully."
echo ""
echo "HLS Playlist:"
echo ""
echo "http://SERVER_IP:8090/${CAMERA_NAME}/index.m3u8"
echo ""
echo "========================================="
