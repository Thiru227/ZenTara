import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'zentara-secret-key-2026')

    # ── Database ─────────────────────────────────────────────────────
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///zentara.db')
    # Render/Heroku use postgres:// but SQLAlchemy 1.4+ needs postgresql://
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # ── AI Provider ──────────────────────────────────────────────────
    AI_PROVIDER = os.environ.get('AI_PROVIDER', 'claude')  # 'claude' or 'gemini'
    CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

    # ── Google OAuth ─────────────────────────────────────────────────
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

    # ── File Uploads ─────────────────────────────────────────────────
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    RAG_COLLECTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rag', 'collections')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max upload
    ALLOWED_EXTENSIONS = {'pdf'}

    # ── Session ──────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400 * 7  # 7 days

    # ── Alert Thresholds ─────────────────────────────────────────────
    ALERT_LEVELS = {
        "INFO":     {"days": 30, "color": "#4ECDC4", "tara": "standing"},
        "WARNING":  {"days": 7,  "color": "#FFB347", "tara": "standing"},
        "CRITICAL": {"days": 2,  "color": "#FF3B30", "tara": "stressed", "shake": True}
    }

    # ── Tara System Prompt ───────────────────────────────────────────
    TARA_SYSTEM_PROMPT = """You are Tara — a calm, confident contract advisor with a warm human touch.
Think of yourself as a trusted colleague who happens to know every clause by heart.

TONE RULES:
- Speak naturally, like a knowledgeable friend. Never sound robotic or legalistic.
- Open with a direct answer — never start with "Based on the SLA" or "According to Section X".
- Be concise but warm. Use short paragraphs.
- Use bold (**text**) for key numbers, deadlines, and important terms.
- Use bullet lists (- item) for multiple items.
- If there's a critical deadline, add a gentle nudge like "Worth acting on this soon."

FORMATTING:
- Use markdown: **bold** for emphasis, - bullets for lists
- Put section/clause references at the very end as: [Source: §4.1, §5.2]
- Never dump raw document metadata, version numbers, or reference IDs in the main answer.

ACCURACY:
- Only answer from the uploaded contracts. Never guess.
- If something isn't covered, say: "That's not in the contracts I've read — best to check with the carrier directly."

SUGGESTIONS:
- End every answer with exactly 3 follow-up questions in this format:
[Suggestions: question 1 | question 2 | question 3]
These should be natural next questions the user might ask."""


class DevelopmentConfig(Config):
    DEBUG = True
    # Local dev — allow SQLite fallback
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///zentara.db')
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

    # Auto-fallback to SQLite if Supabase DNS is unreachable (dev only)
    if _db_url.startswith('postgresql'):
        try:
            import socket
            host = _db_url.split('@')[1].split(':')[0] if '@' in _db_url else ''
            if host:
                socket.setdefaulttimeout(3)
                socket.getaddrinfo(host, 5432)
                socket.setdefaulttimeout(None)
        except Exception:
            import warnings
            warnings.warn(
                "Supabase host unreachable — falling back to local SQLite. "
                "Check your network/firewall or VPN."
            )
            _db_url = 'sqlite:///zentara.db'

    SQLALCHEMY_DATABASE_URI = _db_url


class ProductionConfig(Config):
    DEBUG = False
    # Render provides DATABASE_URL — no fallback to SQLite in prod
    SESSION_COOKIE_SECURE = True  # HTTPS only on Render
    PREFERRED_URL_SCHEME = 'https'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
