#!/usr/bin/env bash
# Public, configurable adaptation of the original homeserverv2 FFmpeg script.
set -euo pipefail
: "${CAMERA_SLUG:?Missing CAMERA_SLUG}"
[[ "$CAMERA_SLUG" =~ ^[a-z][a-z0-9_]{0,39}$ ]] || { echo 'Bad camera slug' >&2; exit 2; }
URL_FILE='/run/secrets/rtsp_url'
[[ -r "$URL_FILE" ]] || { echo 'Missing RTSP credential file' >&2; exit 2; }
IFS= read -r RTSP_URL < "$URL_FILE" || [[ -n "${RTSP_URL:-}" ]]
[[ "$RTSP_URL" == rtsp://* || "$RTSP_URL" == rtsps://* ]] || { echo 'Not an RTSP URL' >&2; exit 2; }
mkdir -p "/hls/${CAMERA_SLUG}"
exec ffmpeg -hide_banner -nostdin -loglevel warning \
  -rtsp_transport tcp -fflags +genpts+nobuffer -flags low_delay \
  -i "$RTSP_URL" -an \
  -vf 'scale=960:540:in_range=full:out_range=limited,format=yuv420p,fps=15' \
  -c:v libx264 -profile:v baseline -level:v 3.1 \
  -preset ultrafast -tune zerolatency -color_range tv \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
  -r 15 -g 15 -keyint_min 15 -sc_threshold 0 \
  -x264-params 'keyint=15:min-keyint=15:scenecut=0:open-gop=0:repeat-headers=1' \
  -b:v 1000k -maxrate 1000k -bufsize 1000k \
  -f hls -hls_time 1 -hls_list_size 6 -hls_start_number_source epoch \
  -hls_flags delete_segments+omit_endlist+independent_segments \
  -hls_segment_filename "/hls/${CAMERA_SLUG}/segment_%d.ts" \
  "/hls/${CAMERA_SLUG}/index.m3u8"
