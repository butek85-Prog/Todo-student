#!/usr/bin/env python3
"""
Веб-сервер и REST API для Telegram Mini App (Планировщик задач).
Работает на базе встроенного модуля http.server (без сторонних зависимостей).
Предоставляет статический веб-интерфейс (HTML/CSS/JS) и API для синхронизации задач с базой todo.py.
"""

import json
import mimetypes
import os
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Импортируем методы работы с задачами из todo.py
from todo import (
    add_task,
    delete_task,
    load_tasks,
    set_task_done,
    toggle_task,
)

BASE_DIR = Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"


class MiniAppRequestHandler(BaseHTTPRequestHandler):
    """Обработчик HTTP-запросов для Mini App и REST API."""

    def log_message(self, format, *args):
        # Компактное логирование запросов
        sys.stdout.write(f"[MiniApp Server] {self.address_string()} - {format % args}\n")
        sys.stdout.flush()

    def _set_cors_headers(self):
        """Устанавливает CORS заголовки для безопасной работы внутри Telegram WebApp."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")

    def _send_json(self, data: dict, status: int = 200):
        """Отправляет JSON-ответ клиенту."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400):
        """Отправляет структурированную ошибку в формате JSON."""
        self._send_json({"ok": False, "error": message}, status=status)

    def do_OPTIONS(self):
        """Поддержка preflight-запросов CORS."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Маршрутизация GET-запросов: статика (HTML/CSS/JS) или API задач."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)

        # 1. API: Получение списка задач
        if path == "/api/tasks":
            user_id = query.get("user_id", [None])[0]
            tasks = load_tasks(user_id=user_id)
            self._send_json({
                "ok": True,
                "user_id": str(user_id) if user_id else "local",
                "tasks": tasks,
                "count": len(tasks),
            })
            return

        # 2. API: Проверка статуса сервера
        if path == "/api/health":
            self._send_json({"ok": True, "status": "running"})
            return

        # 3. Раздача статических файлов веб-приложения Mini App
        if path in ("/", "/index.html"):
            file_path = WEBAPP_DIR / "index.html"
        else:
            rel_path = path.lstrip("/")
            file_path = (WEBAPP_DIR / rel_path).resolve()
            # Защита от Path Traversal
            try:
                file_path.relative_to(WEBAPP_DIR)
            except ValueError:
                self.send_error(HTTPStatus.FORBIDDEN, "Access denied")
                return

        if not file_path.exists() or not file_path.is_file():
            # Если запрошен favicon
            if path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            self.send_error(HTTPStatus.NOT_FOUND, f"File not found: {path}")
            return

        # Определение типа контента
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"
        if mime_type.startswith("text/") or mime_type in ("application/javascript", "application/json"):
            mime_type += "; charset=utf-8"

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(content)
        except OSError as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Error reading file: {e}")

    def do_POST(self):
        """Маршрутизация POST-запросов для управления задачами."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # Чтение тела запроса
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 1024 * 1024:  # Лимит 1 МБ
            self._send_error_json("Payload too large", status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return

        body_raw = self.rfile.read(content_length)
        try:
            data = json.loads(body_raw.decode("utf-8")) if body_raw else {}
        except json.JSONDecodeError:
            self._send_error_json("Invalid JSON body", status=400)
            return

        user_id = data.get("user_id")

        # 1. Добавление новой задачи: POST /api/tasks
        if path == "/api/tasks":
            text = (data.get("text") or "").strip()
            if not text:
                self._send_error_json("Text is required", status=400)
                return
            task = add_task(text, user_id=user_id)
            self._send_json({"ok": True, "task": task}, status=201)
            return

        # 2. Переключение статуса задачи: POST /api/tasks/toggle
        if path == "/api/tasks/toggle":
            task_id = data.get("id")
            if task_id is None:
                self._send_error_json("Task id is required", status=400)
                return
            try:
                task_id = int(task_id)
            except (ValueError, TypeError):
                self._send_error_json("Task id must be an integer", status=400)
                return

            task = toggle_task(task_id, user_id=user_id)
            if task:
                self._send_json({"ok": True, "task": task})
            else:
                self._send_error_json(f"Task #{task_id} not found", status=404)
            return

        # 3. Удаление задачи: POST /api/tasks/delete
        if path == "/api/tasks/delete":
            task_id = data.get("id")
            if task_id is None:
                self._send_error_json("Task id is required", status=400)
                return
            try:
                task_id = int(task_id)
            except (ValueError, TypeError):
                self._send_error_json("Task id must be an integer", status=400)
                return

            deleted = delete_task(task_id, user_id=user_id)
            if deleted:
                self._send_json({"ok": True, "id": task_id, "deleted": True})
            else:
                self._send_error_json(f"Task #{task_id} not found", status=404)
            return

        # 4. Очистка завершенных задач: POST /api/tasks/clear_completed
        if path == "/api/tasks/clear_completed":
            tasks = load_tasks(user_id=user_id)
            active_tasks = [t for t in tasks if not t.get("done")]
            deleted_count = len(tasks) - len(active_tasks)
            from todo import save_tasks
            save_tasks(active_tasks, user_id=user_id)
            self._send_json({"ok": True, "deleted_count": deleted_count})
            return

        self._send_error_json("Endpoint not found", status=404)


class MiniAppServer:
    """Управление жизненным циклом веб-сервера."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self, in_thread: bool = True) -> None:
        """Запускает HTTP сервер."""
        self.httpd = ThreadingHTTPServer((self.host, self.port), MiniAppRequestHandler)
        display_host = "localhost" if self.host in ("0.0.0.0", "127.0.0.1") else self.host
        print(f"🌐 [MiniApp Server] Сервер запущен: http://{display_host}:{self.port}")
        print(f"📁 [MiniApp Server] Раздача статики из: {WEBAPP_DIR.resolve()}")

        if in_thread:
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name="MiniAppServerThread")
            self.thread.start()
        else:
            try:
                self.httpd.serve_forever()
            except KeyboardInterrupt:
                self.stop()

    def stop(self) -> None:
        """Останавливает сервер."""
        if self.httpd:
            print("🛑 [MiniApp Server] Остановка веб-сервера...")
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


_global_server: MiniAppServer | None = None


def start_webapp_server(host: str = "0.0.0.0", port: int = 8080, in_thread: bool = True) -> MiniAppServer:
    """Глобальная функция запуска веб-сервера Mini App."""
    global _global_server
    if _global_server is not None:
        return _global_server
    server = MiniAppServer(host=host, port=port)
    server.start(in_thread=in_thread)
    _global_server = server
    return server


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8080
    host_arg = os.environ.get("WEBAPP_HOST", "0.0.0.0")
    print("=" * 60)
    print(" 🚀 Запуск автономного веб-сервера Telegram Mini App")
    print(f" Локальный адрес: http://localhost:{port_arg}")
    print(" Для остановки нажмите Ctrl+C")
    print("=" * 60)
    server = MiniAppServer(host=host_arg, port=port_arg)
    server.start(in_thread=False)
