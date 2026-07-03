#!/usr/bin/env bash
# stop_decoder.sh — cleanly stop the Confluence Decoder stack
set -e

echo "Stopping Confluence Decoder..."
lsof -ti :3000 | xargs kill -9 2>/dev/null && echo "  React (:3000) stopped" || echo "  React not running"
lsof -ti :8000 | xargs kill -9 2>/dev/null && echo "  Backend (:8000) stopped" || echo "  Backend not running"
pkill -f "app_mode_loader" 2>/dev/null && echo "  PWA closed" || echo "  PWA not running"
echo "Done. MongoDB left running (shared service)."
