#!/usr/bin/env bash
# Start the Trans-EnV demo API and expose it with the ngrok CLI.
#
#   server/run.sh                      # port 8000, random ngrok URL
#   PORT=9000 server/run.sh            # custom port
#   NGROK_DOMAIN=my.ngrok-free.app server/run.sh   # reserved domain
#
# Alternative without the ngrok CLI (uses pyngrok):  python server/app.py --ngrok
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
PYTHON="${PYTHON:-$(command -v ../.venv/bin/python || command -v python3)}"

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok CLI not found. Install it from https://ngrok.com/download and run" >&2
  echo "  ngrok config add-authtoken <YOUR_TOKEN>" >&2
  echo "or use:  python server/app.py --ngrok" >&2
  exit 1
fi

"$PYTHON" app.py --port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

if [[ -n "${NGROK_DOMAIN:-}" ]]; then
  ngrok http "$PORT" --domain="$NGROK_DOMAIN"
else
  ngrok http "$PORT"
fi
