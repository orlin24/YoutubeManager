#!/usr/bin/env bash
# Stop the app.
set -euo pipefail

if systemctl list-unit-files | grep -q '^ai-youtube-manager.service'; then
  sudo systemctl stop ai-youtube-manager
  echo "Stopped 'ai-youtube-manager'."
else
  pkill -f "uvicorn app.main:app" || echo "No running uvicorn process."
fi
