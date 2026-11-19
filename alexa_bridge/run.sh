#!/bin/sh
set -eu
# Supervisor persists options under /data. Standalone Compose uses environment variables.
DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"
if [ -f "$DATA_DIR/options.json" ]; then
  # Only accept validated numeric settings; do not evaluate JSON as shell commands.
  IDLE_TIMEOUT="$(python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); n=int(p.get("idle_timeout",30)); assert 10<=n<=3600; print(n)' "$DATA_DIR/options.json")"
  SNAPSHOT_TTL="$(python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); n=int(p.get("snapshot_ttl",120)); assert 15<=n<=3600; print(n)' "$DATA_DIR/options.json")"
  export IDLE_TIMEOUT SNAPSHOT_TTL
fi
exec python3 -m promax.service
