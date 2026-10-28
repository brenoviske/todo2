document.addEventListener("DOMContentLoaded", () => {
  const themeButtons = document.querySelectorAll("[data-theme-toggle]");
  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    const isDark = theme === "dark";
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", isDark ? "#151a16" : "#314d3c");
    themeButtons.forEach((button) => {
      const icon = button.querySelector("[aria-hidden='true']");
      const label = button.querySelector(".theme-toggle-label");
      const action = isDark ? "Ativar modo claro" : "Ativar modo escuro";
      if (icon) icon.textContent = isDark ? "☀" : "☾";
      if (label) label.textContent = isDark ? "Modo claro" : "Modo escuro";
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

  const suggestButton = document.getElementById("suggest-steps");
  if (suggestButton) {
    suggestButton.addEventListener("click", async () => {
      const status = document.getElementById("suggest-status");
      const textarea = document.getElementById("steps-text");
      const csrf = document.querySelector('#steps-form input[name="csrf_token"]')?.value || "";
      suggestButton.disabled = true;
      status.textContent = "Pensando em etapas práticas…";
      try {
        const response = await fetch(suggestButton.dataset.url, { method: "POST", headers: { "X-CSRF-TOKEN": csrf } });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Não foi possível sugerir etapas.");
        textarea.value = data.steps.join("\n");
        status.textContent = "Sugestões prontas. Revise e salve quando quiser.";
      } catch (error) {
        status.textContent = error.message || "Não foi possível sugerir etapas.";
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
    const userBubble = document.createElement("div");
    userBubble.className = "chat-message user-message";
    userBubble.textContent = text;
    messages.appendChild(userBubble);
    input.value = "";
    const pending = document.createElement("div");
    pending.className = "chat-message assistant-message pending";
    pending.textContent = "Pensando…";
    messages.appendChild(pending);
    messages.scrollTop = messages.scrollHeight;
    try {
      const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-TOKEN": readCookie("csrf_access_token") || "" }, body: JSON.stringify({ message: text }) });
      const data = await response.json();
      pending.textContent = data.reply || data.error || "Não consegui responder. Tente novamente.";
      pending.classList.remove("pending");
    } catch (_) {
      pending.textContent = "Não foi possível conectar. Tente novamente.";
      pending.classList.remove("pending");
    }
    messages.scrollTop = messages.scrollHeight;
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); send(input.value); });
  document.querySelectorAll(".suggestion").forEach((button) => button.addEventListener("click", () => send(button.dataset.prompt || "")));
});
