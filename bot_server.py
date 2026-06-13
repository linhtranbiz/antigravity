#!/usr/bin/env python3
"""DDS 24/7 Telegram Briefing Bot Server.

Integrates Telegram command polling and an internal async scheduler to trigger
automatic briefings at 07:30, 11:30, and 16:00 ICT.
"""
import os
import re
import sys
import asyncio
import logging
import datetime as dt
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

# Add current directory to path to ensure we can import main
ROOT = Path(__file__).parent
sys.path.append(str(ROOT))

from main import run_briefing, WINDOWS, LABELS, TZ, log
from chat import call_claude_with_tools
import council_relay

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
except ImportError as e:
    print(f"Error: Missing required dependency: {e}. Please run 'pip install python-telegram-bot anthropic'.")
    sys.exit(1)

# ── Setup Logging ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(ROOT / "logs" / "bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("briefing_bot")

START_TIME = dt.datetime.now()

# ── Authorization Helper ──────────────────────────────────────────────────────
_auth_str = os.getenv("AUTHORIZED_USER_IDS", "").strip()
AUTHORIZED_IDS = {int(uid.strip()) for uid in _auth_str.split(",") if uid.strip()} if _auth_str else set()

# Group/supergroup chats where the bot is fully enabled for multi-bot coordination.
# In these chats, ANY member (including peer bots) may summon Rey via @mention/reply,
# without each sender needing to be listed in AUTHORIZED_USER_IDS.
_chat_str = os.getenv("AUTHORIZED_CHAT_IDS", "").strip()
AUTHORIZED_CHAT_IDS = {int(cid.strip()) for cid in _chat_str.split(",") if cid.strip()} if _chat_str else set()

# Peer bot @usernames Rey may coordinate with and @mention systematically.
_peer_str = os.getenv("PEER_BOTS", "").strip()
PEER_BOTS = [
    (u.strip() if u.strip().startswith("@") else f"@{u.strip()}")
    for u in _peer_str.split(",") if u.strip()
]
# Lowercased usernames (no '@') for fast mention matching / relay routing.
PEER_USERNAMES = {p.lstrip("@").lower() for p in PEER_BOTS}

# Rey's own Telegram username (no '@'), resolved at startup via get_me().
REY_USERNAME = None

# ── Open Council Discussion config ────────────────────────────────────────────
# When ON, any substantive message in a whitelisted council chat is thrown open
# to the whole council; every bot may freely contribute. Restraints below exist
# ONLY to stop runaway loops / cost, not to limit what bots may discuss.
COUNCIL_OPEN_MODE = os.getenv("COUNCIL_OPEN_MODE", "true").strip().lower() in ("1", "true", "yes", "on")
# Max messages a single bot may add to one discussion thread.
try:
    THREAD_BOT_LIMIT = int(os.getenv("COUNCIL_THREAD_BOT_LIMIT", "3"))
except ValueError:
    THREAD_BOT_LIMIT = 3
# Hard ceiling on total messages in one thread before it auto-closes.
try:
    THREAD_MAX_MSGS = int(os.getenv("COUNCIL_THREAD_MAX_MSGS", "24"))
except ValueError:
    THREAD_MAX_MSGS = 24
# A bot replies with EXACTLY this token when it has nothing new to add (stays silent).
PASS_TOKEN = "[[PASS]]"
# Skip opening a thread for trivial chatter shorter than this many chars.
MIN_TOPIC_CHARS = 8

_MENTION_RE = re.compile(r"@([A-Za-z0-9_]{3,32})")

def extract_peer_mentions(text: str):
    """Return the list of known peer-bot usernames @mentioned in `text`."""
    found = {m.lower() for m in _MENTION_RE.findall(text or "")}
    return [u for u in found if u in PEER_USERNAMES and u != REY_USERNAME]

def is_authorized(user_id: int) -> bool:
    if not AUTHORIZED_IDS:
        return True  # If not configured, allow all (not recommended)
    return user_id in AUTHORIZED_IDS

def is_authorized_chat(chat_id: int) -> bool:
    """True if the chat itself is whitelisted (multi-bot coordination group)."""
    return chat_id in AUTHORIZED_CHAT_IDS

# ── Scheduler State ───────────────────────────────────────────────────────────
last_runs = {
    "morning": None,  # Will store date string e.g. '2026-05-28'
    "lunch": None,
    "daybreak": None
}

def get_current_mode():
    """Detect current briefing mode based on server time."""
    now = dt.datetime.now(TZ)
    time_str = now.strftime("%H:%M")
    if time_str < "11:30":
        return "morning"
    elif time_str < "16:00":
        return "lunch"
    else:
        return "daybreak"

# ── Telegram Command Handlers ─────────────────────────────────────────────────
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        logger.warning(f"Unauthorized start attempt from user: {update.effective_user.id}")
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    await update.message.reply_text(
        "🤖 *DDS Email Intelligence Bot (24/7 Server)*\n\n"
        "Uptime status: *Online* ✅\n\n"
        "Available commands:\n"
        "🔹 /brief - Triggers the brief for the current active window\n"
        "🔹 /morning - Triggers the Morning Brief (16:00 yesterday → 07:30 today)\n"
        "🔹 /lunch - Triggers the Lunch Brief (07:30 today → 11:30 today)\n"
        "🔹 /daybreak - Triggers the Day Break Brief (11:30 today → 16:00 today)\n"
        "🔹 /status - Checks system configuration and scheduled runs\n"
        "🔹 /backups - Lists available system backups on VPS\n"
        "🔹 /rollback [name] - Reverts bot code to a previous snapshot\n"
        "🔹 /help - Show this command reference list",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return

    # Check Gmail token
    token_path = ROOT / "token.json"
    if token_path.exists():
        try:
            from google.oauth2.credentials import Credentials
            from main import SCOPES
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            if creds.valid:
                oauth_ok = "✅ Valid"
            elif creds.expired and creds.refresh_token:
                oauth_ok = "⏳ Expired (will auto-refresh on use)"
            else:
                oauth_ok = "❌ Invalid/Expired (needs auth_setup.py)"
        except Exception as e:
            oauth_ok = f"❌ Error checking token: {e} (run auth_setup.py)"
    else:
        oauth_ok = "❌ Missing (run auth_setup.py)"
    
    # Check Env keys
    anthropic_ok = "✅ Configured" if os.environ.get("ANTHROPIC_API_KEY") else "❌ Missing"
    bot_token_ok = "✅ Configured" if os.environ.get("TELEGRAM_BOT_TOKEN") else "❌ Missing"
    
    now = dt.datetime.now(TZ)
    uptime_sec = int((dt.datetime.now() - START_TIME).total_seconds())
    uptime_str = str(dt.timedelta(seconds=uptime_sec))
    
    # Next scheduled runs
    next_runs_info = []
    today_str = now.strftime("%Y-%m-%d")
    for mode, time_val in [("morning", "07:30"), ("lunch", "11:30"), ("daybreak", "16:00")]:
        status_symbol = "✅ Sent" if last_runs.get(mode) == today_str else "⏳ Pending"
        next_runs_info.append(f"- {mode.capitalize()} ({time_val}): {status_symbol}")
        
    status_text = (
        f"🤖 *DDS Briefing Bot Status*\n\n"
        f"⏰ *Server Time:* {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"⏱️ *Uptime:* {uptime_str}\n\n"
        f"⚙️ *Configuration:*\n"
        f"• Gmail OAuth: {oauth_ok}\n"
        f"• Anthropic API: {anthropic_ok}\n"
        f"• Telegram Bot: {bot_token_ok}\n\n"
        f"📅 *Today's Scheduled Briefings:*\n" + "\n".join(next_runs_info)
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def run_briefing_on_demand(update: Update, mode: str):
    """Executes a briefing in a background thread to keep the event loop responsive."""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return

    await update.message.reply_text(
        f"⏳ *Generating {LABELS[mode]} on demand...*\n"
        "Fetching emails and triaging. This will take about 15-30 seconds...",
        parse_mode="Markdown"
    )
    
    try:
        # run in thread executor to prevent blocking bot event loop
        brief = await asyncio.to_thread(run_briefing, mode, False)
        # Verify if brief was created successfully
        await update.message.reply_text(
            f"✅ *{LABELS[mode]}* generated successfully and sent to configured chats.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error generating {mode} briefing on demand: {e}")
        await update.message.reply_text(f"❌ *Failed to generate briefing:* {e}", parse_mode="Markdown")

async def brief_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = get_current_mode()
    await run_briefing_on_demand(update, mode)

async def morning_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_briefing_on_demand(update, "morning")

async def lunch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_briefing_on_demand(update, "lunch")

async def daybreak_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_briefing_on_demand(update, "daybreak")

# ── Conversation Memory Store ────────────────────────────────────────────────
# Stores rolling chat history per chat_id: chat_id -> list of {"role": "user"|"assistant", "content": "..."}
chat_histories = {}

def _chunk_text(text: str, limit: int = 4000):
    """Split text into <= limit-char chunks on paragraph boundaries."""
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) + 2 > limit:
            chunks.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur:
        chunks.append(cur)
    return chunks

async def reply_message_safe(update: Update, text: str):
    """Reply in chunks of <= 4000 chars to avoid Telegram's message length limit."""
    for chunk in _chunk_text(text):
        await update.message.reply_text(chunk)

async def send_message_safe(bot, chat_id, text: str):
    """Send (not reply) in chunks via the bot, for relay-originated messages."""
    for chunk in _chunk_text(text):
        await bot.send_message(chat_id=chat_id, text=chunk)

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return
        
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("ℹ️ Please provide a question. Usage: `/ask <question>`", parse_mode="Markdown")
        return
        
    await update.message.chat.send_action(action="typing")
    
    try:
        # One-shot history that is not saved to global memory
        one_shot_history = [{"role": "user", "content": query}]
        response_text = await asyncio.to_thread(
            call_claude_with_tools,
            messages=one_shot_history
        )
        await reply_message_safe(update, response_text)
    except Exception as e:
        logger.error(f"Error in /ask command: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return
        
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = []
    await update.message.reply_text("🔄 Chat history has been reset for this chat.")

async def backups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return
        
    await update.message.chat.send_action(action="typing")
    
    try:
        import subprocess
        script_path = ROOT / "time_machine.sh"
        if not script_path.exists():
            await update.message.reply_text("❌ Error: `time_machine.sh` not found on this system.")
            return
            
        result = await asyncio.to_thread(
            subprocess.run,
            [str(script_path), "list"],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout.strip()
        await update.message.reply_text(
            f"📁 *Rey Tran Bot Time Machine*\n\n{output}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def rollback_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return
        
    args = context.args
    if not args:
        await update.message.reply_text("❌ Password required. Usage: `/rollback [backup_name] <password>`", parse_mode="Markdown")
        return
        
    # Check if the last argument is the correct password
    password = args[-1].strip()
    if password != "linhtran":
        await update.message.reply_text("❌ Invalid password. Usage: `/rollback [backup_name] <password>`", parse_mode="Markdown")
        return
        
    # If there are arguments other than the password, they form the backup_name
    if len(args) > 1:
        backup_name = " ".join(args[:-1]).strip()
    else:
        backup_name = None
    
    script_path = ROOT / "time_machine.sh"
    if not script_path.exists():
        await update.message.reply_text("❌ Error: `time_machine.sh` not found on this system.")
        return
        
    await update.message.reply_text(
        f"⏳ *Initiating Rollback...*\n"
        f"Target: `{backup_name if backup_name else 'Latest Backup'}`\n"
        "Rey will stop, restore files, and restart. Please wait 10-15 seconds...",
        parse_mode="Markdown"
    )
    
    try:
        import subprocess
        # We run the restore command using systemd-run so that it runs in a transient service
        # outside this bot's service control group. This prevents it from being killed
        # when time_machine.sh stops the email-intel-bot service.
        cmd = ["systemd-run", "--description=Rey Tran Bot Manual Rollback", str(script_path), "restore"]
        if backup_name:
            cmd.append(backup_name)
            
        logger.info(f"Executing manual rollback command: {' '.join(cmd)}")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.error(f"Error initiating rollback: {e}")
        await update.message.reply_text(f"❌ Failed to start rollback process: {e}")

async def restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return
        
    args = context.args
    if not args or args[0].strip() != "linhtran":
        await update.message.reply_text("❌ Invalid or missing password. Usage: `/restart <password>`", parse_mode="Markdown")
        return
        
    await update.message.reply_text("🔄 *Restarting Rey Tran Bot service...*", parse_mode="Markdown")
    logger.info("Restart requested via Telegram. Exiting process...")
    os._exit(1)

async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return
        
    args = context.args
    if not args or args[0].strip() != "linhtran":
        await update.message.reply_text("❌ Invalid or missing password. Usage: `/update <password>`", parse_mode="Markdown")
        return
        
    await update.message.reply_text("⏳ *Checking for updates and pulling latest code...*", parse_mode="Markdown")
    
    try:
        import subprocess
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "pull"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout.strip()
        err = result.stderr.strip()
        
        if result.returncode != 0:
            await update.message.reply_text(
                f"❌ *Update failed (git pull returned non-zero):*\n`{err or output}`",
                parse_mode="Markdown"
            )
            return
            
        if "Already up to date" in output:
            await update.message.reply_text("✅ *Already up to date.* No restart required.", parse_mode="Markdown")
            return
            
        await update.message.reply_text(
            f"✅ *Updates pulled successfully:*\n```{output}```\n🔄 Restarting service to apply changes...",
            parse_mode="Markdown"
        )
        logger.info("Update complete. Exiting process to trigger systemd restart...")
        os._exit(0)
        
    except Exception as e:
        logger.error(f"Error during git update: {e}")
        await update.message.reply_text(f"❌ *Error executing update:* {e}", parse_mode="Markdown")

async def watchdog_loop(bot):
    """Monitors bot health: network connectivity and critical services.
    
    If it detects persistent disconnection or event loop failure, it restarts the bot.
    """
    logger.info("Watchdog monitor loop started.")
    consecutive_failures = 0
    while True:
        await asyncio.sleep(60)  # Check every 60 seconds
        try:
            # Check Telegram API connectivity
            await asyncio.to_thread(
                urllib.request.urlopen,
                "https://api.telegram.org",
                timeout=5
            )
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            logger.warning(f"Watchdog connectivity check failed ({consecutive_failures}/10): {e}")
            if consecutive_failures >= 10:
                logger.fatal("Watchdog: Persistent disconnection detected for 10 minutes. Rebooting service...")
                try:
                    chats_str = os.environ.get("TELEGRAM_CHAT_IDS", "")
                    if chats_str:
                        first_chat = chats_str.split(",")[0].strip()
                        if first_chat:
                            await bot.send_message(
                                chat_id=first_chat,
                                text="⚠️ *Watchdog Alert*: Persistent disconnection detected. Rebooting bot service to recover...",
                                parse_mode="Markdown"
                            )
                except Exception:
                    pass
                os._exit(1)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    # Authorization check.
    # Allow if the user is individually whitelisted OR the chat itself is a
    # whitelisted multi-bot coordination group/supergroup.
    chat_whitelisted = is_authorized_chat(chat_id)
    if not (is_authorized(user_id) or chat_whitelisted):
        # In DMs, respond with unauthorized. In groups, ignore completely to prevent spam.
        if chat_type == "private":
            await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    # ── Open council discussion ──────────────────────────────────────────────
    # In a whitelisted council chat with open mode on, throw the topic open to
    # the WHOLE council instead of a single inline reply. Rey and every peer pick
    # it up via the broadcast loop and freely contribute (with Linh-Tran priority).
    if COUNCIL_OPEN_MODE and chat_whitelisted and chat_type in ("group", "supergroup"):
        topic = update.message.text.strip()
        if len(topic) >= MIN_TOPIC_CHARS:
            opener = update.effective_user.username or update.effective_user.first_name or str(user_id)
            try:
                _id, thread_id = await asyncio.to_thread(
                    council_relay.post_broadcast,
                    f"human:{opener}", chat_id, topic, 0, None,
                )
                logger.info(f"Opened council thread {thread_id[:8]} from {opener} in chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to open council thread: {e}")
        return

    # Check response conditions
    should_respond = False
    if chat_type == "private":
        should_respond = True
    elif chat_type in ["group", "supergroup"]:
        bot_username = context.bot.username
        mention = f"@{bot_username}"
        is_mention = mention in update.message.text
        
        is_reply_to_bot = False
        if update.message.reply_to_message:
            reply_to = update.message.reply_to_message
            if reply_to.from_user and reply_to.from_user.id == context.bot.id:
                is_reply_to_bot = True
                
        if is_mention or is_reply_to_bot:
            should_respond = True

    if not should_respond:
        return

    # Prepare message for Claude
    raw_text = update.message.text
    cleaned_text = raw_text
    
    # Strip bot mention if in group
    if chat_type in ["group", "supergroup"]:
        bot_username = context.bot.username
        mention = f"@{bot_username}"
        cleaned_text = raw_text.replace(mention, "").strip()

    await update.message.chat.send_action(action="typing")
    
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
        
    chat_histories[chat_id].append({"role": "user", "content": cleaned_text})
    # Keep rolling context of last 20 turns (40 messages)
    chat_histories[chat_id] = chat_histories[chat_id][-40:]
    
    try:
        response_text = await asyncio.to_thread(
            call_claude_with_tools,
            messages=chat_histories[chat_id]
        )
        chat_histories[chat_id] = chat_histories[chat_id][-40:]
        await reply_message_safe(update, response_text)
        # If Rey addressed a live peer bot, hand the ask off via the council relay
        # (Telegram won't deliver it bot-to-bot). Human-initiated turn => depth 0.
        relay_outbound(response_text, chat_id, depth=0)
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        if chat_histories[chat_id] and chat_histories[chat_id][-1]["role"] == "user":
            chat_histories[chat_id].pop() # Remove failed user message
        await update.message.reply_text(f"❌ Error: {e}")

# ── Council Bot-to-Bot Relay ──────────────────────────────────────────────────
def relay_outbound(text: str, chat_id, depth: int):
    """Queue an inter-bot ask for every live peer Rey @mentioned in `text`.

    Bounded by COUNCIL_MAX_HOPS so council bots can't loop forever.
    """
    if depth >= council_relay.max_hops():
        return []
    targets = extract_peer_mentions(text)
    for t in targets:
        try:
            council_relay.post_message(
                sender=REY_USERNAME or "rey",
                recipient=t,
                chat_id=chat_id,
                text=text,
                depth=depth + 1,
            )
            logger.info(f"Relay → @{t} (depth {depth + 1}) in chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to relay to @{t}: {e}")
    return targets

async def process_relay_message(bot, msg: dict):
    """Answer an inter-bot ask addressed to Rey, then relay onward if needed."""
    sender = msg.get("sender", "unknown")
    chat_id = msg.get("chat_id")
    text = msg.get("text", "")
    depth = msg.get("depth", 0)

    framed = (
        f"[Council relay] @{sender} addressed you (Rey) in the group:\n\n{text}\n\n"
        "If this is your domain, answer directly and concisely for the group. "
        "If it belongs to another council bot, hand off with a single @mention. "
        "Do not simply echo the request back."
    )
    try:
        response_text = await asyncio.to_thread(
            call_claude_with_tools, messages=[{"role": "user", "content": framed}]
        )
    except Exception as e:
        logger.error(f"Relay processing failed (from @{sender}): {e}")
        return

    if chat_id:
        try:
            await send_message_safe(bot, chat_id, response_text)
        except Exception as e:
            logger.error(f"Failed to post relay reply to chat {chat_id}: {e}")

    # Continue the chain if Rey handed off to another peer (depth-guarded).
    relay_outbound(response_text, chat_id, depth=depth)

async def relay_poll_loop(bot):
    """Poll the shared relay for asks addressed to Rey and handle them."""
    if REY_USERNAME is None:
        logger.warning("Relay poll loop: Rey username unresolved; relay disabled.")
        return
    logger.info(f"Council relay poll loop started for @{REY_USERNAME}.")
    while True:
        try:
            msgs = await asyncio.to_thread(council_relay.claim_unread, REY_USERNAME, 10)
            for m in msgs:
                await process_relay_message(bot, m)
        except Exception as e:
            logger.error(f"Error in relay poll loop: {e}")
        await asyncio.sleep(3)

# ── Open Council Discussion engine ────────────────────────────────────────────
def _format_thread(history) -> str:
    """Render recent thread messages as a readable transcript for the LLM."""
    lines = []
    for h in history:
        who = h["sender"]
        who = who.replace("human:", "👤 ") if who.startswith("human:") else f"@{who}"
        lines.append(f"{who}: {h['text']}")
    return "\n".join(lines)

async def process_broadcast(bot, b: dict):
    """Decide whether Rey contributes to an open council thread, and if so, speak."""
    sender = b.get("sender", "unknown")
    chat_id = b.get("chat_id")
    text = b.get("text", "")
    depth = b.get("depth", 0)
    thread_id = b.get("thread_id")
    if not thread_id:
        return

    # Loop / cost guards — these bound runaway chatter, not the topics themselves.
    if depth >= council_relay.max_hops():
        return
    if await asyncio.to_thread(council_relay.thread_count, thread_id) >= THREAD_MAX_MSGS:
        return
    if await asyncio.to_thread(council_relay.thread_sender_count, thread_id, REY_USERNAME) >= THREAD_BOT_LIMIT:
        return

    history = await asyncio.to_thread(council_relay.thread_recent, thread_id, 12)
    transcript = _format_thread(history)
    directly_addressed = REY_USERNAME in extract_peer_mentions(text) or (REY_USERNAME or "") in text.lower()

    framed = (
        "[Open NBC Council discussion]\n"
        "You (Rey) are in a free-flowing discussion with peer council bots. The floor is open.\n\n"
        f"Discussion so far:\n{transcript}\n\n"
        f"Latest from {sender}: {text}\n\n"
        "Contribute your perspective from YOUR domain (Chief of Staff / executive intelligence). "
        "PRIORITY RULE: if anything here concerns Linh Trần — his decisions, risks, finances, "
        "schedule, businesses (DDS Group, DDS Petro, Van Ninh Port) — treat it as top priority and "
        "drive toward concretely helping Linh solve it: surface the key issue, give a clear recommendation "
        "or next action, and @mention the right council bot if their expertise is needed.\n"
        f"If you have nothing materially NEW to add, reply with EXACTLY {PASS_TOKEN} and nothing else. "
        "Be concise, executive-grade, and never repeat what was already said."
    )

    try:
        response_text = await asyncio.to_thread(
            call_claude_with_tools, messages=[{"role": "user", "content": framed}]
        )
    except Exception as e:
        logger.error(f"Open discussion processing failed (thread {thread_id[:8]}): {e}")
        return

    # Stay silent unless Rey actually has something to add.
    if response_text.strip() == PASS_TOKEN or (PASS_TOKEN in response_text and len(response_text.strip()) <= len(PASS_TOKEN) + 4):
        if not directly_addressed:
            logger.info(f"Rey passed on thread {thread_id[:8]} (nothing new).")
            return
        # Directly addressed but model tried to pass — strip the token and answer anyway.
        response_text = response_text.replace(PASS_TOKEN, "").strip() or "Noted — no further input from my side right now."

    if chat_id:
        try:
            await send_message_safe(bot, chat_id, response_text)
        except Exception as e:
            logger.error(f"Failed to post council contribution to chat {chat_id}: {e}")

    # Re-broadcast Rey's contribution so peers can react (depth-guarded).
    try:
        await asyncio.to_thread(
            council_relay.post_broadcast,
            REY_USERNAME, chat_id, response_text, depth + 1, thread_id,
        )
    except Exception as e:
        logger.error(f"Failed to re-broadcast Rey's contribution: {e}")

async def broadcast_poll_loop(bot):
    """Poll the shared relay for OPEN discussion messages and let Rey join in."""
    if REY_USERNAME is None:
        logger.warning("Broadcast poll loop: Rey username unresolved; open mode disabled.")
        return
    if not COUNCIL_OPEN_MODE:
        logger.info("Open council mode is OFF; broadcast poll loop not started.")
        return
    logger.info(f"Open council discussion loop started for @{REY_USERNAME}.")
    while True:
        try:
            news = await asyncio.to_thread(council_relay.fetch_new_broadcasts, REY_USERNAME, 20)
            for b in news:
                await process_broadcast(bot, b)
        except Exception as e:
            logger.error(f"Error in broadcast poll loop: {e}")
        await asyncio.sleep(3)

# ── Scheduler background loop ─────────────────────────────────────────────────
async def run_scheduled_briefing(bot, mode: str):
    """Utility to run and send scheduled briefing."""
    logger.info(f"Triggering scheduled briefing for mode: {mode}")
    try:
        # Run briefing in background thread
        await asyncio.to_thread(run_briefing, mode, False)
    except Exception as e:
        logger.error(f"Scheduled briefing {mode} failed: {e}")
        # Send error to Telegram
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chats = (os.environ.get("TELEGRAM_CHAT_IDS") or "").split(",")
        for c in chats:
            if c.strip() and token:
                try:
                    await bot.send_message(
                        chat_id=c.strip(),
                        text=f"⚠️ Scheduled briefing {mode} failed: {type(e).__name__}: {e}"
                    )
                except Exception:
                    pass

async def scheduler_loop(bot):
    """Background task checking time for scheduled runs."""
    logger.info("Internal scheduler loop started.")
    while True:
        try:
            now = dt.datetime.now(TZ)
            today_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M")
            
            # Morning brief at 07:30
            if time_str >= "07:30" and last_runs["morning"] != today_str:
                last_runs["morning"] = today_str
                asyncio.create_task(run_scheduled_briefing(bot, "morning"))
                
            # Lunch brief at 11:30
            elif time_str >= "11:30" and last_runs["lunch"] != today_str:
                last_runs["lunch"] = today_str
                asyncio.create_task(run_scheduled_briefing(bot, "lunch"))
                
            # Daybreak brief at 16:00
            elif time_str >= "16:00" and last_runs["daybreak"] != today_str:
                last_runs["daybreak"] = today_str
                asyncio.create_task(run_scheduled_briefing(bot, "daybreak"))
                
            # Check every 15 seconds
            await asyncio.sleep(15)
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}")
            await asyncio.sleep(10)

# ── Main startup ──────────────────────────────────────────────────────────────
async def main():
    # Load environment variables
    load_dotenv(ROOT / ".env")
    
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.fatal("TELEGRAM_BOT_TOKEN is not configured in .env file.")
        sys.exit(1)
        
    # Check Gmail token
    token_path = ROOT / "token.json"
    if not token_path.exists():
        logger.warning("token.json not found. The scheduler/bot will fail to fetch emails until auth_setup.py is run.")

    # Initialize scheduler run-dates so we don't retroactively trigger
    # scheduled runs that should have run earlier today before startup
    now = dt.datetime.now(TZ)
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    
    if time_str >= "07:30":
        last_runs["morning"] = today_str
        logger.info("Initializing Morning Brief as already run for today.")
    if time_str >= "11:30":
        last_runs["lunch"] = today_str
        logger.info("Initializing Lunch Brief as already run for today.")
    if time_str >= "16:00":
        last_runs["daybreak"] = today_str
        logger.info("Initializing Daybreak Brief as already run for today.")

    logger.info("Initializing Telegram bot application...")
    application = Application.builder().token(token).build()
    
    # Add Command Handlers
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("brief", brief_cmd))
    application.add_handler(CommandHandler("morning", morning_cmd))
    application.add_handler(CommandHandler("lunch", lunch_cmd))
    application.add_handler(CommandHandler("daybreak", daybreak_cmd))
    application.add_handler(CommandHandler("ask", ask_cmd))
    application.add_handler(CommandHandler("reset", reset_cmd))
    application.add_handler(CommandHandler("backups", backups_cmd))
    application.add_handler(CommandHandler("rollback", rollback_cmd))
    application.add_handler(CommandHandler("restart", restart_cmd))
    application.add_handler(CommandHandler("update", update_cmd))
    
    # Add Message Handler for general conversations (non-command text)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Resolve Rey's own username (relay routing key) and init the shared relay.
    global REY_USERNAME
    try:
        me = await application.bot.get_me()
        REY_USERNAME = (me.username or "").lower() or None
        council_relay.init_db()
        logger.info(
            f"Council relay ready: identity=@{REY_USERNAME}, "
            f"db={council_relay.db_path()}, peers={sorted(PEER_USERNAMES) or 'none'}"
        )
    except Exception as e:
        logger.error(f"Failed to initialize council relay: {e}")

    # Start scheduler loop as a background asyncio task
    asyncio.create_task(scheduler_loop(application.bot))
    # Start council relay poll loops (direct asks + open discussion)
    asyncio.create_task(relay_poll_loop(application.bot))
    asyncio.create_task(broadcast_poll_loop(application.bot))
    # Start watchdog loop
    asyncio.create_task(watchdog_loop(application.bot))
    
    logger.info("DDS Briefing Bot server started successfully.")
    
    # Send startup message to first configured chat ID for verification
    chats_str = os.environ.get("TELEGRAM_CHAT_IDS", "")
    if chats_str:
        first_chat = chats_str.split(",")[0].strip()
        if first_chat:
            try:
                await application.bot.send_message(
                    chat_id=first_chat,
                    text=f"🤖 *DDS Email Briefing Bot Server Started*\nLocal Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send startup message: {e}")

    # Keep running forever
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received. Stopping bot...")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Bot server stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.fatal(f"Unhandled exception: {e}")
        sys.exit(1)
