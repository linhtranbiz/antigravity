# Rey Tran Bot — Tools and Integrations

## Purpose

This file defines recommended tools and integrations for Rey Tran Bot.

The bot should start simple and expand in phases.

## Phase 1 — Minimum Viable Bot

Required:

- Telegram Bot API.
- Claude API.
- Local database.
- Basic task memory.
- Basic scheduled briefings.
- VPS deployment.

Recommended stack:

- Python FastAPI or Node.js Express.
- SQLite for first version.
- PostgreSQL for production.
- Docker.
- Nginx.
- systemd or Docker Compose.

## Phase 2 — Email Integration

Add:

- Gmail API.
- OAuth authentication.
- Email search.
- Email reading.
- Draft creation.
- Send only with approval.
- Attachment metadata reading.

Email features:

- Summarize email.
- Draft reply.
- Extract tasks.
- Classify priority.
- Track follow-up.

## Phase 3 — Calendar and Contacts

Add:

- Google Calendar API.
- Google Contacts API.

Features:

- Daily schedule briefing.
- Meeting preparation.
- Availability checking.
- Contact-aware drafting.

## Phase 4 — Knowledge Base

Add:

- File storage.
- Document search.
- Vector database.
- Project knowledge folders.

Options:

- PostgreSQL + pgvector.
- Qdrant.
- Chroma.
- Weaviate.

## Phase 5 — Business System Integrations

Potential future integrations:

- Odoo ERP.
- Notion.
- Google Drive.
- Microsoft 365.
- Slack.
- Zalo Business.
- CRM.
- Accounting system.
- Internal dashboards.

## Tool Permission Model

### Read-only Tools

Safe by default:

- Read Telegram messages.
- Read task database.
- Read memory database.
- Read email metadata.
- Read calendar.

### Draft Tools

Require review:

- Draft email.
- Draft Telegram message.
- Draft memo.
- Draft contract comment.
- Draft bank reply.

### Write Tools

Require approval:

- Send email.
- Send Telegram message to third party.
- Update official records.
- Create calendar events with invitees.
- Delete records.
- Mark tasks as closed when ambiguous.

### High-Risk Tools

Require explicit confirmation every time:

- Send banking commitments.
- Send legal statements.
- Confirm price/quantity/payment terms.
- Communicate with regulators.
- Share confidential documents.
- Approve contracts.

## Recommended Internal Tool Names

```text
telegram.receive_message
telegram.send_message
email.search
email.read
email.create_draft
email.send_after_approval
task.create
task.update
task.list
memory.search
memory.write
decision.log
briefing.generate
calendar.search
calendar.create_event
document.search
```

## Claude Tool Prompt Pattern

When the agent uses tools, it should think in this order:

1. What does Linh Tran want?
2. Is this simple or high-stakes?
3. What context is needed?
4. Can memory answer this?
5. Is external/latest data required?
6. Is a draft enough or does this require sending?
7. Is approval required?
8. What should be logged after completion?

## Logging Requirements

Every important action should create a log entry:

```json
{
  "timestamp": "",
  "channel": "telegram | email | system | manual",
  "user_request": "",
  "agent_action": "",
  "approval_required": true,
  "approval_status": "pending | approved | rejected | not_required",
  "related_project": "",
  "risk_level": "low | medium | high",
  "notes": ""
}
```
