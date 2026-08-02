"""Start the Oryntra AI Alpaca-ready API."""
import os
import sys

import uvicorn

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    configured = all(
        os.getenv(name, "").strip()
        for name in (
            "ALPACA_OAUTH_CLIENT_ID",
            "ALPACA_OAUTH_CLIENT_SECRET",
            "ALPACA_OAUTH_REDIRECT_URI",
            "ORYNTRA_TOKEN_ENCRYPTION_KEY",
        )
    )
    private = env_bool("ORYNTRA_PRIVATE_RESEARCH_ROUTES", False)
    print(
        f"""
╔══════════════════════════════════════════════════╗
║          O R Y N T R A  A I  v0.7.0             ║
║           Alpaca Connect API                     ║
╠══════════════════════════════════════════════════╣
║  API        →  http://localhost:{port:<5}              ║
║  Health     →  http://localhost:{port}/health       ║
║  Alpaca     →  {'configured' if configured else 'credentials required':<27}║
║  Public UI  →  {'private research enabled' if private else 'scanner disabled':<27}║
╚══════════════════════════════════════════════════╝
"""
    )
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=env_bool("ORYNTRA_RELOAD", False),
        reload_dirs=["backend"] if env_bool("ORYNTRA_RELOAD", False) else None,
        log_level=os.getenv("ORYNTRA_LOG_LEVEL", "info"),
    )
