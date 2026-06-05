# Rey Tran Bot — VPS Deployment Guide

## Purpose

This guide describes how to deploy Rey Tran Bot on a VPS.

## Recommended VPS Requirements

Minimum:

- 1 vCPU.
- 1–2 GB RAM.
- 25 GB SSD.
- Ubuntu 22.04 or 24.04.
- Static public IP.

Recommended:

- 2 vCPU.
- 4 GB RAM.
- 50 GB SSD.
- Ubuntu 24.04 LTS.
- Automated backups.

## Recommended Architecture

```text
Telegram / Email
       |
       v
Bot Server API
       |
       v
Agent Orchestrator
       |
       +--> Claude API
       +--> Database
       +--> Scheduler
       +--> Email API
       +--> Logs
```

## Suggested Stack

### Python Version

- Python 3.11+
- FastAPI
- python-telegram-bot or aiogram
- Anthropic SDK
- SQLAlchemy
- PostgreSQL
- APScheduler
- Docker Compose
- Nginx

### Node.js Version

- Node.js 20+
- Telegraf
- Express or Fastify
- Anthropic SDK
- Prisma
- PostgreSQL
- node-cron
- Docker Compose
- Nginx

## Deployment Steps

### 1. Create VPS

Create a VPS with Ubuntu 24.04 LTS.

### 2. Secure Server

```bash
sudo apt update && sudo apt upgrade -y
sudo adduser reybot
sudo usermod -aG sudo reybot
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

### 3. Install Docker

```bash
sudo apt install ca-certificates curl gnupg -y
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-compose-plugin -y
```

### 4. Clone Project

```bash
git clone <your-repo-url> rey-tran-bot
cd rey-tran-bot
```

### 5. Configure Environment

Create `.env` from `10_ENV_TEMPLATE.md`.

### 6. Start Services

```bash
docker compose up -d --build
```

### 7. Configure Telegram Webhook

Use either:

- Telegram long polling for simple version.
- Webhook with HTTPS for production.

For webhook, configure:

```text
https://your-domain.com/telegram/webhook
```

### 8. Configure Nginx

Nginx should reverse proxy to the bot server.

### 9. Configure SSL

Use Let’s Encrypt:

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

### 10. Enable Backups

Back up:

- Database.
- `.env` securely.
- Logs.
- Uploaded files.
- Memory records.

## Production Checklist

- [ ] VPS secured.
- [ ] Firewall enabled.
- [ ] SSH key login configured.
- [ ] Password login disabled.
- [ ] Docker running.
- [ ] Database running.
- [ ] Telegram bot responds.
- [ ] Claude API works.
- [ ] Scheduler works.
- [ ] Logs are written.
- [ ] Error alerts configured.
- [ ] Backups enabled.
- [ ] Email sending requires approval.
- [ ] High-risk actions require confirmation.

## Monitoring

Recommended:

- Uptime Kuma.
- Grafana + Prometheus for advanced version.
- Sentry for error logging.
- Daily log digest to Telegram.

## Backup Command Example

```bash
pg_dump "$DATABASE_URL" > backup_$(date +%Y%m%d_%H%M%S).sql
```

## Restart Policy

Docker Compose should use:

```yaml
restart: unless-stopped
```

## Security Warning

Never store API keys in code.

Use:

- `.env`
- server secrets
- restricted file permissions
- separate development and production keys
