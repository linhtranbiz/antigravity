#!/usr/bin/env bash
# MOIT Pricing Platform — VPS deployment helper
# Usage: bash deploy.sh [install|start|stop|restart|status|logs]
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$APP_DIR/.venv"
SERVICE_NAME="moit-pricing"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

cmd="${1:-start}"

install() {
  echo "=== Installing dependencies ==="
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip -q
  "$VENV/bin/pip" install -r "$APP_DIR/requirements.txt" -q
  echo "Done. Run: bash deploy.sh start"
}

start_app() {
  echo "=== Starting MOIT Pricing on $HOST:$PORT ==="
  cd "$APP_DIR"
  "$VENV/bin/python" run.py --host "$HOST" --port "$PORT"
}

start_systemd() {
  # Write systemd unit
  sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=MOIT Pricing Platform
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$APP_DIR
ExecStart=$VENV/bin/python run.py --host 0.0.0.0 --port $PORT
Restart=on-failure
RestartSec=5
Environment=SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable "$SERVICE_NAME"
  sudo systemctl start "$SERVICE_NAME"
  echo "Service started. Check: sudo systemctl status $SERVICE_NAME"
}

case "$cmd" in
  install)   install ;;
  start)     start_app ;;
  systemd)   install && start_systemd ;;
  stop)      sudo systemctl stop "$SERVICE_NAME" ;;
  restart)   sudo systemctl restart "$SERVICE_NAME" ;;
  status)    sudo systemctl status "$SERVICE_NAME" ;;
  logs)      sudo journalctl -u "$SERVICE_NAME" -f ;;
  *)
    echo "Usage: $0 {install|start|systemd|stop|restart|status|logs}"
    exit 1
    ;;
esac
