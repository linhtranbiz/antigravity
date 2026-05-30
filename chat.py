#!/usr/bin/env python3
"""Anthropic Claude Live Chat Client with Tool Calling.

Configures tool descriptions (Gmail and Google Calendar) and runs the execution loop
when Claude decides to query email or calendar data during conversations.
"""
import os
import sys
import logging
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import datetime as dt
from anthropic import Anthropic

ROOT = Path(__file__).parent
sys.path.append(str(ROOT))

from gmail_client import search_emails, get_email
from calendar_client import list_calendar_events

logger = logging.getLogger("briefing_bot")

LIVE_CHAT_SYSTEM_PROMPT = """You are "Rey", the AI Chief of Staff and Executive Intelligence Officer for Linh Trần (CFO of DDS Group, DDS Petro, and Van Ninh International Port).

Your operating style is highly professional, concise, direct, and action-oriented. You exist to make Linh's life easier by summarizing details, tracking crucial timelines, and offering sharp executive guidance on business matters.

Operating Domains & Core Context:
1. Banking & Letters of Credit (LCs):
   - Active relationships: BIDV, ACB, Shinhan, MB, VIB.
   - Core instruments: LCs (Letters of Credit), UNCs (Ủy nhiệm chi), UPAS LCs, credit agreements, covenants.
   - Priority: Monitor limits, interest rates, and fee structures.
2. Petroleum Trading & Pricing:
   - Pricing mechanisms: MOPS (Mean of Platts Singapore), Platts benchmarks, premium formulas.
   - Key suppliers/partners: Vitol, BSR (Bình Sơn Refining / Dung Quất).
   - Terms: Term contracts, spot cargoes, and offtake agreements (e.g., PVNDB terms).
3. Van Ninh International Port:
   - Infrastructure development, investment, construction milestones, concessions, berthing capacities, and regulatory/governmental filings.
4. Group Operations:
   - Vessel scheduling, marine logistics, customs clearance, port agent updates, loading/discharge windows.
5. Investors & Board Relations:
   - Financial reporting, presentation prep, investor queries, and board meeting follow-ups.
6. Personal Admin & CFO Support:
   - Linh's schedule, personal finance, subscriptions, and executive task tracking.

Escalation & Flagging Rules (When discussing these, explicitly highlight or warn Linh immediately):
- LC Expiry or Approaching Deadlines: Highlight any LC expiring in < 7 days or pending document submissions.
- Covenant Breaches: Any indication of leverage, liquidity, or compliance ratio breaches.
- Customs or Regulatory Holds: Immediate flag for port authority, customs, or tax office holds.
- FX Rate Fluctuations: Flag if USD/VND or major relevant currency pairs move >1% within a single day.
- Operational Delay: Vessel discharge or loading delay that incurs demurrage.

Communication & Interaction Guidelines:
- Language: Bilingual. Respond in the language used by the user (Vietnamese or English). If the user mixes them, use professional, high-level business Vietnamese/English blend (typical of multinational executives).
- Style: Bullet-points, bold text for emphasis. Short and structured. No fluff, no generic pleasantries (e.g., "I hope this finds you well"). Start directly with the answer.
- Confidentiality: NEVER leak sensitive financial figures, proprietary pricing formulas, or internal strategy in public Telegram groups. In group chats, keep answers high-level, strictly professional, and avoid detailing confidential data. If asked about highly confidential info in a group, advise Linh to discuss it in DMs. In DMs, you can speak fully and openly.
- Rolling memory: You have access to the rolling chat history. Connect your answers to previous contexts if referenced.
"""

TOOLS = [
    {
        "name": "search_emails",
        "description": "Search user's Gmail mailbox using Gmail query syntax (e.g., 'from:acb.com.vn', 'subject:LC', 'after:2026/05/01'). Returns email metadata (ID, subject, from, date, snippet).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query in Gmail syntax."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 5, max 10).",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_email",
        "description": "Retrieve the full details and body of a specific email by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "The unique ID of the email to retrieve."
                }
            },
            "required": ["email_id"]
        }
    },
    {
        "name": "list_calendar_events",
        "description": "Retrieve the user's scheduled calendar events for a given time range (specified in ISO-8601 format, e.g., '2026-05-30T00:00:00+07:00' or '2026-05-31T23:59:59+07:00'). Use start/end boundaries derived from relative phrases (like 'today', 'tomorrow', 'this week') and the current time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_iso": {
                    "type": "string",
                    "description": "ISO-8601 start time (with offset/timezone)."
                },
                "end_iso": {
                    "type": "string",
                    "description": "ISO-8601 end time (with offset/timezone)."
                }
            },
            "required": ["start_iso", "end_iso"]
        }
    }
]

def execute_tool(name, arguments):
    """Execute local functions mapping to tool names."""
    logger.info(f"Executing tool: {name} with args {arguments}")
    try:
        if name == "search_emails":
            return search_emails(
                query=arguments.get("query"),
                max_results=arguments.get("max_results", 5)
            )
        elif name == "get_email":
            return get_email(
                email_id=arguments.get("email_id")
            )
        elif name == "list_calendar_events":
            return list_calendar_events(
                start_iso=arguments.get("start_iso"),
                end_iso=arguments.get("end_iso")
            )
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        logger.error(f"Error running tool {name}: {e}")
        return f"Error executing tool {name}: {type(e).__name__}: {e}"

def call_claude_with_tools(messages: list) -> str:
    """Invokes Claude messages API, handles automatic tool execution loop, and updates message history."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is missing.")
        
    model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    client = Anthropic(api_key=api_key)
    
    # Resolve relative dates by injecting current Vietnam timezone context
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    now = dt.datetime.now(tz)
    system_prompt = LIVE_CHAT_SYSTEM_PROMPT + f"\n\nCurrent Time Context: {now.strftime('%A, %Y-%m-%d %H:%M:%S %Z')}"
    
    # Copy message history to perform multi-turn loop
    local_messages = list(messages)
    
    max_loops = 5
    for loop_idx in range(max_loops):
        logger.info(f"Claude API call loop {loop_idx+1}/{max_loops} with {len(local_messages)} history messages.")
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=local_messages,
            tools=TOOLS
        )
        
        if resp.stop_reason == "tool_use":
            # Extract tool calls and text response from content blocks
            tool_calls = [c for c in resp.content if c.type == "tool_use"]
            
            # Map response content blocks to structure expected by Anthropic
            assistant_content = []
            for block in resp.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })
            
            local_messages.append({"role": "assistant", "content": assistant_content})
            
            # Resolve tool requests
            tool_results_content = []
            for call in tool_calls:
                result = execute_tool(call.name, call.input)
                
                # Format non-string output into JSON strings
                if not isinstance(result, str):
                    result_str = json.dumps(result, ensure_ascii=False)
                else:
                    result_str = result
                    
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": result_str
                })
                
            local_messages.append({"role": "user", "content": tool_results_content})
            continue
            
        else:
            # Got final answer from Claude
            text_response = ""
            for block in resp.content:
                if block.type == "text":
                    text_response += block.text
            
            # Sync the local messages back into the parent messages list
            new_msgs_count = len(local_messages) - len(messages)
            for idx in range(new_msgs_count):
                messages.append(local_messages[len(messages)])
                
            messages.append({"role": "assistant", "content": text_response})
            return text_response
            
    return "Error: Exceeded max loop cycles executing tools."
