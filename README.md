# RTSP Camera Recorder

A Python script for recording RTSP streams from security cameras using FFmpeg.

## Features

- Configurable FFmpeg binary path
- Configurable RTSP stream URL
- Automatic segmentation of recordings
- Hardware acceleration support
- Error handling and automatic reconnection
- Logging to both console and file

## Requirements

- Python 3.6 or higher
- FFmpeg installed on your system

## Configuration

Configuration is loaded from environment variables. To keep secrets out of
git, create a `.env` file in the project root (this file is ignored by
`.gitignore`). Example `.env` contents:

```
# Local config for RTSP recorder - KEEP THIS FILE OUT OF GIT
FFMPEG_BINARY=/opt/homebrew/bin/ffmpeg
RTSP_URL=rtsp://username:password@camera/stream
OUTPUT_DIR=recordings
SEGMENT_DURATION=900
OUTPUT_FORMAT=mp4
HW_ACCELERATION=
```

Alternatively you can set the same variables in your shell environment.
The project includes `config.py` which reads `.env` (if present) and
exposes the variables with sensible defaults.

## Usage

1. Install FFmpeg if not already installed:
   - macOS: `brew install ffmpeg`
   - Ubuntu/Debian: `sudo apt-get install ffmpeg`

2. Configure your settings in `config.py`

3. Run the script:
```bash
python3 rtsp_recorder.py
```

## Output

Recordings are saved in the configured output directory with timestamps in the filename:
```
recordings/
  recording_20251028_123456.mp4
  recording_20251028_124456.mp4
  ...
```

## Logging

The script logs all activities to both console and `rtsp_recorder.log` file.

## Notes

- The script uses TCP for RTSP transport which is more stable for most networks
- Hardware acceleration is automatically detected when set to 'auto'
- The script automatically reconnects if the connection is lost
- Use Ctrl+C to safely stop the recording