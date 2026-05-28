# Deployment Guide — 24/7 Email Intel Telegram Bot

This guide details how to configure the Gmail API OAuth credentials, package the bot files, deploy them to your Hostinger VPS (`213.190.4.75`), and set up the systemd service to run it 24/7.

---

## Phase 1: Local Setup (On Your Laptop)

### Step 1.1: Obtain Google Cloud Credentials
Because plain password-based Gmail access (IMAP) is deprecated by Google, we use the Gmail API via OAuth.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `DDS-Email-Briefing`).
3. Search for the **Gmail API** in the search bar and click **Enable**.
4. Configure the **OAuth Consent Screen**:
   - Select **External** (unless you are a Google Workspace organization admin and want Internal).
   - Fill in the required fields (App name, User support email, Developer contact email).
   - In the **Scopes** step, click **Add or Remove Scopes** and add:
     `https://www.googleapis.com/auth/gmail.readonly`
   - In the **Test Users** step, add the email address you want to fetch briefs from:
     `linhtran.business@gmail.com`
5. Create **Credentials**:
   - Go to the **Credentials** tab on the left sidebar.
   - Click **Create Credentials** -> **OAuth client ID**.
   - Select Application type: **Desktop app**.
   - Name it (e.g., `DDS Email Bot Desktop`) and click **Create**.
6. Download the JSON file:
   - Click the download icon (JSON format) for the client ID you just created.
   - Rename this file to exactly `credentials.json` and move it into the `email-intel-bot` directory.

### Step 1.2: Perform Google Authentication (Generate `token.json`)
Run the helper script on your laptop to open a browser window and authorize the bot.

1. Make sure dependencies are installed locally:
   ```bash
   pip install google-auth-oauthlib google-api-python-client
   ```
2. Run `auth_setup.py`:
   ```bash
   python auth_setup.py
   ```
3. A browser tab will open asking you to sign in. Log in using `linhtran.business@gmail.com`.
   *Note: Since the app is not verified by Google, click **Advanced** -> **Go to DDS-Email-Briefing (unsafe)**, then click **Continue**.*
4. Upon successful login, the script will create `token.json` in your local directory.

### Step 1.3: Configure `.env`
Create a `.env` file in the `email-intel-bot` directory by copying `.env.template` and filling in the values:
```bash
cp .env.template .env
```
Ensure you provide:
- `ANTHROPIC_API_KEY`: Your Claude API key.
- `TELEGRAM_BOT_TOKEN`: The API token from `@BotFather`.
- `TELEGRAM_CHAT_IDS`: The list of Telegram chat IDs/channels receiving briefings.
- `AUTHORIZED_USER_IDS`: Your Telegram ID (to restrict interactive commands to you).
- `GMAIL_USER`: `linhtran.business@gmail.com`

---

## Phase 2: Copy to VPS (`213.190.4.75`)

Use `rsync` (or `scp`) to copy the bot directory (including `token.json` and `.env`) to the VPS:

```bash
# Run this from your laptop:
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude 'venv' --exclude '.venv' \
  ../email-intel-bot/ root@213.190.4.75:/opt/email-intel-bot/
```

---

## Phase 3: VPS Installation (On the VPS)

Log in to your VPS:
```bash
ssh root@213.190.4.75
```

### Step 3.1: Initialize Python Environment
Configure a virtual environment and install dependencies on the VPS:
```bash
cd /opt/email-intel-bot
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### Step 3.2: Smoke Test
Verify that the Gmail API and Claude credentials work as expected by running a dry-run briefing:
```bash
# Test a morning briefing manually
.venv/bin/python main.py --mode morning --dry-run
```
Check if the emails were retrieved successfully and triaged by Claude without errors.

---

## Phase 4: Configure systemd Service (On the VPS)

To keep the bot server running continuously in the background and survive server restarts:

1. Copy the systemd service file to the system config folder:
   ```bash
   cp /opt/email-intel-bot/email-intel-bot.service /etc/systemd/system/
   ```
2. Reload systemd daemon to pick up the new unit:
   ```bash
   systemctl daemon-reload
   ```
3. Enable and start the service:
   ```bash
   systemctl enable --now email-intel-bot
   ```
4. Verify the service is active and running:
   ```bash
   systemctl status email-intel-bot
   ```

---

## Phase 5: Verification and Monitoring

- **Startup Message**: Within ~10 seconds of starting the service, you should receive a Telegram notification: `🤖 DDS Email Briefing Bot Server Started` in your configured chat ID.
- **Interactive Commands**: Send `/status` or `/brief` directly to your bot in Telegram to verify it responds instantly.
- **Log Files**:
  - Main bot application logs: `/opt/email-intel-bot/logs/briefing.log`
  - Telegram polling server logs: `/opt/email-intel-bot/logs/bot.log`
  - systemd daemon output: `journalctl -u email-intel-bot -f`
