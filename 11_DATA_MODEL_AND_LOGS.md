# Rey Tran Bot — Data Model and Logs

## Purpose

This file defines suggested tables or collections for Rey Tran Bot.

Start simple. Expand later.

## Core Tables

### 1. users

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_user_id TEXT UNIQUE,
    email TEXT,
    name TEXT,
    role TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. memories

```sql
CREATE TABLE memories (
    id SERIAL PRIMARY KEY,
    memory_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    confidence TEXT DEFAULT 'confirmed',
    sensitivity TEXT DEFAULT 'medium',
    tags TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3. tasks

```sql
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    owner TEXT,
    project TEXT,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'open',
    due_at TIMESTAMP,
    source_channel TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4. decisions

```sql
CREATE TABLE decisions (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    decision TEXT NOT NULL,
    context TEXT,
    approved_by TEXT,
    project TEXT,
    risk_level TEXT DEFAULT 'medium',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5. communications

```sql
CREATE TABLE communications (
    id SERIAL PRIMARY KEY,
    channel TEXT NOT NULL,
    direction TEXT,
    counterpart TEXT,
    subject TEXT,
    summary TEXT,
    draft_content TEXT,
    sent BOOLEAN DEFAULT FALSE,
    approval_status TEXT DEFAULT 'not_required',
    related_project TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6. briefing_logs

```sql
CREATE TABLE briefing_logs (
    id SERIAL PRIMARY KEY,
    briefing_type TEXT NOT NULL,
    content TEXT NOT NULL,
    sent_to TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 7. action_logs

```sql
CREATE TABLE action_logs (
    id SERIAL PRIMARY KEY,
    channel TEXT,
    user_request TEXT,
    agent_action TEXT,
    approval_required BOOLEAN DEFAULT FALSE,
    approval_status TEXT DEFAULT 'not_required',
    related_project TEXT,
    risk_level TEXT DEFAULT 'low',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Task Status Values

Use:

- open
- in_progress
- waiting_for_linh
- waiting_for_counterpart
- completed
- cancelled
- deferred

## Priority Values

Use:

- critical
- high
- medium
- low

## Risk Level Values

Use:

- low
- medium
- high
- critical

## Memory Sensitivity Values

Use:

- low
- medium
- high
- restricted

## Suggested Memory Tags

- dds
- dds-petro
- van-ninh-port
- banking
- acb
- bidv
- ccb
- petroleum
- mops
- legal
- hr
- recruitment
- personal
- family
- law-school
- chinese
- ai-agent

## Logging Philosophy

Log what matters, not everything.

Always log:

- Decisions.
- Commitments.
- Sent communications.
- High-risk drafts.
- Changed tasks.
- Briefings.
- Memory updates.
- Errors.
