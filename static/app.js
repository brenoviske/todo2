document.addEventListener("DOMContentLoaded", () => {
  const themeButtons = document.querySelectorAll("[data-theme-toggle]");
  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    const isDark = theme === "dark";
    const english = document.documentElement.lang === "en";
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", isDark ? "#151a16" : "#314d3c");
    themeButtons.forEach((button) => {
      const icon = button.querySelector("[aria-hidden='true']");
      const label = button.querySelector(".theme-toggle-label");
      const action = english ? (isDark ? "Enable light mode" : "Enable dark mode") : (isDark ? "Ativar modo claro" : "Ativar modo escuro");
      if (icon) icon.textContent = isDark ? "☀" : "☾";
      if (label) label.textContent = english ? (isDark ? "Light mode" : "Dark mode") : (isDark ? "Modo claro" : "Modo escuro");
      button.setAttribute("aria-label", action);
      button.title = action;
      button.setAttribute("aria-pressed", String(isDark));
    });
  };
  applyTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  themeButtons.forEach((button) => button.addEventListener("click", () => {
    const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    try { localStorage.setItem("daymark-theme", nextTheme); } catch (_) {}
    applyTheme(nextTheme);
  }));

  const date = document.getElementById("today-date");
  if (date) date.textContent = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "long", year: "numeric" }).format(new Date());
  const createdDate = document.getElementById("created-date");
  if (createdDate && createdDate.dataset.date) {
    createdDate.textContent = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(new Date(createdDate.dataset.date));
  }
  document.querySelectorAll(".bar-day[data-date]").forEach((label) => {
    const localDate = new Date(`${label.dataset.date}T12:00:00`);
    label.textContent = new Intl.DateTimeFormat("pt-BR", { weekday: "short" }).format(localDate).replace(".", "");
  });

  const taskList = document.querySelector(".task-list");
  const taskItems = taskList ? [...taskList.querySelectorAll(".task-item")] : [];
  const taskTools = document.querySelector("[data-task-tools]");
  if (taskTools && taskList) {
    const search = taskTools.querySelector("[data-task-search]");
    const status = taskTools.querySelector("[data-task-status]");
    const priority = taskTools.querySelector("[data-task-priority]");
    const sort = taskTools.querySelector("[data-task-sort]");
    const count = taskTools.querySelector("[data-task-result-count]");
    const noMatches = taskList.querySelector("[data-task-filter-empty]");
    if (!taskItems.length) taskTools.hidden = true;
    const updateTasks = () => {
      const query = search.value.trim().toLocaleLowerCase();
      const matches = taskItems.filter((task) => {
        const text = `${task.querySelector("h3")?.textContent || ""} ${task.querySelector(".task-copy p")?.textContent || ""}`.toLocaleLowerCase();
        const matchesStatus = status.value === "all" || (status.value === "done") === (task.dataset.completed === "true");
        const matchesPriority = priority.value === "all" || task.dataset.priority === priority.value;
        return matchesStatus && matchesPriority && text.includes(query);
      });
      const priorityRank = { high: 3, medium: 2, low: 1 };
      matches.sort((a, b) => {
        if (sort.value === "due") return (a.dataset.due || "9999-99-99").localeCompare(b.dataset.due || "9999-99-99") || Number(a.dataset.originalOrder) - Number(b.dataset.originalOrder);
        if (sort.value === "priority") return priorityRank[b.dataset.priority] - priorityRank[a.dataset.priority] || Number(a.dataset.originalOrder) - Number(b.dataset.originalOrder);
        return Number(a.dataset.originalOrder) - Number(b.dataset.originalOrder);
      });
      matches.forEach((task) => { task.hidden = false; taskList.appendChild(task); });
      taskItems.filter((task) => !matches.includes(task)).forEach((task) => { task.hidden = true; taskList.appendChild(task); });
      if (noMatches) noMatches.hidden = matches.length > 0 || taskItems.length === 0;
      const english = document.documentElement.lang === "en";
      if (count) count.textContent = english ? `${matches.length} of ${taskItems.length} tasks` : `${matches.length} de ${taskItems.length} tarefas`;
    };
    [search, status, priority, sort].forEach((control) => control.addEventListener(control === search ? "input" : "change", updateTasks));
    document.addEventListener("daymark-language-change", updateTasks);
    updateTasks();
  }

  const suggestButton = document.getElementById("suggest-steps");
  if (suggestButton) {
    suggestButton.addEventListener("click", async () => {
      const status = document.getElementById("suggest-status");
      const textarea = document.getElementById("steps-text");
      const csrf = document.querySelector('#steps-form input[name="csrf_token"]')?.value || "";
      const english = document.documentElement.lang === "en";
      suggestButton.disabled = true;
      status.textContent = english ? "Thinking of practical steps…" : "Pensando em etapas práticas…";
      try {
        const response = await fetch(suggestButton.dataset.url, { method: "POST", headers: { "X-CSRF-TOKEN": csrf, "Accept-Language": english ? "en" : "pt-BR" } });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || (english ? "Could not suggest steps." : "Não foi possível sugerir etapas."));
        textarea.value = data.steps.join("\n");
        status.textContent = english ? "Suggestions are ready. Review and save when you're ready." : "Sugestões prontas. Revise e salve quando quiser.";
      } catch (error) {
        status.textContent = error.message || (english ? "Could not suggest steps." : "Não foi possível sugerir etapas.");
      } finally {
        suggestButton.disabled = false;
      }
    });
  }

  const form = document.getElementById("chat-form");
  if (!form) return;
  const input = document.getElementById("chat-input");
  const messages = document.getElementById("chat-messages");
  const readCookie = (name) => document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${name}=`))?.slice(name.length + 1);
  const send = async (message) => {
    const text = message.trim();
    if (!text) return;
    const english = document.documentElement.lang === "en";
    const userBubble = document.createElement("div");
    userBubble.className = "chat-message user-message";
    userBubble.textContent = text;
    messages.appendChild(userBubble);
    input.value = "";
    const pending = document.createElement("div");
    pending.className = "chat-message assistant-message pending";
    pending.textContent = english ? "Thinking…" : "Pensando…";
    messages.appendChild(pending);
    messages.scrollTop = messages.scrollHeight;
    try {
      const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-TOKEN": readCookie("csrf_access_token") || "" }, body: JSON.stringify({ message: text, language: english ? "en" : "pt" }) });
      const data = await response.json();
      pending.textContent = data.reply || data.error || (english ? "I couldn't respond. Try again." : "Não consegui responder. Tente novamente.");
      pending.classList.remove("pending");
    } catch (_) {
      pending.textContent = english ? "Could not connect. Try again." : "Não foi possível conectar. Tente novamente.";
      pending.classList.remove("pending");
    }
    messages.scrollTop = messages.scrollHeight;
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); send(input.value); });
  document.querySelectorAll(".suggestion").forEach((button) => button.addEventListener("click", () => send(button.dataset.prompt || "")));
});
