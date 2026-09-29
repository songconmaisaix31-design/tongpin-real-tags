from __future__ import annotations

import os


DEVELOPMENT_SECRET_KEY = "dev-only-change-me"


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", DEVELOPMENT_SECRET_KEY)
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024
    DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"
    REAL_USER_ONLY = os.environ.get("REAL_USER_ONLY", "0") == "1"
    DATA_SOURCE_TIMEOUT_SECONDS = 4.0
    AI_FALLBACK_ENABLED = os.environ.get("AI_FALLBACK_ENABLED", "0") == "1"
    AI_FALLBACK_API_KEY = os.environ.get("AI_FALLBACK_API_KEY", "")
    AI_FALLBACK_OIDC_TOKEN = os.environ.get("VERCEL_OIDC_TOKEN", "")
    AI_FALLBACK_BASE_URL = os.environ.get("AI_FALLBACK_BASE_URL", "")
    AI_FALLBACK_MODEL = os.environ.get("AI_FALLBACK_MODEL", "")
    AI_FALLBACK_TIMEOUT_SECONDS = 8.0
    AI_FALLBACK_MAX_REPLIES = 30
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
