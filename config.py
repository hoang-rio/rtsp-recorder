"""
Configuration loader for RTSP recorder.

This module reads configuration from environment variables. To keep
secrets out of git, create a `.env` file in the project root based on
the `.env.example` template (see `.gitignore` for details on keeping
secrets secure).

The loader below will read `.env` (if present) and expose Python
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

OUTPUT_FORMAT = os.environ.get('OUTPUT_FORMAT', 'mkv')

# HW_ACCELERATION: treat empty string as None
_hw = os.environ.get('HW_ACCELERATION', '')
HW_ACCELERATION = _hw if _hw else None

# RTSP transport option: set to 'tcp', 'udp', or leave empty to omit
RTSP_TRANSPORT = os.environ.get('RTSP_TRANSPORT', '')

# Option to disable audio stream entirely (saves CPU). Set DISABLE_AUDIO=1 in .env to enable.
_disable_audio = os.environ.get('DISABLE_AUDIO', '0')
DISABLE_AUDIO = _disable_audio.lower() in ('1', 'true', 'yes')