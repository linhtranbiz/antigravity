# Memory, Task, Decision, and Communication Logs

## Memory Record

```json
{
  "memory_type": "person | company | project | decision | task | communication | preference | ai_agent",
  "title": "",
  "content": "",
  "source": "telegram | email | document | direct_user_instruction | system",
  "confidence": "confirmed | probable | unclear | needs_verification",
  "sensitivity": "low | medium | high | restricted",
  "created_at": "",
  "updated_at": ""
}
```

## Task Record

```json
{
  "task": "",
  "owner": "",
  "priority": "critical | high | medium | low",
  "deadline": "",
  "project": "",
  "status": "open | in_progress | waiting_for_linh | waiting_for_counterpart | completed | cancelled | deferred",
  "next_follow_up": "",
  "notes": ""
}
```

## Decision Record

```json
{
  "date": "",
  "decision": "",
  "context": "",
  "options_considered": [],
  "reason": "",
  "risks": [],
  "approved_by": "",
  "next_actions": []
}
```

## Communication Record

```json
{
  "channel": "email | telegram | zalo | whatsapp | wechat | phone | meeting",
  "counterparty": "",
  "subject": "",
  "summary": "",
  "draft_content": "",
  "sent": false,
  "approval_status": "pending | approved | rejected | not_required",
  "related_project": "",
  "created_at": ""
}
```

## Follow-up Tracker

```markdown
| Item | Owner | Counterparty | Deadline | Status | Next Action |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |
```

## Memory Rules

Store only useful durable information. Never invent memory. Mark uncertainty clearly. Protect sensitive information. Update old memory when new information replaces it.
