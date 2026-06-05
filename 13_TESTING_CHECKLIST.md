# Rey Tran Bot — Testing Checklist

## Purpose

Use this checklist before launching Rey Tran Bot.

## 1. Telegram Tests

- [ ] Bot responds to `/start`.
- [ ] Bot only responds to authorized Telegram user IDs.
- [ ] Bot rejects unauthorized users.
- [ ] Bot can capture a task with `/task`.
- [ ] Bot can generate a briefing with `/briefing`.
- [ ] Bot can draft a business message.
- [ ] Bot can translate Vietnamese to Chinese with pinyin and Vietnamese meaning.
- [ ] Bot handles long messages.
- [ ] Bot handles unclear messages without crashing.
- [ ] Bot logs important actions.

## 2. Email Tests

- [ ] Bot can authenticate with Gmail.
- [ ] Bot can read email metadata.
- [ ] Bot can summarize selected email.
- [ ] Bot can draft reply.
- [ ] Bot does not send email without approval.
- [ ] Bot flags high-risk email content.
- [ ] Bot extracts follow-up tasks from email.
- [ ] Bot logs email draft status.

## 3. Memory Tests

- [ ] Bot can save memory.
- [ ] Bot can retrieve memory.
- [ ] Bot can update memory.
- [ ] Bot marks uncertain memory correctly.
- [ ] Bot does not invent missing facts.
- [ ] Bot respects sensitive memory categories.

## 4. Task Tests

- [ ] Bot creates task.
- [ ] Bot updates task.
- [ ] Bot lists open tasks.
- [ ] Bot marks task complete.
- [ ] Bot detects overdue tasks.
- [ ] Bot includes tasks in briefings.

## 5. Briefing Tests

- [ ] 7:30 AM briefing works.
- [ ] 11:30 AM briefing works.
- [ ] 5:00 PM wrap-up works.
- [ ] Briefings include tasks and follow-ups.
- [ ] Briefings are concise enough for Telegram.
- [ ] Briefing logs are stored.

## 6. Security Tests

- [ ] API keys are not in code.
- [ ] `.env` is ignored by Git.
- [ ] HTTPS enabled.
- [ ] Firewall enabled.
- [ ] Database password is strong.
- [ ] Telegram webhook secret configured.
- [ ] Server logs do not expose secrets.
- [ ] High-risk actions require confirmation.

## 7. Failure Tests

- [ ] Claude API failure produces graceful error.
- [ ] Telegram API failure is logged.
- [ ] Database failure is logged.
- [ ] Email API failure is logged.
- [ ] Scheduler failure is logged.
- [ ] Bot restarts automatically after crash.

## 8. Launch Criteria

Launch only when:

- Telegram works.
- Authorized-user restriction works.
- Claude API works.
- Database works.
- Scheduler works.
- Logs work.
- Email sending is draft-only or approval-gated.
- Backups are configured.
