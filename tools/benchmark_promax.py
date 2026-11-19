#!/usr/bin/env python3
"""Measure signed playlist and first-segment availability without printing credentials.

The URL is entered through a hidden prompt so it does not enter shell history.
Run: python3 tools/benchmark_promax.py
"""
from __future__ import annotations
from getpass import getpass
import json
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


def run(url):
    if not url.startswith(('https://', 'http://')):
        raise ValueError('Expected an HLS HTTP URL')
    started = time.monotonic()
    with urlopen(Request(url, headers={'User-Agent':'AlexaRTSPBridgeBench/0.2'}), timeout=30) as response:
        playlist = response.read(1024 * 1024).decode('utf-8')
        status = response.status
    first = time.monotonic()-started
    if status != 200 or not playlist.startswith('#EXTM3U'):
        raise RuntimeError('No valid HLS playlist')
    segments = [line.strip() for line in playlist.splitlines() if line.strip().endswith('.ts')]
    if not segments:
        raise RuntimeError('Playlist has no transport stream segments')
    segment_url = urljoin(url, segments[-1])
    # Segment must be on the same origin and signed path as the playlist.
    origin = urlsplit(url)
    if urlsplit(segment_url).netloc != origin.netloc or not urlsplit(segment_url).path.startswith('/s/'):
        raise ValueError('Playlist points to an unexpected segment URL')
    with urlopen(segment_url, timeout=20) as response:
        segment = response.read(8 * 1024 * 1024)
    total = time.monotonic() - started
    if not segment or segment[0] != 0x47:
        raise RuntimeError('Not an MPEG-TS segment')
    profile = 'not probed'
    with tempfile.TemporaryDirectory() as folder:
        file = Path(folder) / 'sample.ts'
        file.write_bytes(segment)
        try:
            result = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
                '-show_entries','stream=codec_name,profile,width,height',
                '-of','json',str(file)],capture_output=True,timeout=6,check=False)
            streams = json.loads(result.stdout).get('streams',[])
            if streams:
                profile = streams[0]
        except (FileNotFoundError,ValueError,subprocess.TimeoutExpired):
            pass
    return {'playlist_seconds':round(first,3),'segment_seconds_total':round(total,3),
            'segment_bytes':len(segment),'stream':profile,'note':'Test from this client, not glass-to-glass latency'}


if __name__=='__main__':
    url=getpass('Paste the private signed HLS URL (input hidden): ').strip()
    try:
        print(json.dumps(run(url),indent=2))
    except Exception as exc:
        print('Test failed:',type(exc).__name__)
        raise SystemExit(1)
