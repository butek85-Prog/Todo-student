#!/usr/bin/env python3
"""
Основное ASGI / FastAPI приложение для сервера (Production / Cloud Deployment).
Запуск на сервере: uvicorn main:app --host 0.0.0.0 --port $PORT

Объединяет:
- REST API для управления задачами (совместимо с index.html и webapp/);
- Статический веб-интерфейс и Telegram Mini App;
- Автоматический фоновый запуск Telegram-бота через FastAPI lifespan.
"""

import html
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Загружаем окружение из .env
import todo
import bot

BASE_DIR = Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"
INDEX_HTML = BASE_DIR / "index.html"


# ===================== LIFESPAN (ФОНОВЫЙ ЗАПУСК БОТА) =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом: автоматический старт бота в фоновом потоке."""
    start_bot_flag = os.environ.get("START_BOT", "true").strip().lower() in ("true", "1", "yes")
    token = bot.get_bot_token()

    if start_bot_flag and token:
        print("🤖 [Server Lifespan] Запуск Telegram-бота в фоновом режиме...", flush=True)
        bot_thread = threading.Thread(target=bot.run_bot, daemon=True, name="TelegramBotThread")
        bot_thread.start()
    elif not token:
        print("⚠️ [Server Lifespan] BOT_TOKEN не задан. Бот не запущен, работает только веб-сервер.", flush=True)

    yield

    print("🛑 [Server Lifespan] Сервер завершает работу.", flush=True)


app = FastAPI(
    title="Todo Planner API & Mini App",
    description="REST API и веб-интерфейс для планировщика задач с интеграцией Telegram.",
    version="2.0.0",
    lifespan=lifespan,
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

def get_effective_user_id(user_id: Any = None) -> Optional[str]:
    """Возвращает user_id с учётом значения по умолчанию из .env."""
    if user_id is None or not isinstance(user_id, (str, int)):
        return os.environ.get("DEFAULT_USER_ID", "5265404800")
    s = str(user_id).strip()
    if s in ("", "default", "null", "undefined"):
        return os.environ.get("DEFAULT_USER_ID", "5265404800")
    if s.lower() == "local":
        return None
    return s


def get_all_users() -> list[dict[str, Any]]:
    """Возвращает список всех найденных пользователей и общий список tasks.json."""
    users = []
    
    # 1. Локальный список задач
    default_tasks = todo.load_tasks("local")
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
    user_tasks_dir = todo.USER_TASKS_DIR
    if user_tasks_dir.exists():
        for file in sorted(user_tasks_dir.glob("*.json")):
            uid = file.stem
            tasks = todo.load_tasks(uid)
            done_cnt = sum(1 for t in tasks if t.get("done"))
            users.append({
                "id": uid,
                "name": f"👤 Telegram ID: {uid}",
                "is_default": False,
                "total": len(tasks),
                "done": done_cnt,
                "pending": len(tasks) - done_cnt,
            })

    return users


# ===================== REST API ЭНДПОИНТЫ =====================

@app.get("/api/health")
def api_health():
    """Проверка жизнеспособности сервера."""
    return {"ok": True, "status": "running"}


@app.get("/api/users")
def api_users():
    """Список баз данных пользователей."""
    def_uid = os.environ.get("DEFAULT_USER_ID", "5265404800")
    return {
        "ok": True,
        "users": get_all_users(),
        "default_user_id": def_uid,
    }


@app.get("/api/tasks")
def api_get_tasks(user_id: Optional[str] = Query(None)):
    """Получение списка задач с фильтрацией по пользователю."""
    eff_uid = get_effective_user_id(user_id)
    tasks = todo.load_tasks(eff_uid)
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("done"))
    pending = total - done
    percent = round((done / total * 100)) if total > 0 else 0

    return {
        "ok": True,
        "user_id": eff_uid or "default",
        "tasks": tasks,
        "count": total,
        "stats": {
            "total": total,
            "done": done,
            "pending": pending,
            "percent": percent,
        },
    }


@app.post("/api/tasks", status_code=status.HTTP_201_CREATED)
def api_create_task(payload: dict = Body(...)):
    """Создание новой задачи."""
    text = payload.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст задачи не может быть пустым")

    user_id = get_effective_user_id(payload.get("user_id"))
    reminder = payload.get("reminder")
    new_task = todo.add_task(text, user_id=user_id, reminder=reminder)
    return {
        "ok": True,
        "task": new_task,
        "user_id": user_id or "default",
    }


# Поддержка переключения статуса: 2 формата (REST /:id/toggle и body /toggle)
@app.post("/api/tasks/{task_id}/toggle")
def api_toggle_task_path(task_id: int, payload: dict = Body(default={})):
    """Переключение статуса задачи (формат пути /:id/toggle)."""
    user_id = get_effective_user_id(payload.get("user_id"))
    updated = todo.toggle_task(task_id, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Задача #{task_id} не найдена")
    return {"ok": True, "task": updated, "user_id": user_id or "default"}


@app.post("/api/tasks/toggle")
def api_toggle_task_body(payload: dict = Body(...)):
    """Переключение статуса задачи (формат body {"id": ...})."""
    task_id = payload.get("id") or payload.get("task_id")
    if task_id is None:
        raise HTTPException(status_code=400, detail="ID задачи обязателен")
    user_id = get_effective_user_id(payload.get("user_id"))
    updated = todo.toggle_task(int(task_id), user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Задача #{task_id} не найдена")
    return {"ok": True, "task": updated, "user_id": user_id or "default"}


# Установка напоминания
@app.post("/api/tasks/{task_id}/reminder")
def api_set_task_reminder(task_id: int, payload: dict = Body(...)):
    """Установка или сброс напоминания задачи."""
    user_id = get_effective_user_id(payload.get("user_id"))
    reminder_val = payload.get("reminder")
    updated = todo.set_task_reminder(task_id, reminder_val, user_id=user_id)
    if updated is None:
        raise HTTPException(status_code=400, detail="Неверный формат времени или задача не найдена")
    return {"ok": True, "task": updated, "user_id": user_id or "default"}


# Редактирование задачи
@app.post("/api/tasks/{task_id}/edit")
@app.put("/api/tasks/{task_id}")
def api_edit_task(task_id: int, payload: dict = Body(...)):
    """Изменение текста, напоминания или статуса задачи."""
    user_id = get_effective_user_id(payload.get("user_id"))
    new_text = payload.get("text")
    is_done = payload.get("done")
    new_rem = payload.get("reminder")

    task = None
    if (new_text is not None or new_rem is not None) and hasattr(todo, "edit_task"):
        task = todo.edit_task(task_id, new_text=new_text, reminder=new_rem, user_id=user_id)
    if is_done is not None:
        task = todo.set_task_done(task_id, bool(is_done), user_id=user_id)

    if not task:
        # Если статус не изменился через edit_task, пробуем найти задачу
        tasks = todo.load_tasks(user_id)
        task = next((t for t in tasks if t.get("id") == task_id), None)

    if not task:
        raise HTTPException(status_code=404, detail=f"Задача #{task_id} не найдена")

    return {"ok": True, "task": task, "user_id": user_id or "default"}



# Удаление задачи: 2 формата (DELETE /:id и POST /delete)
@app.delete("/api/tasks/{task_id}")
def api_delete_task_path(task_id: int, user_id: Optional[str] = Query(None)):
    """Удаление задачи (DELETE /api/tasks/:id)."""
    eff_uid = get_effective_user_id(user_id)
    if todo.delete_task(task_id, user_id=eff_uid):
        return {"ok": True, "deleted_id": task_id, "user_id": eff_uid or "default"}
    raise HTTPException(status_code=404, detail=f"Задача #{task_id} не найдена")


@app.post("/api/tasks/delete")
def api_delete_task_body(payload: dict = Body(...)):
    """Удаление задачи (POST /api/tasks/delete)."""
    task_id = payload.get("id") or payload.get("task_id")
    if task_id is None:
        raise HTTPException(status_code=400, detail="ID задачи обязателен")
    user_id = get_effective_user_id(payload.get("user_id"))
    if todo.delete_task(int(task_id), user_id=user_id):
        return {"ok": True, "deleted_id": int(task_id), "user_id": user_id or "default"}
    raise HTTPException(status_code=404, detail=f"Задача #{task_id} не найдена")


# Очистка выполненных задач: 2 формата URL
@app.post("/api/tasks/clear-completed")
@app.post("/api/tasks/clear_completed")
def api_clear_completed(payload: dict = Body(default={})):
    """Удаление всех выполненных задач."""
    user_id = get_effective_user_id(payload.get("user_id"))
    if hasattr(todo, "clear_completed_tasks"):
        removed = todo.clear_completed_tasks(user_id=user_id)
    else:
        tasks = todo.load_tasks(user_id)
        active = [t for t in tasks if not t.get("done")]
        removed = len(tasks) - len(active)
        todo.save_tasks(active, user_id)
    return {"ok": True, "cleared_count": removed, "user_id": user_id or "default"}


# Эмулятор Telegram-бота для браузера
@app.post("/api/bot/chat")
def api_bot_chat(payload: dict = Body(...)):
    """Эмуляция текстового сообщения боту."""
    text = payload.get("message", "").strip()
    user_id = get_effective_user_id(payload.get("user_id"))

    if not text:
        raise HTTPException(status_code=400, detail="Пустое сообщение")

    reply_text = ""
    if text.startswith("/start"):
        reply_text = (
            f"👋 <b>Привет!</b> Я эмулятор Telegram-бота.\n"
            f"Ваш ID: <code>{user_id}</code>\n"
            "Все задачи синхронизированы с базой данных."
        )
    elif text.startswith("/list"):
        reply_text, _ = bot.format_tasks_view(user_id)
    elif text.startswith("/remind") or text.startswith("/rem"):
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            reply_text = (
                "⚠️ Укажите ID задачи и время напоминания.\n\n"
                "Примеры:\n"
                "• <code>/remind 1 18:00</code>\n"
                "• <code>/remind 1 15m</code>\n"
                "• <code>/remind 1 завтра 09:30</code>\n"
                "• <code>/remind 1 отмена</code>"
            )
        else:
            try:
                task_id = int(parts[1])
                rem_val = parts[2].strip()
                updated = todo.set_task_reminder(task_id, rem_val, user_id=user_id)
                if updated is None:
                    reply_text = f"❌ Не удалось распознать время «{html.escape(rem_val)}» или задача #{task_id} не найдена."
                elif updated.get("reminder"):
                    disp = todo.format_reminder_display(updated.get("reminder"))
                    reply_text = f"⏰ Напоминание для #{task_id} установлено: <b>{disp}</b>"
                else:
                    reply_text = f"Напоминание для #{task_id} отключено."
            except ValueError:
                reply_text = "⚠️ ID задачи должен быть числом.\nПример: <code>/remind 1 18:00</code>"
    elif text.startswith("/add"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            raw_add = parts[1].strip()
            rem_val = None
            if " -r " in raw_add or " --remind " in raw_add:
                match = re.search(r"\s+(-r|--remind)\s+(.+)$", raw_add)
                if match:
                    rem_val = match.group(2).strip()
                    raw_add = raw_add[:match.start()].strip()
            task = todo.add_task(raw_add, user_id=user_id, reminder=rem_val)
            rem_info = f" (⏰ {todo.format_reminder_display(task.get('reminder'))})" if task.get("reminder") else ""
            reply_text = f"✅ Задача добавлена (<b>ID: {task['id']}</b>):\n«{html.escape(task['text'])}»{rem_info}"
        else:
            reply_text = "⚠️ Укажите текст задачи: <code>/add Текст</code>"
    else:
        # Просто текст — добавляем как задачу
        task = todo.add_task(text, user_id=user_id)
        reply_text = f"✅ Создана задача (<b>ID: {task['id']}</b>):\n«{html.escape(task['text'])}»"

    view_text, markup = bot.format_tasks_view(user_id)
    return {
        "ok": True,
        "reply": reply_text,
        "view": view_text,
        "markup": markup,
        "keyboard": bot.get_main_reply_keyboard(),
    }


@app.post("/api/bot/callback")
def api_bot_callback(payload: dict = Body(...)):
    """Эмуляция нажатия на инлайн-кнопку бота."""
    data = payload.get("data", "")
    user_id = get_effective_user_id(payload.get("user_id"))

    toast = ""
    if data.startswith("toggle:"):
        tid = int(data.split(":")[1])
        t = todo.toggle_task(tid, user_id=user_id)
        toast = f"Задача #{tid} {'выполнена ✅' if t and t.get('done') else 'возвращена в работу ⬜️'}"
    elif data.startswith("del:"):
        tid = int(data.split(":")[1])
        todo.delete_task(tid, user_id=user_id)
        toast = f"Задача #{tid} удалена 🗑️"
    elif data.startswith("rem_menu:"):
        tid = int(data.split(":")[1])
        view_text, markup = bot.format_reminder_menu(tid, user_id)
        return {
            "ok": True,
            "toast": "Настройка напоминания",
            "view_text": view_text,
            "inline_keyboard": markup.get("inline_keyboard", []),
        }
    elif data.startswith("set_rem:"):
        parts = data.split(":")
        tid = int(parts[1])
        preset = parts[2]
        preset_map = {
            "15m": "15m",
            "1h": "1h",
            "3h": "3h",
            "today_18": "сегодня 18:00",
            "tomorrow_09": "завтра 09:00",
            "tomorrow_18": "завтра 18:00",
            "cancel": "отмена",
        }
        val = preset_map.get(preset, preset)
        t = todo.set_task_reminder(tid, val, user_id=user_id)
        if t and t.get("reminder"):
            toast = f"⏰ Установлено: {todo.format_reminder_display(t.get('reminder'))}"
        else:
            toast = "Напоминание выключено"
    elif data == "refresh":
        toast = "Список обновлён 🔄"

    view_text, markup = bot.format_tasks_view(user_id)
    return {
        "ok": True,
        "toast": toast,
        "view": view_text,
        "view_text": view_text,
        "markup": markup,
        "inline_keyboard": markup.get("inline_keyboard", []),
    }


# ===================== СТАТИЧЕСКИЕ СТРАНИЦЫ И РАЗДАЧА =====================

# 1. Раздача Telegram Mini App (папка webapp/)
if WEBAPP_DIR.exists() and WEBAPP_DIR.is_dir():
    app.mount("/webapp", StaticFiles(directory=str(WEBAPP_DIR), html=True), name="webapp")


@app.get("/mini-app", response_class=HTMLResponse)
def get_mini_app():
    """Быстрый доступ к Telegram Mini App."""
    mini_app_file = WEBAPP_DIR / "index.html"
    if mini_app_file.exists():
        return FileResponse(mini_app_file)
    return HTMLResponse("<h3>Mini App не найден</h3>", status_code=404)


# 2. Главная страница (Веб-интерфейс + эмулятор)
@app.get("/", response_class=HTMLResponse)
def get_index():
    """Главная страница веб-планировщика."""
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return HTMLResponse("<h3>index.html не найден</h3>", status_code=404)


# ===================== ПРЯМОЙ ЗАПУСК ЧЕРЕЗ PYTHON =====================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"🚀 Запуск FastAPI + Uvicorn сервера на http://{host}:{port} ...", flush=True)
    uvicorn.run("main:app", host=host, port=port, reload=False)
