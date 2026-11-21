"""Настройки на услугата на асистента. Четат се от .env в главната папка."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Общ таен ключ с Django. Ако е празен, услугата отказва всички заявки.
ASSISTANT_TOKEN = os.getenv("ASSISTANT_TOKEN", "")

# Ключовете за езиковите модели стоят САМО тук – Django не ги знае.
# Тестовият модел (без интернет) – само за автоматичните тестове.
ALLOW_FAKE = os.getenv("ASSISTANT_ALLOW_FAKE", "").lower() in ("1", "true", "yes")

LLM_API_KEYS = {
    "openai": os.getenv("OPENAI_API_KEY", ""),
    "gemini": os.getenv("GEMINI_API_KEY", ""),
    "claude": os.getenv("ANTHROPIC_API_KEY", ""),
}
