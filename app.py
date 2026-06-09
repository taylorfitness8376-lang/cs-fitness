from flask import (Flask, redirect, render_template, request,
                   session, url_for, jsonify)
import bcrypt
import os
from database import init_db, get_db, init_app
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["DATABASE_PATH"] = config.DATABASE_PATH

init_app(app)


def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authed"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    return redirect(url_for("cms"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "").encode()
        if bcrypt.checkpw(pw, config.PASSWORD_HASH):
            session["authed"] = True
            return redirect(url_for("cms"))
        error = "Incorrect password"
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/cms")
@require_auth
def cms():
    return render_template("cms.html")


@app.route("/display")
def display():
    return render_template("display.html")


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
