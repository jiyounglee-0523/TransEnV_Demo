#!/bin/bash

# This script runs a backend server in the background and logs its output to a file.
# With --foreground, it runs in the foreground instead (e.g. as the main process of a Docker container).

# Set the root directory and log file path
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"
LOG_FILE="$LOG_DIR/backend.out"

# Arguments: host, port and optional --foreground
HOST="$1"
PORT="$2"
MODE="$3"

# Check if the required arguments are provided
if [ -z "$HOST" ] || [ -z "$PORT" ]; then
    echo "Error: host and port are required." >&2
    echo "Usage: ./run_backend.sh <host> <port> [--foreground]" >&2
    exit 1
fi

# Check if the optional argument is valid
if [ -n "$MODE" ] && [ "$MODE" != "--foreground" ]; then
    echo "Error: unknown option: $MODE" >&2
    echo "Usage: ./run_backend.sh <host> <port> [--foreground]" >&2
    exit 1
fi

# Check if uvicorn is installed
if ! command -v uvicorn &> /dev/null; then
    echo "Error: uvicorn is not installed. Please install uvicorn and try again." >&2
    exit 1
fi

mkdir -p "$LOG_DIR"
cd "$ROOT/backend" || exit 1

# Foreground execution: replace this shell with the backend so that it keeps the container alive and receives signals.
# Output goes to both stdout (docker logs) and the log file.
if [ "$MODE" = "--foreground" ]; then
    exec > >(tee -a "$LOG_FILE") 2>&1
    echo "Backend starting in foreground... ($HOST:$PORT, log: $LOG_FILE)"
    export PYTHONUNBUFFERED=1
    exec uvicorn main:app --host "$HOST" --port "$PORT"
fi

# Background execution
nohup uvicorn main:app --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
PID=$!


# Wait for a second until the background process is revealed, then check if it is still alive.
sleep 3
if ! kill -0 "$PID" 2>/dev/null; then
    echo "Error: backend failed to start. See $LOG_FILE" >&2
    tail -n 20 "$LOG_FILE" >&2
    exit 1
fi
echo "Backend successfully activated! ($HOST:$PORT, PID: $PID, log: $LOG_FILE)"
