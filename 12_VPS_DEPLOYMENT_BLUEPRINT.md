# Rey Tran Bot — VPS Deployment Blueprint

## Goal

Deploy Rey Tran Bot online so it can operate 24/7 across Telegram, email, memory, task management, and scheduled briefings.

## Recommended Architecture

```text
Telegram / Email / Web Admin
          |
          v
API Server
          |
          v
Rey Agent Orchestrator
          |
          +--> Claude API
          +--> PostgreSQL
          +--> Scheduler
          +--> Email API
          +--> Logs
          +--> Memory Store
          +--> Task Store
```

## Recommended Stack

Backend:

- Python 3.11+
- FastAPI
- aiogram or python-telegram-bot
- Anthropic SDK
- SQLAlchemy
- PostgreSQL
- APScheduler
- Docker Compose

Infrastructure:

- Ubuntu 24.04 LTS
- Nginx
- Let's Encrypt SSL
- UFW firewall
- Docker
- Daily backups

## Minimum VPS

- 1–2 vCPU
- 2 GB RAM
- 25 GB SSD
- Ubuntu 22.04 or 24.04

## Production VPS

- 2 vCPU
- 4 GB RAM
- 50 GB SSD
- Automated backup
- Monitoring

## Services

1. `bot-api`
2. `postgres`
3. `scheduler`
4. `nginx`
5. Optional: `admin-dashboard`
6. Optional: `worker`

## Deployment Checklist

- [ ] VPS created
- [ ] SSH key login enabled
- [ ] Password login disabled
- [ ] Firewall enabled
- [ ] Docker installed
- [ ] Docker Compose installed
- [ ] Domain pointed to VPS
- [ ] SSL enabled
- [ ] Telegram bot token configured
- [ ] Claude API key configured
- [ ] Database configured
- [ ] Scheduler configured
- [ ] Daily briefings tested
- [ ] Email draft flow tested
- [ ] Approval-gated sending tested
- [ ] Logs working
- [ ] Backups working

## Security Rule

Never hardcode API keys. Use `.env` and keep it out of Git.
