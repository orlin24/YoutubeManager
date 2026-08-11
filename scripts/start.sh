#!/usr/bin/env bash
# Start the app. Uses systemd if the service exists, otherwise dev uvicorn.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if systemctl list-unit-files | grep -q '^ai-youtube-manager.service'; then
  sudo systemctl start ai-youtube-manager
  echo "Started systemd service 'ai-youtube-manager'. Logs: journalctl -u ai-youtube-manager -f"
else
  cd "$APP_DIR/backend"
  if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
  fi
  echo "Starting dev server on 0.0.0.0:5000 (Ctrl+C to stop)"
  exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000
fi
