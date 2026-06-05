# Rey Tran Bot — Environment Variable Template

Create a `.env` file based on this template.

Do not commit `.env` to Git.

```bash
# App
APP_ENV=production
APP_NAME=rey-tran-bot
APP_TIMEZONE=Asia/Ho_Chi_Minh
APP_BASE_URL=https://your-domain.com

# Claude / Anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key
CLAUDE_MODEL=claude-sonnet-4-5

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_ALLOWED_USER_IDS=5912209648
TELEGRAM_ADMIN_USER_IDS=5912209648
TELEGRAM_WEBHOOK_SECRET=your_random_secret

# Bot Identity
BOT_NAME=Rey Tran Bot
BOT_OWNER_NAME=Linh Tran
BOT_OWNER_EMAIL=linhtran.business@gmail.com
BOT_DEFAULT_LANGUAGE=auto
BOT_DEFAULT_ADDRESS=Anh Linh

# Database
DATABASE_URL=postgresql://reybot:password@postgres:5432/reybot
DATABASE_POOL_SIZE=10

# Email / Gmail
GMAIL_CLIENT_ID=your_google_client_id
GMAIL_CLIENT_SECRET=your_google_client_secret
GMAIL_REFRESH_TOKEN=your_google_refresh_token
EMAIL_DRAFT_ONLY=true
EMAIL_SEND_REQUIRES_APPROVAL=true

# Scheduler
ENABLE_DAILY_BRIEFINGS=true
MORNING_BRIEFING_TIME=07:30
MIDDAY_BRIEFING_TIME=11:30
EVENING_WRAPUP_TIME=17:00

# Security
ENCRYPTION_KEY=generate_a_long_random_key
JWT_SECRET=generate_a_long_random_secret
LOG_LEVEL=info

# Storage
UPLOAD_DIR=/app/uploads
BACKUP_DIR=/app/backups

# Optional Integrations
GOOGLE_CALENDAR_ENABLED=false
GOOGLE_CONTACTS_ENABLED=false
NOTION_ENABLED=false
ODOO_ENABLED=false

# Runtime Controls
HIGH_RISK_CONFIRMATION_REQUIRED=true
AUTO_SEND_EMAIL=false
AUTO_SEND_TELEGRAM_EXTERNAL=false
```
