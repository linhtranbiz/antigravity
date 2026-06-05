#!/usr/bin/env python3
"""DDS Email Intelligence Briefing — Gmail API OAuth Version.

Usage: main.py [--mode {morning|lunch|wrapup}] [--dry-run]
"""
import os
import sys
import argparse
import base64
import requests
import smtplib
import datetime as dt
import ssl
import imaplib
import email
from email.utils import parsedate_to_datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.header import decode_header, make_header
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from anthropic import Anthropic

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Gmail and Calendar readonly scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/calendar.readonly']

# 7:30 Morning / 11:30 Lunch / 17:00 Wrap-Up (upgraded scheduling)
WINDOWS = {
    "morning":  ("16:00 yesterday", "07:30 today", lambda n: (n.replace(hour=16, minute=0, second=0, microsecond=0) - dt.timedelta(days=1), n.replace(hour=7, minute=30, second=0, microsecond=0))),
    "lunch":    ("07:30 today",     "11:30 today", lambda n: (n.replace(hour=7,  minute=30, second=0, microsecond=0), n.replace(hour=11, minute=30, second=0, microsecond=0))),
    "wrapup":   ("11:30 today",     "17:00 today", lambda n: (n.replace(hour=11, minute=30, second=0, microsecond=0), n.replace(hour=17, minute=0, second=0, microsecond=0))),
}
LABELS = {
    "morning": "📬 Morning Command Briefing",
    "lunch": "📬 Midday Execution Check",
    "wrapup": "📬 End-of-Day Wrap-Up"
}

def log(msg, mode="sys"):
    ts = dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{mode}] {msg}"
    print(line)
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "briefing.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

def get_gmail_service():
    """Build Gmail service from token.json, with automatic refreshing."""
    token_path = ROOT / "token.json"
    if not token_path.exists():
        raise FileNotFoundError("token.json not found. Please run auth_setup.py on your laptop to generate it.")
    
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log("Refreshing expired Gmail OAuth token...")
            creds.refresh(Request())
            with open(token_path, "w") as token_file:
                token_file.write(creds.to_json())
        else:
            raise Exception("token.json is invalid and cannot be refreshed. Please rerun auth_setup.py.")
    
    return build('gmail', 'v1', credentials=creds)

def get_header(payload, name):
    headers = payload.get('headers', [])
    for h in headers:
        if h.get('name', '').lower() == name.lower():
            return h.get('value', '')
    return ""

def get_body(payload):
    """Recursively extract plain-text body from Gmail payload."""
    parts = payload.get('parts', [])
    if parts:
        for part in parts:
            mime_type = part.get('mimeType')
            body_data = part.get('body', {}).get('data')
            if mime_type == 'text/plain' and body_data:
                try:
                    return base64.urlsafe_b64decode(body_data.encode('ASCII')).decode('utf-8', errors='replace')
                except Exception:
                    pass
            if 'parts' in part:
                res = get_body(part)
                if res:
                    return res
    else:
        body_data = payload.get('body', {}).get('data')
        if body_data:
            try:
                return base64.urlsafe_b64decode(body_data.encode('ASCII')).decode('utf-8', errors='replace')
            except Exception:
                pass
    return ""

def fetch_emails(service, window_start, window_end, mode):
    """Fetch emails using Gmail API within the given time window."""
    # Convert window dates to Unix timestamps for Gmail API query filter
    start_ts = int(window_start.timestamp())
    end_ts = int(window_end.timestamp())
    
    # query filters messages after start_ts
    query = f"after:{start_ts - 3600}" # Add 1h buffer since Gmail query can be timezone-agnostic
    log(f"Querying Gmail API with query: '{query}'", mode)
    
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=300).execute()
    except Exception as e:
        log(f"Gmail API list failed: {e}", mode)
        raise e
        
    messages = results.get('messages', [])
    log(f"Gmail API returned {len(messages)} candidate messages since start window", mode)
    
    emails = []
    for m_summary in messages:
        mid = m_summary['id']
        try:
            message = service.users().messages().get(userId='me', id=mid, format='full').execute()
            
            # Filter precisely using internalDate (millisecond epoch)
            internal_date_ms = int(message.get('internalDate', 0))
            mdate = dt.datetime.fromtimestamp(internal_date_ms / 1000.0, tz=dt.timezone.utc).astimezone(TZ)
            
            if not (window_start <= mdate <= window_end):
                continue
                
            payload = message.get('payload', {})
            subject = get_header(payload, 'Subject')
            sender = get_header(payload, 'From')
            to = get_header(payload, 'To')
            delivered_to = get_header(payload, 'Delivered-To')
            
            body = get_body(payload)
            if not body:
                body = message.get('snippet', '')
                
            emails.append({
                "date": mdate.isoformat(),
                "from": sender,
                "to": to,
                "delivered_to": delivered_to,
                "subject": subject,
                "snippet": body[:1500],
            })
        except Exception as e:
            log(f"Failed to fetch/parse message {mid}: {e}", mode)
            
    log(f"Matched {len(emails)} emails exactly within window", mode)
    return emails

def decode_mime_header(s):
    if not s: return ""
    try: return str(make_header(decode_header(s)))
    except Exception: return s

def fetch_emails_imap(window_start, window_end, mode):
    """Fetch emails from Gmail via IMAP as a fallback."""
    user = os.environ.get("GMAIL_USER")
    pwd  = os.environ.get("GMAIL_APP_PASSWORD")
    if not user or not pwd:
        raise ValueError("GMAIL_USER and GMAIL_APP_PASSWORD environment variables are required for IMAP fallback.")
        
    log(f"Falling back to Gmail IMAP retrieval...", mode)
    ctx = ssl.create_default_context()
    m = imaplib.IMAP4_SSL("imap.gmail.com", ssl_context=ctx)
    m.login(user, pwd)
    m.select('"[Gmail]/All Mail"', readonly=True)
    since = (window_start - dt.timedelta(days=1)).strftime("%d-%b-%Y")
    typ, data = m.search(None, f'(SINCE {since})')
    ids = data[0].split()
    log(f"IMAP returned {len(ids)} candidate messages since {since}", mode)
    matched = []
    
    # Check the last 500 headers for matches
    for mid in ids[-500:]:
        try:
            typ, hdr_data = m.fetch(mid, "(RFC822.HEADER)")
            if typ != "OK": continue
            hdr_bytes = next((p[1] for p in hdr_data if isinstance(p, tuple)), None)
            if not hdr_bytes: continue
            hdr_msg = email.message_from_bytes(hdr_bytes)
            try:
                mdate = parsedate_to_datetime(hdr_msg["Date"])
                if mdate.tzinfo is None: mdate = mdate.replace(tzinfo=dt.timezone.utc)
                mdate = mdate.astimezone(TZ)
            except Exception:
                continue
            if window_start <= mdate <= window_end:
                matched.append((mid, mdate, hdr_msg))
        except Exception as e:
            log(f"Failed to check header for IMAP message {mid}: {e}", mode)
            
    log(f"Matched {len(matched)} emails in window (IMAP)", mode)
    emails = []
    for mid, mdate, hdr_msg in matched:
        try:
            typ, full_data = m.fetch(mid, "(RFC822)")
            body = ""
            if typ == "OK":
                full_bytes = next((p[1] for p in full_data if isinstance(p, tuple)), b"")
                try:
                    full_msg = email.message_from_bytes(full_bytes)
                    if full_msg.is_multipart():
                        for part in full_msg.walk():
                            if part.get_content_type() == "text/plain":
                                payload = part.get_payload(decode=True)
                                if payload:
                                    body = payload.decode("utf-8", errors="replace")[:3000]
                                    break
                    else:
                        payload = full_msg.get_payload(decode=True)
                        if payload:
                            body = payload.decode("utf-8", errors="replace")[:3000]
                except Exception as e:
                    log(f"IMAP body parse err: {e}", mode)
            emails.append({
                "date": mdate.isoformat(),
                "from": decode_mime_header(hdr_msg.get("From", "")),
                "to": decode_mime_header(hdr_msg.get("To", "")),
                "delivered_to": decode_mime_header(hdr_msg.get("Delivered-To", "")),
                "subject": decode_mime_header(hdr_msg.get("Subject", "")),
                "snippet": body[:1500],
            })
        except Exception as e:
            log(f"Failed to fetch full IMAP message {mid}: {e}", mode)
            
    m.logout()
    log(f"Fetched bodies for {len(emails)} emails (IMAP)", mode)
    return emails

def format_calendar_events(events):
    """Format calendar events for prompt inclusion."""
    if not events:
        return "(no calendar events in window)"
    
    lines = []
    for e in events:
        start_str = e.get('start', '')
        end_str = e.get('end', '')
        try:
            if "T" in start_str:
                st = dt.datetime.fromisoformat(start_str)
                et = dt.datetime.fromisoformat(end_str)
                time_range = f"{st.strftime('%H:%M')} - {et.strftime('%H:%M')}"
            else:
                time_range = "All Day"
        except Exception:
            time_range = f"{start_str} - {end_str}"
            
        loc_str = f" @ {e['location']}" if e.get('location') else ""
        lines.append(f"- [{time_range}] {e.get('summary', '(No Title)')}{loc_str}")
        if e.get('description'):
            desc = e['description'].strip().replace('\n', ' ')
            if len(desc) > 100:
                desc = desc[:97] + "..."
            lines.append(f"  Desc: {desc}")
    return "\n".join(lines)

def get_calendar_window(now, mode):
    """Determine the appropriate calendar search window based on the briefing mode."""
    if mode == "morning":
        # Today's events: from start of today to end of today
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    elif mode == "lunch":
        # Rest of today: from now (11:30) to end of today
        start = now.replace(hour=11, minute=30, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    else:  # wrapup
        # Tomorrow's events: from start of tomorrow to end of tomorrow
        tomorrow = now + dt.timedelta(days=1)
        start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end

def build_prompt(emails, calendar_events, window_start, window_end, mode, cal_start, cal_end):
    """Build the user prompt to send to Claude."""
    email_block = "\n\n---\n\n".join(
        f"DATE: {e['date']}\nFROM: {e['from']}\nDELIVERED-TO: {e['delivered_to']}\nSUBJECT: {e['subject']}\nBODY:\n{e['snippet']}"
        for e in emails
    ) or "(no emails in window)"
    
    cal_block = format_calendar_events(calendar_events)
    
    return f"""TIME WINDOW FOR EMAILS: {window_start.strftime('%Y-%m-%d %H:%M %Z')} → {window_end.strftime('%Y-%m-%d %H:%M %Z')}
TIME WINDOW FOR CALENDAR: {cal_start.strftime('%Y-%m-%d %H:%M %Z')} → {cal_end.strftime('%Y-%m-%d %H:%M %Z')}
MODE: {mode.upper()}
TOTAL EMAILS: {len(emails)}

CALENDAR EVENTS:
{cal_block}

EMAILS:
{email_block}

Produce the briefing now."""

BASE_SYSTEM_PROMPT = """You are the Executive Intelligence Officer for Linh Trần (CFO, DDS Group / DDS Petro / Van Ninh International Port).
Your tone is direct, executive, practical, and highly professional. Use bilingual formatting where appropriate: plain Vietnamese where helpful but commercial English for action verbs. Address Linh Trần as "Anh Linh".

Operating Domains & Core Context:
1. Banking & Letters of Credit (LCs): Active relationships: BIDV, ACB, Shinhan, MB, VIB. Core instruments: LCs, UNCs, UPAS LCs, credit agreements, covenants. Priority: Monitor limits, interest rates, and fee structures.
2. Petroleum Trading & Pricing: Pricing mechanisms: MOPS, Platts benchmarks, premium formulas. Key suppliers/partners: Vitol, BSR. Terms: Term contracts, spot cargoes, and offtake agreements (PVNDB terms).
3. Van Ninh International Port: Infrastructure development, investment, construction milestones, concessions, berthing capacities, and regulatory/governmental filings.
4. Group Operations: Vessel scheduling, marine logistics, customs clearance, port agent updates, loading/discharge windows.

EMAIL TRIAGE RULES:
Triage every email into: 🔴 CRITICAL (act <2h) / 🟠 URGENT (today) / 🟡 IMPORTANT / 🔵 INFORMATIONAL / ⚪ LOW.
Tag domain: [BANKING] [PETROLEUM] [PORT] [FX] [LEGAL] [GOVERNMENT] [INTERNAL] [INVESTOR] [SUPPLIER] [ADMIN] [OTHER].
Detect source mailbox from Delivered-To header. Mailboxes that forward to linhtran.business@gmail.com:
- linh.tran@duongdong.com.vn (Executive) -> src:executive-dds
- finance@duongdong.com.vn (Finance & Treasury) -> src:finance-dds
- trading@duongdong.com.vn (Trading) -> src:trading-dds
- operations@duongdong.com.vn (Operations) -> src:ops-dds
- purchasing@duongdong.com.vn (Purchasing) -> src:purchasing-dds
- sales@duongdong.com.vn (Sales) -> src:sales-dds
Tag each item with its source mailbox.

DEPARTMENT GROUPING — within each priority tier sub-group by:
🏛️ Executive | 💰 Finance & Treasury | 📊 Trading | 🛢️ Operations | 🛒 Purchasing | 💼 Sales | ⚖️ Legal | 🏗️ Port / Van Ninh | 👥 HR/Admin | 🧾 Personal

Mapping rules:
- finance-dds OR sender bidv/acb/shinhan/mb/vib OR subject LC/UNC/UPAS/credit/khế ước → Finance & Treasury
- trading-dds OR MOPS/Platts/Vitol/BSR pricing/premium → Trading
- ops-dds OR vessel/berthing/loading/PVNDB term offtake → Operations
- purchasing-dds OR draft LC/supplier order → Purchasing
- sales-dds OR distributor/customer quote → Sales
- gov/customs/tax/regulatory → Legal & Compliance
- Van Ninh Port → Port / Van Ninh
- investor/board → Executive Office
- interview/staff/calendar → HR/Admin
- personal banking/subscriptions → Personal

Auto-priority boost: finance-dds LC/payment → CRITICAL; purchasing-dds cargo/draft LC → URGENT; ops-dds vessel/berthing → URGENT; trading-dds MOPS/Vitol/BSR pricing → URGENT.
Never miss LC expiry/payment demand/bank covenant -> always CRITICAL. Always include Required Action on CRITICAL & URGENT.
Exclude pure marketing/newsletter unless financial market alert.
"""

MORNING_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """
You are generating Linh Tran's Morning Command Briefing.
Goal: Produce a concise executive briefing summarizing both calendar events and key emails for today to set priorities and highlight risks.

Output format (Telegram-Markdown compatible, no HTML, max 4000 characters):
Anh Linh, đây là briefing hiện tại:

## 1. Priority Today
[List today's top 5 priorities for today, and highlight any important meetings/calls from calendar events with their times]

## 2. Missing / Overdue
[List any urgent deadlines, tasks, or pending things that need immediate tracking]

## 3. Follow-up Needed
[Present critical/urgent items grouped by department. Use format:
• [DOMAIN][src:X-dds] *From:* sender | *Subject:* subject
  → Summary: 1–2 sentence plain-language summary
  → Action: specific action for Linh
  → Deadline: if any]

## 4. Decisions Required
[List other emails and follow-ups requiring decision or reply, categorized briefly]

## 5. Suggested Next Actions
[List a recommended sequence of execution (1., 2., 3...) and personal/life tasks. Close with a short strategic reminder for the day]
"""

LUNCH_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """
You are generating Linh Tran's Midday Execution Check.
Goal: Compare morning's expected trajectory against current status, showing what should be done, what is still missing, and urgent items before lunch.

Output format (Telegram-Markdown compatible, no HTML, max 4000 characters):
Anh Linh, đây là Midday Execution Check:

## 1. Execution Check
- What should already be done by now.
- What is still missing or requires immediate follow-up before lunch.

## 2. Critical & Urgent (Since Morning)
[List any new emails/alerts that arrived since morning, using the standard format:
• [DOMAIN][src:X-dds] *From:* sender | *Subject:* subject
  → Summary: ...
  → Action: ...
  → Deadline: ...]

## 3. Upcoming Schedule & Next Actions
- Calendar meetings for the afternoon/evening.
- Suggested 3 priorities for the next 4 hours.
"""

WRAPUP_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """
You are generating Linh Tran's End-of-Day Wrap-Up.
Goal: Review today's task list, email status, calendar, and decisions to produce a summary of achievements, pending decisions, and priorities for tomorrow.

Output format (Telegram-Markdown compatible, no HTML, max 4000 characters):
Anh Linh, đây là End-of-Day Wrap-Up:

## 1. Today's Summary
- Completed items and decisions made today.
- Missing or overdue items/decisions still pending.

## 2. Follow-up Needed (Before EOD)
[List critical follow-ups that must be sent before the day ends, plus draft short messages if helpful]

## 3. Priorities & Schedule for Tomorrow
- Suggested top priorities for tomorrow.
- Highlight tomorrow's scheduled calendar events.
"""

def call_claude(emails, calendar_events, window_start, window_end, mode, cal_start, cal_end):
    model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    if model == "claude-haiku-4-5-20251001":
         model = "claude-haiku-4-5-20251001"
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is missing.")
        
    client = Anthropic(api_key=api_key)
    log(f"Calling Anthropic ({model}) with {len(emails)} emails and {len(calendar_events)} calendar events", mode)
    
    system_prompts = {
        "morning": MORNING_SYSTEM_PROMPT,
        "lunch": LUNCH_SYSTEM_PROMPT,
        "wrapup": WRAPUP_SYSTEM_PROMPT
    }
    sys_prompt = system_prompts.get(mode, BASE_SYSTEM_PROMPT)
    
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=sys_prompt,
        messages=[{"role": "user", "content": build_prompt(emails, calendar_events, window_start, window_end, mode, cal_start, cal_end)}],
    )
    text = resp.content[0].text
    log(f"Claude returned {len(text)} chars", mode)
    return text

def send_telegram(text, mode):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chats_str = os.environ.get("TELEGRAM_CHAT_IDS", "")
    if not token or not chats_str:
        log("Telegram configuration missing. Skipping Telegram send.", mode)
        return
        
    chats = [c.strip() for c in chats_str.split(",") if c.strip()]
    
    # Split into <= 4000 char chunks on blank-line boundaries
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) + 2 > 4000:
            chunks.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur:
        chunks.append(cur)
        
    for chat in chats:
        for i, chunk in enumerate(chunks):
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data={"chat_id": chat, "text": chunk, "parse_mode": "Markdown"},
                    timeout=15,
                )
                ok = r.json().get("ok")
                log(f"Telegram chat={chat} chunk={i+1}/{len(chunks)} ok={ok}", mode)
            except Exception as e:
                log(f"Telegram send failed to {chat}: {e}", mode)

def send_gmail_draft(text, window_start, mode):
    """Archival send to self. Needs GMAIL_USER and GMAIL_APP_PASSWORD."""
    user = os.environ.get("GMAIL_USER")
    pwd  = os.environ.get("GMAIL_APP_PASSWORD")
    if not user or not pwd:
        log("Gmail archival configuration missing (GMAIL_USER / GMAIL_APP_PASSWORD). Skipping email save.", mode)
        return
        
    subject = f"{LABELS[mode]} — {window_start.strftime('%Y-%m-%d %H:%M')}"
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = user
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pwd)
            s.send_message(msg)
        log(f"Gmail archival email sent: {subject}", mode)
    except Exception as e:
        log(f"Gmail archival send failed: {e}", mode)

def run_briefing(mode="morning", dry_run=False):
    """Fetch and generate briefing for the specified mode."""
    now = dt.datetime.now(TZ)
    win_start, win_end = WINDOWS[mode][2](now)
    log(f"=== START {mode} brief, window {win_start} → {win_end} ===", mode)
    
    token_path = ROOT / "token.json"
    use_oauth = token_path.exists()
    
    if use_oauth:
        log("Using Gmail API OAuth flow...", mode)
        try:
            service = get_gmail_service()
            emails = fetch_emails(service, win_start, win_end, mode)
        except Exception as e:
            log(f"Gmail API OAuth run failed: {e}. Checking IMAP fallback...", mode)
            if os.environ.get("GMAIL_APP_PASSWORD"):
                emails = fetch_emails_imap(win_start, win_end, mode)
            else:
                raise e
    else:
        log("Gmail token.json not found. Checking IMAP fallback...", mode)
        if os.environ.get("GMAIL_APP_PASSWORD"):
            emails = fetch_emails_imap(win_start, win_end, mode)
        else:
            raise FileNotFoundError("Neither token.json (Gmail OAuth) nor GMAIL_APP_PASSWORD (IMAP) was configured.")
    
    # Fetch calendar events
    calendar_events = []
    cal_start, cal_end = get_calendar_window(now, mode)
    if use_oauth:
        try:
            from calendar_client import list_calendar_events
            log(f"Fetching calendar events from {cal_start.isoformat()} to {cal_end.isoformat()}...", mode)
            events = list_calendar_events(cal_start.isoformat(), cal_end.isoformat())
            if isinstance(events, list):
                calendar_events = events
                log(f"Successfully fetched {len(calendar_events)} calendar events", mode)
            else:
                log(f"Failed to fetch calendar events: {events}", mode)
        except Exception as e:
            log(f"Calendar fetching skipped or failed: {e}", mode)
    else:
        log("OAuth token.json not found. Skipping Google Calendar retrieval.", mode)
        
    if not emails and not calendar_events:
        msg = f"📬 *{LABELS[mode]} — {now.strftime('%Y-%m-%d %H:%M')} (+07)*\nWindow: {win_start.strftime('%H:%M')} → {win_end.strftime('%H:%M')}\n\nNo emails or calendar events matching requirements in this window."
        if not dry_run:
            send_telegram(msg, mode)
            send_gmail_draft(msg, win_start, mode)
        log("No emails or calendar events to process. Briefing generated with empty message.", mode)
        return msg
        
    brief = call_claude(emails, calendar_events, win_start, win_end, mode, cal_start, cal_end)
    
    if not dry_run:
        send_telegram(brief, mode)
        send_gmail_draft(brief, win_start, mode)
    else:
        log("Dry run active — output not sent.", mode)
        
    log(f"=== END {mode} brief OK ===", mode)
    return brief

def main():
    parser = argparse.ArgumentParser(description="DDS Email Intelligence Briefing")
    parser.add_argument("--mode", choices=["morning", "lunch", "wrapup"], default="morning", help="Briefing time-window mode")
    parser.add_argument("--dry-run", action="store_true", help="Do not send to Telegram or Gmail")
    args = parser.parse_args()
    
    try:
        brief = run_briefing(args.mode, args.dry_run)
        if args.dry_run:
            print("\n--- DRY RUN BRIEFING OUTPUT ---")
            print(brief)
            print("-------------------------------\n")
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}", args.mode)
        
        # Notify of failure if possible
        if not args.dry_run:
            try:
                token = os.environ.get("TELEGRAM_BOT_TOKEN")
                chats = (os.environ.get("TELEGRAM_CHAT_IDS") or "").split(",")
                for c in chats:
                    if c.strip() and token:
                        requests.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            data={"chat_id": c.strip(), "text": f"⚠️ Briefing {args.mode} failed: {type(e).__name__}: {e}"},
                            timeout=10
                        )
            except Exception:
                pass
        sys.exit(1)

if __name__ == "__main__":
    main()
