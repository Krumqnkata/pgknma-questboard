/*
 * Чат с асистента. Обикновен JavaScript, без библиотеки.
 * Работи в прозорчето на всяка страница и на страницата „Асистент“.
 *
 * Браузърът изпраща въпроса към REST API-то на Django (POST /api/assistant/ask/).
 * Django проверява правата, пита услугата на асистента и връща готов отговор.
 * Браузърът никога не говори директно с асистента или с езиковия модел.
 */
(function () {
  "use strict";

  const root = document.querySelector("[data-chat]");
  if (!root) return;

  const log = root.querySelector("[data-chat-log]");
  const form = root.querySelector("[data-chat-form]");
  const input = form.querySelector("input");
  const sendButton = form.querySelector("button");
  const examples = root.querySelector("[data-chat-examples]");
  const KEY = "qb-chat";

  // Разговорът се помни само в този раздел на браузъра, за да не се губи при смяна на страницата.
  // Записан е с номера на потребителя – друг човек на същия компютър започва наново.
  function load() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(KEY) || "null");
      if (saved && saved.user === root.dataset.chat) return saved;
    } catch (error) { /* започваме наново */ }
    return { user: root.dataset.chat, open: false, items: [] };
  }
  const state = load();

  function save() {
    state.items = state.items.slice(-30);
    try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (error) { /* напр. частен режим */ }
  }

  function remember(text, kind) {
    state.items.push({ text: text, kind: kind });
    save();
  }

  // Django изисква CSRF ключ при всяка POST заявка. Взимаме го от бисквитката.
  function csrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  // Добавя съобщение в чата. Ползваме textContent, а не innerHTML,
  // за да не може текст от отговора да се изпълни като HTML (защита от XSS).
  function addBubble(text, kind) {
    const bubble = document.createElement("div");
    bubble.className = "bubble " + kind;
    bubble.textContent = text;
    log.appendChild(bubble);
    log.scrollTop = log.scrollHeight;
    return bubble;
  }

  function finish(bubble, text, kind) {
    bubble.textContent = text;
    bubble.className = "bubble " + kind;
    log.scrollTop = log.scrollHeight;
    remember(text, kind);
  }

  async function ask(question) {
    addBubble(question, "user");
    remember(question, "user");
    const waiting = addBubble("Мисля…", "bot waiting");
    sendButton.disabled = true;

    try {
      const response = await fetch(root.dataset.askUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ question: question }),
      });
      const data = await response.json().catch(() => ({}));

      if (response.ok) {
        finish(waiting, data.answer, "bot");
      } else {
        // Ясно съобщение при грешка – напр. асистентът е изключен или е достигнат лимитът.
        finish(waiting, data.detail || "Възникна грешка. Опитайте отново.", "bot error");
      }
    } catch (error) {
      finish(waiting, "Няма връзка със сървъра. Проверете интернета и опитайте отново.", "bot error");
    } finally {
      sendButton.disabled = false;
      input.focus();
    }
  }

  state.items.forEach(function (item) { addBubble(item.text, item.kind); });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || sendButton.disabled) return;
    input.value = "";
    ask(question);
  });

  // Бутоните с примерни въпроси
  examples.addEventListener("click", function (event) {
    if (event.target.matches("button") && !sendButton.disabled) {
      ask(event.target.textContent);
    }
  });

  // ---------- Прозорчето ----------
  const opener = document.querySelector("[data-assistant-open]");
  if (!opener) return;

  function show(open, focus) {
    root.hidden = !open;
    opener.setAttribute("aria-expanded", open ? "true" : "false");
    opener.classList.toggle("is-open", open);
    state.open = open;
    save();
    if (open) {
      log.scrollTop = log.scrollHeight;
      if (focus) input.focus();
    } else if (focus) {
      opener.focus();
    }
  }

  opener.addEventListener("click", function (event) {
    event.preventDefault();
    show(root.hidden, true);
  });
  root.querySelector("[data-assistant-close]").addEventListener("click", function () { show(false, true); });
  root.addEventListener("keydown", function (event) {
    if (event.key === "Escape") show(false, true);
  });

  // Отворено остава отворено и на следващата страница, но не и на телефон, където закрива екрана.
  if (state.open && window.matchMedia("(min-width: 701px)").matches) show(true, false);
})();
