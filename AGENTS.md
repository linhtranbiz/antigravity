# AGENTS.md

## Cursor Cloud specific instructions

### Product

Single Python application: **DDS Email Intelligence / Rey Tran Telegram Bot**. It fetches Gmail via Google OAuth, triages mail with Claude (Anthropic), and delivers scheduled or on-demand briefings over Telegram. There is no Docker, database, or Node.js stack in this repo.

### System prerequisites (one-time on fresh Ubuntu VMs)

`python3 -m venv` requires the distro venv package:

```bash
sudo apt-get install -y python3.12-venv
```

### Dependency refresh

On each agent session startup, the VM update script recreates/refreshes `.venv` and installs `requirements.txt`. Activate with:

```bash
source .venv/bin/activate
```

### Configuration files (not in git)

| File | Purpose |
|------|---------|
| `.env` | Copy from `.env.template`; set `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS`, `AUTHORIZED_USER_IDS`, `GMAIL_USER` |
| `token.json` | Gmail/Calendar OAuth token; generate locally with `python auth_setup.py` (needs `credentials.json` from Google Cloud) |
| `credentials.json` | Google OAuth client secret (only needed to run `auth_setup.py`) |

### Logs directory

Create `logs/` before the first `bot_server.py` run — the module configures a `FileHandler` for `logs/bot.log` at import time:

```bash
mkdir -p logs
```

### Running the app

| Goal | Command |
|------|---------|
| Verify Google OAuth | `.venv/bin/python verify_oauth.py` |
| One-shot briefing (no Telegram send) | `.venv/bin/python main.py --mode morning --dry-run` |
| One-shot briefing + Telegram | `.venv/bin/python main.py --mode morning` |
| Full 24/7 bot (scheduler + chat) | `.venv/bin/python bot_server.py` |

Scheduled briefing times are **07:30**, **11:30**, and **16:00** in `Asia/Ho_Chi_Minh`.

### Lint / tests

No linter config or automated test suite is checked in. Use `python -m py_compile *.py` for a quick syntax check.

### Production deploy

`launch.sh` and `email-intel-bot.service` are for VPS/systemd deployment (`DEPLOY.md`). Not required for local development.
