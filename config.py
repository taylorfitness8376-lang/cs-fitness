import bcrypt
import os
import secrets

# Change this password before deploying
_RAW_PASSWORD = "csfit2024"
PASSWORD_HASH = bcrypt.hashpw(_RAW_PASSWORD.encode(), bcrypt.gensalt())

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
PORT = int(os.environ.get("PORT", 9090))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "data", "gym.db")
