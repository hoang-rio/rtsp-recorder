# RTSP Camera Recorder

A Python script for recording RTSP streams from security cameras using FFmpeg.

## Features

- Configurable FFmpeg binary path and RTSP URL via environment / `.env`
- Saves recordings in dated folders: `OUTPUT_DIR/YYYY/MM/DD/`
- Automatic segmentation: creates a new file every `SEGMENT_DURATION` seconds
- Rotating logs (10 MB per file, 5 backups) stored in `logs/`
- On FFmpeg failure the recorder removes any newly-created partial segment files and restarts
- Graceful shutdown on SIGINT / SIGTERM

## Requirements

- Python 3.6 or higher
- FFmpeg installed on your system

## Configuration

Configuration is read from environment variables. To keep secrets out of git,
copy `.env.example` to `.env` in the project root (`.env` is ignored by `.gitignore`).
The included `config.py` will automatically load `.env` if present.

Available configuration options:

- `FFMPEG_BINARY`: path to the ffmpeg executable
- `RTSP_URL`: your camera RTSP URL (include auth if required)
- `OUTPUT_DIR`: base output directory
- `SEGMENT_DURATION`: segment length in seconds (integer)
- `OUTPUT_FORMAT`: output container/extension (defaults to `mkv`)
- `HW_ACCELERATION`: optional; values like `videotoolbox`, `nvenc`, `qsv`, `auto`, or empty
- `RTSP_TRANSPORT`: optional; set to `tcp` or `udp` for specific transport
- `DISABLE_AUDIO`: set to `1`, `true`, or `yes` to disable audio and save CPU

You can alternatively export these variables in your shell instead of using
`.env`.

## Usage

1. Install FFmpeg if not already installed:

```bash
# macOS (Homebrew)
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install ffmpeg
```

2. Copy `.env.example` to `.env` in the project root and configure your values:
```bash
cp .env.example .env
nano .env  # or use your preferred editor
```

3. Run the recorder:

```bash
python3 rtsp_recorder.py
```

The script runs in the foreground. Use your process supervisor (systemd,
launchd, tmux/screen) for long-running background operation.

## Output layout

Recordings are saved under `OUTPUT_DIR` in a date-based hierarchy:

```
recordings/
  2025/
    10/
      28/
        recording_143045.mkv    # segment started at 14:30:45
        recording_144045.mkv    # next segment (after SEGMENT_DURATION)
```

- Filenames are created using an `strftime` pattern so FFmpeg will substitute
  the timestamp when it writes each segment (the script shows an example
  expanded name in the start log).
- Each segment will be approximately `SEGMENT_DURATION` seconds long (the
  final segment may be shorter when you stop the script).

## Logging

- Logs are written to `logs/rtsp_recorder.log` with rotation: max 10 MB per
  file and up to 5 backups.
- The script also logs to the console.

## Behavior on failure

- If FFmpeg exits with a non-zero return code, the recorder will:
  1. Read the `dated` directory to find any newly-created segment files
  2. Remove files that look like `recording_*.{OUTPUT_FORMAT}` that were
     created during the failed run
  3. Log what was removed and wait briefly before restarting (permanent retry)

This avoids keeping partial/corrupted segments when the recorder loses the
camera stream or FFmpeg fails.

## Notes & tips

- The recorder uses `-re` and copies streams when possible to minimize CPU
  usage; change codec settings in `rtsp_recorder.py` if you want to re-encode.
- The script resets timestamps for each segment so each file starts at 0.
- Hardware acceleration is supported via the `HW_ACCELERATION` environment
  variable — set to `videotoolbox`, `nvenc`, `qsv`, etc. Use `auto` for
  simple platform-based detection.
- `config.py` automatically loads `.env` if present. For CI or production,
  prefer environment variables or a secrets manager instead of `.env`.

## Troubleshooting

- If segments are not appearing, verify that `RTSP_URL` is reachable and the
  `FFMPEG_BINARY` points to a working ffmpeg installation.
- Check `logs/rtsp_recorder.log` for FFmpeg stderr output and errors.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.