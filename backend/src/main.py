"""Builds the app. Wiring only — no logic lives here."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import chat, sessions

app = FastAPI(title="LLM Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    # Browsers hide non-standard response headers on cross-origin requests
    # unless they're listed here; the frontend reads this on a 429.
    expose_headers=["Retry-After"],
)

app.include_router(sessions.router)
app.include_router(chat.router)