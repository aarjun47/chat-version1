import requests
import os
import re
import json

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
PROMPT_PATH = "app/prompts/system_prompt.txt"


def load_system_prompt():
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------
# 🔥 Core OpenRouter Caller (Reusable)
# ---------------------------------------
def call_openrouter(messages, temperature=0.7, max_tokens=120):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "arcee-ai/trinity-large-preview:free",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
    )

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


# ---------------------------------------
# 🤖 Chat Assistant
# ---------------------------------------
def ask_llm(user_text: str):
    system_prompt = load_system_prompt()

    return call_openrouter(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        temperature=0.7,
        max_tokens=120
    )


# ---------------------------------------
# 🔥 TWO-LAYER NAME EXTRACTION
# ---------------------------------------
def extract_name_with_two_layers(user_text: str):
    """
    Layer 1: LLM extraction
    Layer 2: Regex + heuristic fallback
    """

    # ---------- LAYER 1: LLM ----------
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
            max_tokens=60
        )

        json_match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            name = data.get("name", "N/A")
            if name and name != "N/A":
                return name.strip().title()

    except Exception as e:
        print("LLM name extraction error:", e)

    # ---------- LAYER 2: REGEX FALLBACK ----------
    patterns = [
        r"(?:my name is|i am|i'm|this is|it's)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)"
    ]

    for pattern in patterns:
        match = re.search(pattern, user_text, re.IGNORECASE)
        if match:
            return match.group(1).strip().title()

    # Heuristic fallback (WhatsApp style: "Arjun")
    possible_names = re.findall(r"\b[A-Z][a-z]{2,}\b", user_text)
    blacklist = {"Hi", "Hello", "Thanks", "Yes", "Okay", "Ok", "Sure"}

    for word in possible_names:
        if word not in blacklist:
            return word

    return None
