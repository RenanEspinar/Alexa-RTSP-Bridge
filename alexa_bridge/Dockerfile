ARG BUILD_FROM=python:3.13-alpine
FROM ${BUILD_FROM}

RUN apk add --no-cache ffmpeg ca-certificates \
    && ffmpeg -hide_banner -encoders | grep -q libx264 \
    && ffprobe -version >/dev/null
WORKDIR /app
COPY promax /app/promax
COPY run.sh /app/run.sh
RUN chmod 755 /app/run.sh

# /data comes from Home Assistant Supervisor, or a Docker named volume.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
EXPOSE 8090 8099
CMD ["/app/run.sh"]
