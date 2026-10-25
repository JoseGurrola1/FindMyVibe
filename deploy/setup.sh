#!/usr/bin/env bash
#
# One-time setup for FindMyVibe on a fresh Ubuntu 24.04 server (e.g. AWS EC2).
#
# Usage, from the repo folder on the server:
#   bash deploy/setup.sh yourdomain.tech
#
# It installs Python, Node.js and Caddy, builds the app, asks for your API
# keys, and starts everything as services that survive reboots and crashes.
# Safe to run again if something fails partway.

set -euo pipefail

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "Usage: bash deploy/setup.sh yourdomain.tech"
  exit 1
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="$(id -un)"
step() { echo; echo "==> $*"; }

step "Installing system packages"
sudo apt-get update -y
sudo apt-get install -y git curl python3-venv python3-pip \
  debian-keyring debian-archive-keyring apt-transport-https gnupg

step "Installing Node.js 22 (Next.js 16 needs Node 20.9 or newer)"
if ! command -v node >/dev/null || [[ "$(node -v | cut -c2- | cut -d. -f1)" -lt 22 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
node -v

step "Installing Caddy (web server + automatic HTTPS)"
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y caddy
fi

step "Adding 2 GB of swap so the Next.js build doesn't run out of memory"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

step "API keys"
if [[ -f "$APP_DIR/.env" ]]; then
  echo "$APP_DIR/.env already exists; keeping it."
else
  read -rsp "Paste your SERPAPI_KEY (hidden), then Enter: " SERPAPI_KEY; echo
  read -rsp "Paste your GEMINI_API_KEY (hidden), then Enter: " GEMINI_API_KEY; echo
  umask 077
  printf 'SERPAPI_KEY=%s\nGEMINI_API_KEY=%s\n' "$SERPAPI_KEY" "$GEMINI_API_KEY" > "$APP_DIR/.env"
  umask 022
  echo "Saved to $APP_DIR/.env (readable only by $APP_USER)."
fi

step "Installing backend (Python)"
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

step "Building frontend (Next.js) - this takes a few minutes"
cd "$APP_DIR/frontend"
npm ci
npm run build

step "Creating services"
sudo tee /etc/systemd/system/findmyvibe-api.service >/dev/null <<EOF
[Unit]
Description=FindMyVibe API (FastAPI)
After=network.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/findmyvibe-web.service >/dev/null <<EOF
[Unit]
Description=FindMyVibe Web (Next.js)
After=network.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR/frontend
Environment=NODE_ENV=production
ExecStart=$(command -v npm) start -- -p 3000 -H 127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now findmyvibe-api findmyvibe-web
sudo systemctl restart findmyvibe-api findmyvibe-web

step "Configuring Caddy for $DOMAIN"
SITES="$DOMAIN"
# Also serve www.<domain>, except for sslip.io / nip.io style addresses.
if [[ "$DOMAIN" != *sslip.io && "$DOMAIN" != *nip.io && "$DOMAIN" != www.* ]]; then
  SITES="$DOMAIN, www.$DOMAIN"
fi

sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
$SITES {
    encode gzip

    # Backend API
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    # Everything else: the Next.js site
    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
EOF

sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl enable caddy
sudo systemctl reload caddy || sudo systemctl restart caddy

step "Checking services"
sleep 3
systemctl --no-pager --lines=0 status findmyvibe-api findmyvibe-web caddy | grep -E "●|Active:" || true
curl -fsS http://127.0.0.1:8000/ && echo || echo "API not answering yet; check: sudo journalctl -u findmyvibe-api -n 50"

echo
echo "Done. Open https://$DOMAIN"
echo "If HTTPS isn't working yet, your DNS may still be updating; Caddy keeps"
echo "retrying on its own. Check with: sudo journalctl -u caddy -n 50"
