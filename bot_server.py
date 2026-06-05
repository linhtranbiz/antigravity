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
from chat import call_claude_with_tools

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

# Fully-authorized chats/groups (e.g. the OCLO x NBC council group). In these chats
# Rey converses freely with everyone, and any member may run commands.
_chat_auth_str = os.getenv("AUTHORIZED_CHAT_IDS", "").strip()
AUTHORIZED_CHAT_IDS = {int(c.strip()) for c in _chat_auth_str.split(",") if c.strip()} if _chat_auth_str else set()

# The OCLO x NBC collaboration group ID (Rey = OCLO GM Rep, Lance = NBC Chief Operating Intelligence).
_nbc_group = os.getenv("NBC_GROUP_ID", "").strip()
NBC_GROUP_ID = int(_nbc_group) if _nbc_group else None

def is_authorized(user_id: int) -> bool:
    if not AUTHORIZED_IDS:
        return True  # If not configured, allow all (not recommended)
    return user_id in AUTHORIZED_IDS

def is_allowed(update: Update) -> bool:
    """Authorize by user ID OR by an explicitly whitelisted chat/group."""
    chat = update.effective_chat
    if chat is not None and chat.id in AUTHORIZED_CHAT_IDS:
        return True
    user = update.effective_user
    if user is not None and is_authorized(user.id):
        return True
    # If neither users nor chats are configured, allow all (legacy behavior)
    return not AUTHORIZED_IDS and not AUTHORIZED_CHAT_IDS

# ── Scheduler State ───────────────────────────────────────────────────────────
last_runs = {
    "morning": None,  # Will store date string e.g. '2026-05-28'
    "lunch": None,
    "wrapup": None
}

def get_current_mode():
    """Detect current briefing mode based on server time."""
    now = dt.datetime.now(TZ)
    time_str = now.strftime("%H:%M")
    if time_str < "11:30":
        return "morning"
    elif time_str < "17:00":
        return "lunch"
    else:
        return "wrapup"

# ── Telegram Command Handlers ─────────────────────────────────────────────────
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        logger.warning(f"Unauthorized start attempt from user: {update.effective_user.id}")
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    await update.message.reply_text(
        "🤖 *DDS Email Intelligence Bot (24/7 Server)*\n\n"
        "Uptime status: *Online* ✅\n\n"
        "*Briefing & chat:*\n"
        "🔹 /brief - Brief for the current active window\n"
        "🔹 /morning - Morning Brief (17:00 yesterday → 07:30 today)\n"
        "🔹 /lunch - Lunch Brief (07:30 today → 11:30 today)\n"
        "🔹 /wrapup - End-of-Day Wrap-Up (11:30 today → 17:00 today)\n"
        "🔹 /ask <question> - One-shot question to Rey\n"
        "🔹 /reset - Reset chat memory for this chat\n"
        "🔹 /status - System configuration and scheduled runs\n"
        "🔹 /help - This command list\n\n"
        "*OCLO × NBC collaboration:*\n"
        "🔸 /oclo_nbc_analyze <topic> - Classify OCLO-only / NBC-only / joint\n"
        "🔸 /rey_request_nbc <topic> - Rey requests NBC analysis via Lance\n"
        "🔸 /lance_route <topic> - Lance routes NBC lead/support agents\n"
        "🔸 /oclo_nbc_taskforce <topic> - Create a joint taskforce\n"
        "🔸 /oclo_nbc_email <email> - Review an email with NBC + OCLO follow-up\n"
        "🔸 /oclo_nbc_news <news> - News impact review\n"
        "🔸 /oclo_nbc_owner <topic> - Assign owners / lead / support\n"
        "🔸 /oclo_nbc_risk <topic> - Joint risk review\n"
        "🔸 /oclo_nbc_draft <topic> - Draft external reply (approval-marked)\n"
        "🔸 /oclo_nbc_highstakes <topic> - Activate High-Stakes Mode\n"
        "🔸 /oclo_nbc_memory <topic> - Create an OCLO memory item\n"
        "🔸 /oclo_nbc_followup - List active joint follow-ups\n"
        "🔸 /rey_final - Rey's final executive recommendation after NBC input",
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
    for mode, time_val in [("morning", "07:30"), ("lunch", "11:30"), ("wrapup", "17:00")]:
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

async def wrapup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_briefing_on_demand(update, "wrapup")

# ── Conversation Memory Store ────────────────────────────────────────────────
# Stores rolling chat history per chat_id: chat_id -> list of {"role": "user"|"assistant", "content": "..."}
chat_histories = {}

async def reply_message_safe(update: Update, text: str):
    """Sends text in chunks of <= 4000 chars to avoid Telegram message length limit."""
    if len(text) <= 4000:
        await update.message.reply_text(text)
        return
        
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) + 2 > 4000:
            chunks.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur:
        chunks.append(cur)
        
    for chunk in chunks:
        await update.message.reply_text(chunk)

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

# ── OCLO × NBC Collaboration Commands ─────────────────────────────────────────
# Each protocol is a directive prepended to the user's topic. The OCLO x NBC
# framework lives in the live-chat system prompt (chat.py), so these directives
# only need to name the protocol and the expected structure.
OCLO_NBC_PROTOCOLS = {
    "oclo_nbc_analyze": (
        "Run the OCLO x NBC TOPIC CLASSIFICATION protocol. Classify the topic and state: "
        "Primary/Secondary topic, OCLO relevance, NBC relevance, Collaboration Type "
        "(OCLO-only / NBC-only / OCLO x NBC joint / Needs external specialist), Urgency, "
        "Sensitivity, Money impact, Risk level, and whether approval is required before external use."
    ),
    "rey_request_nbc": (
        "Act as Rey (OCLO General Manager Representative). Clarify Anh Linh's true objective, then "
        "formally request NBC specialist analysis THROUGH Lance: state which NBC lead/support agents "
        "should be activated and exactly what question OCLO needs NBC to answer."
    ),
    "lance_route": (
        "Act as Lance Tran (NBC Chief Operating Intelligence). Route this topic inside NBC: assign the "
        "NBC Lead Agent and Supporting Agents, give a short reason for each assignment, and outline how "
        "the NBC-side discussion will be structured."
    ),
    "oclo_nbc_taskforce": (
        "Create a joint OCLO x NBC TASKFORCE. Produce the Taskforce Report: Taskforce Name, OCLO Owner (Rey), "
        "NBC Coordinator (Lance), NBC Lead Agent, Supporting Agents, Mission, Situation, Discussion Summary "
        "(let agents challenge each other), NBC Recommendation, OCLO Execution View, Final Recommendation for "
        "Anh Linh, Action Plan table, Risks, Linh Approval Needed (Yes/No), Follow-Up, and an OCLO Memory Item."
    ),
    "oclo_nbc_email": (
        "Run the OCLO x NBC EMAIL REVIEW on the pasted email: Sender, Summary, Sender intent, Required response, "
        "NBC Lead Agent + supporting agents, NBC recommended reply direction, Rey OCLO execution view, a Draft Reply, "
        "Risks, Approval required (Yes/No), and Follow-up/memory. Mark external drafts as approval-required."
    ),
    "oclo_nbc_news": (
        "Run the OCLO x NBC NEWS IMPACT REVIEW: News summary, relevance to Linh/OCLO/NBC/DDS/Van Ninh Port, "
        "affected areas, NBC Lead Agent, Rey OCLO view, business impact, risk/opportunity, recommended action, "
        "follow-up needed, and whether OCLO memory is needed."
    ),
    "oclo_nbc_owner": (
        "Assign TASK OWNERSHIP for this topic: OCLO Owner, NBC Lead Agent, Supporting Agents, Final Output Owner, "
        "and the reason for the assignment."
    ),
    "oclo_nbc_risk": (
        "Run a joint OCLO x NBC RISK REVIEW: confirmed facts vs assumptions, key risks (legal/financial/"
        "reputation/relationship/control), money impact, mitigations, and whether approval is required before any action."
    ),
    "oclo_nbc_draft": (
        "Draft an external response/message for this topic. Keep it professional and safe. Append "
        "'Draft only — requires Linh Tran approval before sending.' and, for legal/financial/bank/government "
        "content, also 'Specialist review required before external use.'"
    ),
    "oclo_nbc_highstakes": (
        "Activate HIGH-STAKES MODE for this topic: Stakeholder, Sensitivity, Confirmed Facts, Assumptions, Risks, "
        "NBC specialist reviews required, Rey OCLO safe position, Draft Output (external = draft-only), and "
        "'Linh Approval Required: Yes'."
    ),
    "oclo_nbc_memory": (
        "Create an OCLO-side MEMORY ITEM from this discussion in the structured format: date, source, topic, summary, "
        "oclo_owner, nbc_lead, supporting_agents, decision, risk_level, money_impact, next_action, owner, deadline, "
        "approval_required, status."
    ),
    "oclo_nbc_followup": (
        "List active OCLO x NBC follow-ups based on the recent conversation: for each open item give the action, "
        "owner, deadline, approval status, and current status. If nothing is pending, say so clearly."
    ),
    "rey_final": (
        "Act as Rey (OCLO General Manager Representative). Based on the NBC discussion in this conversation, produce "
        "the OCLO x NBC FINAL RECOMMENDATION for Anh Linh: Executive Summary, OCLO View (Rey), NBC View (Lance/lead), "
        "Final Recommendation, Task Ownership, Known Facts vs Assumptions, Money/Value impact, Key Risks, Recommended "
        "Action, Next Steps table, Items to Verify, any Draft message (approval-marked), Approval required (Yes/No), "
        "Follow-up needed (Yes/No), and an OCLO Memory Item to store. Be concise and decision-ready."
    ),
}

# Protocols that synthesize from the running conversation rather than a one-shot topic argument.
_CONTEXT_PROTOCOLS = {"rey_final", "oclo_nbc_followup"}

# Legacy NBC commands map to their OCLO x NBC equivalents.
LEGACY_NBC_ALIASES = {
    "nbc_analyze": "oclo_nbc_analyze",
    "nbc_taskforce": "oclo_nbc_taskforce",
    "nbc_email": "oclo_nbc_email",
    "nbc_news": "oclo_nbc_news",
    "nbc_owner": "oclo_nbc_owner",
    "nbc_risk": "oclo_nbc_risk",
    "nbc_draft": "oclo_nbc_draft",
    "nbc_highstakes": "oclo_nbc_highstakes",
    "nbc_memory": "oclo_nbc_memory",
    "nbc_followup": "oclo_nbc_followup",
}

async def run_oclo_nbc_command(update: Update, context: ContextTypes.DEFAULT_TYPE, protocol_key: str):
    if not is_allowed(update):
        await update.message.reply_text("❌ Unauthorized.")
        return

    directive = OCLO_NBC_PROTOCOLS[protocol_key]
    topic = " ".join(context.args).strip()

    if protocol_key in _CONTEXT_PROTOCOLS:
        # Synthesize from the running conversation in this chat.
        history = list(chat_histories.get(update.effective_chat.id, []))
        focus = f"\n\nFocus topic: {topic}" if topic else ""
        messages = history + [{"role": "user", "content": directive + focus}]
    else:
        if not topic:
            await update.message.reply_text(
                f"ℹ️ Usage: `/{protocol_key} <topic / pasted content>`", parse_mode="Markdown"
            )
            return
        messages = [{"role": "user", "content": directive + "\n\nINPUT:\n" + topic}]

    await update.message.chat.send_action(action="typing")
    try:
        response_text = await asyncio.to_thread(call_claude_with_tools, messages=messages)
        await reply_message_safe(update, response_text)
    except Exception as e:
        logger.error(f"Error in /{protocol_key} command: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

def make_oclo_nbc_handler(protocol_key: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await run_oclo_nbc_command(update, context, protocol_key)
    return handler

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    # Authorization check
    if not is_allowed(update):
        # In DMs, respond with unauthorized. In groups, ignore completely to prevent spam.
        if chat_type == "private":
            await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    # Ignore other bots' messages to prevent agent-to-agent reply loops in collaboration groups.
    if update.effective_user.is_bot:
        return

    # Check response conditions
    should_respond = False
    if chat_type == "private":
        should_respond = True
    elif chat_type in ["group", "supergroup"]:
        # In fully-authorized collaboration chats (e.g. the OCLO x NBC council),
        # Rey converses freely with every (human) message.
        if chat_id in AUTHORIZED_CHAT_IDS:
            should_respond = True
        else:
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
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        if chat_histories[chat_id] and chat_histories[chat_id][-1]["role"] == "user":
            chat_histories[chat_id].pop() # Remove failed user message
        await update.message.reply_text(f"❌ Error: {e}")

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
                
            # Wrap-Up brief at 17:00
            elif time_str >= "17:00" and last_runs["wrapup"] != today_str:
                last_runs["wrapup"] = today_str
                asyncio.create_task(run_scheduled_briefing(bot, "wrapup"))
                
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
    if time_str >= "17:00":
        last_runs["wrapup"] = today_str
        logger.info("Initializing Wrap-Up Brief as already run for today.")

    logger.info("Initializing Telegram bot application...")
    application = Application.builder().token(token).build()
    
    # Add Command Handlers
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("brief", brief_cmd))
    application.add_handler(CommandHandler("morning", morning_cmd))
    application.add_handler(CommandHandler("lunch", lunch_cmd))
    application.add_handler(CommandHandler("wrapup", wrapup_cmd))
    application.add_handler(CommandHandler("ask", ask_cmd))
    application.add_handler(CommandHandler("reset", reset_cmd))

    # OCLO x NBC collaboration commands (+ legacy /nbc_* aliases)
    for protocol_key in OCLO_NBC_PROTOCOLS:
        application.add_handler(CommandHandler(protocol_key, make_oclo_nbc_handler(protocol_key)))
    for legacy_cmd, protocol_key in LEGACY_NBC_ALIASES.items():
        application.add_handler(CommandHandler(legacy_cmd, make_oclo_nbc_handler(protocol_key)))

    # Add Message Handler for general conversations (non-command text)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
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
