#!/usr/bin/env python3
"""
Мини-планировщик задач (Todo App для Windows)
Поддерживает как графический оконный интерфейс (GUI), так и работу через командную строку (CLI).
"""

import json
import os
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


def get_default_user_id() -> str | None:
    """Возвращает ID пользователя по умолчанию из окружения (например, из .env)."""
    uid = os.environ.get("DEFAULT_USER_ID")
    if uid and uid.strip() and uid.strip().lower() not in ("local", "default"):
        return uid.strip()
    return None


def get_tasks_file(user_id: str | int | None = None) -> Path:
    """Возвращает путь к файлу задач: либо общий tasks.json, либо персональный user_tasks/{user_id}.json."""
    if user_id is None:
        user_id = get_default_user_id()

    if user_id is None or str(user_id).lower() in ("local", "default"):
        return TASKS_FILE
    USER_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(c for c in str(user_id) if c.isalnum() or c in ("-", "_"))
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


def add_task(text: str, user_id: str | int | None = None) -> dict:
    """Добавляет задачу для указанного пользователя и возвращает её."""
    tasks = load_tasks(user_id)
    new_id = max((t.get("id", 0) for t in tasks), default=0) + 1
    new_task = {
        "id": new_id,
        "text": text.strip(),
        "done": False,
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


def delete_task(task_id: int, user_id: str | int | None = None) -> bool:
    """Удаляет задачу по ID для конкретного пользователя."""
    tasks = load_tasks(user_id)
    original_len = len(tasks)
    tasks = [t for t in tasks if t.get("id") != task_id]
    if len(tasks) != original_len:
        save_tasks(tasks, user_id)
        return True
    return False


def edit_task(task_id: int, new_text: str, user_id: str | int | None = None) -> dict | None:
    """Изменяет текст задачи по ID для конкретного пользователя."""
    tasks = load_tasks(user_id)
    for task in tasks:
        if task.get("id") == task_id:
            task["text"] = new_text.strip()
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
  {prog} add "<текст>"   - Добавить новую задачу
  {prog} list            - Показать список всех задач
  {prog} done <id>       - Отметить задачу как выполненную
  {prog} help            - Показать эту подсказку

Без параметров:
  {prog}                 - Запустить графическое окно Windows (GUI)

Примеры:
  {prog} add "Купить продукты"
  {prog} list
  {prog} done 1
"""
    print(help_text.strip())


def cmd_add(args: list[str]) -> None:
    text = " ".join(args).strip()
    if not text:
        prog = get_prog_name()
        print("Ошибка: текст задачи не может быть пустым.")
        print(f'Пример: {prog} add "Купить продукты"')
        sys.exit(1)
    task = add_task(text)
    print(f'Задача добавлена (ID: {task["id"]}): "{task["text"]}"')


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
        print(f"  {icon} {task_id}. {task_text}")


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

    columns = ("id", "status", "text")
    tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
    tree.heading("id", text="ID")
    tree.heading("status", text="Статус")
    tree.heading("text", text="Текст задачи")

    tree.column("id", width=55, minwidth=40, anchor="center")
    tree.column("status", width=75, minwidth=60, anchor="center")
    tree.column("text", width=420, minwidth=250, anchor="w")

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
            item_id = tree.insert("", tk.END, values=(t.get("id"), status_icon, t.get("text")))
            if task_id_str == selected_id:
                item_to_select = item_id

        if item_to_select:
            tree.selection_set(item_to_select)

        lbl_stats.config(
            text=f"Всего: {total}  •  Выполнено: {done_count}  •  Осталось: {pending_count}    |    (Двойной клик / Пробел: переключить статус)"
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

    def on_delete_task() -> None:
        """Удаляет выбранную задачу с подтверждением."""
        task_id = get_selected_task_id()
        if task_id is None:
            messagebox.showinfo("Подсказка", "Выберите задачу из списка для удаления.")
            return
        if messagebox.askyesno("Подтверждение", f"Удалить задачу с ID {task_id}?"):
            delete_task(task_id)
            refresh_task_list()

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
