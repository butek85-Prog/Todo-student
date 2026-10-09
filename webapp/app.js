/**
 * Todo Telegram Mini App - Клиентская логика
 * Интеграция с Telegram WebApp SDK и REST API планировщика.
 */

// Инициализация Telegram WebApp
const tg = window.Telegram?.WebApp;

if (tg) {
  tg.ready();
  tg.expand();
}

// Состояние приложения
const state = {
  userId: "5265404800",
  userName: "Пользователь",
  tasks: [],
  currentTab: "all",
  searchQuery: "",
  isLoading: false,
  lastTasksJson: "",
};

// DOM Элементы
const elements = {
  banner: document.getElementById("browser-banner"),
  bannerUserId: document.getElementById("banner-user-id"),
  switchUserBtn: document.getElementById("switch-user-btn"),
  userName: document.getElementById("user-name"),
  userSubtitle: document.getElementById("user-subtitle"),
  userAvatar: document.getElementById("user-avatar"),
  refreshBtn: document.getElementById("refresh-btn"),
  statTotal: document.getElementById("stat-total"),
  statPending: document.getElementById("stat-pending"),
  statCompleted: document.getElementById("stat-completed"),
  statCards: document.querySelectorAll(".stat-card"),
  addForm: document.getElementById("add-task-form"),
  taskInput: document.getElementById("new-task-input"),
  searchInput: document.getElementById("search-input"),
  clearSearchBtn: document.getElementById("clear-search-btn"),
  tabButtons: document.querySelectorAll(".tab-btn"),
  tabBadgeAll: document.getElementById("tab-badge-all"),
  tabBadgePending: document.getElementById("tab-badge-pending"),
  tabBadgeCompleted: document.getElementById("tab-badge-completed"),
  tasksContainer: document.getElementById("tasks-list"),
  loadingIndicator: document.getElementById("loading-indicator"),
  emptyState: document.getElementById("empty-state"),
  emptyTitle: document.getElementById("empty-title"),
  emptyDesc: document.getElementById("empty-desc"),
  clearCompletedWrapper: document.getElementById("clear-completed-wrapper"),
  clearCompletedBtn: document.getElementById("clear-completed-btn"),
  toast: document.getElementById("toast"),
};

/**
 * Тактильная отдача (вибрация) через Telegram WebApp HapticFeedback
 */
function triggerHaptic(type = "light") {
  if (!tg?.HapticFeedback) return;
  try {
    if (type === "success" || type === "error" || type === "warning") {
      tg.HapticFeedback.notificationOccurred(type);
    } else {
      tg.HapticFeedback.impactOccurred(type);
    }
  } catch (e) {
    // Игнорируем в браузерах без поддержки
  }
}

/**
 * Показ всплывающего уведомления (Toast)
 */
let toastTimeout = null;
function showToast(message) {
  if (!elements.toast) return;
  clearTimeout(toastTimeout);
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  toastTimeout = setTimeout(() => {
    elements.toast.classList.add("hidden");
  }, 2200);
}

/**
 * Извлекает объект пользователя Telegram из всех доступных источников WebApp SDK и URL
 */
function extractTelegramUser() {
  const tg = window.Telegram?.WebApp;

  // 1. Прямой объект в initDataUnsafe
  if (tg?.initDataUnsafe?.user?.id) {
    return tg.initDataUnsafe.user;
  }

  // 2. Строка запроса в tg.initData (в Telegram Web / Desktop)
  if (tg?.initData) {
    try {
      const q = new URLSearchParams(tg.initData);
      const userStr = q.get("user");
      if (userStr) {
        try {
          const u = JSON.parse(userStr);
          if (u && u.id) return u;
        } catch (e) {
          const u = JSON.parse(decodeURIComponent(userStr));
          if (u && u.id) return u;
        }
      }
    } catch (e) {
      console.warn("Ошибка парсинга tg.initData:", e);
    }
  }

  // 3. Хэш URL (#tgWebAppData=...)
  if (window.location.hash) {
    try {
      const rawHash = window.location.hash.startsWith("#")
        ? window.location.hash.substring(1)
        : window.location.hash;
      const hashParams = new URLSearchParams(rawHash);
      const tgWebAppData = hashParams.get("tgWebAppData");
      if (tgWebAppData) {
        const innerParams = new URLSearchParams(tgWebAppData);
        const userStr = innerParams.get("user");
        if (userStr) {
          try {
            const u = JSON.parse(userStr);
            if (u && u.id) return u;
          } catch (e) {
            const u = JSON.parse(decodeURIComponent(userStr));
            if (u && u.id) return u;
          }
        }
      }
      const directUser = hashParams.get("user");
      if (directUser) {
        try {
          const u = JSON.parse(directUser);
          if (u && u.id) return u;
        } catch (e) {
          const u = JSON.parse(decodeURIComponent(directUser));
          if (u && u.id) return u;
        }
      }
    } catch (e) {
      console.warn("Ошибка парсинга хэша Telegram:", e);
    }
  }

  return null;
}

/**
 * Определение текущего пользователя из Telegram WebApp или URL/LocalStorage
 */
function initUser() {
  const urlParams = new URLSearchParams(window.location.search);
  const paramUserId = urlParams.get("user_id");

  if (tg) {
    tg.ready();
    tg.expand();

    try {
      tg.enableClosingConfirmation();
    } catch (e) {}

    // Синхронизация реальной высоты окна Telegram с CSS-переменными
    const syncViewportHeight = () => {
      const vh = tg.viewportHeight ? `${tg.viewportHeight}px` : `${window.innerHeight}px`;
      document.documentElement.style.setProperty("--tg-viewport-height", vh);
      document.documentElement.style.setProperty("--app-height", vh);
    };
    syncViewportHeight();

    if (typeof tg.onEvent === "function") {
      tg.onEvent("viewportChanged", syncViewportHeight);
    }
  }

  // 1. Проверяем данные от Telegram WebApp (пользователь в Telegram)
  const tgUser = extractTelegramUser();
  if (tgUser && tgUser.id) {
    state.userId = String(tgUser.id);
    localStorage.setItem("todo_user_id", state.userId);
    localStorage.setItem("todo_test_user_id", state.userId);
    const fullName = [tgUser.first_name, tgUser.last_name].filter(Boolean).join(" ");
    state.userName = fullName || tgUser.username || `Пользователь #${tgUser.id}`;
    elements.userName.textContent = `Привет, ${tgUser.first_name || state.userName}!`;
    elements.userSubtitle.textContent = `ID: ${state.userId} • Синхронизировано с ботом`;
    if (tgUser.first_name) {
      elements.userAvatar.textContent = tgUser.first_name.charAt(0).toUpperCase();
    }
    // Скрываем баннер браузера при работе внутри Telegram
    elements.banner.classList.add("hidden");
    return;
  }

  // 2. Если передан параметр user_id в URL (например, из ссылки или инлайн-кнопки бота)
  if (paramUserId && paramUserId.trim() && !paramUserId.trim().startsWith("web_") && paramUserId.trim() !== "default" && paramUserId.trim() !== "local") {
    state.userId = paramUserId.trim();
    localStorage.setItem("todo_user_id", state.userId);
    localStorage.setItem("todo_test_user_id", state.userId);
    elements.userName.textContent = `Мои задачи (${state.userId})`;
    elements.userSubtitle.textContent = "Личный список • Синхронизация активна";
    elements.bannerUserId.textContent = state.userId;
    if (tg && (tg.platform === "web" || tg.platform === "weba" || tg.platform === "webk")) {
      elements.banner.classList.add("hidden");
    } else {
      elements.banner.classList.remove("hidden");
    }
    return;
  }

  // 3. Если открыто в обычном браузере (тестирование / веб-режим)
  elements.banner.classList.remove("hidden");

  let savedId = localStorage.getItem("todo_user_id") || localStorage.getItem("todo_test_user_id");
  // Очищаем любые фиктивные/старые ID (web_xxx, default, local)
  if (!savedId || savedId === "default" || savedId === "null" || savedId === "undefined" || savedId === "local" || savedId.startsWith("web_")) {
    savedId = "5265404800";
  }
  state.userId = savedId;
  localStorage.setItem("todo_user_id", state.userId);
  localStorage.setItem("todo_test_user_id", state.userId);

  elements.bannerUserId.textContent = state.userId;
  elements.userName.textContent = `Мои задачи (${state.userId})`;
  elements.userSubtitle.textContent = "Режим браузера • Личный список";
}

/**
 * Загрузка списка задач с бэкенда с предотвращением кэширования и проверкой изменений
 */
async function fetchTasks(showSpinner = true) {
  // Защита от фиктивных ID
  if (!state.userId || state.userId.startsWith("web_") || state.userId === "default" || state.userId === "local") {
    state.userId = "5265404800";
    localStorage.setItem("todo_user_id", state.userId);
    localStorage.setItem("todo_test_user_id", state.userId);
  }

  if (showSpinner) {
    state.isLoading = true;
    elements.loadingIndicator.classList.remove("hidden");
    elements.emptyState.classList.add("hidden");
    elements.refreshBtn.classList.add("rotating");
  }

  try {
    const timestamp = Date.now();
    const res = await fetch(`/api/tasks?user_id=${encodeURIComponent(state.userId)}&_t=${timestamp}`, {
      cache: "no-store",
      headers: {
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
      },
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    const newTasks = Array.isArray(data.tasks) ? data.tasks : [];

    const newTasksJson = JSON.stringify(newTasks);
    // Обновляем DOM только если данные изменились либо запрошен принудительный спиннер
    if (newTasksJson !== state.lastTasksJson || showSpinner) {
      state.tasks = newTasks;
      state.lastTasksJson = newTasksJson;
      render();
    }
  } catch (err) {
    console.error("Ошибка загрузки задач:", err);
    if (showSpinner) {
      showToast("⚠️ Ошибка синхронизации с сервером");
      triggerHaptic("error");
    }
  } finally {
    if (showSpinner) {
      state.isLoading = false;
      elements.loadingIndicator.classList.add("hidden");
      elements.refreshBtn.classList.remove("rotating");
    }
  }
}

/**
 * Добавление новой задачи
 */
async function handleAddTask(e) {
  if (e) e.preventDefault();
  const text = elements.taskInput.value.trim();
  if (!text) return;

  triggerHaptic("medium");

  // Очищаем поле ввода
  elements.taskInput.value = "";
  if (tg?.MainButton) {
    tg.MainButton.hide();
  }

  let cleanText = text;
  let reminderVal = null;
  if (text.includes(" -r ")) {
    const parts = text.split(" -r ");
    cleanText = parts[0].trim();
    reminderVal = parts[1].trim();
  } else if (text.includes(" --remind ")) {
    const parts = text.split(" --remind ");
    cleanText = parts[0].trim();
    reminderVal = parts[1].trim();
  }

  try {
    const res = await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringifyWithUtf8({
        user_id: state.userId,
        text: cleanText,
        reminder: reminderVal,
      }),
    });

    if (!res.ok) throw new Error("Не удалось добавить задачу");
    const data = await res.json();

    if (data.ok && data.task) {
      state.tasks.push(data.task);
      state.lastTasksJson = JSON.stringify(state.tasks);
      render();
      const remInfo = data.task.reminder ? " (с напоминанием ⏰)" : "";
      showToast(`✅ Задача добавлена!${remInfo}`);
      triggerHaptic("success");
    }
  } catch (err) {
    console.error("Ошибка создания задачи:", err);
    showToast("❌ Ошибка добавления задачи");
    triggerHaptic("error");
    // Возвращаем текст в поле
    elements.taskInput.value = text;
  }
}

/**
 * Переключение статуса задачи (выполнена / в процессе)
 */
async function handleToggleTask(taskId) {
  triggerHaptic("light");

  // Оптимистичное обновление UI
  const task = state.tasks.find((t) => t.id === taskId);
  if (!task) return;

  const previousState = task.done;
  task.done = !task.done;
  render();

  try {
    const res = await fetch("/api/tasks/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringifyWithUtf8({
        user_id: state.userId,
        id: taskId,
      }),
    });

    if (!res.ok) throw new Error("Ошибка обновления статуса");
    const data = await res.json();
    if (data.ok && data.task) {
      task.done = data.task.done;
      state.lastTasksJson = JSON.stringify(state.tasks);
      render();
    }
  } catch (err) {
    console.error("Ошибка при переключении статуса:", err);
    task.done = previousState;
    state.lastTasksJson = JSON.stringify(state.tasks);
    render();
    showToast("⚠️ Не удалось обновить статус");
    triggerHaptic("error");
  }
}

/**
 * Удаление задачи
 */
async function handleDeleteTask(taskId, event) {
  if (event) event.stopPropagation();
  triggerHaptic("medium");

  const itemEl = document.querySelector(`[data-task-id="${taskId}"]`);
  if (itemEl) {
    itemEl.classList.add("removing");
  }

  setTimeout(async () => {
    const originalTasks = [...state.tasks];
    state.tasks = state.tasks.filter((t) => t.id !== taskId);
    state.lastTasksJson = JSON.stringify(state.tasks);
    render();

    try {
      const res = await fetch("/api/tasks/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonStringifyWithUtf8({
          user_id: state.userId,
          id: taskId,
        }),
      });

      if (!res.ok) throw new Error("Ошибка удаления");
      showToast("🗑️ Задача удалена");
      triggerHaptic("success");
    } catch (err) {
      console.error("Ошибка при удалении задачи:", err);
      state.tasks = originalTasks;
      state.lastTasksJson = JSON.stringify(state.tasks);
      render();
      showToast("❌ Не удалось удалить задачу");
      triggerHaptic("error");
    }
  }, 180);
}

/**
 * Очистка всех выполненных задач
 */
async function handleClearCompleted() {
  const completedCount = state.tasks.filter((t) => t.done).length;
  if (completedCount === 0) return;

  triggerHaptic("warning");
  if (!confirm(`Удалить все выполненные задачи (${completedCount} шт.)?`)) {
    return;
  }

  try {
    const res = await fetch("/api/tasks/clear_completed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringifyWithUtf8({ user_id: state.userId }),
    });

    if (!res.ok) throw new Error("Ошибка очистки");
    state.tasks = state.tasks.filter((t) => !t.done);
    state.lastTasksJson = JSON.stringify(state.tasks);
    render();
    showToast(`🗑️ Очищено задач: ${completedCount}`);
    triggerHaptic("success");
  } catch (err) {
    console.error("Ошибка очистки:", err);
    showToast("❌ Ошибка при очистке");
  }
}

/**
 * Форматирование напоминания для отображения бейджа
 */
function formatReminderBadge(reminderStr) {
  if (!reminderStr) return null;
  try {
    const parts = reminderStr.split(" ");
    const [y, m, d] = parts[0].split("-");
    const time = parts[1] || "";
    const remDate = new Date(`${parts[0]}T${time}:00`);
    const now = new Date();
    const isPast = remDate < now;

    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomStr = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`;

    let text = `${d}.${m} ${time}`;
    if (parts[0] === todayStr) text = `Сегодня ${time}`;
    else if (parts[0] === tomStr) text = `Завтра ${time}`;
    return { text, isPast };
  } catch (e) {
    return { text: reminderStr, isPast: false };
  }
}

/**
 * Установка или изменение напоминания для задачи
 */
async function handleSetReminder(taskId, currentReminder, event) {
  if (event) event.stopPropagation();
  triggerHaptic("selection");

  const promptMsg = currentReminder
    ? `Текущее напоминание: ${currentReminder}\n\nВведите новое время (напр. 15m, 1h, 18:00, завтра 09:00) или 'отмена' для выключения:`
    : "Введите время напоминания:\n(например: 15m, 1h, 18:00, завтра 09:30, 2026-10-08 14:00)";

  const ans = prompt(promptMsg, currentReminder || "18:00");
  if (ans === null) return;

  try {
    const res = await fetch(`/api/tasks/${taskId}/reminder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: state.userId,
        reminder: ans.trim(),
      }),
    });

    if (!res.ok) throw new Error("Ошибка обновления напоминания");
    const data = await res.json();
    if (data.ok && data.task) {
      const idx = state.tasks.findIndex((t) => t.id === taskId);
      if (idx !== -1) {
        state.tasks[idx] = data.task;
        state.lastTasksJson = JSON.stringify(state.tasks);
        render();
      }
      showToast(data.task.reminder ? `⏰ Напоминание установлено!` : "Напоминание выключено");
      triggerHaptic("success");
    }
  } catch (err) {
    console.error("Ошибка при установке напоминания:", err);
    showToast("❌ Ошибка при установке времени");
    triggerHaptic("error");
  }
}

/**
 * Вспомогательный метод кодирования JSON
 */
function jsonStringifyWithUtf8(obj) {
  return JSON.stringify(obj);
}

/**
 * Отрисовка задач и обновление интерфейса
 */
function render() {
  const total = state.tasks.length;
  const completed = state.tasks.filter((t) => t.done).length;
  const pending = total - completed;

  // Обновляем счетчики в карточках
  elements.statTotal.textContent = total;
  elements.statPending.textContent = pending;
  elements.statCompleted.textContent = completed;

  // Обновляем бейджи табов
  elements.tabBadgeAll.textContent = total;
  elements.tabBadgePending.textContent = pending;
  elements.tabBadgeCompleted.textContent = completed;

  // Фильтрация по табам и поиску
  const query = state.searchQuery.toLowerCase().trim();
  const filtered = state.tasks.filter((t) => {
    // Фильтр таба
    if (state.currentTab === "pending" && t.done) return false;
    if (state.currentTab === "completed" && !t.done) return false;

    // Поисковый запрос
    if (query && !t.text.toLowerCase().includes(query)) return false;

    return true;
  });

  // Показ кнопки "Очистить выполненные"
  if (completed > 0 && state.currentTab !== "pending") {
    elements.clearCompletedWrapper.classList.remove("hidden");
  } else {
    elements.clearCompletedWrapper.classList.add("hidden");
  }

  // Отрисовка списка
  elements.tasksContainer.innerHTML = "";

  if (filtered.length === 0) {
    elements.emptyState.classList.remove("hidden");
    if (total === 0) {
      elements.emptyTitle.textContent = "Дел пока нет!";
      elements.emptyDesc.textContent = "Добавьте первую задачу через поле выше или в Telegram чате с ботом.";
    } else if (query) {
      elements.emptyTitle.textContent = "Ничего не найдено";
      elements.emptyDesc.textContent = `По запросу «${escapeHtml(query)}» нет задач.`;
    } else if (state.currentTab === "pending") {
      elements.emptyTitle.textContent = "Все задачи выполнены! 🎉";
      elements.emptyDesc.textContent = "Отличная работа! Можно отдохнуть или поставить новые цели.";
    } else if (state.currentTab === "completed") {
      elements.emptyTitle.textContent = "Пока нет выполненных дел";
      elements.emptyDesc.textContent = "Отмечайте задачи галочкой по мере их завершения.";
    }
  } else {
    elements.emptyState.classList.add("hidden");

    filtered.forEach((task) => {
      const li = document.createElement("li");
      li.className = `task-item ${task.done ? "completed" : ""}`;
      li.setAttribute("data-task-id", task.id);

      // Чекбокс
      const checkWrapper = document.createElement("div");
      checkWrapper.className = "task-checkbox-wrapper";
      checkWrapper.innerHTML = `
        <div class="task-checkbox" aria-label="Статус задачи">
          <svg viewBox="0 0 24 24" width="14" height="14" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </div>
      `;
      checkWrapper.addEventListener("click", () => handleToggleTask(task.id));

      // Тело задачи
      const body = document.createElement("div");
      body.className = "task-body";
      let remHtml = "";
      if (task.reminder) {
        const remInfo = formatReminderBadge(task.reminder);
        if (remInfo) {
          remHtml = `<span class="task-reminder-badge ${remInfo.isPast ? "past" : ""}">⏰ ${remInfo.text}</span>`;
        }
      }
      body.innerHTML = `
        <span class="task-id-badge">#${task.id}</span>
        <span class="task-text">${escapeHtml(task.text)}</span>
        ${remHtml}
      `;
      body.addEventListener("click", () => handleToggleTask(task.id));

      // Кнопка напоминания
      const remindBtn = document.createElement("button");
      remindBtn.className = `remind-btn ${task.reminder ? "active" : ""}`;
      remindBtn.setAttribute("title", task.reminder ? "Изменить напоминание" : "Установить напоминание");
      remindBtn.setAttribute("aria-label", "Напоминание");
      remindBtn.innerHTML = task.reminder ? "⏰" : "⏱️";
      remindBtn.addEventListener("click", (e) => handleSetReminder(task.id, task.reminder, e));

      // Кнопка удаления
      const deleteBtn = document.createElement("button");
      deleteBtn.className = "delete-btn";
      deleteBtn.setAttribute("title", "Удалить задачу");
      deleteBtn.setAttribute("aria-label", "Удалить задачу");
      deleteBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 6 5 6 21 6"></polyline>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          <line x1="10" y1="11" x2="10" y2="17"></line>
          <line x1="14" y1="11" x2="14" y2="17"></line>
        </svg>
      `;
      deleteBtn.addEventListener("click", (e) => handleDeleteTask(task.id, e));

      li.appendChild(checkWrapper);
      li.appendChild(body);
      li.appendChild(remindBtn);
      li.appendChild(deleteBtn);
      elements.tasksContainer.appendChild(li);
    });
  }
}

/**
 * Экранирование HTML для защиты от XSS
 */
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Настройка событий интерфейса
 */
function setupEventListeners() {
  // Добавление задачи
  elements.addForm.addEventListener("submit", handleAddTask);

  // Интеграция с Telegram MainButton при вводе текста
  elements.taskInput.addEventListener("input", () => {
    const val = elements.taskInput.value.trim();
    if (tg?.MainButton) {
      if (val.length > 0) {
        tg.MainButton.setText("➕ Добавить задачу").show();
      } else {
        tg.MainButton.hide();
      }
    }
  });

  if (tg?.MainButton) {
    tg.MainButton.onClick(() => {
      handleAddTask();
    });
  }

  // Обновление
  elements.refreshBtn.addEventListener("click", () => {
    triggerHaptic("light");
    fetchTasks(false);
  });

  // Клик по карточкам статистики
  elements.statCards.forEach((card) => {
    card.addEventListener("click", () => {
      triggerHaptic("light");
      const filter = card.getAttribute("data-filter");
      setActiveTab(filter);
    });
  });

  // Клик по вкладкам фильтров
  elements.tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      triggerHaptic("light");
      const tab = btn.getAttribute("data-tab");
      setActiveTab(tab);
    });
  });

  // Живой поиск
  elements.searchInput.addEventListener("input", (e) => {
    state.searchQuery = e.target.value;
    if (state.searchQuery) {
      elements.clearSearchBtn.classList.remove("hidden");
    } else {
      elements.clearSearchBtn.classList.add("hidden");
    }
    render();
  });

  elements.clearSearchBtn.addEventListener("click", () => {
    elements.searchInput.value = "";
    state.searchQuery = "";
    elements.clearSearchBtn.classList.add("hidden");
    render();
  });

  // Очистить выполненные
  elements.clearCompletedBtn.addEventListener("click", handleClearCompleted);

  // Смена тестового пользователя в браузере
  elements.switchUserBtn.addEventListener("click", () => {
    const newId = prompt("Введите Telegram User ID для тестирования:", state.userId);
    if (newId && newId.trim()) {
      const cleanId = newId.trim();
      state.userId = cleanId;
      localStorage.setItem("todo_user_id", cleanId);
      localStorage.setItem("todo_test_user_id", cleanId);
      elements.bannerUserId.textContent = cleanId;
      elements.userName.textContent = `Мои задачи (${cleanId})`;
      state.lastTasksJson = "";
      fetchTasks(true);
    }
  });
}

function setActiveTab(tab) {
  state.currentTab = tab;

  // Обновляем визуальное состояние табов
  elements.tabButtons.forEach((btn) => {
    if (btn.getAttribute("data-tab") === tab) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Обновляем визуальное состояние карточек
  elements.statCards.forEach((card) => {
    if (card.getAttribute("data-filter") === tab) {
      card.classList.add("active");
    } else {
      card.classList.remove("active");
    }
  });

  render();
}

/**
 * Настройка автоматической синхронизации данных в реальном времени с ботом
 */
function setupAutoSync() {
  // 1. Фоновый опрос каждые 3 секунды, когда страница активна
  setInterval(() => {
    if (!document.hidden && !state.isLoading) {
      fetchTasks(false);
    }
  }, 3000);

  // 2. Моментальное обновление при возвращении на экран / вкладку
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      fetchTasks(false);
    }
  });

  window.addEventListener("focus", () => {
    fetchTasks(false);
  });

  // 3. Обновление при событиях окна Telegram WebApp
  if (tg && typeof tg.onEvent === "function") {
    tg.onEvent("viewportChanged", () => {
      fetchTasks(false);
    });
  }
}

// Запуск инициализации при загрузке страницы
document.addEventListener("DOMContentLoaded", () => {
  initUser();
  setupEventListeners();
  fetchTasks(true);
  setupAutoSync();
});
