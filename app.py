import os
import threading
from flask import Flask, render_template, abort, send_from_directory
from dotenv import load_dotenv

load_dotenv()

from db import init_db, get_passport_by_uuid
from bot import run_bot

app = Flask(__name__)


# ---------- Основные страницы ----------
@app.route("/")
def index():
	return render_template("index.html")


@app.route("/history")
def history_page():
	return render_template("history.html")


@app.route("/symbols")
def symbols_page():
	return render_template("symbols.html")


@app.route("/links")
def links_page():
	return render_template("links.html")


# ---------- Паспорт ----------
@app.route("/passport")
def passport_info():
	return render_template("passport_info.html")


@app.route("/passport/<uuid_str>")
def passport_page(uuid_str):
	p = get_passport_by_uuid(uuid_str)
	if not p:
		abort(404)
	return render_template("passport.html", p=p)


# ---------- Служебные ----------
@app.route("/health")
def health():
	return "OK", 200


@app.route("/favicon.ico")
def favicon():
	return send_from_directory("static", "favicon.ico")


# ---------- Обработка 404 ----------
@app.errorhandler(404)
def not_found(e):
	return render_template("404.html"), 404


# ---------- Инициализация ----------
init_db()

# Бот в фоновом потоке
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()


if __name__ == "__main__":
	port = int(os.getenv("PORT", 8080))
	app.run(host="0.0.0.0", port=port)