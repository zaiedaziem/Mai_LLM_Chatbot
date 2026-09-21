"""Every environment variable the app reads, in one place.

Nothing else calls os.getenv. Need a new setting? Add it here.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # finds backend/.env by walking up from this file

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

# Only the LLM endpoint is rate-limited (it's the one that costs money).
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "3"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Relative to this file, NOT the working directory, so it works no matter
# where uvicorn is launched from.
SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"

TITLE_MAX_LEN = 50