#!/usr/bin/env python3

import os
import sys
import time
import signal
import logging
from logging.handlers import RotatingFileHandler
import subprocess
from datetime import datetime
from pathlib import Path
import config

class RTSPRecorder:
    def __init__(self):
        self.setup_logging()
        self.setup_output_directory()
        self.process = None
        self.running = True
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
        """Build FFmpeg command with configured settings"""
        command = [
            config.FFMPEG_BINARY,
            '-y',  # Overwrite output files
            # '-rtsp_transport', 'tcp',  # Use TCP for RTSP (more stable)
            '-re',
            '-hide_banner',
            '-i', config.RTSP_URL,
        ]

        # Add hardware acceleration if configured
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
            '-c:a', 'copy',   # Copy audio stream without re-encoding
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
            try:
                self.process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                # Wait for the process to complete or be interrupted
                self.process.wait()

                # Read stderr for logging/debugging
                try:
                    stderr = self.process.stderr.read().decode()
                except Exception:
                    stderr = ''

                # If FFmpeg failed (non-zero return) and we are still running,
                # delete any newly-created segment files and retry after a delay.
                if self.process.returncode != 0:
                    self.logger.error(f"FFmpeg process failed (rc={self.process.returncode}): {stderr}")

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

                    # Wait a bit before retrying (permanent restart behavior)
                    time.sleep(5)

            except Exception as e:
                self.logger.error(f"Error during recording: {str(e)}")
                time.sleep(5)  # Wait before retrying

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info("Shutdown signal received, stopping recorder...")
        self.running = False
        if self.process:
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