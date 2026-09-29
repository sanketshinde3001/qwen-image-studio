#!/bin/bash
# Start Qwen-Image Studio: ./studio.sh [port]   (Ctrl+C to stop)
cd "$(dirname "$0")"
PORT="${1:-7860}"
export PYTHONDONTWRITEBYTECODE=1
(sleep 1.5 && open "http://127.0.0.1:$PORT") &
exec /usr/bin/python3 studio/server.py "$PORT"
