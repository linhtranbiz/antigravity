#!/usr/bin/env bash
# deploy.sh - Safe backup-and-deploy script for Rey Tran Bot
# Run this on your laptop to deploy local code to the VPS.

set -euo pipefail

# Text colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

VPS_IP="213.190.4.75"
APP_DIR="/opt/email-intel-bot"

echo -e "${GREEN}=== Rey Tran Bot Safe Deployer ===${NC}"

# 1. Compile Check python code locally
echo -e "${YELLOW}[1/5] Checking python syntax locally...${NC}"
if ! python3 -m compileall -q .; then
    echo -e "${RED}❌ Syntax check failed! Please fix your Python syntax errors before deploying.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Local python compile check passed.${NC}"

# 2. Trigger backup on the VPS of currently working code
echo -e "${YELLOW}[2/5] Ordering VPS to create a pre-deploy backup...${NC}"
# Check if time_machine.sh exists on VPS. If not, we skip the pre-backup for the first run.
if ssh root@$VPS_IP "[ -f $APP_DIR/time_machine.sh ]"; then
    ssh root@$VPS_IP "$APP_DIR/time_machine.sh backup"
    echo -e "${GREEN}✅ Pre-deploy backup created successfully on VPS.${NC}"
else
    echo -e "${YELLOW}⚠️ No time_machine.sh found on VPS yet (first deploy of time machine). Skipping pre-deploy backup.${NC}"
fi

# 3. Deploy code via rsync
echo -e "${YELLOW}[3/5] Syncing code to VPS...${NC}"
rsync -avz --delete \
  --exclude '__pycache__/' \
  --exclude '.venv/' \
  --exclude 'logs/' \
  --exclude 'backups/' \
  ./ root@$VPS_IP:$APP_DIR/
echo -e "${GREEN}✅ Files copied successfully.${NC}"

# 4. Configure systemd Services on VPS
echo -e "${YELLOW}[4/5] Updating and reloading systemd configuration on VPS...${NC}"
ssh root@$VPS_IP "
  chmod +x $APP_DIR/time_machine.sh && \
  cp $APP_DIR/email-intel-bot.service /etc/systemd/system/ && \
  cp $APP_DIR/email-intel-bot-rollback.service /etc/systemd/system/ && \
  systemctl daemon-reload && \
  systemctl enable email-intel-bot-rollback.service
"
echo -e "${GREEN}✅ systemd configuration updated.${NC}"

# 5. Restart Bot Service and Verify
echo -e "${YELLOW}[5/5] Restarting email-intel-bot service on VPS...${NC}"
ssh root@$VPS_IP "systemctl restart email-intel-bot"
echo -e "${YELLOW}Waiting for service to initialize (5 seconds)...${NC}"
sleep 5

# Check if service is active and running
if ssh root@$VPS_IP "systemctl is-active --quiet email-intel-bot"; then
    echo -e "${GREEN}★ SUCCESS: Rey Tran Bot is running perfectly on VPS!${NC}"
    ssh root@$VPS_IP "systemctl status email-intel-bot --no-pager"
else
    echo -e "${RED}❌ ERROR: Service is not active. Checking logs...${NC}"
    ssh root@$VPS_IP "journalctl -u email-intel-bot -n 20 --no-pager"
    echo -e "${YELLOW}Note: The auto-rollback systemd handler might be running in the background to restore the previous state.${NC}"
    exit 1
fi
