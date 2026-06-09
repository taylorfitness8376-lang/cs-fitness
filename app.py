from flask import Flask
from database import init_app
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["DATABASE_PATH"] = config.DATABASE_PATH

init_app(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
