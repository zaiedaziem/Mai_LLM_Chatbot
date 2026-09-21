"""Everything endpoints request via Depends().

Built lazily + cached: the module imports without credentials, and the test
suite swaps these for fakes through app.dependency_overrides.
"""
from functools import lru_cache

from supabase import Client, create_client

from . import config
from .llm import GroqProvider, LLMProvider


@lru_cache
def get_db() -> Client:
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


@lru_cache
def get_llm() -> LLMProvider:
    # The ONE line that decides which provider the app uses.
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY must be set")
    return GroqProvider(api_key=config.GROQ_API_KEY, model=config.GROQ_MODEL)


@lru_cache
def get_system_prompt() -> str | None:
    if not config.SYSTEM_PROMPT_PATH.exists():
        return None
    return config.SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip() or None