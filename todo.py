#!/usr/bin/env python3
"""
Мини-планировщик задач (Todo App для Windows)
Поддерживает как графический оконный интерфейс (GUI), так и работу через командную строку (CLI).
"""

import datetime
import json
import os
import re
import sys
from pathlib import Path

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

# Расположение файла tasks.json: рядом с .exe или рядом со скриптом
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

TASKS_FILE = BASE_DIR / "tasks.json"
USER_TASKS_DIR = BASE_DIR / "user_tasks"
ENV_FILE = BASE_DIR / ".env"


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


load_env_file()


def get_default_user_id() -> str:
    """Возвращает ID пользователя по умолчанию из окружения (например, из .env) или основного пользователя бота."""
    uid = os.environ.get("DEFAULT_USER_ID")
    if uid and uid.strip() and uid.strip().lower() not in ("local", "default"):
        return uid.strip()
    return "5265404800"


def get_tasks_file(user_id: str | int | None = None) -> Path:
    """Возвращает путь к файлу задач: персональный user_tasks/{user_id}.json."""
    if user_id is None or str(user_id).lower() in ("local", "default"):
        user_id = get_default_user_id()

    USER_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(c for c in str(user_id) if c.isalnum() or c in ("-", "_"))
    if not safe_id:
        safe_id = get_default_user_id()
    return USER_TASKS_DIR / f"{safe_id}.json"


# ===================== БАЗОВЫЕ ФУНКЦИИ ХРАНИЛИЩА =====================

def load_tasks(user_id: str | int | None = None) -> list[dict]:
    """Загружает список задач из файла (для пользователя user_id или общий tasks.json)."""
    filepath = get_tasks_file(user_id)
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, OSError) as e:
        print(f"Предупреждение: ошибка чтения {filepath.name} ({e}).", file=sys.stderr)
        return []


def save_tasks(tasks: list[dict], user_id: str | int | None = None) -> None:
    """Сохраняет список задач в файл (для пользователя user_id или общий tasks.json)."""
    filepath = get_tasks_file(user_id)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def parse_reminder_datetime(text: str | None) -> str | None:
    """Парсит гибкие форматы времени и возвращает строку 'YYYY-MM-DD HH:MM' или None."""
    if not text:
        return None
    s = text.strip().lower()
    if s in ("none", "cancel", "отмена", "удалить", "нет", "0", "clear", "off", "-", "null"):
        return ""

    now = datetime.datetime.now()

    # Быстрые фразы
    if s in ("через час", "час"):
        return (now + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    if s in ("через полчаса", "полчаса"):
        return (now + datetime.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")
    if s in ("через день", "завтра"):
        return (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")

    # Относительное время: '+15m', '15m', '15м', 'через 15 минут', '2 часа', '1 день'
    m_rel = re.match(r"^(?:\+|(?:через\s+))?(\d+)\s*(m|min|м|мин|минут[уыа]?|h|ч|час|часа|часов|d|д|дн|дней|день|дня)?$", s)
    if m_rel:
        val = int(m_rel.group(1))
        unit = m_rel.group(2) or "m"
        if unit in ("m", "min", "м", "мин", "минут", "минута", "минуты"):
            dt = now + datetime.timedelta(minutes=val)
        elif unit in ("h", "ч", "час", "часа", "часов"):
            dt = now + datetime.timedelta(hours=val)
        elif unit in ("d", "д", "дн", "дней", "день", "дня"):
            dt = now + datetime.timedelta(days=val)
        else:
            dt = now + datetime.timedelta(minutes=val)
        return dt.strftime("%Y-%m-%d %H:%M")

    # 'сегодня' / 'завтра' / 'послезавтра' + время: 'завтра 15:30', 'сегодня в 18:00'
    m_word = re.match(r"^(сегодня|завтра|послезавтра)(?:\s+в)?\s+(\d{1,2})[:\.](\d{2})$", s)
    if m_word:
        day_type = m_word.group(1)
        h = int(m_word.group(2))
        mi = int(m_word.group(3))
        if day_type == "сегодня":
            target_date = now.date()
        elif day_type == "завтра":
            target_date = now.date() + datetime.timedelta(days=1)
        else:
            target_date = now.date() + datetime.timedelta(days=2)
        try:
            dt = datetime.datetime.combine(target_date, datetime.time(h, mi))
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return None

    # Просто время: '18:30' или '18.30'
    m_time = re.match(r"^(\d{1,2})[:\.](\d{2})$", s)
    if m_time:
        h = int(m_time.group(1))
        mi = int(m_time.group(2))
        try:
            dt = datetime.datetime.combine(now.date(), datetime.time(h, mi))
            if dt <= now:
                dt += datetime.timedelta(days=1)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return None

    # ДД.ММ [ГГГГ] ЧЧ:ММ
    m_date = re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?(?:\s+в)?\s+(\d{1,2})[:\.](\d{2})$", s)
    if m_date:
        d = int(m_date.group(1))
        m = int(m_date.group(2))
        y = int(m_date.group(3)) if m_date.group(3) else now.year
        h = int(m_date.group(4))
        mi = int(m_date.group(5))
        try:
            dt = datetime.datetime(y, m, d, h, mi)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return None

    # ISO формат: ГГГГ-ММ-ДД[T| ]ЧЧ:ММ
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})[t\s](\d{1,2}):(\d{2})(?::\d{2})?$", s)
    if m_iso:
        y, m, d, h, mi = map(int, m_iso.groups())
        try:
            dt = datetime.datetime(y, m, d, h, mi)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return None

    return None


def format_reminder_display(reminder: str | None) -> str:
    """Возвращает понятную человеку строку напоминания (например, 'Сегодня в 18:00')."""
    if not reminder:
        return ""
    try:
        dt = datetime.datetime.strptime(reminder, "%Y-%m-%d %H:%M")
        now = datetime.datetime.now()
        is_past = dt < now
        warn = " (⚠️)" if is_past else ""
        time_str = dt.strftime("%H:%M")
        if dt.date() == now.date():
            return f"Сегодня в {time_str}{warn}"
        elif dt.date() == (now + datetime.timedelta(days=1)).date():
            return f"Завтра в {time_str}{warn}"
        else:
            return f"{dt.strftime('%d.%m')} в {time_str}{warn}"
    except Exception:
        return str(reminder)


def add_task(text: str, user_id: str | int | None = None, reminder: str | None = None) -> dict:
    """Добавляет задачу для указанного пользователя и возвращает её."""
    tasks = load_tasks(user_id)
    new_id = max((t.get("id", 0) for t in tasks), default=0) + 1
    parsed_rem = parse_reminder_datetime(reminder) if reminder else None
    new_task = {
        "id": new_id,
        "text": text.strip(),
        "done": False,
        "reminder": parsed_rem if parsed_rem else None,
        "reminded": False,
    }
    tasks.append(new_task)
    save_tasks(tasks, user_id)
    return new_task


def set_task_done(task_id: int, done: bool = True, user_id: str | int | None = None) -> dict | None:
    """Устанавливает статус выполнения задачи для конкретного пользователя."""
    tasks = load_tasks(user_id)
    for task in tasks:
        if task.get("id") == task_id:
            task["done"] = done
            save_tasks(tasks, user_id)
            return task
    return None


def toggle_task(task_id: int, user_id: str | int | None = None) -> dict | None:
    """Переключает статус выполнения задачи для конкретного пользователя."""
    tasks = load_tasks(user_id)
    for task in tasks:
        if task.get("id") == task_id:
            task["done"] = not task.get("done", False)
            save_tasks(tasks, user_id)
            return task
    return None


def set_task_reminder(task_id: int, reminder_text: str | None, user_id: str | int | None = None) -> dict | None:
    """Устанавливает или сбрасывает напоминание для задачи."""
    tasks = load_tasks(user_id)
    for task in tasks:
        if task.get("id") == task_id:
            if not reminder_text:
                task["reminder"] = None
                task["reminded"] = False
            else:
                parsed = parse_reminder_datetime(reminder_text)
                if parsed == "":  # отмена
                    task["reminder"] = None
                    task["reminded"] = False
                elif parsed:
                    task["reminder"] = parsed
                    task["reminded"] = False
                else:
                    return None  # некорректный формат
            save_tasks(tasks, user_id)
            return task
    return None


def check_due_reminders(user_id: str | int | None = None) -> list[dict]:
    """Возвращает список невыполненных задач с наступившим временем напоминания."""
    tasks = load_tasks(user_id)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    due = []
    for task in tasks:
        if not task.get("done") and task.get("reminder"):
            if not task.get("reminded", False) and task["reminder"] <= now_str:
                due.append(task)
    return due


def mark_reminder_sent(task_id: int, user_id: str | int | None = None) -> bool:
    """Помечает напоминание задачи как отправленное."""
    tasks = load_tasks(user_id)
    for task in tasks:
        if task.get("id") == task_id:
            task["reminded"] = True
            save_tasks(tasks, user_id)
            return True
    return False


def delete_task(task_id: int, user_id: str | int | None = None) -> bool:
    """Удаляет задачу по ID для конкретного пользователя."""
    tasks = load_tasks(user_id)
    original_len = len(tasks)
    tasks = [t for t in tasks if t.get("id") != task_id]
    if len(tasks) != original_len:
        save_tasks(tasks, user_id)
        return True
    return False


def edit_task(
    task_id: int,
    new_text: str | None = None,
    reminder: str | None = None,
    user_id: str | int | None = None,
) -> dict | None:
    """Изменяет текст и/или напоминание задачи по ID."""
    tasks = load_tasks(user_id)
    for task in tasks:
        if task.get("id") == task_id:
            if new_text is not None:
                task["text"] = str(new_text).strip()
            if reminder is not None:
                parsed = parse_reminder_datetime(reminder)
                if parsed == "":
                    task["reminder"] = None
                    task["reminded"] = False
                elif parsed:
                    task["reminder"] = parsed
                    task["reminded"] = False
            save_tasks(tasks, user_id)
            return task
    return None


def clear_completed_tasks(user_id: str | int | None = None) -> int:
    """Удаляет все выполненные задачи для конкретного пользователя и возвращает количество удаленных."""
    tasks = load_tasks(user_id)
    active_tasks = [t for t in tasks if not t.get("done")]
    removed_count = len(tasks) - len(active_tasks)
    if removed_count > 0:
        save_tasks(active_tasks, user_id)
    return removed_count



# ===================== CLI РЕЖИМ =====================

def get_prog_name() -> str:
    """Возвращает имя программы для отображения в подсказках."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).name
    script_name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "todo.py"
    return f"python {script_name}"


def print_help() -> None:
    """Выводит справку по использованию CLI."""
    prog = get_prog_name()
    help_text = f"""
Мини-планировщик задач
======================
Использование (CLI):
  {prog} add "<текст>" [-r "<время>"]  - Добавить задачу (опционально с напоминанием)
  {prog} list                          - Показать список всех задач
  {prog} done <id>                     - Отметить задачу как выполненную
  {prog} remind <id> "<время>"         - Установить/снять напоминание (напр. '18:00', '15m', 'отмена')
  {prog} help                          - Показать эту подсказку

Без параметров:
  {prog}                               - Запустить графическое окно Windows (GUI)

Примеры:
  {prog} add "Купить продукты" -r "18:00"
  {prog} remind 1 "завтра 10:00"
  {prog} list
  {prog} done 1
"""
    print(help_text.strip())


def cmd_add(args: list[str]) -> None:
    reminder_val = None
    clean_args = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--remind", "-r") and i + 1 < len(args):
            reminder_val = args[i + 1]
            i += 2
        else:
            clean_args.append(a)
            i += 1

    text = " ".join(clean_args).strip()
    if not text:
        prog = get_prog_name()
        print("Ошибка: текст задачи не может быть пустым.")
        print(f'Пример: {prog} add "Купить продукты" -r "18:00"')
        sys.exit(1)

    task = add_task(text, reminder=reminder_val)
    rem_info = ""
    if task.get("reminder"):
        rem_info = f" [⏰ {format_reminder_display(task.get('reminder'))}]"
    print(f'Задача добавлена (ID: {task["id"]}): "{task["text"]}"{rem_info}')


def cmd_remind(args: list[str]) -> None:
    prog = get_prog_name()
    if len(args) < 2:
        print("Ошибка: укажите ID задачи и время напоминания.")
        print(f'Пример: {prog} remind 1 "18:00"  (или "15m", "завтра 09:00", "отмена")')
        sys.exit(1)

    try:
        task_id = int(args[0])
    except ValueError:
        print(f"Ошибка: ID задачи должен быть числом, получено '{args[0]}'.")
        sys.exit(1)

    rem_text = " ".join(args[1:]).strip()
    updated = set_task_reminder(task_id, rem_text)
    if updated is None:
        print(f"Ошибка: не удалось распознать формат времени '{rem_text}' или задача не найдена.")
        sys.exit(1)

    if updated.get("reminder"):
        disp = format_reminder_display(updated.get("reminder"))
        print(f'Напоминание для задачи #{task_id} установлено: ⏰ {disp}')
    else:
        print(f'Напоминание для задачи #{task_id} отключено.')


def cmd_list() -> None:
    tasks = load_tasks()
    if not tasks:
        prog = get_prog_name()
        print("Список задач пуст.")
        print(f'Добавьте задачу с помощью: {prog} add "Текст задачи"')
        return

    print("Список задач:")
    for task in tasks:
        icon = "✅" if task.get("done") else "⬜️"
        task_id = task.get("id")
        task_text = task.get("text", "")
        rem_str = ""
        if task.get("reminder"):
            rem_str = f"  [⏰ {format_reminder_display(task.get('reminder'))}]"
        print(f"  {icon} {task_id}. {task_text}{rem_str}")


def cmd_done(args: list[str]) -> None:
    prog = get_prog_name()
    if not args:
        print("Ошибка: укажите ID задачи.")
        print(f"Пример: {prog} done 1")
        sys.exit(1)

    try:
        task_id = int(args[0])
    except ValueError:
        print(f"Ошибка: ID задачи должен быть числом, получено '{args[0]}'.")
        print(f"Пример: {prog} done 1")
        sys.exit(1)

    task = set_task_done(task_id, True)
    if task is None:
        print(f"Ошибка: задача с ID {task_id} не найдена.")
        sys.exit(1)

    print(f'Задача {task_id} отмечена как выполненная (✅): "{task.get("text")}"')



# ===================== GUI РЕЖИМ (WINDOWS APP) =====================

def run_gui() -> None:
    """Запускает графический интерфейс для Windows."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    # Поддержка четких шрифтов на High-DPI экранах Windows
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    root.title("Планировщик задач")
    root.geometry("640x560")
    root.minsize(500, 400)

    # Устанавливаем стиль оформления
    style = ttk.Style(root)
    available_themes = style.theme_names()
    if "vista" in available_themes:
        style.theme_use("vista")
    elif "clam" in available_themes:
        style.theme_use("clam")

    # Конфигурация шрифтов
    FONT_FAMILY = "Segoe UI"
    style.configure(".", font=(FONT_FAMILY, 10))
    style.configure("Treeview", font=(FONT_FAMILY, 10), rowheight=28)
    style.configure("Treeview.Heading", font=(FONT_FAMILY, 10, "bold"))
    style.configure("Title.TLabel", font=(FONT_FAMILY, 15, "bold"))
    style.configure("Subtitle.TLabel", font=(FONT_FAMILY, 9), foreground="#555555")
    style.configure("Status.TLabel", font=(FONT_FAMILY, 9), foreground="#444444")
    style.configure("Primary.TButton", font=(FONT_FAMILY, 10, "bold"))

    # Основной контейнер с отступами
    main_frame = ttk.Frame(root, padding="16 14 16 12")
    main_frame.pack(fill=tk.BOTH, expand=True)

    # Верхний заголовок
    header_frame = ttk.Frame(main_frame)
    header_frame.pack(fill=tk.X, pady=(0, 12))

    lbl_title = ttk.Label(header_frame, text="📋 Планировщик задач", style="Title.TLabel")
    lbl_title.pack(anchor="w")
    lbl_sub = ttk.Label(header_frame, text="Добавляйте задачи и отмечайте их выполнение", style="Subtitle.TLabel")
    lbl_sub.pack(anchor="w", pady=(2, 0))

    # Блок ввода новой задачи
    input_frame = ttk.Frame(main_frame)
    input_frame.pack(fill=tk.X, pady=(0, 10))

    entry_task = ttk.Entry(input_frame, font=(FONT_FAMILY, 11))
    entry_task.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=4)
    entry_task.focus_set()

    # Фильтры
    filter_var = tk.StringVar(value="all")

    filter_frame = ttk.Frame(main_frame)
    filter_frame.pack(fill=tk.X, pady=(0, 8))

    lbl_filter = ttk.Label(filter_frame, text="Показать:", font=(FONT_FAMILY, 9, "bold"))
    lbl_filter.pack(side=tk.LEFT, padx=(0, 10))

    # Таблица задач (Treeview)
    tree_frame = ttk.Frame(main_frame)
    tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

    columns = ("id", "status", "reminder", "text")
    tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
    tree.heading("id", text="ID")
    tree.heading("status", text="Статус")
    tree.heading("reminder", text="⏰ Напоминание")
    tree.heading("text", text="Текст задачи")

    tree.column("id", width=45, minwidth=35, anchor="center")
    tree.column("status", width=65, minwidth=50, anchor="center")
    tree.column("reminder", width=145, minwidth=110, anchor="w")
    tree.column("text", width=340, minwidth=200, anchor="w")

    scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)

    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Статусная строка
    lbl_stats = ttk.Label(main_frame, text="", style="Status.TLabel")
    lbl_stats.pack(anchor="w", pady=(0, 8))

    # Панель кнопок действий
    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(fill=tk.X)

    def refresh_task_list() -> None:
        """Перезагружает и отображает задачи согласно выбранному фильтру."""
        current_selection = tree.selection()
        selected_id = None
        if current_selection:
            item_vals = tree.item(current_selection[0], "values")
            if item_vals:
                selected_id = str(item_vals[0])

        tree.delete(*tree.get_children())
        tasks = load_tasks()

        total = len(tasks)
        done_count = sum(1 for t in tasks if t.get("done"))
        pending_count = total - done_count

        current_filter = filter_var.get()
        if current_filter == "active":
            filtered_tasks = [t for t in tasks if not t.get("done")]
        elif current_filter == "done":
            filtered_tasks = [t for t in tasks if t.get("done")]
        else:
            filtered_tasks = tasks

        item_to_select = None
        for t in filtered_tasks:
            status_icon = "✅" if t.get("done") else "⬜️"
            task_id_str = str(t.get("id"))
            rem_str = format_reminder_display(t.get("reminder"))
            item_id = tree.insert("", tk.END, values=(t.get("id"), status_icon, rem_str, t.get("text")))
            if task_id_str == selected_id:
                item_to_select = item_id

        if item_to_select:
            tree.selection_set(item_to_select)

        lbl_stats.config(
            text=f"Всего: {total}  •  Выполнено: {done_count}  •  Осталось: {pending_count}    |    (Двойной клик: переключить)"
        )

    def on_add_task() -> None:
        """Обработчик добавления задачи."""
        text = entry_task.get().strip()
        if not text:
            messagebox.showwarning("Внимание", "Пожалуйста, введите текст задачи.")
            entry_task.focus_set()
            return
        add_task(text)
        entry_task.delete(0, tk.END)
        refresh_task_list()

    def get_selected_task_id() -> int | None:
        selection = tree.selection()
        if not selection:
            return None
        values = tree.item(selection[0], "values")
        if not values:
            return None
        try:
            return int(values[0])
        except (ValueError, TypeError):
            return None

    def on_toggle_task() -> None:
        """Переключает статус выполнения выбранной задачи."""
        task_id = get_selected_task_id()
        if task_id is None:
            messagebox.showinfo("Подсказка", "Выберите задачу из списка, чтобы изменить её статус.")
            return
        toggle_task(task_id)
        refresh_task_list()

    def on_set_reminder() -> None:
        """Устанавливает или изменяет напоминание для выбранной задачи."""
        task_id = get_selected_task_id()
        if task_id is None:
            messagebox.showinfo("Подсказка", "Выберите задачу из списка, чтобы установить напоминание.")
            return
        import tkinter.simpledialog as sd
        ans = sd.askstring(
            "⏰ Напоминание к задаче",
            f"Введите время напоминания для задачи #{task_id}:\n\n"
            "Примеры:\n"
            "• 15m или 30 мин (через сколько минут)\n"
            "• 18:00 (сегодня или завтра)\n"
            "• завтра 09:30\n"
            "• отмена (чтобы выключить напоминание)",
            parent=root,
        )
        if ans is not None and ans.strip():
            updated = set_task_reminder(task_id, ans.strip())
            if updated is None:
                messagebox.showerror("Ошибка", f"Не удалось распознать формат времени: '{ans}'.")
            else:
                refresh_task_list()

    def on_delete_task() -> None:
        """Удаляет выбранную задачу с подтверждением."""
        task_id = get_selected_task_id()
        if task_id is None:
            messagebox.showinfo("Подсказка", "Выберите задачу из списка для удаления.")
            return
        if messagebox.askyesno("Подтверждение", f"Удалить задачу с ID {task_id}?"):
            delete_task(task_id)
            refresh_task_list()

    def check_reminders_gui() -> None:
        """Фоновая проверка напоминаний в графическом интерфейсе."""
        try:
            due = check_due_reminders()
            for t in due:
                mark_reminder_sent(t.get("id"))
                messagebox.showinfo(
                    "⏰ Напоминание о задаче!",
                    f"Наступило время задачи #{t.get('id')}:\n\n«{t.get('text')}»"
                )
                refresh_task_list()
        except Exception:
            pass
        root.after(10000, check_reminders_gui)

    root.after(5000, check_reminders_gui)

    btn_add = ttk.Button(input_frame, text="➕ Добавить", style="Primary.TButton", command=on_add_task)
    btn_add.pack(side=tk.RIGHT)
    entry_task.bind("<Return>", lambda e: on_add_task())

    # Фильтры-радиокнопки
    rb_all = ttk.Radiobutton(filter_frame, text="Все", variable=filter_var, value="all", command=refresh_task_list)
    rb_all.pack(side=tk.LEFT, padx=4)
    rb_active = ttk.Radiobutton(filter_frame, text="Активные", variable=filter_var, value="active", command=refresh_task_list)
    rb_active.pack(side=tk.LEFT, padx=4)
    rb_done = ttk.Radiobutton(filter_frame, text="Выполненные", variable=filter_var, value="done", command=refresh_task_list)
    rb_done.pack(side=tk.LEFT, padx=4)

    # Кнопки под таблицей
    btn_toggle = ttk.Button(btn_frame, text="✅ Выполнить / Вернуть", command=on_toggle_task)
    btn_toggle.pack(side=tk.LEFT, padx=(0, 6))

    btn_remind = ttk.Button(btn_frame, text="⏰ Напомнить", command=on_set_reminder)
    btn_remind.pack(side=tk.LEFT, padx=(0, 6))

    btn_delete = ttk.Button(btn_frame, text="🗑️ Удалить", command=on_delete_task)
    btn_delete.pack(side=tk.LEFT, padx=(0, 6))

    btn_refresh = ttk.Button(btn_frame, text="🔄 Обновить", command=refresh_task_list)
    btn_refresh.pack(side=tk.LEFT)

    # Привязка горячих клавиш к таблице
    tree.bind("<Double-1>", lambda e: on_toggle_task())
    tree.bind("<space>", lambda e: on_toggle_task())
    tree.bind("<Delete>", lambda e: on_delete_task())

    # Начальная загрузка списка
    refresh_task_list()

    # Центрирование окна на экране
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = max(0, (screen_w - w) // 2)
    y = max(0, (screen_h - h) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.mainloop()


# ===================== ТОЧКА ВХОДА =====================

def main() -> None:
    # Если аргументов нет — запускаем полноценное оконное приложение Windows
    if len(sys.argv) == 1:
        run_gui()
        return

    # Если переданы аргументы командной строки — работаем в режиме CLI
    if sys.platform == "win32":
        try:
            import ctypes
            # Если приложение скомпилировано в noconsole, подключаемся к родительской консоли для вывода
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8")
                sys.stderr = open("CONOUT$", "w", encoding="utf-8")
        except Exception:
            pass

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    if command == "add":
        cmd_add(args)
    elif command == "list":
        cmd_list()
    elif command == "done":
        cmd_done(args)
    elif command == "remind":
        cmd_remind(args)
    elif command in ("gui", "--gui", "-g"):
        run_gui()
    elif command in ("help", "-h", "--help"):
        print_help()
    else:
        print(f"Неизвестная команда: '{command}'\n")
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
