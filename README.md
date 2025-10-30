# RTSP Camera Recorder

A Python script for recording RTSP streams from security cameras using FFmpeg.

## Disclaimer

Most Line of Code in this repository powered by Github Copilot

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
- `LOG_LEVEL`: set the main application log level. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (defaults to `INFO`)
- `ENABLE_FFMPEG_LOG`: set to `0` to disable writing FFmpeg stderr to `logs/ffmpeg.log` (defaults to enabled `1`)
- `LOG_MAX_BYTES`: maximum bytes per rotated log file (default: `10485760`, 10MB)
- `LOG_BACKUP_COUNT`: number of rotated log files to keep (default: `5`)

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

Managing the recorder with the included helper script
----------------------------------------------------

A small helper script, `manage_rtsp.sh`, is included at the project root to
make starting, stopping and restarting the recorder easier during
development or when running manually.

Usage:

```
./manage_rtsp.sh start    # start the recorder in the background
./manage_rtsp.sh stop     # request a clean shutdown (SIGTERM); escalates to SIGKILL after a timeout
./manage_rtsp.sh restart  # stop then start
./manage_rtsp.sh status   # show whether the recorder is running
```

Behavior and files:

- The helper writes a PID file at `.rtsp_recorder.pid` when it starts the
  recorder and prefers that PID file for subsequent stop/status actions.
- Launcher actions are appended to `logs/launcher.log` for auditing.
- The recorder's stdout/stderr (the Python process) is redirected to
  `logs/rtsp_recorder.log` when started via the helper script.
- The helper will try to perform a clean shutdown (SIGTERM) and wait up to
  `TIMEOUT` seconds (default 10). You can override `TIMEOUT` and `PYTHON` via
  the environment when invoking the helper, for example:

```
PYTHON=/usr/local/bin/python3.12 TIMEOUT=30 ./manage_rtsp.sh restart
```

Notes:

- The helper uses a combination of the PID file and `pgrep -f` as a fallback
  to find a running instance; this makes it robust for typical single-instance
  use but not suitable for running multiple independent instances with the
  same script name. If you need per-instance control, consider running via a
  process supervisor (launchd/systemd) or we can extend the helper to match
  absolute paths.


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

- Filenames are created using an `strftime` pattern using python date
  the timestamp when it writes each segment (the script shows an example
  expanded name in the start log).
- Each segment will be approximately `SEGMENT_DURATION` seconds long (the
  final segment may be shorter when you stop the script).

## Logging

- Logs are written to `logs/rtsp_recorder.log` with rotation: max 10 MB per
  file and up to 5 backups.
- The script also logs to the console when direct run with `python3 rtsp_recorder.py`

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