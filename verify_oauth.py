#!/usr/bin/env python3
"""Google OAuth Verification Script for DDS Email Intelligence Bot.

Run this script locally or on the VPS to verify the validity of your Google OAuth configuration.
It checks credentials.json, token.json, refreshes the token if expired, and performs a test Gmail API query.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Set ROOT to the directory containing this script
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    print("=" * 80)
    print("Error: Missing required libraries. Please run:")
    print("  pip install google-auth-oauthlib google-api-python-client python-dotenv")
    print("=" * 80)
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/calendar.readonly']

def check_env():
    print("🔍 [1/4] Checking Environment Configuration...")
    gmail_user = os.environ.get("GMAIL_USER")
    if not gmail_user:
        print("⚠️ Warning: GMAIL_USER is not set in your .env file.")
    else:
        print(f"✅ GMAIL_USER is set to: {gmail_user}")
    
    # Also check if token.json and credentials.json exist
    token_path = ROOT / "token.json"
    creds_path = ROOT / "credentials.json"
    
    print(f"• token.json path: {token_path} ({'Exists' if token_path.exists() else 'Missing'})")
    print(f"• credentials.json path: {creds_path} ({'Exists' if creds_path.exists() else 'Missing'})")
    return gmail_user, token_path, creds_path

def verify_token(gmail_user, token_path):
    print("\n🔍 [2/4] Loading and Verifying token.json...")
    if not token_path.exists():
        print("❌ Error: token.json not found.")
        print("👉 Please run 'python3 auth_setup.py' first on your laptop to generate it.")
        return False, None
    
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        print(f"✅ Loaded token.json successfully.")
        print(f"• Current token expiry (UTC): {creds.expiry}")
        return True, creds
    except Exception as e:
        print(f"❌ Error loading token.json: {e}")
        return False, None

def refresh_token_if_needed(creds, token_path):
    print("\n🔍 [3/4] Checking Token Expiration & Refresh Capability...")
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            print("⏳ Token is expired. Attempting to refresh using the refresh token...")
            try:
                creds.refresh(Request())
                with open(token_path, "w") as token_file:
                    token_file.write(creds.to_json())
                print("✅ Token refreshed successfully!")
                print(f"• New token expiry (UTC): {creds.expiry}")
                return True
            except Exception as e:
                print(f"❌ Failed to refresh token: {e}")
                print("👉 The refresh token might have expired, been revoked, or the client credentials changed.")
                print("👉 Please run 'python3 auth_setup.py' again to generate a new token.")
                return False
        else:
            print("❌ Token is invalid and does not have a valid refresh token.")
            print("👉 Please run 'python3 auth_setup.py' again.")
            return False
    else:
        print("✅ Token is still active and valid. No refresh required.")
        return True

def test_google_apis(creds, gmail_user):
    print("\n🔍 [4/4] Testing Gmail and Calendar API Integration...")
    gmail_ok = False
    calendar_ok = False
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        
        email_address = profile.get('emailAddress')
        messages_total = profile.get('messagesTotal')
        
        print("✅ Successfully authenticated with the Gmail API!")
        print(f"• Gmail Account: {email_address}")
        print(f"• Total messages: {messages_total}")
        
        if gmail_user and email_address.lower() != gmail_user.lower():
            print(f"\n⚠️ WARNING: The authenticated Gmail account ({email_address}) does not match GMAIL_USER in .env ({gmail_user}).")
        
        gmail_ok = True
    except Exception as e:
        print(f"❌ Gmail API test call failed: {e}")
        
    try:
        cal_service = build('calendar', 'v3', credentials=creds)
        # Call a lightweight endpoint to verify read access
        cal_service.colors().get().execute()
        print("✅ Successfully authenticated with the Google Calendar API!")
        calendar_ok = True
    except Exception as e:
        print(f"❌ Calendar API test call failed: {e}")
        print("👉 Make sure you ran 'auth_setup.py' and checked the calendar permission box.")

    if gmail_ok and calendar_ok:
        print("\n🎉 Verification Successful! Your Google OAuth setup is fully functional for Gmail and Calendar.")
        return True
    return False

def main():
    print("=" * 80)
    print("           DDS BOT GOOGLE OAUTH VERIFICATION TOOL")
    print("=" * 80)
    
    gmail_user, token_path, creds_path = check_env()
    
    success, creds = verify_token(gmail_user, token_path)
    if not success:
        sys.exit(1)
        
    success = refresh_token_if_needed(creds, token_path)
    if not success:
        sys.exit(1)
        
    success = test_google_apis(creds, gmail_user)
    if not success:
        sys.exit(1)
        
    print("=" * 80)

if __name__ == "__main__":
    main()
