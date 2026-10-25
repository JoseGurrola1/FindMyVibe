#!/usr/bin/env bash
#
# Pull the latest code from GitHub and restart FindMyVibe.
# Usage, from the repo folder on the server:  bash deploy/update.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> Pulling latest code"
git pull --ff-only

echo "==> Updating backend"
.venv/bin/pip install -r requirements.txt -q

echo "==> Rebuilding frontend"
cd frontend
npm ci
npm run build

echo "==> Restarting"
sudo systemctl restart findmyvibe-api findmyvibe-web
sleep 3
systemctl --no-pager --lines=0 status findmyvibe-api findmyvibe-web | grep -E "●|Active:" || true
echo "Done."
