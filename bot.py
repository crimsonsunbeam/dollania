import os
import time
import uuid
from datetime import datetime

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

from db import (
    init_db,
    get_passport,
    create_passport,
    update_passport,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

TOKEN = os.getenv("VK_TOKEN")

PRESIDENT_RAW = os.getenv(
    "PRESIDENT_ID",
    "1094812154"
)

GROUP_RAW = os.getenv(
    "GROUP_ID",
    "dollania"
)

BASE_URL = os.getenv(
    "BASE_URL",
    "http://localhost:8080"
)


# ============================================================
# ЗАПУСК БОТА
# ============================================================

def run_bot():

    # --------------------------------------------------------
    # Проверка токена
    # --------------------------------------------------------

    if not TOKEN:
        raise RuntimeError(
            "Не задана переменная окружения VK_TOKEN"
        )

    # --------------------------------------------------------
    # Подключение VK
    # --------------------------------------------------------

    print("[VK] Подключение...")

    vk_session = vk_api.VkApi(
        token=TOKEN
    )

    vk = vk_session.get_api()

    # --------------------------------------------------------
    # Resolve screen name
    # --------------------------------------------------------

    def resolve(screen_name):

        try:

            result = vk.utils.resolveScreenName(
                screen_name=screen_name
            )

            if result and result.get("object_id"):

                return int(
                    result["object_id"]
                )

        except Exception as e:

            print(
                f"[RESOLVE] Ошибка: {e}"
            )

        return None

    # --------------------------------------------------------
    # PRESIDENT ID
    # --------------------------------------------------------

    if str(PRESIDENT_RAW).isdigit():

        PRESIDENT_ID = int(
            PRESIDENT_RAW
        )

    else:

        PRESIDENT_ID = resolve(
            PRESIDENT_RAW
        )

    # --------------------------------------------------------
    # GROUP ID
    # --------------------------------------------------------

    if str(GROUP_RAW).isdigit():

        GROUP_ID = int(
            GROUP_RAW
        )

    else:

        GROUP_ID = resolve(
            GROUP_RAW
        )

    if PRESIDENT_ID is None:

        raise RuntimeError(
            f"Не удалось определить "
            f"PRESIDENT_ID: {PRESIDENT_RAW}"
        )

    if GROUP_ID is None:

        raise RuntimeError(
            f"Не удалось определить "
            f"GROUP_ID: {GROUP_RAW}"
        )

    print(
        f"[START] Президент ID: {PRESIDENT_ID}"
    )

    print(
        f"[START] Группа ID: {GROUP_ID}"
    )

    # ========================================================
    # БАЗА ДАННЫХ
    # ========================================================

    try:

        init_db()

        print(
            "[DB] База данных инициализирована"
        )

    except Exception as e:

        print(
            f"[DB] Ошибка: {e}"
        )

        raise

    # ========================================================
    # СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ
    # ========================================================

    states = {}

    # ========================================================
    # ОБРАБОТАННЫЕ EVENT ID
    # ========================================================

    processed_events = set()

    # ========================================================
    # ОТПРАВКА СООБЩЕНИЯ
    # ========================================================

    def send(
        peer_id,
        text,
        keyboard=None
    ):

        try:

            params = {
                "peer_id": peer_id,
                "message": text or " ",
                "random_id": 0,
            }

            if keyboard is not None:

                params["keyboard"] = (
                    keyboard.get_keyboard()
                )

            vk.messages.send(
                **params
            )

            return True

        except Exception as e:

            print(
                f"[SEND] Ошибка отправки "
                f"peer_id={peer_id}: {e}"
            )

            return False

    # ========================================================
    # ПОЛУЧЕНИЕ АДМИНИСТРАТОРОВ
    # ========================================================

    def get_admins():

        ids = set()

        allowed_roles = {
            "administrator",
            "creator",
            "moderator",
        }

        try:

            result = vk.groups.getMembers(
                group_id=GROUP_ID,
                filter="managers"
            )

            managers = result.get(
                "items",
                []
            )

            for manager in managers:

                if isinstance(
                    manager,
                    dict
                ):

                    user_id = manager.get(
                        "id"
                    )

                    role = manager.get(
                        "role"
                    )

                    if (
                        user_id
                        and role in allowed_roles
                    ):

                        ids.add(
                            int(user_id)
                        )

                else:

                    ids.add(
                        int(manager)
                    )

        except Exception as e:

            print(
                f"[ADMINS] Ошибка: {e}"
            )

        return list(ids)

    # ========================================================
    # ГЛАВНАЯ КЛАВИАТУРА
    # ========================================================

    def main_kb():

        kb = VkKeyboard(
            one_time=False
        )

        kb.add_button(
            "Паспорт",
            color=VkKeyboardColor.PRIMARY
        )

        kb.add_line()

        kb.add_button(
            "Написать Президенту",
            color=VkKeyboardColor.SECONDARY
        )

        kb.add_line()

        kb.add_button(
            "Написать администраторам",
            color=VkKeyboardColor.SECONDARY
        )

        return kb

    # ========================================================
    # КЛАВИАТУРА ПАСПОРТА
    # ========================================================

    def passport_kb(has_passport):

        kb = VkKeyboard(
            one_time=False
        )

        if has_passport:

            kb.add_button(
                "Изменить ФИО",
                color=VkKeyboardColor.SECONDARY
            )

            kb.add_line()

            kb.add_button(
                "Изменить дату рождения",
                color=VkKeyboardColor.SECONDARY
            )

            kb.add_line()

            kb.add_button(
                "Назад",
                color=VkKeyboardColor.NEGATIVE
            )

        else:

            kb.add_button(
                "Зарегистрировать",
                color=VkKeyboardColor.POSITIVE
            )

            kb.add_line()

            kb.add_button(
                "Назад",
                color=VkKeyboardColor.NEGATIVE
            )

        return kb

    # ========================================================
    # КНОПКА НАЗАД
    # ========================================================

    def back_kb():

        kb = VkKeyboard(
            one_time=False
        )

        kb.add_button(
            "Назад",
            color=VkKeyboardColor.NEGATIVE
        )

        return kb

    # ========================================================
    # НЕИЗВЕСТНАЯ КОМАНДА
    # ========================================================

    def unknown_kb():

        kb = VkKeyboard(
            one_time=False
        )

        kb.add_button(
            "В меню",
            color=VkKeyboardColor.PRIMARY
        )

        return kb

    # ========================================================
    # ФОРМАТ ПАСПОРТА
    # ========================================================

    def format_passport(passport):

        url = (
            f"{BASE_URL.rstrip('/')}"
            f"/passport/"
            f"{passport['citizen_uuid']}"
        )

        return (
            "Паспорт\n\n"
            f"ФИО: {passport['full_name']}\n"
            f"Дата рождения: "
            f"{passport['birth_date']}\n"
            f"UUID: "
            f"{passport['citizen_uuid']}\n"
            f"Дата выдачи: "
            f"{passport['issue_date']}\n\n"
            "Открыть паспорт на сайте:\n"
            f"{url}"
        )

    # ========================================================
    # НЕИЗВЕСТНЫЙ ЗАПРОС
    # ========================================================

    def unknown(peer_id):

        send(
            peer_id,
            "Неизвестный запрос.\n\n"
            "Используйте кнопки меню "
            "или напишите /start.",
            unknown_kb()
        )

    # ========================================================
    # ПРОВЕРКА ДАТЫ
    # ========================================================

    def valid_birth_date(value):

        try:

            date = datetime.strptime(
                value,
                "%d.%m.%Y"
            )

            if date > datetime.now():

                return False

            return True

        except ValueError:

            return False

    # ========================================================
    # ПРОВЕРКА СОБЫТИЯ
    # ========================================================

    def is_own_message(event):

        """
        Проверяет, не является ли событие
        сообщением, которое отправил сам бот.
        """

        # from_id — реальный отправитель сообщения
        from_id = getattr(
            event,
            "from_id",
            None
        )

        if from_id is None:

            return False

        try:

            from_id = int(
                from_id
            )

        except (
            TypeError,
            ValueError
        ):

            return False

        # Возможные варианты ID сообщества
        # VK может отдавать отрицательный ID
        return from_id in {
            GROUP_ID,
            -GROUP_ID
        }

    # ========================================================
    # ОБРАБОТКА СООБЩЕНИЯ
    # ========================================================

    def handle(event):

        # ----------------------------------------------------
        # КРИТИЧЕСКАЯ ЗАЩИТА:
        # НЕ ОБРАБАТЫВАЕМ СВОИ СООБЩЕНИЯ
        # ----------------------------------------------------

        if is_own_message(event):

            print(
                "[IGNORE] Игнорируем "
                "собственное сообщение бота"
            )

            return

        # ----------------------------------------------------
        # Данные сообщения
        # ----------------------------------------------------

        uid = int(
            event.user_id
        )

        peer_id = int(
            event.peer_id
        )

        text = (
            event.text or ""
        ).strip()

        print(
            f"[MESSAGE] "
            f"uid={uid} "
            f"peer={peer_id} "
            f"text={text!r}"
        )

        # ----------------------------------------------------
        # Только личные сообщения
        # ----------------------------------------------------

        if peer_id != uid:

            print(
                "[IGNORE] Сообщение "
                "не из личного диалога"
            )

            return

        # ----------------------------------------------------
        # Получение паспорта
        # ----------------------------------------------------

        try:

            passport = get_passport(
                uid
            )

        except Exception as e:

            print(
                f"[DB] Ошибка получения "
                f"паспорта: {e}"
            )

            send(
                peer_id,
                "Произошла ошибка базы данных. "
                "Попробуйте позже.",
                main_kb()
            )

            return

        # ====================================================
        # В МЕНЮ
        # ====================================================

        if text == "В меню":

            states.pop(
                uid,
                None
            )

            send(
                peer_id,
                "Главное меню:",
                main_kb()
            )

            return

        # ====================================================
        # START
        # ====================================================

        if text in (
            "/start",
            "Начать",
            "начать",
            "Start",
            "start",
        ):

            states.pop(
                uid,
                None
            )

            send(
                peer_id,

                "Добро пожаловать "
                "в бот виртуального "
                "государства Доллания!\n\n"

                "Здесь вы можете:\n"
                "— получить паспорт гражданина;\n"
                "— просмотреть и изменить "
                "данные паспорта;\n"
                "— написать Президенту;\n"
                "— написать администраторам.\n\n"

                "Выберите действие "
                "в меню ниже.",

                main_kb()
            )

            return

        # ====================================================
        # МЕНЮ
        # ====================================================

        if text in (
            "Меню",
            "меню"
        ):

            states.pop(
                uid,
                None
            )

            send(
                peer_id,
                "Главное меню:",
                main_kb()
            )

            return

        # ====================================================
        # ПАСПОРТ
        # ====================================================

        if text == "Паспорт":

            states.pop(
                uid,
                None
            )

            if passport:

                send(
                    peer_id,
                    format_passport(
                        passport
                    ),
                    passport_kb(True)
                )

            else:

                send(
                    peer_id,

                    "Раздел «Паспорт».\n\n"
                    "У вас нет паспорта.\n"
                    "Нажмите "
                    "«Зарегистрировать».",

                    passport_kb(False)
                )

            return

        # ====================================================
        # РЕГИСТРАЦИЯ
        # ====================================================

        if text in (
            "Зарегистрировать",
            "Получить",
        ):

            if passport:

                send(
                    peer_id,
                    "У вас уже есть паспорт.",
                    passport_kb(True)
                )

                return

            states[uid] = {
                "mode": "create",
                "field": "full_name",
                "data": {},
            }

            send(
                peer_id,
                "Введите ваше ФИО:",
                back_kb()
            )

            return

        # ====================================================
        # ИЗМЕНЕНИЕ ФИО
        # ====================================================

        if text == "Изменить ФИО":

            if not passport:

                send(
                    peer_id,
                    "Сначала зарегистрируйтесь.",
                    passport_kb(False)
                )

                return

            states[uid] = {
                "mode": "edit",
                "field": "full_name",
            }

            send(
                peer_id,
                "Введите новое ФИО:",
                back_kb()
            )

            return

        # ====================================================
        # ИЗМЕНЕНИЕ ДАТЫ
        # ====================================================

        if text == "Изменить дату рождения":

            if not passport:

                send(
                    peer_id,
                    "Сначала зарегистрируйтесь.",
                    passport_kb(False)
                )

                return

            states[uid] = {
                "mode": "edit",
                "field": "birth_date",
            }

            send(
                peer_id,
                "Введите новую дату рождения "
                "(ДД.ММ.ГГГГ):",
                back_kb()
            )

            return

        # ====================================================
        # ПРЕЗИДЕНТ
        # ====================================================

        if text in (
            "Написать Президенту",
            "Сообщить Президенту",
        ):

            if uid == PRESIDENT_ID:

                states.pop(
                    uid,
                    None
                )

                send(
                    peer_id,

                    "Вы — Президент.\n\n"
                    "Вы не можете отправить "
                    "сообщение самому себе.",

                    main_kb()
                )

                return

            states[uid] = {
                "mode": "president"
            }

            send(
                peer_id,

                "Введите ваше сообщение "
                "Президенту.\n\n"
                "Разрешён только текст.",

                back_kb()
            )

            return

        # ====================================================
        # АДМИНИСТРАТОРЫ
        # ====================================================

        if text == "Написать администраторам":

            states[uid] = {
                "mode": "admins"
            }

            send(
                peer_id,

                "Введите ваше сообщение "
                "администраторам.\n\n"
                "Разрешён только текст.",

                back_kb()
            )

            return

        # ====================================================
        # НАЗАД
        # ====================================================

        if text == "Назад":

            states.pop(
                uid,
                None
            )

            send(
                peer_id,
                "Главное меню:",
                main_kb()
            )

            return

        # ====================================================
        # FSM
        # ====================================================

        state = states.get(
            uid
        )

        # Нет активного состояния
        if not state:

            unknown(
                peer_id
            )

            return

        mode = state.get(
            "mode"
        )

        # ====================================================
        # СООБЩЕНИЕ ПРЕЗИДЕНТУ
        # ====================================================

        if mode == "president":

            if uid == PRESIDENT_ID:

                states.pop(
                    uid,
                    None
                )

                send(
                    peer_id,
                    "Вы — Президент. "
                    "Сообщение не отправлено.",
                    main_kb()
                )

                return

            # Запрещаем вложения
            if getattr(
                event,
                "attachments",
                None
            ):

                send(
                    peer_id,
                    "Можно отправить "
                    "только текст.\n\n"
                    "Напишите сообщение заново.",
                    back_kb()
                )

                return

            if not text:

                send(
                    peer_id,
                    "Сообщение пустое.\n\n"
                    "Введите текст:",
                    back_kb()
                )

                return

            # Сбрасываем состояние
            states.pop(
                uid,
                None
            )

            if passport:

                info = (
                    "Гражданин\n"
                    f"ФИО: "
                    f"{passport['full_name']}\n"
                    f"Страница: "
                    f"[vk.com/id{uid}|"
                    f"{passport['full_name']}]\n"
                    f"UUID: "
                    f"{passport['citizen_uuid']}\n"
                    f"Дата рождения: "
                    f"{passport['birth_date']}"
                )

            else:

                info = (
                    "Гражданин\n"
                    "ФИО: —\n"
                    f"Страница: "
                    f"[vk.com/id{uid}|Страница]\n"
                    "UUID: —\n"
                    "Дата рождения: —"
                )

            message = (
                "Новое сообщение "
                "от гражданина\n\n"
                f"{info}\n\n"
                "Сообщение:\n"
                f"{text}"
            )

            if not send(
                PRESIDENT_ID,
                message
            ):

                send(
                    peer_id,
                    "Не удалось доставить "
                    "сообщение Президенту.",
                    main_kb()
                )

                return

            send(
                peer_id,

                "Ваше сообщение "
                "отправлено Президенту.\n\n"
                "Ответ придёт в этом диалоге.",

                main_kb()
            )

            return

        # ====================================================
        # СООБЩЕНИЕ АДМИНИСТРАТОРАМ
        # ====================================================

        if mode == "admins":

            if getattr(
                event,
                "attachments",
                None
            ):

                send(
                    peer_id,
                    "Можно отправить "
                    "только текст.\n\n"
                    "Напишите сообщение заново.",
                    back_kb()
                )

                return

            if not text:

                send(
                    peer_id,
                    "Сообщение пустое.\n\n"
                    "Введите текст:",
                    back_kb()
                )

                return

            states.pop(
                uid,
                None
            )

            if passport:

                info = (
                    "Отправитель\n"
                    f"ФИО: "
                    f"{passport['full_name']}\n"
                    f"Страница: "
                    f"[vk.com/id{uid}|"
                    f"{passport['full_name']}]\n"
                    f"UUID: "
                    f"{passport['citizen_uuid']}\n"
                    f"Дата рождения: "
                    f"{passport['birth_date']}"
                )

            else:

                info = (
                    "Отправитель\n"
                    "ФИО: —\n"
                    f"Страница: "
                    f"[vk.com/id{uid}|Страница]\n"
                    "UUID: —\n"
                    "Дата рождения: —"
                )

            message = (
                "Новое сообщение "
                "администраторам\n\n"
                f"{info}\n\n"
                "Сообщение:\n"
                f"{text}"
            )

            admin_ids = get_admins()

            print(
                f"[ADMINS] "
                f"Администраторы: "
                f"{admin_ids}"
            )

            delivered = 0

            for admin_id in admin_ids:

                if admin_id == uid:
                    continue

                if send(
                    admin_id,
                    message
                ):

                    delivered += 1

            if delivered == 0:

                send(
                    peer_id,

                    "Не удалось доставить "
                    "сообщение ни одному "
                    "администратору.",

                    main_kb()
                )

                return

            send(
                peer_id,

                "Ваше сообщение отправлено "
                f"администраторам "
                f"({delivered} получателей).\n\n"
                "Ответ придёт в этом диалоге.",

                main_kb()
            )

            return

        # ====================================================
        # ИЗМЕНЕНИЕ ПАСПОРТА
        # ====================================================

        if mode == "edit":

            field = state.get(
                "field"
            )

            # ------------------------------------------------
            # ФИО
            # ------------------------------------------------

            if field == "full_name":

                if len(text) < 3:

                    send(
                        peer_id,
                        "Слишком короткое ФИО.\n\n"
                        "Введите ещё раз:",
                        back_kb()
                    )

                    return

            # ------------------------------------------------
            # Дата рождения
            # ------------------------------------------------

            elif field == "birth_date":

                if not valid_birth_date(
                    text
                ):

                    send(
                        peer_id,

                        "Неверный формат "
                        "или дата.\n\n"
                        "Введите дату "
                        "в формате "
                        "ДД.ММ.ГГГГ:",

                        back_kb()
                    )

                    return

            else:

                states.pop(
                    uid,
                    None
                )

                unknown(
                    peer_id
                )

                return

            # ------------------------------------------------
            # Обновляем
            # ------------------------------------------------

            try:

                update_passport(
                    uid,
                    field,
                    text
                )

            except Exception as e:

                print(
                    f"[DB] Ошибка обновления: "
                    f"{e}"
                )

                states.pop(
                    uid,
                    None
                )

                send(
                    peer_id,
                    "Не удалось обновить "
                    "паспорт.",
                    main_kb()
                )

                return

            states.pop(
                uid,
                None
            )

            try:

                new_passport = get_passport(
                    uid
                )

            except Exception:

                new_passport = None

            if not new_passport:

                send(
                    peer_id,

                    "Данные обновлены, "
                    "но паспорт не удалось "
                    "получить.",

                    main_kb()
                )

                return

            send(
                peer_id,

                "Данные обновлены.\n\n"
                + format_passport(
                    new_passport
                ),

                passport_kb(True)
            )

            return

        # ====================================================
        # СОЗДАНИЕ ПАСПОРТА
        # ====================================================

        if mode == "create":

            # ------------------------------------------------
            # Повторная проверка
            # ------------------------------------------------

            try:

                existing = get_passport(
                    uid
                )

            except Exception as e:

                print(
                    f"[DB] Ошибка: {e}"
                )

                send(
                    peer_id,
                    "Ошибка базы данных.",
                    main_kb()
                )

                return

            if existing:

                states.pop(
                    uid,
                    None
                )

                send(
                    peer_id,
                    "Вы уже зарегистрированы.",
                    passport_kb(True)
                )

                return

            field = state.get(
                "field"
            )

            # ------------------------------------------------
            # ФИО
            # ------------------------------------------------

            if field == "full_name":

                if len(text) < 3:

                    send(
                        peer_id,

                        "Слишком короткое ФИО.\n\n"
                        "Введите ещё раз:",

                        back_kb()
                    )

                    return

                state["data"][
                    "full_name"
                ] = text

                state["field"] = (
                    "birth_date"
                )

                send(
                    peer_id,

                    "Введите дату рождения "
                    "(ДД.ММ.ГГГГ):",

                    back_kb()
                )

                return

            # ------------------------------------------------
            # ДАТА
            # ------------------------------------------------

            if field == "birth_date":

                if not valid_birth_date(
                    text
                ):

                    send(
                        peer_id,

                        "Неверный формат "
                        "или дата.\n\n"
                        "Введите ДД.ММ.ГГГГ:",

                        back_kb()
                    )

                    return

                state["data"][
                    "birth_date"
                ] = text

                # UUID паспорта
                citizen_uuid = str(
                    uuid.uuid4()
                )

                # Дата выдачи
                issue_date = (
                    datetime.now()
                    .strftime("%d.%m.%Y")
                )

                try:

                    create_passport(
                        uid,
                        citizen_uuid,
                        issue_date,
                        state["data"][
                            "full_name"
                        ],
                        state["data"][
                            "birth_date"
                        ]
                    )

                except Exception as e:

                    print(
                        f"[DB] Ошибка создания: "
                        f"{e}"
                    )

                    states.pop(
                        uid,
                        None
                    )

                    send(
                        peer_id,

                        "Ошибка регистрации.\n"
                        "Попробуйте ещё раз.",

                        main_kb()
                    )

                    return

                states.pop(
                    uid,
                    None
                )

                try:

                    new_passport = (
                        get_passport(uid)
                    )

                except Exception:

                    new_passport = None

                if not new_passport:

                    send(
                        peer_id,

                        "Паспорт создан, "
                        "но произошла ошибка "
                        "при его получении.",

                        main_kb()
                    )

                    return

                send(
                    peer_id,

                    "Паспорт выдан!\n\n"
                    + format_passport(
                        new_passport
                    ),

                    passport_kb(True)
                )

                return

        # ====================================================
        # НЕИЗВЕСТНЫЙ РЕЖИМ
        # ====================================================

        states.pop(
            uid,
            None
        )

        unknown(
            peer_id
        )

    # ========================================================
    # LONG POLL
    # ========================================================

    print(
        "[BOT] Запуск Long Poll..."
    )

    while True:

        try:

            longpoll = VkLongPoll(
                vk_session,
                wait=25
            )

            print(
                "[BOT] Бот запущен."
            )

            print(
                "[BOT] Ожидаю сообщения..."
            )

            # ------------------------------------------------
            # Слушаем события
            # ------------------------------------------------

            for event in longpoll.listen():

                # --------------------------------------------
                # Только новые сообщения
                # --------------------------------------------

                if (
                    event.type
                    != VkEventType.MESSAGE_NEW
                ):

                    continue

                # --------------------------------------------
                # Защита от повторной обработки
                # --------------------------------------------

                event_id = getattr(
                    event,
                    "event_id",
                    None
                )

                if event_id is not None:

                    if event_id in processed_events:

                        print(
                            "[IGNORE] Повторное "
                            f"событие {event_id}"
                        )

                        continue

                    processed_events.add(
                        event_id
                    )

                    # ----------------------------------------
                    # Ограничиваем размер set
                    # ----------------------------------------

                    if len(
                        processed_events
                    ) > 10000:

                        processed_events.clear()

                # --------------------------------------------
                # Только личные сообщения
                # --------------------------------------------

                if (
                    event.peer_id
                    != event.user_id
                ):

                    print(
                        "[IGNORE] Сообщение "
                        "из беседы"
                    )

                    continue

                # --------------------------------------------
                # Игнорируем собственные сообщения
                # --------------------------------------------

                if is_own_message(
                    event
                ):

                    print(
                        "[IGNORE] Собственное "
                        "сообщение бота"
                    )

                    continue

                # --------------------------------------------
                # Обрабатываем сообщение
                # --------------------------------------------

                try:

                    handle(
                        event
                    )

                except Exception as e:

                    print(
                        "[HANDLE] Критическая "
                        f"ошибка: {e}"
                    )

                    import traceback

                    traceback.print_exc()

        # ====================================================
        # ОСТАНОВКА
        # ====================================================

        except KeyboardInterrupt:

            print(
                "\n[BOT] Бот остановлен."
            )

            break

        # ====================================================
        # ОШИБКА LONG POLL
        # ====================================================

        except Exception as e:

            print(
                "[LONGPOLL] Соединение "
                f"оборвано: "
                f"{type(e).__name__}: {e}"
            )

            print(
                "[LONGPOLL] "
                "Переподключение "
                "через 5 секунд..."
            )

            time.sleep(5)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    run_bot()