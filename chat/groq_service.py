import os
import requests
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
AI_USERNAME = "assistant"

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Tu es un assistant IA intégré dans une application de chat. "
        "Tu t'appelles Assistant. Tu réponds en français de façon naturelle et concise. "
        "Tu es poli, serviable et tu utilises le tutoiement. "
        "Tu peux aider avec des questions générales, du code, des explications, etc."
    )
}

def get_groq_api_key() -> str | None:
    return os.getenv("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", None)

def call_groq(messages: list[dict], model: str = "llama-3.3-70b-versatile") -> str | None:
    api_key = get_groq_api_key()
    if not api_key:
        logger.error("GROQ_API_KEY not configured")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [SYSTEM_PROMPT, *messages],
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.exception("Groq API call failed: %s", e)
        return None
