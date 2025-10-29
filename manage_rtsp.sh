#!/usr/bin/env bash
# manage_rtsp.sh
# Usage: ./manage_rtsp.sh
#
# If the recorder is running, send SIGTERM for a clean shutdown and wait up to
# TIMEOUT seconds. If it doesn't exit, send SIGKILL. If not running, start it
# in background. Actions are appended to logs/launcher.log and the started PID
# is written to .rtsp_recorder.pid

set -euo pipefail

# manage_rtsp.sh - start / stop / restart / status helper for rtsp_recorder.py
#
# Usage:
#   ./manage_rtsp.sh start
#   ./manage_rtsp.sh stop
#   ./manage_rtsp.sh restart
#   ./manage_rtsp.sh status

# Configuration (can be overridden in the environment)
SCRIPT_NAME="rtsp_recorder.py"
PYTHON_CMD="${PYTHON:-python3}"
TIMEOUT=${TIMEOUT:-10}
LOG_DIR="logs"
LAUNCHER_LOG="$LOG_DIR/launcher.log"
OUT_LOG="$LOG_DIR/rtsp_recorder.out"
PID_FILE=".rtsp_recorder.pid"

mkdir -p "$LOG_DIR"

log() {
  echo "$(date +'%Y-%m-%d %H:%M:%S') - $*" | tee -a "$LAUNCHER_LOG"
}

read_pidfile() {
  if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    echo "$pid"
  else
    echo ""
  fi
}

is_running() {
  local _pid=$1
  if [ -z "$_pid" ]; then
    return 1
  fi
  if kill -0 "$_pid" 2>/dev/null; then
    return 0
  fi
  return 1
}

find_pid() {
  # Prefer PID file if present and valid
  pid=$(read_pidfile)
  if [ -n "$pid" ] && is_running "$pid"; then
    # verify it looks like the recorder process (command contains script name)
    cmd=$(ps -p "$pid" -o args= 2>/dev/null || true)
    if echo "$cmd" | grep -q "$SCRIPT_NAME"; then
      echo "$pid"
      return
    fi
  fi

  # Fallback: use pgrep to find a running python process that references the script
  pids=$(pgrep -f "$SCRIPT_NAME" || true)
  if [ -z "$pids" ]; then
    echo ""
    return
  fi
  for p in $pids; do
    # skip our own shell
    if [ "$p" != "$$" ]; then
      echo "$p"
      return
    fi
  done
  echo ""
}

do_start() {
  pid=$(find_pid)
  if [ -n "$pid" ]; then
    log "Recorder already running (pid=$pid)."
    return 0
  fi

  START_CMD="$PYTHON_CMD $(pwd)/$SCRIPT_NAME"
  log "Starting recorder: $START_CMD"
  nohup $START_CMD >> "$OUT_LOG" 2>&1 &
  newpid=$!
  echo "$newpid" > "$PID_FILE"
  # small sleep to ensure process starts
  sleep 0.2
  if is_running "$newpid"; then
    log "Recorder started (pid=$newpid). stdout/stderr -> $OUT_LOG"
    return 0
  else
    log "Failed to start recorder; check $OUT_LOG and $LAUNCHER_LOG"
    return 1
  fi
}

do_stop() {
  pid=$(find_pid)
  if [ -z "$pid" ]; then
    log "Recorder not running."
    # ensure pidfile removed
    [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
    return 0
  fi
  log "Stopping recorder (pid=$pid) with SIGTERM..."
  kill -TERM "$pid" || true

  waited=0
  while is_running "$pid"; do
    if [ "$waited" -ge "$TIMEOUT" ]; then
      log "Process $pid did not exit after ${TIMEOUT}s; sending SIGKILL..."
      kill -KILL "$pid" 2>/dev/null || true
      break
    fi
    sleep 1
    waited=$((waited + 1))
  done

  if ! is_running "$pid"; then
    log "Process $pid exited."
    [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
    return 0
  else
    log "Process $pid still running after kill attempts; manual intervention may be required."
    return 1
  fi
}

do_status() {
  pid=$(find_pid)
  if [ -n "$pid" ]; then
    log "Recorder is running (pid=$pid)."
    ps -p "$pid" -o pid,cmd --no-headers || true
    return 0
  else
    log "Recorder is not running."
    return 1
  fi
}

# Main
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 {start|stop|restart|status}"
  exit 2
fi

case "$1" in
  start)
    do_start
    ;;
  stop)
    do_stop
    ;;
  restart)
    do_stop
    # give a short pause between stop and start
    sleep 1
    do_start
    ;;
  status)
    do_status
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 2
    ;;
esac

exit 0
