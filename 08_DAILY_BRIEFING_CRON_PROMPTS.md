# Daily Briefing Cron Prompts

## Time Zone

Asia/Ho_Chi_Minh

## 7:30 AM — Morning Command Briefing

Cron:

```cron
30 7 * * *
```

Prompt:

```markdown
Generate Linh Tran’s Morning Command Briefing.

Review all available task logs, email follow-ups, Telegram notes, calendar items, decision logs, and open loops.

Produce:
1. Top 5 priorities for today.
2. Urgent deadlines.
3. Important meetings or calls.
4. Emails requiring decision or reply.
5. People Anh Linh should follow up with.
6. Business risks to watch today.
7. Personal/life tasks that should not be forgotten.
8. Recommended execution sequence.
9. One short strategic reminder.

Tone: direct, executive, practical.
Address: Anh Linh.
```

## 11:30 AM — Midday Execution Check

Cron:

```cron
30 11 * * *
```

Prompt:

```markdown
Generate Linh Tran’s Midday Execution Check.

Compare the morning briefing against completed and incomplete items.

Produce:
1. What should already be done by now.
2. What is still missing.
3. What requires immediate follow-up before lunch.
4. Emails or messages waiting for reply.
5. People who may be waiting for Anh Linh.
6. Urgent risks that appeared since morning.
7. Suggested 3 priorities for the next 4 hours.

Tone: concise, practical, no lecture.
Address: Anh Linh.
```

## 5:00 PM — End-of-Day Wrap-Up

Cron:

```cron
0 17 * * *
```

Prompt:

```markdown
Generate Linh Tran’s End-of-Day Wrap-Up.

Review today’s task list, email status, Telegram notes, meetings, decisions, and pending follow-ups.

Produce:
1. Completed items today.
2. Missing or overdue items.
3. Follow-ups that must be sent before end of day.
4. Decisions made today.
5. Decisions still pending.
6. Important notes for tomorrow.
7. Draft short follow-up messages if needed.
8. Suggested top priorities for tomorrow.

Tone: executive, clear, supportive, disciplined.
Address: Anh Linh.
```
