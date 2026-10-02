import os
import threading

from flask import (
    Flask,
    render_template,
    abort,
    send_from_directory,
)

from dotenv import load_dotenv


# ============================================================
# ENV
# ============================================================

load_dotenv()


# ============================================================
# IMPORTS
# ============================================================

from db import (
    init_db,
    get_passport_by_uuid,
)

from bot import run_bot


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# ОСНОВНЫЕ СТРАНИЦЫ
# ============================================================

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


# ============================================================
# ПАСПОРТ
# ============================================================

@app.route("/passport")
def passport_info():
    return render_template("passport_info.html")


@app.route("/passport/<uuid_str>")
def passport_page(uuid_str):

    p = get_passport_by_uuid(
        uuid_str
    )

    if not p:
        abort(404)

    return render_template(
        "passport.html",
        p=p
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():
    return "OK", 200


# ============================================================
# FAVICON
# ============================================================

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        "static",
        "favicon.ico"
    )


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def not_found(e):
    return render_template(
        "404.html"
    ), 404


# ============================================================
# ЗАПУСК БОТА
# ============================================================

def start_bot():

    print("[APP] Запуск VK-бота...")

    bot_thread = threading.Thread(
        target=run_bot,
        name="VK-Bot",
        daemon=True,
    )

    bot_thread.start()

    print(
        f"[APP] VK-бот запущен. "
        f"Thread={bot_thread.name}"
    )

    return bot_thread


# ============================================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # База данных
    # --------------------------------------------------------

    print("[APP] Инициализация базы данных...")

    init_db()

    print(
        "[APP] База данных готова."
    )

    # --------------------------------------------------------
    # Запускаем бота ОДИН раз
    # --------------------------------------------------------

    start_bot()

    # --------------------------------------------------------
    # Flask
    # --------------------------------------------------------

    port = int(
        os.getenv(
            "PORT",
            "8080"
        )
    )

    print(
        f"[APP] Flask запускается "
        f"на порту {port}"
    )

    app.run(
        host="0.0.0.0",
        port=port,

        # КРИТИЧЕСКИ ВАЖНО:
        # Flask не должен создавать второй процесс,
        # иначе VK-бот запустится дважды.
        debug=False,
        use_reloader=False,
    )