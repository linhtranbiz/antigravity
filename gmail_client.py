#!/usr/bin/env python3
"""Gmail client helper functions for tool use.

Handles connection to the Gmail API and functions to search and fetch full email content.
"""
import os
import sys
import base64
import logging
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

ROOT = Path(__file__).parent
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/calendar.readonly']

logger = logging.getLogger("briefing_bot")

def get_gmail_service():
    """Build Gmail service from token.json, with automatic refreshing."""
    token_path = ROOT / "token.json"
    if not token_path.exists():
        raise FileNotFoundError("token.json not found. Please run auth_setup.py on your laptop to generate it.")
    
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing Gmail OAuth token for live chat tools...")
            creds.refresh(Request())
            with open(token_path, "w") as token_file:
                token_file.write(creds.to_json())
        else:
            raise Exception("token.json is invalid and cannot be refreshed. Please rerun auth_setup.py.")
    
    return build('gmail', 'v1', credentials=creds)

def get_header(payload, name):
    """Extract a header value from payload."""
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

def search_emails(query, max_results=5):
    """Search Gmail messages matching query and return list of metadata."""
    try:
        service = get_gmail_service()
        # Cap max results at 10 to prevent large response overhead
        max_results = min(int(max_results), 10)
        
        logger.info(f"Gmail search tool query: '{query}', max: {max_results}")
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        out = []
        for m in messages:
            mid = m['id']
            # Fetch minimal metadata to save latency
            msg = service.users().messages().get(
                userId='me', 
                id=mid, 
                format='metadata', 
                metadataHeaders=['Subject', 'From', 'Date']
            ).execute()
            
            headers = msg.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(No Subject)')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), '(No Sender)')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '(No Date)')
            snippet = msg.get('snippet', '')
            
            out.append({
                "id": mid,
                "subject": subject,
                "from": sender,
                "date": date,
                "snippet": snippet
            })
        return out
    except Exception as e:
        logger.error(f"Error searching emails: {e}")
        return f"Error searching emails: {type(e).__name__}: {e}"

def get_email(email_id):
    """Retrieve full details of a specific email by ID."""
    try:
        service = get_gmail_service()
        logger.info(f"Gmail fetch email tool id: '{email_id}'")
        message = service.users().messages().get(userId='me', id=email_id, format='full').execute()
        
        payload = message.get('payload', {})
        subject = get_header(payload, 'Subject')
        sender = get_header(payload, 'From')
        to = get_header(payload, 'To')
        date = get_header(payload, 'Date')
        
        body = get_body(payload)
        if not body:
            body = message.get('snippet', '')
            
        # Truncate body to ~4000 characters to prevent context window overflow
        truncated_body = body[:4000]
        if len(body) > 4000:
            truncated_body += "\n\n[... content truncated due to size ...]"
            
        return {
            "id": email_id,
            "subject": subject,
            "from": sender,
            "to": to,
            "date": date,
            "body": truncated_body
        }
    except Exception as e:
        logger.error(f"Error retrieving email {email_id}: {e}")
        return f"Error retrieving email: {type(e).__name__}: {e}"
