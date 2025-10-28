"""
Configuration loader for RTSP recorder.

This module reads configuration from environment variables. To keep
secrets out of git, create a `.env` file in the project root (this file
is ignored by default — see `.gitignore`) with the following keys:

FFMPEG_BINARY=/opt/homebrew/bin/ffmpeg
RTSP_URL=rtsp://username:password@camera/stream
OUTPUT_DIR=recordings
SEGMENT_DURATION=900
OUTPUT_FORMAT=mp4
HW_ACCELERATION=auto

The loader below will read `.env` (if present) and then expose Python
variables with safe defaults.
"""

import os
from pathlib import Path


def _load_dotenv(dotenv_path: str = '.env') -> None:
	"""Simple .env loader: reads KEY=VALUE lines and sets os.environ.

	Lines starting with # are ignored, blank lines are skipped. Values may
	be quoted with single or double quotes.
	"""
	p = Path(dotenv_path)
	if not p.is_file():
		return

	for raw in p.read_text(encoding='utf8').splitlines():
		line = raw.strip()
		if not line or line.startswith('#'):
			continue
		if '=' not in line:
			continue
		key, val = line.split('=', 1)
		key = key.strip()
		val = val.strip()
		# Remove surrounding quotes if present
		if (val.startswith("'") and val.endswith("'")) or (
			val.startswith('"') and val.endswith('"')
		):
			val = val[1:-1]
		# Only set if not already set in environment
		os.environ.setdefault(key, val)


# Try to load .env automatically if present
_load_dotenv()

# Now expose config variables from environment (with defaults)
FFMPEG_BINARY = os.environ.get('FFMPEG_BINARY', '/usr/local/bin/ffmpeg')
RTSP_URL = os.environ.get('RTSP_URL', '')
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', 'recordings')

# Convert SEGMENT_DURATION to int safely
try:
	SEGMENT_DURATION = int(os.environ.get('SEGMENT_DURATION', '900'))
except ValueError:
	SEGMENT_DURATION = 900

OUTPUT_FORMAT = os.environ.get('OUTPUT_FORMAT', 'mp4')

# HW_ACCELERATION: treat empty string as None
_hw = os.environ.get('HW_ACCELERATION', '')
HW_ACCELERATION = _hw if _hw else None