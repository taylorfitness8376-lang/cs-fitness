import bcrypt
import os
import secrets

# Change this password before deploying (or set ADMIN_PASSWORD env var)
_RAW_PASSWORD = os.environ.get("ADMIN_PASSWORD", "csfit2024")
PASSWORD_HASH = bcrypt.hashpw(_RAW_PASSWORD.encode(), bcrypt.gensalt())

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
PORT = int(os.environ.get("PORT", 9090))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(DATA_DIR, "gym.db"))
