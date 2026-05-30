#!/usr/bin/env bash
# launch.sh - Idempotent deployment script for DDS Email Intel Telegram Bot
# Run this on the VPS as root/sudo

set -euo pipefail

# Text colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== DDS Email Intel Bot Setup & Launch ===${NC}"

# 1. Check root privileges
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Error: Please run this script as root or with sudo.${NC}"
  exit 1
fi

APP_DIR="/opt/email-intel-bot"
cd "$APP_DIR"

# 2. Configure Timezone
echo -e "${YELLOW}[1/6] Configuring server timezone to Asia/Ho_Chi_Minh...${NC}"
if command -v timedatectl >/dev/null 2>&1; then
  timedatectl set-timezone Asia/Ho_Chi_Minh
  echo -e "${GREEN}Timezone set to Asia/Ho_Chi_Minh.${NC}"
else
  echo -e "${YELLOW}Warning: timedatectl not found, skipping timezone configuration.${NC}"
fi

# 3. Create Logs Directory
echo -e "${YELLOW}[2/6] Creating logs directory...${NC}"
mkdir -p "$APP_DIR/logs"
chmod 755 "$APP_DIR/logs"
echo -e "${GREEN}Logs directory ready: $APP_DIR/logs${NC}"

# 4. Validate Environment Variables
echo -e "${YELLOW}[3/6] Validating environment variables in .env...${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
  echo -e "${RED}Error: .env file not found at $APP_DIR/.env.${NC}"
  echo -e "${RED}Please create it by copying .env.template and filling in your credentials.${NC}"
  exit 1
fi

# Load variables for validation
check_var() {
  local var_name=$1
  # Get value from .env
  local val
  val=$(grep "^${var_name}=" "$APP_DIR/.env" | cut -d'=' -f2- | tr -d '"' | tr -d "'") || true
  if [ -z "$val" ] || [[ "$val" == *"your_"* ]] || [[ "$val" == *"_here"* ]]; then
    echo -e "${RED}Error: $var_name is not configured in .env file.${NC}"
    exit 1
  fi
}

check_var "ANTHROPIC_API_KEY"
check_var "TELEGRAM_BOT_TOKEN"
check_var "TELEGRAM_CHAT_IDS"
check_var "AUTHORIZED_USER_IDS"
check_var "GMAIL_USER"

echo -e "${GREEN}Environment variables validated successfully.${NC}"

# 5. Set up Virtual Environment and Dependencies
echo -e "${YELLOW}[4/6] Setting up Python virtual environment and dependencies...${NC}"
if [ ! -d "$APP_DIR/.venv" ]; then
  echo "Creating new virtual environment..."
  python3 -m venv "$APP_DIR/.venv"
fi

echo "Installing requirements..."
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
echo -e "${GREEN}Dependencies installed successfully.${NC}"

# 6. Configure systemd Service
echo -e "${YELLOW}[5/6] Configuring systemd service...${NC}"
SERVICE_FILE="email-intel-bot.service"
if [ -f "$APP_DIR/$SERVICE_FILE" ]; then
  cp "$APP_DIR/$SERVICE_FILE" "/etc/systemd/system/$SERVICE_FILE"
  echo "Service file copied to /etc/systemd/system/"
  
  systemctl daemon-reload
  systemctl enable "$SERVICE_FILE"
  echo -e "${GREEN}Service enabled for auto-start on boot.${NC}"
else
  echo -e "${RED}Error: Service file not found at $APP_DIR/$SERVICE_FILE.${NC}"
  exit 1
fi

# 7. Start/Restart the Service
echo -e "${YELLOW}[6/6] Starting/Restarting the service...${NC}"
systemctl restart "$SERVICE_FILE"
echo -e "${GREEN}Service restarted.${NC}"

# Check status
echo -e "${YELLOW}Verifying service status...${NC}"
sleep 2
if systemctl is-active --quiet "$SERVICE_FILE"; then
  echo -e "${GREEN}★ SUCCESS: DDS Email Intel Bot is running!${NC}"
  systemctl status "$SERVICE_FILE" --no-pager
  
  echo -e "${YELLOW}Calculating next briefing run time...${NC}"
  "$APP_DIR/.venv/bin/python" -c '
import datetime as dt
from zoneinfo import ZoneInfo
tz = ZoneInfo("Asia/Ho_Chi_Minh")
now = dt.datetime.now(tz)
times = [
    ("Morning Brief", now.replace(hour=7, minute=30, second=0, microsecond=0)),
    ("Lunch Brief", now.replace(hour=11, minute=30, second=0, microsecond=0)),
    ("Day Break Brief", now.replace(hour=16, minute=0, second=0, microsecond=0))
]
next_brief = None
for name, t in times:
    if t > now:
        next_brief = (name, t)
        break
if not next_brief:
    next_brief = (times[0][0], times[0][1] + dt.timedelta(days=1))
date_str = next_brief[1].strftime("%Y-%m-%d %H:%M:%S %Z")
print(f"\033[1;32m★ Next Scheduled Briefing: {next_brief[0]} at {date_str}\033[0m")
'
else
  echo -e "${RED}❌ ERROR: Service failed to start. Printing systemd logs:${NC}"
  journalctl -u "$SERVICE_FILE" -n 20 --no-pager
  exit 1
fi
