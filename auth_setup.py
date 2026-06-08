#!/usr/bin/env python3
"""Gmail OAuth Authentication Setup Script.

Run this script locally on your laptop to generate the `token.json` file
required for Gmail API access.
"""
import os
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
except ImportError:
    print("Error: Missing required libraries. Please run:")
    print("  pip install google-auth-oauthlib google-api-python-client")
    sys.exit(1)

# Gmail and Calendar readonly scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/calendar.readonly']

def main():
    if not os.path.exists('credentials.json'):
        print("=" * 80)
        print("Error: 'credentials.json' not found in the current directory.")
        print("Please follow these steps to download it:")
        print("1. Go to the Google Cloud Console: https://console.cloud.google.com/")
        print("2. Create a new project (e.g., 'DDS-Email-Briefing')")
        print("3. Search for 'Gmail API' and click 'Enable'")
        print("4. Go to 'APIs & Services' -> 'OAuth consent screen':")
        print("   - Select User Type: 'External' (or 'Internal' if using Workspace)")
        print("   - Fill in app name and email addresses")
        print("   - In Scopes, add: 'https://www.googleapis.com/auth/gmail.readonly'")
        print("   - In Test Users, add your gmail address (linhtran.business@gmail.com)")
        print("5. Go to 'APIs & Services' -> 'Credentials':")
        print("   - Click 'Create Credentials' -> 'OAuth client ID'")
        print("   - Application type: 'Desktop app'")
        print("   - Name: 'Email Intel Bot' and click 'Create'")
        print("6. Click the download icon (JSON format) for the credential you just created")
        print("7. Rename that downloaded file to 'credentials.json' and place it in this folder")
        print("=" * 80)
        sys.exit(1)

    creds = None
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            print("Existing token.json found.")
        except Exception as e:
            print(f"Warning: Failed to load existing token.json: {e}")

    try:
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("Refreshing expired credentials...")
                try:
                    creds.refresh(Request())
                except Exception as refresh_err:
                    print(f"Failed to refresh credentials ({refresh_err}). Re-authenticating via browser...")
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
            else:
                print("Opening browser for Google Authentication flow...")
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.json', 'w') as token_file:
                token_file.write(creds.to_json())
            print("\n" + "=" * 60)
            print("SUCCESS! 'token.json' has been generated and saved successfully.")
            print("You can now copy it to your VPS.")
            print("=" * 60)
        else:
            print("Your existing token.json is still valid!")
    except Exception as e:
        print(f"\nAuthentication failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
