import os
import uuid
import random
import time
from datetime import datetime

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from dotenv import load_dotenv
import requests

# ---------- Токен ----------
load_dotenv()
TOKEN = os.getenv("VK_TOKEN")
if not TOKEN:
    raise RuntimeError("Не найден VK_TOKEN. Создайте .env")

TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN")
if not TURSO_URL or not TURSO_TOKEN:
    raise RuntimeError("Не найдены TURSO_DATABASE_URL / TURSO_AUTH_TOKEN")

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()


# ---------- Turso HTTP API ----------
_TURSO_HTTP = TURSO_URL.replace("libsql://", "https://").rstrip("/")
_TURSO_HEADERS = {
    "Authorization": f"Bearer {TURSO_TOKEN}",
    "Content-Type": "application/json",
}


def _to_arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": str(v)}
    return {"type": "text", "value": str(v)}


def _unwrap(cell):
    if isinstance(cell, dict):
        return cell.get("value")
    return cell


def db_execute(sql, args=None):
    stmt = {"sql": sql}
    if args:
        stmt["args"] = [_to_arg(a) for a in args]

    body = {"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]}
    try:
        r = requests.post(
            f"{_TURSO_HTTP}/v2/pipeline",
            headers=_TURSO_HEADERS,
            json=body,
            timeout=30,
        )
        if r.status_code != 200:
            print(f"Ошибка HTTP БД: {r.status_code} {r.text[:200]}")
            return None

        data = r.json()
        first = data.get("results", [{}])[0]
        if first.get("type") == "error":
            print(f"Ошибка SQL: {first}")
            return None

        response = first.get("response", {}).get("result", {})
        return {
            "rows": response.get("rows", []),
            "cols": [c.get("name") for c in response.get("cols", [])],
        }
    except Exception as e:
        print(f"Ошибка БД: {e}")
        return None


def init_db():
    print("init_db: создаю таблицу...")
    r = db_execute("""
        CREATE TABLE IF NOT EXISTS citizens (
            user_id      INTEGER PRIMARY KEY,
            citizen_uuid TEXT UNIQUE NOT NULL,
            issue_date   TEXT NOT NULL,
            full_name    TEXT,
            birth_date   TEXT
        )
    """)
    print(f"init_db: {r}")


def get_passport(uid):
    r = db_execute(
        "SELECT user_id, citizen_uuid, issue_date, full_name, birth_date "
        "FROM citizens WHERE user_id = ?",
        [uid]
    )
    if not r or not r.get("rows"):
        return None
    row = r["rows"][0]
    return {
        "user_id": int(_unwrap(row[0])),
        "citizen_uuid": _unwrap(row[1]),
        "issue_date": _unwrap(row[2]),
        "full_name": _unwrap(row[3]),
        "birth_date": _unwrap(row[4]),
    }


def create_passport(uid, citizen_uuid, issue_date, full_name, birth_date):
    db_execute(
        "INSERT INTO citizens "
        "(user_id, citizen_uuid, issue_date, full_name, birth_date) "
        "VALUES (?, ?, ?, ?, ?)",
        [uid, citizen_uuid, issue_date, full_name, birth_date]
    )


def update_passport(uid, field, value):
    if field not in ("full_name", "birth_date"):
        raise ValueError("Недопустимое поле")
    db_execute(
        f"UPDATE citizens SET {field} = ? WHERE user_id = ?",
        [value, uid]
    )


# ---------- Преобразование буквенного адреса в ID ----------
def resolve_screen_name(screen_name):
    try:
        r = vk.utils.resolveScreenName(screen_name=screen_name)
        if r and r.get("object_id"):
            return int(r["object_id"])
    except Exception as e:
        print(f"Ошибка resolveScreenName: {e}")
    return None


# ---------- ID Президента ----------
PRESIDENT_RAW = "1094812154"

if isinstance(PRESIDENT_RAW, int) or str(PRESIDENT_RAW).isdigit():
    PRESIDENT_ID = int(PRESIDENT_RAW)
else:
    PRESIDENT_ID = resolve_screen_name(PRESIDENT_RAW)
    if not PRESIDENT_ID:
        raise RuntimeError(f"Не удалось преобразовать '{PRESIDENT_RAW}' в ID")
    print(f"Президент: '{PRESIDENT_RAW}' -> ID {PRESIDENT_ID}")


# ---------- ID группы ----------
GROUP_RAW = "dollania"

if isinstance(GROUP_RAW, int) or str(GROUP_RAW).isdigit():
    GROUP_ID = int(GROUP_RAW)
else:
    GROUP_ID = resolve_screen_name(GROUP_RAW)
    if not GROUP_ID:
        raise RuntimeError(f"Не удалось преобразовать '{GROUP_RAW}' в ID")
    print(f"Группа: '{GROUP_RAW}' -> ID {GROUP_ID}")


states = {}


# ---------- Утилиты ----------
def send(peer_id, text, keyboard=None):
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=text or " ",
            keyboard=keyboard.get_keyboard() if keyboard else None,
            random_id=random.randint(0, 2**31)
        )
    except Exception as e:
        print(f"Ошибка отправки: {e}")


def get_admin_ids():
    ids = set()
    allowed_roles = {"administrator", "creator", "moderator"}
    try:
        managers = vk.groups.getMembers(
            group_id=GROUP_ID, filter="managers"
        )["items"]
        for m in managers:
            if isinstance(m, dict):
                if m.get("role") in allowed_roles:
                    ids.add(int(m["id"]))
            else:
                ids.add(int(m))
    except Exception as e:
        print(f"Ошибка получения админов: {e}")
    return list(ids)


# ---------- Клавиатуры ----------
def main_menu_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("Паспорт", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("Написать Президенту", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("Написать администраторам", color=VkKeyboardColor.SECONDARY)
    return kb


def passport_menu_keyboard(has_passport):
    kb = VkKeyboard(one_time=False)
    if has_passport:
        kb.add_button("Изменить ФИО", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("Изменить дату рождения", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    else:
        kb.add_button("Зарегистрировать", color=VkKeyboardColor.POSITIVE)
        kb.add_line()
        kb.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return kb


def back_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return kb


def format_passport(p):
    uid = p['user_id']
    return (
        f"Паспорт\n\n"
        f"ФИО: {p['full_name']}\n"
        f"Страница: [vk.com/id{uid}|{p['full_name']}]\n"
        f"Дата рождения: {p['birth_date']}\n"
        f"UUID: {p['citizen_uuid']}\n"
        f"Дата выдачи: {p['issue_date']}"
    )


# ---------- Обработка событий ----------
def handle_event(event):
    uid = event.user_id
    text = (event.text or "").strip()
    peer_id = event.peer_id
    print(f"Сообщение от {uid}: {text}")

    p = get_passport(uid)

    if text in ("/start", "Начать", "начать", "Start"):
        states.pop(uid, None)
        send(peer_id,
             "Добро пожаловать в бот виртуального государства Доллания!\n\n"
             "Здесь вы можете:\n"
             "— получить паспорт гражданина;\n"
             "— просмотреть и изменить данные паспорта;\n"
             "— написать сообщение Президенту или администраторам.\n\n"
             "Выберите действие в меню ниже.",
             main_menu_keyboard())
        return

    if text in ("Меню", "меню"):
        states.pop(uid, None)
        send(peer_id, "Главное меню:", main_menu_keyboard())
        return

    if text == "Паспорт":
        if p:
            send(peer_id, format_passport(p), passport_menu_keyboard(True))
        else:
            send(peer_id,
                 "Раздел «Паспорт».\n\n"
                 "У вас нет паспорта. Нажмите «Зарегистрировать».",
                 passport_menu_keyboard(False))
        return

    if text in ("Зарегистрировать", "Получить"):
        if p:
            send(peer_id, "У вас уже есть паспорт.",
                 passport_menu_keyboard(True))
            return
        states[uid] = {"mode": "create", "field": "full_name", "data": {}}
        send(peer_id, "Введите ваше ФИО:", back_keyboard())
        return

    if text == "Изменить ФИО":
        if not p:
            send(peer_id, "Сначала зарегистрируйтесь.",
                 passport_menu_keyboard(False))
            return
        states[uid] = {"mode": "edit", "field": "full_name"}
        send(peer_id, "Введите новое ФИО:", back_keyboard())
        return

    if text == "Изменить дату рождения":
        if not p:
            send(peer_id, "Сначала зарегистрируйтесь.",
                 passport_menu_keyboard(False))
            return
        states[uid] = {"mode": "edit", "field": "birth_date"}
        send(peer_id, "Введите новую дату рождения (ДД.ММ.ГГГГ):",
             back_keyboard())
        return

    if text in ("Написать Президенту", "Сообщить Президенту"):
        # Президент не может писать сам себе
        if uid == PRESIDENT_ID:
            states.pop(uid, None)
            send(peer_id,
                 "Вы — Президент.\n\n"
                 "Вы не можете отправить сообщение самому себе.\n",
                 main_menu_keyboard())
            return
        states[uid] = {"mode": "president"}
        send(peer_id,
             "Введите ваше сообщение Президенту.\n\n"
             "Разрешён только текст.",
             back_keyboard())
        return

    if text == "Написать администраторам":
        states[uid] = {"mode": "admins"}
        send(peer_id,
             "Введите ваше сообщение администраторам.\n\n"
             "Разрешён только текст.",
             back_keyboard())
        return

    if text == "Назад":
        states.pop(uid, None)
        send(peer_id, "Главное меню:", main_menu_keyboard())
        return

    st = states.get(uid)
    if not st:
        return

    # --- Сообщение Президенту ---
    if st["mode"] == "president":
        # Президент не может писать сам себе (двойная защита)
        if uid == PRESIDENT_ID:
            states.pop(uid, None)
            send(peer_id,
                 "Вы — Президент. Сообщение не отправлено.",
                 main_menu_keyboard())
            return

        if event.attachments:
            send(peer_id,
                 "Можно отправить только текст. Напишите заново:",
                 back_keyboard())
            return
        if not text:
            send(peer_id, "Сообщение пустое. Напишите текст:",
                 back_keyboard())
            return
        states.pop(uid, None)

        if p:
            sender_info = (
                f"Гражданин\n"
                f"ФИО: {p['full_name']}\n"
                f"Страница: [vk.com/id{uid}|{p['full_name']}]\n"
                f"UUID: {p['citizen_uuid']}\n"
                f"Дата рождения: {p['birth_date']}"
            )
        else:
            sender_info = (
                f"Гражданин\n"
                f"ФИО: —\n"
                f"Страница: [vk.com/id{uid}|Страница]\n"
                f"UUID: —\n"
                f"Дата рождения: —"
            )

        president_message = (
            f"Новое сообщение от гражданина\n\n"
            f"{sender_info}\n\n"
            f"Сообщение\n{text}"
        )

        try:
            vk.messages.send(
                peer_id=PRESIDENT_ID,
                message=president_message,
                random_id=random.randint(0, 2**31)
            )
            print(f"Президенту отправлено от {uid}")
        except Exception as e:
            print(f"Ошибка Президенту: {e}")
            send(peer_id, "Не удалось доставить.", main_menu_keyboard())
            return

        send(peer_id,
             "Ваше сообщение отправлено Президенту.\n\n"
             "Ответ придёт в это сообщение.",
             main_menu_keyboard())
        return

    # --- Сообщение администраторам ---
    if st["mode"] == "admins":
        if event.attachments:
            send(peer_id,
                 "Можно отправить только текст. Напишите заново:",
                 back_keyboard())
            return
        if not text:
            send(peer_id, "Сообщение пустое. Напишите текст:",
                 back_keyboard())
            return
        states.pop(uid, None)

        if p:
            sender_info = (
                f"Отправитель\n"
                f"ФИО: {p['full_name']}\n"
                f"Страница: [vk.com/id{uid}|{p['full_name']}]\n"
                f"UUID: {p['citizen_uuid']}\n"
                f"Дата рождения: {p['birth_date']}"
            )
        else:
            sender_info = (
                f"Отправитель\n"
                f"ФИО: —\n"
                f"Страница: [vk.com/id{uid}|Страница]\n"
                f"UUID: —\n"
                f"Дата рождения: —"
            )

        admin_message = (
            f"Новое сообщение администраторам\n\n"
            f"{sender_info}\n\n"
            f"Сообщение\n{text}"
        )

        admin_ids = get_admin_ids()
        print(f"Админы: {admin_ids}")
        delivered = 0
        for admin_id in admin_ids:
            if admin_id == uid:
                continue
            try:
                vk.messages.send(
                    peer_id=admin_id,
                    message=admin_message,
                    random_id=random.randint(0, 2**31)
                )
                delivered += 1
            except Exception as e:
                print(f"Ошибка {admin_id}: {e}")

        if delivered == 0:
            send(peer_id,
                 "Не удалось доставить ни одному администратору.",
                 main_menu_keyboard())
            return
        send(peer_id,
             f"Ваше сообщение отправлено администраторам "
             f"({delivered} получателей).\n\n"
             "Ответ придёт в это сообщение.",
             main_menu_keyboard())
        return

    # --- Редактирование ---
    if st["mode"] == "edit":
        field = st["field"]

        if field == "birth_date":
            try:
                datetime.strptime(text, "%d.%m.%Y")
            except ValueError:
                send(peer_id, "Неверный формат. Введите ДД.ММ.ГГГГ:",
                     back_keyboard())
                return

        if field == "full_name" and len(text) < 3:
            send(peer_id, "Слишком короткое ФИО. Введите ещё раз:",
                 back_keyboard())
            return

        update_passport(uid, field, text)
        states.pop(uid, None)

        p_new = get_passport(uid)
        send(peer_id, "Обновлено.\n\n" + format_passport(p_new),
             passport_menu_keyboard(True))
        return

    # --- Регистрация ---
    if st["mode"] == "create":
        if get_passport(uid):
            states.pop(uid, None)
            send(peer_id, "Вы уже зарегистрированы.",
                 passport_menu_keyboard(True))
            return

        field = st["field"]

        if field == "full_name":
            if len(text) < 3:
                send(peer_id, "Слишком короткое ФИО. Введите ещё раз:",
                     back_keyboard())
                return
            st["data"]["full_name"] = text
            st["field"] = "birth_date"
            send(peer_id, "Введите дату рождения (ДД.ММ.ГГГГ):",
                 back_keyboard())
            return

        if field == "birth_date":
            try:
                datetime.strptime(text, "%d.%m.%Y")
            except ValueError:
                send(peer_id, "Неверный формат. Введите ДД.ММ.ГГГГ:",
                     back_keyboard())
                return
            st["data"]["birth_date"] = text

            citizen_uuid = str(uuid.uuid4())
            issue_date = datetime.now().strftime("%d.%m.%Y")

            try:
                create_passport(
                    uid, citizen_uuid, issue_date,
                    st["data"]["full_name"], st["data"]["birth_date"]
                )
            except Exception as e:
                print(f"Ошибка создания: {e}")
                send(peer_id, "Ошибка регистрации.",
                     main_menu_keyboard())
                return

            states.pop(uid, None)
            p_new = get_passport(uid)
            send(peer_id,
                 "Паспорт выдан!\n\n" + format_passport(p_new),
                 passport_menu_keyboard(True))
            return


# ---------- Главный цикл ----------
init_db()
print("Бот запущен.")

while True:
    try:
        longpoll = VkLongPoll(vk_session, wait=15)
        print("Long Poll переподключён")
        for event in longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                print(f"Сообщение от {event.user_id}: {event.text!r}")
                try:
                    handle_event(event)
                except Exception as e:
                    print(f"Ошибка обработки: {e}")
                    import traceback
                    traceback.print_exc()
    except KeyboardInterrupt:
        print("\nОстановлено.")
        break
    except Exception as e:
        print(f"Обрыв ({type(e).__name__}). Переподключение через 5 сек...")
        time.sleep(5)
        continue