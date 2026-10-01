#!/usr/bin/env python3
"""
Веб-приложение Планировщика задач (Web-версия Telegram-бота и Todo App).
Запускает локальный веб-сервер без внешних зависимостей (на базе http.server),
предоставляя современный веб-интерфейс и интерактивный веб-эмулятор Telegram-бота.
"""

import html
import http.server
import json
import os
import re
import socket
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

# Добавляем текущую директорию в путь поиска модулей
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Импортируем ядро задач и функции форматирования бота
import todo

try:
    from bot import format_tasks_view, get_main_reply_keyboard
except Exception:
    def format_tasks_view(user_id=None):
        tasks = todo.load_tasks(user_id)
        total = len(tasks)
        done_count = sum(1 for t in tasks if t.get("done"))
        pending_count = total - done_count
        display_id = str(user_id) if user_id else "Локальный"
        if not tasks:
            text = f"📋 <b>Ваш персональный список задач пуст!</b>\n<i>👤 ID: <code>{display_id}</code></i>"
            return text, {"inline_keyboard": [[{"text": "🔄 Обновить", "callback_data": "refresh"}]]}
        text_lines = [f"📋 <b>Ваш список задач</b> (ID: <code>{display_id}</code>):\n"]
        for t in tasks:
            icon = "✅" if t.get("done") else "⬜️"
            text_lines.append(f"{icon} <b>#{t.get('id')}</b> {html.escape(t.get('text', ''))}")
        text_lines.append(f"\n📊 <i>Всего: {total} | Выполнено: {done_count} | Осталось: {pending_count}</i>")
        inline_keyboard = []
        for t in tasks:
            status_icon = "✅" if t.get("done") else "⬜️"
            btn_text = f"{status_icon} #{t.get('id')} {t.get('text', '')[:25]}"
            inline_keyboard.append([
                {"text": btn_text, "callback_data": f"toggle:{t.get('id')}"},
                {"text": "🗑️", "callback_data": f"del:{t.get('id')}"},
            ])
        inline_keyboard.append([{"text": "🔄 Обновить список", "callback_data": "refresh"}])
        return "\n".join(text_lines), {"inline_keyboard": inline_keyboard}

    def get_main_reply_keyboard():
        return {
            "keyboard": [
                [{"text": "📋 Список задач"}, {"text": "➕ Добавить задачу"}],
                [{"text": "ℹ️ Помощь"}],
            ],
            "resize_keyboard": True,
        }

HTML_FILE = BASE_DIR / "index.html"


def find_available_port(start_port: int = 5000, max_attempts: int = 20) -> int:
    """Ищет свободный TCP порт, начиная со start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


def get_all_users() -> list[dict[str, Any]]:
    """Возвращает список всех найденных пользователей и общий список tasks.json."""
    users = []
    
    # 1. Общий список задач (локальный)
    default_tasks = todo.load_tasks(None)
    default_done = sum(1 for t in default_tasks if t.get("done"))
    users.append({
        "id": "default",
        "name": "📁 Общий список (tasks.json)",
        "is_default": True,
        "total": len(default_tasks),
        "done": default_done,
        "pending": len(default_tasks) - default_done,
    })

    # 2. Персональные базы в user_tasks/
    user_tasks_dir = BASE_DIR / "user_tasks"
    if user_tasks_dir.exists():
        for file in user_tasks_dir.glob("*.json"):
            user_id = file.stem
            tasks = todo.load_tasks(user_id)
            done_cnt = sum(1 for t in tasks if t.get("done"))
            users.append({
                "id": user_id,
                "name": f"👤 Telegram ID: {user_id}",
                "is_default": False,
                "total": len(tasks),
                "done": done_cnt,
                "pending": len(tasks) - done_cnt,
            })

    return users


class TodoWebHandler(http.server.BaseHTTPRequestHandler):
    """HTTP обработчик запросов для веб-интерфейса и REST API."""

    server_version = "TodoWebServer/1.0"

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def send_json(self, data: Any, status: int = 200) -> None:
        """Отправляет ответ в формате JSON."""
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def read_json_body(self) -> dict:
        """Считывает тело POST запроса в виде словаря."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                raw_body = self.rfile.read(content_length).decode("utf-8")
                return json.loads(raw_body)
        except Exception:
            pass
        return {}

    def log_message(self, format: str, *args: Any) -> None:
        """Подавляем лишний шум в консоли, логируем только важные запросы."""
        if args and str(args[1]) in ("404", "500"):
            super().log_message(format, *args)

    # ---------------- GET ЗАПРОСЫ ----------------
    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # Главная страница (веб-интерфейс)
        if path in ("/", "/index.html"):
            if not HTML_FILE.exists():
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"index.html not found")
                return

            with open(HTML_FILE, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
            return

        # API: Список пользователей
        if path == "/api/users":
            users = get_all_users()
            self.send_json({"ok": True, "users": users})
            return

        # API: Список задач конкретного пользователя
        if path == "/api/tasks":
            user_id = query.get("user_id", [None])[0]
            if user_id in ("default", "", "null"):
                user_id = None

            tasks = todo.load_tasks(user_id)
            total = len(tasks)
            done = sum(1 for t in tasks if t.get("done"))
            pending = total - done
            percent = round((done / total * 100)) if total > 0 else 0

            self.send_json({
                "ok": True,
                "user_id": user_id or "default",
                "tasks": tasks,
                "stats": {
                    "total": total,
                    "done": done,
                    "pending": pending,
                    "percent": percent,
                },
            })
            return

        # 404 для неизвестных путей
        self.send_json({"ok": False, "error": "Not Found"}, status=404)

    # ---------------- POST ЗАПРОСЫ ----------------
    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        body = self.read_json_body()

        # API: Добавить задачу
        if path == "/api/tasks":
            text = body.get("text", "").strip()
            user_id = body.get("user_id")
            if user_id in ("default", "", "null"):
                user_id = None

            if not text:
                self.send_json({"ok": False, "error": "Текст задачи не может быть пустым"}, status=400)
                return

            task = todo.add_task(text, user_id=user_id)
            self.send_json({"ok": True, "task": task, "user_id": user_id or "default"})
            return

        # API: Переключить статус задачи
        match_toggle = re.match(r"^/api/tasks/(\d+)/toggle$", path)
        if match_toggle:
            task_id = int(match_toggle.group(1))
            user_id = body.get("user_id")
            if user_id in ("default", "", "null"):
                user_id = None

            task = todo.toggle_task(task_id, user_id=user_id)
            if task:
                self.send_json({"ok": True, "task": task, "user_id": user_id or "default"})
            else:
                self.send_json({"ok": False, "error": f"Задача #{task_id} не найдена"}, status=404)
            return

        # API: Установить статус задачи (done/undone)
        match_done = re.match(r"^/api/tasks/(\d+)/done$", path)
        if match_done:
            task_id = int(match_done.group(1))
            done = bool(body.get("done", True))
            user_id = body.get("user_id")
            if user_id in ("default", "", "null"):
                user_id = None

            task = todo.set_task_done(task_id, done=done, user_id=user_id)
            if task:
                self.send_json({"ok": True, "task": task, "user_id": user_id or "default"})
            else:
                self.send_json({"ok": False, "error": f"Задача #{task_id} не найдена"}, status=404)
            return

        # API: Редактировать текст задачи
        match_edit = re.match(r"^/api/tasks/(\d+)/edit$", path)
        if match_edit:
            task_id = int(match_edit.group(1))
            new_text = body.get("text", "").strip()
            user_id = body.get("user_id")
            if user_id in ("default", "", "null"):
                user_id = None

            if not new_text:
                self.send_json({"ok": False, "error": "Текст задачи не может быть пустым"}, status=400)
                return

            task = todo.edit_task(task_id, new_text, user_id=user_id)
            if task:
                self.send_json({"ok": True, "task": task, "user_id": user_id or "default"})
            else:
                self.send_json({"ok": False, "error": f"Задача #{task_id} не найдена"}, status=404)
            return

        # API: Очистить все выполненные задачи
        if path == "/api/tasks/clear-completed":
            user_id = body.get("user_id")
            if user_id in ("default", "", "null"):
                user_id = None

            removed = todo.clear_completed_tasks(user_id=user_id)
            self.send_json({"ok": True, "removed_count": removed, "user_id": user_id or "default"})
            return

        # API: Эмуляция отправки сообщения в Telegram-бот
        if path == "/api/bot/chat":
            user_id = body.get("user_id")
            if user_id in ("default", "", "null"):
                user_id = None

            user_name = body.get("user_name", "Пользователь")
            raw_text = body.get("text", "").strip()

            messages = []
            reply_keyboard = get_main_reply_keyboard().get("keyboard", [])

            effective_id_str = str(user_id) if user_id else "Локальный"

            # Команда /start
            if raw_text.startswith("/start"):
                welcome = (
                    f"👋 Привет, <b>{html.escape(user_name)}</b>!\n\n"
                    "Я ваш <b>персональный бот-планировщик задач</b>.\n"
                    f"Ваш ID: <code>{effective_id_str}</code>.\n\n"
                    "🔒 <b>Все задачи хранятся индивидуально для вашего профиля.</b>\n\n"
                    "📌 <b>Что я умею:</b>\n"
                    "• 📋 <code>/list</code> — показать ваш персональный список задач\n"
                    "• ➕ <code>/add &lt;текст&gt;</code> — добавить задачу\n"
                    "• ✅ <code>/done &lt;id&gt;</code> — отметить выполненной\n"
                    "• 🗑️ <code>/delete &lt;id&gt;</code> — удалить задачу\n"
                    "• ℹ️ <code>/help</code> — показать справку\n\n"
                    "<i>💡 Вы можете просто отправить любой текст в чат, и я создам задачу!</i>"
                )
                messages.append({"text": welcome, "inline_keyboard": []})

                view_text, markup = format_tasks_view(user_id)
                messages.append({
                    "text": view_text,
                    "inline_keyboard": markup.get("inline_keyboard", []),
                })

            # Команда /help или кнопка "ℹ️ Помощь"
            elif raw_text.startswith("/help") or raw_text == "ℹ️ Помощь":
                help_text = (
                    f"📖 <b>Справка (ID профиля: <code>{effective_id_str}</code>):</b>\n\n"
                    "• <b>/list</b> (кнопка «📋 Список задач») — выводит ваш персональный список с интерактивными кнопками;\n"
                    "• <b>/add &lt;текст&gt;</b> — добавляет задачу в список;\n"
                    "• <b>/done &lt;номер&gt;</b> — отмечает задачу выполненной;\n"
                    "• <b>/delete &lt;номер&gt;</b> — удаляет задачу;\n"
                    "• <b>Обычный текст</b> — просто напишите боту задачу (например: <i>Купить молоко</i>), и она будет добавлена."
                )
                messages.append({"text": help_text, "inline_keyboard": []})

            # Команда /list или кнопка "📋 Список задач"
            elif raw_text.startswith("/list") or raw_text == "📋 Список задач":
                view_text, markup = format_tasks_view(user_id)
                messages.append({
                    "text": view_text,
                    "inline_keyboard": markup.get("inline_keyboard", []),
                })

            # Кнопка "➕ Добавить задачу"
            elif raw_text == "➕ Добавить задачу":
                messages.append({
                    "text": "✍️ <b>Напишите текст задачи в следующем сообщении:</b>",
                    "inline_keyboard": [],
                    "await_task_text": True,
                })

            # Команда /add <текст>
            elif raw_text.startswith("/add"):
                parts = raw_text.split(maxsplit=1)
                if len(parts) < 2 or not parts[1].strip():
                    messages.append({
                        "text": "⚠️ Укажите текст задачи.\nПример: <code>/add Купить продукты</code>",
                        "inline_keyboard": [],
                    })
                else:
                    task = todo.add_task(parts[1].strip(), user_id=user_id)
                    view_text, markup = format_tasks_view(user_id)
                    messages.append({
                        "text": f"✅ Задача добавлена в список (<b>ID: #{task['id']}</b>):\n«{html.escape(task['text'])}»",
                        "inline_keyboard": [],
                    })
                    messages.append({
                        "text": view_text,
                        "inline_keyboard": markup.get("inline_keyboard", []),
                    })

            # Команда /done <id>
            elif raw_text.startswith("/done"):
                parts = raw_text.split()
                if len(parts) < 2:
                    messages.append({
                        "text": "⚠️ Укажите ID задачи.\nПример: <code>/done 1</code>",
                        "inline_keyboard": [],
                    })
                else:
                    try:
                        task_id = int(parts[1])
                        task = todo.set_task_done(task_id, True, user_id=user_id)
                        if task:
                            messages.append({
                                "text": f"✅ Задача #{task_id} выполнена:\n«{html.escape(task.get('text', ''))}»",
                                "inline_keyboard": [],
                            })
                            view_text, markup = format_tasks_view(user_id)
                            messages.append({
                                "text": view_text,
                                "inline_keyboard": markup.get("inline_keyboard", []),
                            })
                        else:
                            messages.append({
                                "text": f"❌ Задача с ID #{task_id} не найдена в вашем списке.",
                                "inline_keyboard": [],
                            })
                    except ValueError:
                        messages.append({
                            "text": "⚠️ ID задачи должен быть числом.\nПример: <code>/done 1</code>",
                            "inline_keyboard": [],
                        })

            # Команда /delete <id> или /del <id>
            elif raw_text.startswith("/delete") or raw_text.startswith("/del"):
                parts = raw_text.split()
                if len(parts) < 2:
                    messages.append({
                        "text": "⚠️ Укажите ID задачи для удаления.\nПример: <code>/delete 1</code>",
                        "inline_keyboard": [],
                    })
                else:
                    try:
                        task_id = int(parts[1])
                        if todo.delete_task(task_id, user_id=user_id):
                            messages.append({
                                "text": f"🗑️ Задача #{task_id} удалена из вашего списка.",
                                "inline_keyboard": [],
                            })
                            view_text, markup = format_tasks_view(user_id)
                            messages.append({
                                "text": view_text,
                                "inline_keyboard": markup.get("inline_keyboard", []),
                            })
                        else:
                            messages.append({
                                "text": f"❌ Задача с ID #{task_id} не найдена.",
                                "inline_keyboard": [],
                            })
                    except ValueError:
                        messages.append({
                            "text": "⚠️ ID задачи должен быть числом.",
                            "inline_keyboard": [],
                        })

            # Обычный текст сообщения: создаём задачу
            else:
                task = todo.add_task(raw_text, user_id=user_id)
                view_text, markup = format_tasks_view(user_id)
                messages.append({
                    "text": f"✅ Создана задача (<b>ID: #{task['id']}</b>):\n«{html.escape(task['text'])}»",
                    "inline_keyboard": [],
                })
                messages.append({
                    "text": view_text,
                    "inline_keyboard": markup.get("inline_keyboard", []),
                })

            self.send_json({
                "ok": True,
                "messages": messages,
                "reply_keyboard": reply_keyboard,
                "user_id": user_id or "default",
            })
            return

        # API: Эмуляция клика по инлайн-кнопкам бота
        if path == "/api/bot/callback":
            user_id = body.get("user_id")
            if user_id in ("default", "", "null"):
                user_id = None

            callback_data = body.get("data", "")
            toast_text = "Действие выполнено"

            if callback_data.startswith("toggle:"):
                try:
                    task_id = int(callback_data.split(":")[1])
                    updated_task = todo.toggle_task(task_id, user_id=user_id)
                    if updated_task:
                        status = "выполнена ✅" if updated_task.get("done") else "возвращена в работу ⬜️"
                        toast_text = f"Задача #{task_id} {status}"
                    else:
                        toast_text = f"Задача #{task_id} не найдена"
                except Exception:
                    toast_text = "Ошибка переключения"

            elif callback_data.startswith("del:"):
                try:
                    task_id = int(callback_data.split(":")[1])
                    if todo.delete_task(task_id, user_id=user_id):
                        toast_text = f"Задача #{task_id} удалена 🗑️"
                    else:
                        toast_text = "Задача не найдена"
                except Exception:
                    toast_text = "Ошибка удаления"

            elif callback_data == "refresh":
                toast_text = "Список обновлен 🔄"

            elif callback_data == "prompt_add":
                toast_text = "Напишите текст задачи в чат"

            view_text, markup = format_tasks_view(user_id)

            self.send_json({
                "ok": True,
                "toast": toast_text,
                "view_text": view_text,
                "inline_keyboard": markup.get("inline_keyboard", []),
                "user_id": user_id or "default",
            })
            return

        self.send_json({"ok": False, "error": "Not Found"}, status=404)

    # ---------------- DELETE ЗАПРОСЫ ----------------
    def do_DELETE(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        match_del = re.match(r"^/api/tasks/(\d+)$", path)
        if match_del:
            task_id = int(match_del.group(1))
            user_id = query.get("user_id", [None])[0]
            if user_id in ("default", "", "null"):
                user_id = None

            if todo.delete_task(task_id, user_id=user_id):
                self.send_json({"ok": True, "deleted_id": task_id, "user_id": user_id or "default"})
            else:
                self.send_json({"ok": False, "error": f"Задача #{task_id} не найдена"}, status=404)
            return

        self.send_json({"ok": False, "error": "Not Found"}, status=404)


def run_web_server(host: str = "0.0.0.0", port: int | None = None, auto_open: bool = True) -> None:
    """Запускает многопоточный веб-сервер и открывает страницу в браузере."""
    if port is None:
        env_port = os.environ.get("PORT")
        if env_port and env_port.isdigit():
            port = int(env_port)
        else:
            port = find_available_port(5000)

    server_address = (host, port)
    httpd = http.server.ThreadingHTTPServer(server_address, TodoWebHandler)
    local_url = f"http://localhost:{port}" if host in ("0.0.0.0", "127.0.0.1") else f"http://{host}:{port}"

    print("=" * 64)
    print(" 🚀 ВЕБ-ПРИЛОЖЕНИЕ ПЛАНИРОВЩИКА ЗАДАЧ ЗАПУЩЕНО!")
    print("=" * 64)
    print(f" 🌐 Адрес веб-сервера:                {local_url} (host: {host})")
    print(f" 📁 Локальный файл задач:             {todo.TASKS_FILE.resolve()}")
    print(f" 👥 Папка профилей пользователей:    {todo.USER_TASKS_DIR.resolve()}")
    print("=" * 64)
    print(" 💡 Для остановки сервера нажмите:    Ctrl + C")
    print("=" * 64 + "\n")

    if auto_open and host in ("0.0.0.0", "127.0.0.1", "localhost"):
        def open_browser():
            import time
            time.sleep(0.6)
            try:
                webbrowser.open(local_url)
            except Exception:
                pass
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановка веб-сервера по запросу пользователя...")
    finally:
        httpd.server_close()
        print("Веб-сервер остановлен.")


if __name__ == "__main__":
    auto_open = "--no-browser" not in sys.argv
    port_arg = None
    host_arg = "0.0.0.0"

    for i, arg in enumerate(sys.argv):
        if arg in ("--port", "-p") and i + 1 < len(sys.argv):
            try:
                port_arg = int(sys.argv[i + 1])
            except ValueError:
                pass
        elif arg in ("--host", "-h") and i + 1 < len(sys.argv):
            host_arg = sys.argv[i + 1].strip()

    run_web_server(host=host_arg, port=port_arg, auto_open=auto_open)
