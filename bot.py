import os
import uuid
import random
import time
from datetime import datetime

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

from db import (init_db, get_passport, create_passport, update_passport)


def run_bot():
    TOKEN = os.getenv("VK_TOKEN")
    PRESIDENT_RAW = os.getenv("PRESIDENT_ID", "1094812154")
    GROUP_RAW = os.getenv("GROUP_ID", "dollania")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")

    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()

    def resolve(name):
        try:
            r = vk.utils.resolveScreenName(screen_name=name)
            if r and r.get("object_id"):
                return int(r["object_id"])
        except Exception as e:
            print(f"Ошибка resolve: {e}")
        return None

    PRESIDENT_ID = (int(PRESIDENT_RAW) if str(PRESIDENT_RAW).isdigit()
                    else resolve(PRESIDENT_RAW))
    GROUP_ID = (int(GROUP_RAW) if str(GROUP_RAW).isdigit()
                else resolve(GROUP_RAW))
    print(f"Бот: Президент={PRESIDENT_ID}, Группа={GROUP_ID}")

    states = {}

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

    def get_admins():
        ids = set()
        allowed = {"administrator", "creator", "moderator"}
        try:
            managers = vk.groups.getMembers(
                group_id=GROUP_ID, filter="managers"
            )["items"]
            for m in managers:
                if isinstance(m, dict):
                    if m.get("role") in allowed:
                        ids.add(int(m["id"]))
                else:
                    ids.add(int(m))
        except Exception as e:
            print(f"Ошибка админов: {e}")
        return list(ids)

    def main_kb():
        kb = VkKeyboard(one_time=False)
        kb.add_button("Паспорт", color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button("Написать Президенту", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("Написать администраторам", color=VkKeyboardColor.SECONDARY)
        return kb

    def passport_kb(has):
        kb = VkKeyboard(one_time=False)
        if has:
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

    def back_kb():
        kb = VkKeyboard(one_time=False)
        kb.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
        return kb

    def format_passport(p):
        url = f"{BASE_URL}/passport/{p['citizen_uuid']}"
        return (
            f"Паспорт\n\n"
            f"ФИО: {p['full_name']}\n"
            f"Дата рождения: {p['birth_date']}\n"
            f"UUID: {p['citizen_uuid']}\n"
            f"Дата выдачи: {p['issue_date']}\n\n"
            f"Открыть паспорт на сайте:\n{url}"
        )

    def handle(event):
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
                 main_kb())
            return

        if text in ("Меню", "меню"):
            states.pop(uid, None)
            send(peer_id, "Главное меню:", main_kb())
            return

        if text == "Паспорт":
            if p:
                send(peer_id, format_passport(p), passport_kb(True))
            else:
                send(peer_id,
                     "Раздел «Паспорт».\n\n"
                     "У вас нет паспорта. Нажмите «Зарегистрировать».",
                     passport_kb(False))
            return

        if text in ("Зарегистрировать", "Получить"):
            if p:
                send(peer_id, "У вас уже есть паспорт.", passport_kb(True))
                return
            states[uid] = {"mode": "create", "field": "full_name", "data": {}}
            send(peer_id, "Введите ваше ФИО:", back_kb())
            return

        if text == "Изменить ФИО":
            if not p:
                send(peer_id, "Сначала зарегистрируйтесь.", passport_kb(False))
                return
            states[uid] = {"mode": "edit", "field": "full_name"}
            send(peer_id, "Введите новое ФИО:", back_kb())
            return

        if text == "Изменить дату рождения":
            if not p:
                send(peer_id, "Сначала зарегистрируйтесь.", passport_kb(False))
                return
            states[uid] = {"mode": "edit", "field": "birth_date"}
            send(peer_id, "Введите новую дату рождения (ДД.ММ.ГГГГ):", back_kb())
            return

        if text in ("Написать Президенту", "Сообщить Президенту"):
            if uid == PRESIDENT_ID:
                states.pop(uid, None)
                send(peer_id,
                     "Вы — Президент.\n\n"
                     "Вы не можете отправить сообщение самому себе.",
                     main_kb())
                return
            states[uid] = {"mode": "president"}
            send(peer_id,
                 "Введите ваше сообщение Президенту.\n\nРазрешён только текст.",
                 back_kb())
            return

        if text == "Написать администраторам":
            states[uid] = {"mode": "admins"}
            send(peer_id,
                 "Введите ваше сообщение администраторам.\n\n"
                 "Разрешён только текст.",
                 back_kb())
            return

        if text == "Назад":
            states.pop(uid, None)
            send(peer_id, "Главное меню:", main_kb())
            return

        st = states.get(uid)
        if not st:
            return

        # --- president ---
        if st["mode"] == "president":
            if uid == PRESIDENT_ID:
                states.pop(uid, None)
                send(peer_id, "Вы — Президент. Сообщение не отправлено.",
                     main_kb())
                return
            if event.attachments:
                send(peer_id, "Можно отправить только текст. Напишите заново:",
                     back_kb())
                return
            if not text:
                send(peer_id, "Сообщение пустое. Напишите текст:", back_kb())
                return
            states.pop(uid, None)

            if p:
                info = (f"Гражданин\nФИО: {p['full_name']}\n"
                        f"Страница: [vk.com/id{uid}|{p['full_name']}]\n"
                        f"UUID: {p['citizen_uuid']}\n"
                        f"Дата рождения: {p['birth_date']}")
            else:
                info = (f"Гражданин\nФИО: —\n"
                        f"Страница: [vk.com/id{uid}|Страница]\n"
                        f"UUID: —\nДата рождения: —")

            msg = f"Новое сообщение от гражданина\n\n{info}\n\nСообщение\n{text}"
            try:
                vk.messages.send(peer_id=PRESIDENT_ID, message=msg,
                                 random_id=random.randint(0, 2**31))
                print(f"Президенту отправлено от {uid}")
            except Exception as e:
                print(f"Ошибка Президенту: {e}")
                send(peer_id, "Не удалось доставить.", main_kb())
                return
            send(peer_id,
                 "Ваше сообщение отправлено Президенту.\n\n"
                 "Ответ придёт в это сообщение.",
                 main_kb())
            return

        # --- admins ---
        if st["mode"] == "admins":
            if event.attachments:
                send(peer_id, "Можно отправить только текст. Напишите заново:",
                     back_kb())
                return
            if not text:
                send(peer_id, "Сообщение пустое. Напишите текст:", back_kb())
                return
            states.pop(uid, None)

            if p:
                info = (f"Отправитель\nФИО: {p['full_name']}\n"
                        f"Страница: [vk.com/id{uid}|{p['full_name']}]\n"
                        f"UUID: {p['citizen_uuid']}\n"
                        f"Дата рождения: {p['birth_date']}")
            else:
                info = (f"Отправитель\nФИО: —\n"
                        f"Страница: [vk.com/id{uid}|Страница]\n"
                        f"UUID: —\nДата рождения: —")

            msg = f"Новое сообщение администраторам\n\n{info}\n\nСообщение\n{text}"
            admin_ids = get_admins()
            print(f"Админы: {admin_ids}")
            delivered = 0
            for aid in admin_ids:
                if aid == uid:
                    continue
                try:
                    vk.messages.send(peer_id=aid, message=msg,
                                     random_id=random.randint(0, 2**31))
                    delivered += 1
                except Exception as e:
                    print(f"Ошибка {aid}: {e}")

            if delivered == 0:
                send(peer_id, "Не удалось доставить ни одному администратору.",
                     main_kb())
                return
            send(peer_id,
                 f"Ваше сообщение отправлено администраторам "
                 f"({delivered} получателей).\n\nОтвет придёт в это сообщение.",
                 main_kb())
            return

        # --- edit ---
        if st["mode"] == "edit":
            field = st["field"]
            if field == "birth_date":
                try:
                    datetime.strptime(text, "%d.%m.%Y")
                except ValueError:
                    send(peer_id, "Неверный формат. Введите ДД.ММ.ГГГГ:",
                         back_kb())
                    return
            if field == "full_name" and len(text) < 3:
                send(peer_id, "Слишком короткое ФИО. Введите ещё раз:",
                     back_kb())
                return
            update_passport(uid, field, text)
            states.pop(uid, None)
            p_new = get_passport(uid)
            send(peer_id, "Обновлено.\n\n" + format_passport(p_new),
                 passport_kb(True))
            return

        # --- create ---
        if st["mode"] == "create":
            if get_passport(uid):
                states.pop(uid, None)
                send(peer_id, "Вы уже зарегистрированы.", passport_kb(True))
                return
            field = st["field"]
            if field == "full_name":
                if len(text) < 3:
                    send(peer_id, "Слишком короткое ФИО. Введите ещё раз:",
                         back_kb())
                    return
                st["data"]["full_name"] = text
                st["field"] = "birth_date"
                send(peer_id, "Введите дату рождения (ДД.ММ.ГГГГ):", back_kb())
                return
            if field == "birth_date":
                try:
                    datetime.strptime(text, "%d.%m.%Y")
                except ValueError:
                    send(peer_id, "Неверный формат. Введите ДД.ММ.ГГГГ:",
                         back_kb())
                    return
                st["data"]["birth_date"] = text
                citizen_uuid = str(uuid.uuid4())
                issue_date = datetime.now().strftime("%d.%m.%Y")
                try:
                    create_passport(uid, citizen_uuid, issue_date,
                                    st["data"]["full_name"],
                                    st["data"]["birth_date"])
                except Exception as e:
                    print(f"Ошибка создания: {e}")
                    send(peer_id, "Ошибка регистрации.", main_kb())
                    return
                states.pop(uid, None)
                p_new = get_passport(uid)
                send(peer_id, "Паспорт выдан!\n\n" + format_passport(p_new),
                     passport_kb(True))
                return

    # ----- Главный цикл -----
    print("Бот запущен (фоновый поток)")
    while True:
        try:
            longpoll = VkLongPoll(vk_session, wait=15)
            print("Long Poll переподключён")
            for event in longpoll.listen():
                if event.type != VkEventType.MESSAGE_NEW:
                    continue

                # Принимаем сообщения только в ЛС (не в беседах)
                # peer_id == user_id — это ЛС сообщества
                if event.peer_id != event.user_id:
                    continue

                print(f"СОБЫТИЕ: type={event.type}, user_id={event.user_id}, "
                      f"peer_id={event.peer_id}, text={event.text!r}")

                try:
                    handle(event)
                except Exception as e:
                    print(f"Ошибка обработки: {e}")
                    import traceback
                    traceback.print_exc()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Обрыв ({type(e).__name__}). Переподключение через 5 сек...")
            time.sleep(5)
            continue