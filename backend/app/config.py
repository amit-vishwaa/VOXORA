"""Configuration helpers (no third-party dependency: tiny .env loader)."""
import os
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_INSTANCE = BACKEND_DIR / "instance"
FRONTEND_DIR = PROJECT_DIR / "frontend"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"

INDUSTRIES = ["real_estate", "healthcare", "education", "sales", "support", "other"]
LANGUAGES = {"en": "English", "hi": "Hindi", "gu": "Gujarati"}
VOICES = {
    "en": ["en-female-1", "en-male-1"],
    "hi": ["hi-female-1", "hi-male-1"],
    "gu": ["gu-female-1", "gu-male-1"],
}


def load_dotenv():
    """Load KEY=VALUE lines from <project>/.env without overriding real env vars."""
    path = PROJECT_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_secret(instance_dir: Path) -> str:
    """Secret key from env, otherwise generated once and stored in instance/ (never in git)."""
    env = os.environ.get("VOXORA_SECRET_KEY")
    if env:
        return env
    f = instance_dir / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()
