#!/usr/bin/env python3

import os
import sys
import time
import signal
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import threading
from datetime import datetime
from pathlib import Path
import config

class RTSPRecorder:
    def __init__(self):
        self.setup_logging()
        self.setup_output_directory()
        self.process = None
        self.running = True
        self.clean_shutdown = False
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def setup_logging(self):
        # Ensure logs directory exists
        logs_dir = Path('logs')
        logs_dir.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)

        # Rotating file handler: 10 MB max, 5 backups
        log_path = logs_dir / 'rtsp_recorder.log'
        fh = RotatingFileHandler(str(log_path), maxBytes=10 * 1024 * 1024, backupCount=5)
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)

        # Remove any existing handlers attached to root logger to avoid duplicates
        if logger.handlers:
            logger.handlers = []

        logger.addHandler(ch)
        logger.addHandler(fh)

        self.logger = logging.getLogger(__name__)

    def setup_output_directory(self):
        """Create base output directory"""
        Path(config.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    def get_dated_output_directory(self):
        """Generate directory path with year/month/day structure"""
        now = datetime.now()
        dated_dir = os.path.join(
            config.OUTPUT_DIR,
            now.strftime('%Y'),  # Year folder
            now.strftime('%m'),  # Month folder
            now.strftime('%d')   # Day folder
        )
        Path(dated_dir).mkdir(parents=True, exist_ok=True)
        return dated_dir

    def get_output_filename(self):
        """Generate output filename pattern with date-based directory structure"""
        dated_dir = self.get_dated_output_directory()
        return os.path.join(dated_dir, f'recording_%H%M%S.{config.OUTPUT_FORMAT}')

    def build_ffmpeg_command(self, output_file):
        """Build FFmpeg command with optimized settings for low CPU usage"""
        command = [
            config.FFMPEG_BINARY,
            '-y',  # Overwrite output files
            # Reduce probe size and analyzeduration to speed up stream start and lower CPU
            '-analyzeduration', '1M',
            '-probesize', '1M',
            # Low-latency flags
            '-fflags', '+nobuffer',
            '-flags', 'low_delay',
        ]

        # Add RTSP transport if configured (must come before -i)
        if getattr(config, 'RTSP_TRANSPORT', ''):
            command.extend(['-rtsp_transport', config.RTSP_TRANSPORT])

        command.extend([
            '-hide_banner',
            '-i', config.RTSP_URL,
        ])

        # Add hardware acceleration if configured (optional, but often not needed on low-end CPUs)
        if config.HW_ACCELERATION:
            if config.HW_ACCELERATION == 'auto':
                if sys.platform == 'darwin':
                    command.extend(['-hwaccel', 'videotoolbox'])
                elif os.path.exists('/dev/nvidia0'):
                    command.extend(['-hwaccel', 'cuda'])
                elif os.path.exists('/dev/dri/renderD128'):
                    command.extend(['-hwaccel', 'vaapi'])
            else:
                command.extend(['-hwaccel', config.HW_ACCELERATION])

        # Output options
        command.extend([
            '-c:v', 'copy',  # Copy video stream without re-encoding
        ])
        # Optionally disable audio to save CPU
        if getattr(config, 'DISABLE_AUDIO', False):
            command.append('-an')
        else:
            command.extend(['-c:a', 'copy'])
        command.extend([
            '-f', 'segment',  # Enable segmentation
            '-segment_time', str(config.SEGMENT_DURATION),
            '-strftime', '1',  # Enable strftime for segment names
            '-reset_timestamps', '1',  # Reset timestamps at the beginning of each segment
            '-segment_format', config.OUTPUT_FORMAT,  # Set segment format
            output_file
        ])

        return command

    def start_recording(self):
        """Start the recording process"""
        while self.running:
            # Use dated directory and prepare a pattern for FFmpeg to create
            # segmented files (strftime tokens will be expanded by FFmpeg).
            dated_dir = self.get_dated_output_directory()

            # Snapshot existing files so we can remove any new files created if
            # FFmpeg exits with an error.
            try:
                before_files = set(os.listdir(dated_dir))
            except FileNotFoundError:
                before_files = set()

            output_pattern = os.path.join(dated_dir, f'recording_%H%M%S.{config.OUTPUT_FORMAT}')
            command = self.build_ffmpeg_command(output_pattern)

            # Prepare a human-friendly example filename for logging by expanding
            # the strftime tokens with current time (FFmpeg will use its own times
            # when creating actual segments).
            try:
                example_basename = datetime.now().strftime(os.path.basename(output_pattern))
                example_path = os.path.join(dated_dir, example_basename)
            except Exception:
                example_path = output_pattern

            self.logger.info(
                f"Starting recording into directory: {dated_dir} | "
                f"filename pattern: {os.path.basename(output_pattern)} | "
                f"first segment example: {example_path}"
            )
            def _stream_ffmpeg_stderr(proc):
                """Continuously read FFmpeg stderr and log it to the logger.

                This prevents the stderr buffer from filling and blocking the
                FFmpeg process. Runs in a daemon thread.
                """
                try:
                    for raw in iter(proc.stderr.readline, b''):
                        if not raw:
                            break
                        try:
                            line = raw.decode(errors='replace').rstrip()
                        except Exception:
                            line = str(raw)
                        # Log FFmpeg output as DEBUG to keep main logs cleaner,
                        # but include as INFO if you prefer.
                        self.logger.debug(f"ffmpeg: {line}")
                except Exception as e:
                    self.logger.debug(f"stderr reader stopped: {e}")

            try:
                # start ffmpeg process; send stdout to DEVNULL to avoid buffering
                self.process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE
                )

                # start background thread to drain stderr
                t = threading.Thread(target=_stream_ffmpeg_stderr, args=(self.process,), daemon=True)
                t.start()

                # Short startup check: ensure at least one segment file appears
                # within STARTUP_TIMEOUT seconds, otherwise assume ffmpeg is
                # stuck and restart.
                STARTUP_TIMEOUT = 20
                started_ok = False
                for _ in range(STARTUP_TIMEOUT):
                    try:
                        after_files = set(os.listdir(dated_dir))
                    except FileNotFoundError:
                        after_files = set()

                    new_files = after_files - before_files
                    if any(f.startswith('recording_') and f.endswith(f'.{config.OUTPUT_FORMAT}') for f in new_files):
                        started_ok = True
                        break
                    # if process has exited quickly, break and handle below
                    if self.process.poll() is not None:
                        break
                    time.sleep(1)

                if not started_ok:
                    # Either no files were created or process exited early.
                    rc = self.process.poll()
                    try:
                        # attempt to read a small portion of stderr by terminating
                        # after a short wait to let ffmpeg flush messages
                        time.sleep(0.1)
                    except Exception:
                        pass
                    if rc is None:
                        # process still running but no output -> kill and restart
                        self.logger.warning("FFmpeg started but produced no segments within timeout; restarting")
                        try:
                            self.process.terminate()
                            self.process.wait(timeout=2)
                        except Exception:
                            try:
                                self.process.kill()
                            except Exception:
                                pass
                    else:
                        self.logger.error(f"FFmpeg exited early with returncode={rc}; will remove partial files and retry")

                    # cleanup any new files from the failed attempt
                    try:
                        after_files = set(os.listdir(dated_dir))
                    except FileNotFoundError:
                        after_files = set()
                    new_files = after_files - before_files
                    deleted = []
                    for fname in new_files:
                        if fname.startswith('recording_') and fname.endswith(f'.{config.OUTPUT_FORMAT}'):
                            fpath = os.path.join(dated_dir, fname)
                            try:
                                os.remove(fpath)
                                deleted.append(fname)
                            except Exception as e:
                                self.logger.warning(f"Failed removing file {fpath}: {e}")
                    if deleted:
                        self.logger.info(f"Removed {len(deleted)} failed/partial segment(s): {deleted}")

                    # short backoff before restarting
                    time.sleep(5)
                    continue

                # If we reach here, ffmpeg produced at least one segment. Now wait
                # for the process to end (normal operation) or restart on error.
                self.process.wait()

                # process finished; collect stderr tail if any via implicit reader
                rc = self.process.returncode
                if rc != 0 and not self.clean_shutdown:
                    # Only clean up segments if this was an actual error, not a clean shutdown
                    self.logger.error(f"FFmpeg process failed (rc={rc}) — will remove newly created segments and restart")
                    try:
                        after_files = set(os.listdir(dated_dir))
                    except FileNotFoundError:
                        after_files = set()
                    new_files = after_files - before_files
                    deleted = []
                    for fname in new_files:
                        if fname.startswith('recording_') and fname.endswith(f'.{config.OUTPUT_FORMAT}'):
                            fpath = os.path.join(dated_dir, fname)
                            try:
                                os.remove(fpath)
                                deleted.append(fname)
                            except Exception as e:
                                self.logger.warning(f"Failed removing file {fpath}: {e}")
                    if deleted:
                        self.logger.info(f"Removed {len(deleted)} failed/partial segment(s): {deleted}")
                    else:
                        self.logger.info("No new segment files found to remove after failure.")
                elif self.clean_shutdown:
                    self.logger.info("Clean shutdown requested, keeping recorded segments")

                    time.sleep(5)

            except Exception as e:
                self.logger.error(f"Error during recording: {str(e)}")
                time.sleep(5)  # Wait before retrying

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info("Shutdown signal received, stopping recorder...")
        self.running = False
        if self.process:
            # Signal a clean shutdown to avoid triggering error cleanup
            self.clean_shutdown = True
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def validate_config(self):
        """Validate the configuration settings"""
        if not os.path.exists(config.FFMPEG_BINARY):
            raise ValueError(f"FFmpeg binary not found at {config.FFMPEG_BINARY}")
        
        if not config.RTSP_URL.startswith('rtsp://'):
            raise ValueError("Invalid RTSP URL format")
        
        if config.SEGMENT_DURATION <= 0:
            raise ValueError("Segment duration must be positive")

def main():
    recorder = RTSPRecorder()
    
    try:
        recorder.validate_config()
        recorder.start_recording()
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()