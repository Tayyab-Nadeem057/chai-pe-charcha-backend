import os


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing."""


def _require(key: str) -> str:
    """Return an env var or fail fast. Secrets must never have code defaults."""
    val = os.environ.get(key)
    if not val or not val.strip():
        raise ConfigError(
            f"Missing required environment variable: {key}. "
            f"Set it in your environment (.env locally, dashboard on Render). "
            f"Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return val.strip()


def _normalize_db_url(url: str) -> str:
    # Render/Heroku hand out 'postgres://' which SQLAlchemy 1.4+ rejects.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _origins() -> list[str]:
    raw = os.environ.get("FRONTEND_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]


class Config:
    # ── Secrets (REQUIRED — no fallback) ──────────────────────────
    SECRET_KEY = _require("SECRET_KEY")
    JWT_SECRET_KEY = _require("JWT_SECRET_KEY")

    # ── Database ──────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get("DATABASE_URL", "sqlite:///chai_pe_charcha.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # ── JWT — Authorization: Bearer header ────────────────────────
    # The frontend (GitHub Pages) and backend (Render) are on different domains,
    # so cross-site cookies are blocked by mobile browsers. We use a Bearer token
    # instead, which works everywhere. XSS is mitigated by escaping all output.
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_ACCESS_TOKEN_EXPIRES = 60 * 60 * 12  # 12 hours

    # ── CORS ──────────────────────────────────────────────────────
    # Exact frontend origin(s) only. Comma-separated in FRONTEND_ORIGINS.
    FRONTEND_ORIGINS = _origins()

    # ── Uploads ───────────────────────────────────────────────────
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"),
    )
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024  # 6 MB max request body
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

    # ── Rate limiting ─────────────────────────────────────────────
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
