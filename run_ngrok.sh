#!/bin/bash

# This script runs ngrok in the background and logs its output to a file.

# Set the root directory and log file path
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"
LOG_FILE="$LOG_DIR/ngrok.out"

# Arguments: port and ngrok config file
NGROK_PORT="$1"
NGROK_CONFIG="$2"

# Check if the required arguments are provided
if [ -z "$NGROK_PORT" ] || [ -z "$NGROK_CONFIG" ]; then
    echo "Error: port and ngrok config are required." >&2
    echo "Usage: ./run_ngrok.sh <port> <ngrok_config>" >&2
    exit 1
fi

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo "Error: ngrok is not installed. Please install ngrok and try again." >&2
    exit 1
fi

# Check if the ngrok config file exists
if [ ! -f "$NGROK_CONFIG" ]; then
    echo "Error: ngrok config not found: $NGROK_CONFIG" >&2
    exit 1
fi

# Background execution
mkdir -p "$LOG_DIR"
nohup ngrok http "$NGROK_PORT" --config "$NGROK_CONFIG" --log=stdout > "$LOG_FILE" 2>&1 &
PID=$!

# Wait for a second until the background process is revealed, then check if it is still alive.
sleep 5
if ! kill -0 "$PID" 2>/dev/null; then
    echo "Error: ngrok failed to start. See $LOG_FILE" >&2
    tail -n 20 "$LOG_FILE" >&2
    exit 1
fi
echo "Ngrok successfully activated! (:$NGROK_PORT, PID: $PID, log: $LOG_FILE)"
