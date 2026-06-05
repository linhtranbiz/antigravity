# Rey Tran Bot — Daily Briefing and Todo Cron Prompts

## Purpose

Rey Tran Bot should send Linh Tran three daily briefings:

1. **7:30 AM** — Morning Command Briefing.
2. **11:30 AM** — Midday Execution Check.
3. **5:00 PM** — End-of-Day Wrap-Up.

These briefings should consolidate tasks, email follow-ups, Telegram commitments, deadlines, and missing items.

## Time Zone

Default time zone:

```text
Asia/Ho_Chi_Minh
```

## 7:30 AM — Morning Command Briefing

### Cron

```cron
30 7 * * *
```

### Prompt

```markdown
Generate Linh Tran’s Morning Command Briefing.

Review all available task logs, email follow-ups, Telegram notes, calendar events, decision logs, and open loops.

Produce a concise executive briefing with:

1. Top 5 priorities for today.
2. Urgent deadlines.
3. Important meetings or calls.
4. Emails requiring Linh Tran’s decision or reply.
5. People Linh Tran should follow up with.
6. Business risks to watch today.
7. Personal/life tasks that should not be forgotten.
8. Recommended sequence of execution.
9. One short strategic reminder for the day.

Tone: direct, executive, practical.
Address: Anh Linh.
Language: match Linh Tran’s default working language or use Vietnamese if context is Vietnamese.
```

## 11:30 AM — Midday Execution Check

### Cron

```cron
30 11 * * *
```

### Prompt

```markdown
Generate Linh Tran’s Midday Execution Check.

Compare the morning briefing against current completed and incomplete items.

Produce:

1. What should already be done by now.
2. What is still missing.
3. What requires immediate follow-up before lunch.
4. Emails or messages waiting for reply.
5. People who may be waiting for Linh Tran.
6. Any urgent risks that appeared since morning.
7. Suggested 3 priorities for the next 4 hours.

Tone: concise, practical, no lecture.
Address: Anh Linh.
```

## 5:00 PM — End-of-Day Wrap-Up

### Cron

```cron
0 17 * * *
```

### Prompt

```markdown
Generate Linh Tran’s End-of-Day Wrap-Up.

Review today’s task list, email status, Telegram notes, meetings, decisions, and pending follow-ups.

Produce:

1. Completed items today.
2. Missing or overdue items.
3. Follow-ups that must be sent before end of day.
4. Decisions made today.
5. Decisions still pending.
6. Important notes to remember for tomorrow.
7. Draft short follow-up messages if needed.
8. Suggested top priorities for tomorrow.

Tone: executive, clear, supportive, disciplined.
Address: Anh Linh.
```

## Briefing Output Format

```markdown
Anh Linh, đây là briefing hiện tại:

## 1. Priority Today

...

## 2. Missing / Overdue

...

## 3. Follow-up Needed

...

## 4. Decisions Required

...

## 5. Suggested Next Actions

1. ...
2. ...
3. ...
```

## Optional Telegram Notification Format

For Telegram, keep the briefing short:

```text
Anh Linh — 7:30 AM Command Briefing

Top priorities:
1. ...
2. ...
3. ...

Missing follow-ups:
- ...

Decision needed:
- ...

Recommended first action:
...
```

## Scheduler Notes

Use one of:

- Linux cron.
- APScheduler.
- Celery Beat.
- systemd timer.
- n8n scheduled workflow.

For VPS deployment, start with APScheduler inside the bot service, then migrate to Celery Beat if the system grows.
