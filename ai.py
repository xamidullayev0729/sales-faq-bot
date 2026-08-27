"""
Google Gemini API bilan ishlash uchun yupqa (thin) wrapper.

REST orqali to'g'ridan-to'g'ri chaqiramiz (qo'shimcha og'ir SDK shart emas).
"""

import os
import requests

from knowledge import SYSTEM_INSTRUCTION, ESCALATE_MARKER

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
# Model nomi vaqt o'tishi bilan eskirishi mumkin — shuning uchun
# environment variable orqali osongina almashtirish mumkin.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def ask_ai(customer_message: str) -> str | None:
    """
    Gemini'ga mijoz xabarini yuboradi.

    Qaytaradi:
    - AI javobi (string) — agar savol bilim bazasi doirasida bo'lsa
    - None — agar AI "ESCALATE" deb topsa (ya'ni admin aralashuvi kerak)
    """
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": customer_message}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 300},
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

    response = requests.post(API_URL, json=payload, headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

    if ESCALATE_MARKER in text:
        return None
    return text
