import os
import threading
from flask import Flask, render_template, abort, send_from_directory
from dotenv import load_dotenv

load_dotenv()

from db import init_db, get_passport_by_uuid
from bot import run_bot

app = Flask(__name__)


# ---------- Сайт ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/test.html")
def test_page():
    return render_template("test.html")


@app.route("/health")
def health():
    return "OK", 200


@app.route("/passport/<uuid_str>")
def passport_page(uuid_str):
    p = get_passport_by_uuid(uuid_str)
    if not p:
        abort(404)
    return render_template("passport.html", p=p)

@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.ico")

# ---------- Инициализация и запуск ----------
init_db()

# Бот в фоновом потоке
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)