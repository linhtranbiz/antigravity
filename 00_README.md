# Rey Tran Bot — Launch Package

## Purpose

**Rey Tran Bot** is a General Manager AI Agent for **Linh Tran**. It is designed to operate across **Telegram** and **email**, and later be deployed online on a **VPS**.

Rey Tran Bot is not only a task assistant. It acts as Linh Tran’s executive operating layer: a practical, strategic, confidential General Manager who helps manage business, finance, operations, communication, learning, relationships, personal execution, and daily life matters.

## Core Mission

Rey Tran Bot helps Linh Tran:

1. Think clearly.
2. Make better decisions.
3. Execute faster.
4. Track commitments.
5. Communicate professionally.
6. Manage business and personal priorities.
7. Protect confidentiality and reputation.
8. Operate with the discipline of a high-level executive office.

## Target Channels

- Telegram bot for fast daily interaction, notifications, task capture, briefings, and urgent executive support.
- Email assistant for drafting, summarizing, triaging, replying, and following up.
- VPS deployment for 24/7 availability and future integration with databases, calendars, Google Workspace, Notion, CRM, and internal business systems.

## Recommended File Use

Use the files in this package as follows:

| File | Purpose |
|---|---|
| `01_CLAUDE_PROJECT_INSTRUCTION.md` | Paste into Claude Project Instruction |
| `02_REY_TRAN_BOT_SYSTEM_PROMPT.md` | Main system prompt for the AI agent |
| `03_AGENT_MEMORY_PROFILE.md` | Standing memory and personal/business context |
| `04_OPERATING_PRINCIPLES.md` | Behavioral rules and execution philosophy |
| `05_TELEGRAM_WORKFLOW.md` | Telegram interaction design |
| `06_EMAIL_WORKFLOW.md` | Email assistant workflow |
| `07_DAILY_BRIEFING_AND_TODO_CRON.md` | Scheduled briefing prompts |
| `08_TOOLS_AND_INTEGRATIONS.md` | Tools, APIs, and permission model |
| `09_VPS_DEPLOYMENT_GUIDE.md` | Practical VPS launch checklist |
| `10_ENV_TEMPLATE.md` | Environment variable template |
| `11_DATA_MODEL_AND_LOGS.md` | Suggested database schema and logs |
| `12_SECURITY_AND_PRIVACY_POLICY.md` | Confidentiality and safety rules |
| `13_TESTING_CHECKLIST.md` | Launch testing checklist |
| `14_REY_TRAN_BOT_MASTER_PROMPT.md` | One-file master prompt for quick deployment |

## Recommended Build Stack

A practical first version can use:

- **Python** or **Node.js**
- Telegram Bot API
- Gmail API or IMAP/SMTP
- Claude API as reasoning engine
- PostgreSQL or SQLite for task/memory logs
- Docker
- Nginx reverse proxy
- VPS from Hetzner, DigitalOcean, AWS Lightsail, or similar

## Launch Philosophy

Start simple. The first production version should reliably do five things:

1. Receive Telegram messages.
2. Draft and classify email.
3. Maintain task and follow-up lists.
4. Send scheduled briefings.
5. Preserve important memory in a structured database.

After stability is achieved, add more complex integrations.
