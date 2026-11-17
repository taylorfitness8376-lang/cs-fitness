import bcrypt
import hashlib
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ENV_FILE = os.path.join(ROOT_DIR, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE, "r", encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# Change this password before deploying (or set ADMIN_PASSWORD env var)
_RAW_PASSWORD = os.environ.get("ADMIN_PASSWORD", "csfit2024")
PASSWORD_HASH = bcrypt.hashpw(_RAW_PASSWORD.encode(), bcrypt.gensalt())

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    hashlib.sha256(f"cs-fitness-persistent-key-{_RAW_PASSWORD}".encode("utf-8")).hexdigest(),
)
PORT = int(os.environ.get("PORT", 9090))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(ROOT_DIR, "data"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(DATA_DIR, "gym.db"))
