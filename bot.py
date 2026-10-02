#!/usr/bin/env python3
"""
Телеграм-бот для планировщика задач (Todo Telegram Bot).
Поддерживает индивидуальные списки задач для каждого пользователя по Telegram ID.
Работает на базе стандартной библиотеки Python (urllib), без обязательных сторонних зависимостей.
"""

import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Импортируем функции управления задачами из todo.py
from todo import (
    USER_TASKS_DIR,
    add_task,
    delete_task,
    load_tasks,
    set_task_done,
    toggle_task,
)

# Обеспечиваем корректный вывод UTF-8 в консоли Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ENV_FILE = Path(__file__).resolve().parent / ".env"
TOKEN_FILE = Path(__file__).resolve().parent / "bot_token.txt"


def load_env_file() -> None:
    """Загружает переменные из .env файла в os.environ."""
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
        except Exception:
            pass


def get_bot_token() -> str:
    """Получает токен Telegram бота из окружения, файла .env, аргументов или файла bot_token.txt."""
    # Загружаем переменные из .env
    load_env_file()

    # 1. Из аргументов командной строки: python bot.py <TOKEN> или --token <TOKEN>
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--token", "-t") and len(sys.argv) > 2:
            return sys.argv[2].strip()
        elif not sys.argv[1].startswith("-"):
            return sys.argv[1].strip()

    # 2. Из переменной окружения (.env или системного окружения)
    env_token = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if env_token:
        return env_token.strip()

    # 3. Из файла bot_token.txt
    if TOKEN_FILE.exists():
        try:
            content = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass

    return ""


class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}/"
        self.bot_info = None

    def api_request(self, method: str, params: dict | None = None, timeout: int = 40) -> dict | None:
        """Отправляет POST-запрос к Telegram Bot API."""
        url = self.base_url + method
        headers = {"Content-Type": "application/json"}
        data_bytes = json.dumps(params or {}).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                if resp_data.get("ok"):
                    return resp_data.get("result")
                return None
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            if "message is not modified" not in err_body and "query is too old" not in err_body:
                print(f"[API Ошибка HTTP {e.code}]: {err_body}", file=sys.stderr)
            return None
        except (urllib.error.URLError, TimeoutError) as e:
            # При long polling таймаут — это нормальное явление
            if "timed out" not in str(e).lower():
                print(f"[Сетевая ошибка]: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"[Ошибка запроса]: {e}", file=sys.stderr)
            return None

    def get_me(self) -> dict | None:
        """Проверяет токен и получает информацию о боте."""
        return self.api_request("getMe")

    def get_updates(self, offset: int = 0, timeout: int = 25) -> list[dict]:
        """Получает новые сообщения методом Long Polling."""
        result = self.api_request("getUpdates", {"offset": offset, "timeout": timeout}, timeout=timeout + 5)
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: int | str, text: str, reply_markup: dict | None = None, parse_mode: str = "HTML") -> dict | None:
        """Отправляет текстовое сообщение в чат."""
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self.api_request("sendMessage", payload)

    def edit_message_text(self, chat_id: int | str, message_id: int, text: str, reply_markup: dict | None = None, parse_mode: str = "HTML") -> dict | None:
        """Редактирует существующее сообщение."""
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self.api_request("editMessageText", payload)

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        """Отвечает на callback_query от инлайн-кнопок."""
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        self.api_request("answerCallbackQuery", payload)


def format_tasks_view(user_id: int | str) -> tuple[str, dict]:
    """Формирует текст списка задач и инлайн-клавиатуру для конкретного пользователя."""
    tasks = load_tasks(user_id=user_id)
    total = len(tasks)
    done_count = sum(1 for t in tasks if t.get("done"))
    pending_count = total - done_count

    if not tasks:
        text = (
            f"📋 <b>Ваш персональный список задач пуст!</b>\n"
            f"<i>👤 Ваш ID: <code>{user_id}</code></i>\n\n"
            "Чтобы добавить задачу, отправьте команду:\n"
            "<code>/add Купить продукты</code>\n"
            "или просто напишите текст задачи сообщением в чат."
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "➕ Добавить задачу", "callback_data": "prompt_add"}],
                [{"text": "🔄 Обновить", "callback_data": "refresh"}],
            ]
        }
        return text, keyboard

    text_lines = [
        f"📋 <b>Ваш личный список задач</b> (ID: <code>{user_id}</code>):\n",
    ]
    for t in tasks:
        icon = "✅" if t.get("done") else "⬜️"
        text_lines.append(f"{icon} <b>#{t.get('id')}</b> {html.escape(t.get('text', ''))}")

    text_lines.append(f"\n📊 <i>Всего: {total} | Выполнено: {done_count} | Осталось: {pending_count}</i>")
    text_lines.append("<i>💡 Нажмите кнопку ниже, чтобы переключить статус задачи:</i>")
    text = "\n".join(text_lines)

    # Инлайн-кнопки для каждой персональной задачи
    inline_keyboard = []
    for t in tasks:
        status_icon = "✅" if t.get("done") else "⬜️"
        btn_text = f"{status_icon} #{t.get('id')} {t.get('text', '')[:25]}"
        inline_keyboard.append([
            {"text": btn_text, "callback_data": f"toggle:{t.get('id')}"},
            {"text": "🗑️", "callback_data": f"del:{t.get('id')}"},
        ])

    webapp_url = os.environ.get("WEBAPP_URL", "").strip()
    bottom_row = [{"text": "🔄 Обновить список", "callback_data": "refresh"}]
    if webapp_url.startswith("https://"):
        bottom_row.append({"text": "🌐 Веб-приложение", "web_app": {"url": webapp_url}})

    inline_keyboard.append(bottom_row)

    keyboard = {"inline_keyboard": inline_keyboard}
    return text, keyboard


def get_main_reply_keyboard() -> dict:
    """Главная клавиатура внизу экрана."""
    webapp_url = os.environ.get("WEBAPP_URL", "").strip()
    keyboard = [
        [{"text": "📋 Список задач"}, {"text": "➕ Добавить задачу"}],
    ]
    if webapp_url.startswith("https://"):
        keyboard.append([{"text": "🌐 Открыть веб-приложение", "web_app": {"url": webapp_url}}])
    keyboard.append([{"text": "ℹ️ Помощь"}])

    return {
        "keyboard": keyboard,
        "resize_keyboard": True,
    }


def handle_message(bot: TelegramBot, message: dict, pending_add: set) -> None:
    """Обрабатывает входящее сообщение от пользователя с учётом его индивидуального ID."""
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if not chat_id:
        return

    # Индивидуальный идентификатор пользователя
    user_id = message.get("from", {}).get("id") or chat_id
    user_name = message.get("from", {}).get("first_name", "пользователь")
    text = message.get("text", "").strip()

    if not text:
        return

    # Ожидание ввода текста новой задачи после нажатия кнопки "➕ Добавить задачу"
    if user_id in pending_add and not text.startswith("/"):
        pending_add.discard(user_id)
        task = add_task(text, user_id=user_id)
        view_text, markup = format_tasks_view(user_id)
        bot.send_message(
            chat_id,
            f"✅ Задача добавлена в ваш личный список (<b>ID: {task['id']}</b>):\n«{html.escape(task['text'])}»",
            reply_markup=get_main_reply_keyboard(),
        )
        bot.send_message(chat_id, view_text, reply_markup=markup)
        return

    # Команда /start
    if text.startswith("/start"):
        pending_add.discard(user_id)
        welcome = (
            f"👋 Привет, <b>{html.escape(user_name)}</b>!\n\n"
            "Я ваш <b>персональный бот-планировщик задач</b>.\n"
            f"Ваш персональный ID: <code>{user_id}</code>.\n\n"
            "🔒 <b>Все задачи хранятся индивидуально для вашего профиля и не видны другим пользователям бота.</b>\n\n"
            "📌 <b>Что я умею:</b>\n"
            "• 📋 <code>/list</code> — показать ваш персональный список задач\n"
            "• ➕ <code>/add &lt;текст&gt;</code> — добавить задачу в ваш список\n"
            "• ✅ <code>/done &lt;id&gt;</code> — отметить выполненной\n"
            "• 🗑️ <code>/delete &lt;id&gt;</code> — удалить задачу\n"
            "• ℹ️ <code>/help</code> — показать справку\n\n"
            "<i>💡 Вы можете просто отправить любой текст в чат, и я добавлю его в ваш личный список!</i>"
        )
        bot.send_message(chat_id, welcome, reply_markup=get_main_reply_keyboard())
        view_text, markup = format_tasks_view(user_id)
        bot.send_message(chat_id, view_text, reply_markup=markup)
        return

    # Команда /help или кнопка "ℹ️ Помощь"
    if text.startswith("/help") or text == "ℹ️ Помощь":
        pending_add.discard(user_id)
        help_text = (
            f"📖 <b>Справка (Ваш личный ID: <code>{user_id}</code>):</b>\n\n"
            "🔒 <b>Индивидуальность:</b> ваш список задач хранится в отдельном защищённом файле и доступен только вам.\n\n"
            "• <b>/list</b> (или кнопка «📋 Список задач») — выводит ваш персональный список с интерактивными кнопками;\n"
            "• <b>/add &lt;текст&gt;</b> — добавляет задачу в ваш список;\n"
            "• <b>/done &lt;номер&gt;</b> — отмечает задачу выполненной;\n"
            "• <b>/delete &lt;номер&gt;</b> — удаляет задачу;\n"
            "• <b>Обычный текст</b> — просто напишите боту задачу (например: <i>Купить молоко</i>), и она будет добавлена."
        )
        bot.send_message(chat_id, help_text, reply_markup=get_main_reply_keyboard())
        return

    # Команда /list или кнопка "📋 Список задач"
    if text.startswith("/list") or text == "📋 Список задач":
        pending_add.discard(user_id)
        view_text, markup = format_tasks_view(user_id)
        bot.send_message(chat_id, view_text, reply_markup=markup)
        return

    # Кнопка "➕ Добавить задачу"
    if text == "➕ Добавить задачу":
        pending_add.add(user_id)
        bot.send_message(
            chat_id,
            "✍️ <b>Напишите текст задачи в следующем сообщении:</b>",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    # Команда /add <текст>
    if text.startswith("/add"):
        pending_add.discard(user_id)
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.send_message(chat_id, "⚠️ Укажите текст задачи.\nПример: <code>/add Купить продукты</code>")
            return
        task_text = parts[1].strip()
        task = add_task(task_text, user_id=user_id)
        view_text, markup = format_tasks_view(user_id)
        bot.send_message(
            chat_id,
            f"✅ Задача добавлена в ваш список (<b>ID: {task['id']}</b>):\n«{html.escape(task['text'])}»",
            reply_markup=get_main_reply_keyboard(),
        )
        bot.send_message(chat_id, view_text, reply_markup=markup)
        return

    # Команда /done <id>
    if text.startswith("/done"):
        pending_add.discard(user_id)
        parts = text.split()
        if len(parts) < 2:
            bot.send_message(chat_id, "⚠️ Укажите ID задачи.\nПример: <code>/done 1</code>")
            return
        try:
            task_id = int(parts[1])
        except ValueError:
            bot.send_message(chat_id, "⚠️ ID задачи должен быть числом.\nПример: <code>/done 1</code>")
            return

        task = set_task_done(task_id, True, user_id=user_id)
        if task:
            bot.send_message(chat_id, f"✅ Задача #{task_id} выполнена:\n«{html.escape(task.get('text', ''))}»")
            view_text, markup = format_tasks_view(user_id)
            bot.send_message(chat_id, view_text, reply_markup=markup)
        else:
            bot.send_message(chat_id, f"❌ Задача с ID #{task_id} не найдена в вашем списке.")
        return

    # Команда /delete <id>
    if text.startswith("/delete") or text.startswith("/del"):
        pending_add.discard(user_id)
        parts = text.split()
        if len(parts) < 2:
            bot.send_message(chat_id, "⚠️ Укажите ID задачи для удаления.\nПример: <code>/delete 1</code>")
            return
        try:
            task_id = int(parts[1])
        except ValueError:
            bot.send_message(chat_id, "⚠️ ID задачи должен быть числом.")
            return

        if delete_task(task_id, user_id=user_id):
            bot.send_message(chat_id, f"🗑️ Задача #{task_id} удалена из вашего списка.")
            view_text, markup = format_tasks_view(user_id)
            bot.send_message(chat_id, view_text, reply_markup=markup)
        else:
            bot.send_message(chat_id, f"❌ Задача с ID #{task_id} не найдена в вашем списке.")
        return

    # Если обычное текстовое сообщение — добавляем как индивидуальную задачу
    if not text.startswith("/"):
        task = add_task(text, user_id=user_id)
        view_text, markup = format_tasks_view(user_id)
        bot.send_message(
            chat_id,
            f"✅ Создана задача в вашем списке (<b>ID: {task['id']}</b>):\n«{html.escape(task['text'])}»",
            reply_markup=get_main_reply_keyboard(),
        )
        bot.send_message(chat_id, view_text, reply_markup=markup)


def handle_callback_query(bot: TelegramBot, callback: dict) -> None:
    """Обрабатывает нажатия на инлайн-кнопки под списком задач с учётом индивидуального пользователя."""
    query_id = callback.get("id")
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    user_id = callback.get("from", {}).get("id") or chat_id

    if not chat_id or not message_id:
        return

    if data.startswith("toggle:"):
        try:
            task_id = int(data.split(":")[1])
            updated_task = toggle_task(task_id, user_id=user_id)
            if updated_task:
                status = "выполнена ✅" if updated_task.get("done") else "возвращена в работу ⬜️"
                bot.answer_callback_query(query_id, f"Задача #{task_id} {status}")
            else:
                bot.answer_callback_query(query_id, f"Задача #{task_id} не найдена в вашем списке")
        except Exception:
            bot.answer_callback_query(query_id, "Ошибка переключения")

        view_text, markup = format_tasks_view(user_id)
        bot.edit_message_text(chat_id, message_id, view_text, reply_markup=markup)

    elif data.startswith("del:"):
        try:
            task_id = int(data.split(":")[1])
            if delete_task(task_id, user_id=user_id):
                bot.answer_callback_query(query_id, f"Задача #{task_id} удалена 🗑️")
            else:
                bot.answer_callback_query(query_id, "Задача не найдена")
        except Exception:
            bot.answer_callback_query(query_id, "Ошибка удаления")

        view_text, markup = format_tasks_view(user_id)
        bot.edit_message_text(chat_id, message_id, view_text, reply_markup=markup)

    elif data == "refresh":
        bot.answer_callback_query(query_id, "Список обновлен 🔄")
        view_text, markup = format_tasks_view(user_id)
        bot.edit_message_text(chat_id, message_id, view_text, reply_markup=markup)

    elif data == "prompt_add":
        bot.answer_callback_query(query_id)
        bot.send_message(
            chat_id,
            "✍️ Просто напишите текст задачи сообщением в чат:",
            reply_markup=get_main_reply_keyboard(),
        )


def run_bot() -> None:
    """Запуск long polling цикла бота."""
    token = get_bot_token()
    if not token:
        print("=" * 60)
        print(" ОШИБКА: Токен Telegram бота не найден!")
        print("=" * 60)
        print("\nКак запустить бота:")
        print("1. Получите токен у официального бота @BotFather в Telegram.")
        print("2. Передайте токен одним из способов:")
        print("   а) Создайте файл bot_token.txt и запишите в него токен;")
        print("   б) Или запустите: python bot.py <ВАШ_ТОКЕН>;")
        print("   в) Или установите переменную окружения TELEGRAM_BOT_TOKEN.\n")
        print(f"Путь к файлу с токеном: {TOKEN_FILE}")
        print("=" * 60)
        sys.exit(1)

    bot = TelegramBot(token)
    print("Подключение к Telegram Bot API...")
    bot_info = bot.get_me()

    if not bot_info:
        print("\n❌ Ошибка: Не удалось авторизоваться в Telegram Bot API.")
        print("Проверьте правильность токена и подключение к интернету.")
        sys.exit(1)

    bot_username = bot_info.get("username", "UnknownBot")
    bot_first_name = bot_info.get("first_name", "TodoBot")

    print("\n" + "=" * 60)
    print(f" 🚀 Бот успешно запущен: @{bot_username} ({bot_first_name})")
    print(" 🔒 Режим: Индивидуальные списки задач по каждому Telegram ID")
    print(f" 📁 Папка персональных баз: {USER_TASKS_DIR.resolve()}")
    print(" Бот ожидает входящие сообщения. Для остановки нажмите Ctrl+C.")
    print("=" * 60 + "\n")

    offset = 0
    pending_add = set()

    while True:
        try:
            updates = bot.get_updates(offset=offset, timeout=25)
            for update in updates:
                update_id = update.get("update_id", 0)
                offset = max(offset, update_id + 1)

                if "message" in update:
                    msg = update["message"]
                    sender = msg.get("from", {}).get("username") or msg.get("from", {}).get("first_name", "User")
                    uid = msg.get("from", {}).get("id")
                    txt = msg.get("text", "")
                    print(f"[{time.strftime('%H:%M:%S')}] Сообщение от @{sender} (ID: {uid}): {txt}", flush=True)
                    handle_message(bot, msg, pending_add)
                elif "callback_query" in update:
                    cb = update["callback_query"]
                    sender = cb.get("from", {}).get("username") or cb.get("from", {}).get("first_name", "User")
                    uid = cb.get("from", {}).get("id")
                    data = cb.get("data", "")
                    print(f"[{time.strftime('%H:%M:%S')}] Кнопка от @{sender} (ID: {uid}): {data}", flush=True)
                    handle_callback_query(bot, cb)

        except KeyboardInterrupt:
            print("\nОстановка бота по запросу пользователя.", flush=True)
            break
        except Exception as e:
            print(f"Неожиданная ошибка в цикле: {e}", file=sys.stderr, flush=True)
            time.sleep(3)


if __name__ == "__main__":
    run_bot()
