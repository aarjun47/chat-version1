import requests
import os
import re
import json
import dateparser
from datetime import datetime
import locale
from dotenv import load_dotenv

from .crud import get_recent_messages

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DEFAULT_PROMPT_PATH = "app/prompts/system_prompt.txt"

# Fallback chain — tries each model in order until one works
MODELS = [
    "meta-llama/llama-3.1-8b-instruct:free",
    "minimax/minimax-m2.5:free",
    "arcee-ai/trinity-large-preview:free",
]

try:
    locale.setlocale(locale.LC_TIME, locale.getdefaultlocale())
except:
    pass


def load_default_system_prompt():
    with open(DEFAULT_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def call_openrouter(messages, temperature=0.7, max_tokens=300, response_format=None):
    """
    Tries each model in MODELS list in order.
    Returns the first successful response.
    Raises the last exception if all models fail.
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    last_exception = None

    for model in MODELS:
        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if response_format:
                payload["response_format"] = response_format

            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            if content:
                return content.strip()
        except Exception as e:
            print(f"Model {model} failed: {e}")
            last_exception = e
            continue

    raise last_exception


# ---------------------------------------
# MEMORY AWARE CHAT ASSISTANT
# ---------------------------------------
async def ask_llm(user_text: str, lead=None, greeting_type="NONE", client=None):
    if client and client.get("system_prompt"):
        system_prompt = client["system_prompt"]
    else:
        system_prompt = load_default_system_prompt()

    if client and client.get("persona_name"):
        system_prompt = system_prompt.replace("Arun", client["persona_name"])

    memory_context = f"Greeting type: {greeting_type}\n"

    if lead and lead.get("name"):
        memory_context += f"Known user name: {lead['name']}\n"
    else:
        memory_context += "Known user name: Unknown\n"

    if lead:
        memory_context += f"Current interest: {lead.get('service_interest') or 'None'}\n"

    if lead:
        chats = await get_recent_messages(lead["id"], limit=6)
        if chats:
            memory_context += "\nRecent conversation:\n"
            for c in reversed(chats):
                role = "User" if c["direction"] == "inbound" else "Assistant"
                memory_context += f"{role}: {c['text']}\n"

    full_system_content = f"{system_prompt}\n\n[CONTEXT]\n{memory_context.strip()}"

    messages = [
        {"role": "system", "content": full_system_content},
        {"role": "user", "content": user_text}
    ]

    try:
        return call_openrouter(messages)
    except Exception:
        return "I'm sorry, I'm having trouble connecting right now."


# -------- NAME EXTRACTION --------
def extract_name_with_two_layers(user_text: str):
    extraction_prompt = f"""
Extract ONLY the full name from the text.
Return JSON: {{ "name": "value" }}
If no name found, return {{ "name": "N/A" }}

Text: "{user_text}"
"""
    try:
        raw_output = call_openrouter(
            [{"role": "user", "content": extraction_prompt}],
            temperature=0.0,
            max_tokens=60,
            response_format={"type": "json_object"}
        )
        data = json.loads(raw_output)
        name = data.get("name", "N/A")
        if name and name != "N/A":
            return name.strip().title()
    except:
        pass

    patterns = [
        r"(?:my name is|i am|i'm|this is|it's)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)"
    ]
    for pattern in patterns:
        match = re.search(pattern, user_text, re.IGNORECASE)
        if match:
            return match.group(1).title()

    return None


# -------- INTEREST EXTRACTION --------
def extract_service_interest(user_text: str):
    prompt = f"""
Identify ONLY program interest:
CA, ACCA, CMA, CS, CPA
Return NONE if unclear.

Message: "{user_text}"
"""
    try:
        res = call_openrouter(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=20
        )
        service = res.strip().upper()
        if service in ["CA", "ACCA", "CMA", "CS", "CPA"]:
            return service
    except:
        pass
    return None


# -------- APPOINTMENT ----------
def process_appointment_request(user_text: str, current_lead_state: str = "normal"):
    prompt = f"""
Return JSON:
{{"intent":"schedule_appointment|confirm_appointment|none","time_info":string|null}}

State: {current_lead_state}
Message: {user_text}
"""
    try:
        response = call_openrouter(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        return json.loads(response)
    except:
        return {"intent": "none", "time_info": None}


def parse_and_format_time_info(time_info_str: str):
    if not time_info_str:
        return "the requested time"
    parsed = dateparser.parse(
        time_info_str,
        settings={
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": datetime.now()
        }
    )
    if parsed:
        return parsed.strftime("%A, %B %d, %Y at %I:%M %p")
    return time_info_str