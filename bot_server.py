#!/usr/bin/env python3
"""DDS 24/7 Telegram Briefing Bot Server.

Integrates Telegram command polling and an internal async scheduler to trigger
automatic briefings at 07:30, 11:30, and 16:00 ICT.
"""
import os
import sys
import asyncio
import logging
import datetime as dt
from pathlib import Path
from dotenv import load_dotenv

# Add current directory to path to ensure we can import main
ROOT = Path(__file__).parent
sys.path.append(str(ROOT))

from main import run_briefing, WINDOWS, LABELS, TZ, log

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
except ImportError:
    print("Error: Missing 'python-telegram-bot' library. Please run 'pip install python-telegram-bot'.")
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

def is_authorized(user_id: int) -> bool:
    if not AUTHORIZED_IDS:
        return True  # If not configured, allow all (not recommended)
    return user_id in AUTHORIZED_IDS

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
    oauth_ok = "✅ Valid" if token_path.exists() else "❌ Missing (run auth_setup.py)"
    
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
    
    # Start bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Start scheduler loop as a background asyncio task
    asyncio.create_task(scheduler_loop(application.bot))
    
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
