# Debian FFmpeg provides libx264 and the libzmq drawbox command filter.
ARG BUILD_FROM=python:3.13-slim
FROM ${BUILD_FROM}
RUN set -eux; \
    if command -v apt-get >/dev/null; then \
      apt-get update; apt-get install -y --no-install-recommends ffmpeg ca-certificates; \
      rm -rf /var/lib/apt/lists/*; \
    else \
      apk add --no-cache ffmpeg ca-certificates; \
    fi; \
    ffmpeg -hide_banner -encoders | grep -q libx264; \
    ffmpeg -hide_banner -filters | grep -q zmq; \
    ffmpeg -hide_banner -filters | grep -q drawbox
RUN pip install --no-cache-dir 'pyzmq>=26,<28'
WORKDIR /app
COPY promax /app/promax
COPY run.sh /app/run.sh
RUN chmod 755 /app/run.sh
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
EXPOSE 8090 8099
CMD ["/app/run.sh"]
