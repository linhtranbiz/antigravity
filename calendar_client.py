#!/usr/bin/env python3
"""Google Calendar client helper functions for tool use.

Handles connection to the Google Calendar API and retrieves user schedule events.
"""
import os
import sys
import logging
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

ROOT = Path(__file__).parent
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/calendar.readonly']

logger = logging.getLogger("briefing_bot")

def get_calendar_service():
    """Build Calendar service from token.json, with automatic refreshing."""
    token_path = ROOT / "token.json"
    if not token_path.exists():
        raise FileNotFoundError("token.json not found. Please run auth_setup.py on your laptop to generate it.")
    
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing Calendar OAuth token for live chat tools...")
            creds.refresh(Request())
            with open(token_path, "w") as token_file:
                token_file.write(creds.to_json())
        else:
            raise Exception("token.json is invalid and cannot be refreshed. Please rerun auth_setup.py.")
    
    return build('calendar', 'v3', credentials=creds)

def list_calendar_events(start_iso, end_iso):
    """Retrieve schedule events from the user's primary calendar within the specified ISO-8601 timeframe."""
    try:
        service = get_calendar_service()
        logger.info(f"Google Calendar list_events: start='{start_iso}', end='{end_iso}'")
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        out = []
        for event in events:
            # start/end dates can be dateTime or simple date (for all-day events)
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            summary = event.get('summary', '(No Title)')
            description = event.get('description', '')
            location = event.get('location', '')
            
            out.append({
                "summary": summary,
                "start": start,
                "end": end,
                "location": location,
                "description": description
            })
        return out
    except Exception as e:
        logger.error(f"Error retrieving calendar events: {e}")
        return f"Error listing calendar events: {type(e).__name__}: {e}"
