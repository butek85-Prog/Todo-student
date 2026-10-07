/**
 * Todo Telegram Mini App - Клиентская логика
 * Интеграция с Telegram WebApp SDK и REST API планировщика.
 */

// Инициализация Telegram WebApp
const tg = window.Telegram?.WebApp;

// Состояние приложения
const state = {
  userId: "local",
  userName: "Пользователь",
  tasks: [],
  currentTab: "all",
  searchQuery: "",
  isLoading: false,
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
 * Определение текущего пользователя из Telegram WebApp или URL/LocalStorage
 */
function initUser() {
  const urlParams = new URLSearchParams(window.location.search);
  const paramUserId = urlParams.get("user_id");

  if (tg) {
    tg.ready();

    const p = (tg.platform || "").toLowerCase();
    const isDesktop = ["tdesktop", "macos", "web", "weba", "webk"].includes(p) || window.innerWidth >= 768;

    if (!isDesktop) {
      tg.expand();

      // Запрос полноэкранного режима только для смартфонов (Bot API 8.0+)
      if (typeof tg.requestFullscreen === "function") {
        try {
          tg.requestFullscreen();
        } catch (e) {}
      }

      // Отключение вертикального смахивания (чтобы окно не сворачивалось при скролле)
      if (typeof tg.disableVerticalSwipes === "function") {
        try {
          tg.disableVerticalSwipes();
        } catch (e) {}
      }
    }

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

  // 1. Проверяем данные от Telegram WebApp
  const tgUser = tg?.initDataUnsafe?.user;
  if (tgUser && tgUser.id) {
    state.userId = String(tgUser.id);
    const fullName = [tgUser.first_name, tgUser.last_name].filter(Boolean).join(" ");
    state.userName = fullName || tgUser.username || `Пользователь #${tgUser.id}`;
    elements.userName.textContent = `Привет, ${tgUser.first_name || state.userName}!`;
    elements.userSubtitle.textContent = `ID: ${state.userId} • Личный список`;
    if (tgUser.first_name) {
      elements.userAvatar.textContent = tgUser.first_name.charAt(0).toUpperCase();
    }
    // Скрываем баннер браузера
    elements.banner.classList.add("hidden");
    return;
  }

  // 2. Если открыто в обычном браузере (тестирование)
  elements.banner.classList.remove("hidden");

  if (paramUserId) {
    state.userId = paramUserId;
  } else {
    const savedId = localStorage.getItem("todo_test_user_id");
    state.userId = savedId || "5265404800"; // Используем существующего пользователя по умолчанию
  }

  elements.bannerUserId.textContent = state.userId;
  elements.userName.textContent = `Мои задачи (${state.userId})`;
  elements.userSubtitle.textContent = "Режим браузера • Синхронизация активна";
}

/**
 * Загрузка списка задач с бэкенда
 */
async function fetchTasks(showSpinner = true) {
  if (showSpinner) {
    state.isLoading = true;
    elements.loadingIndicator.classList.remove("hidden");
    elements.emptyState.classList.add("hidden");
  }

  elements.refreshBtn.classList.add("rotating");

  try {
    const res = await fetch(`/api/tasks?user_id=${encodeURIComponent(state.userId)}`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    state.tasks = Array.isArray(data.tasks) ? data.tasks : [];
    render();
  } catch (err) {
    console.error("Ошибка загрузки задач:", err);
    showToast("⚠️ Ошибка синхронизации с сервером");
    triggerHaptic("error");
  } finally {
    state.isLoading = false;
    elements.loadingIndicator.classList.add("hidden");
    elements.refreshBtn.classList.remove("rotating");
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
      render();
    }
  } catch (err) {
    console.error("Ошибка при переключении статуса:", err);
    task.done = previousState;
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
      localStorage.setItem("todo_test_user_id", cleanId);
      elements.bannerUserId.textContent = cleanId;
      elements.userName.textContent = `Мои задачи (${cleanId})`;
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

// Запуск инициализации при загрузке страницы
document.addEventListener("DOMContentLoaded", () => {
  initUser();
  setupEventListeners();
  fetchTasks(true);
});
