/*
 * Чат с асистента. Обикновен JavaScript, без библиотеки.
 *
 * Браузърът изпраща въпроса към REST API-то на Django (POST /api/assistant/ask/).
 * Django проверява правата, пита услугата на асистента и връща готов отговор.
 * Браузърът никога не говори директно с асистента или с езиковия модел.
 */
(function () {
  "use strict";

  const log = document.getElementById("chat-log");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const sendButton = document.getElementById("chat-send");
  const examples = document.getElementById("examples");

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

  async function ask(question) {
    addBubble(question, "user");
    const waiting = addBubble("Мисля…", "bot waiting");
    sendButton.disabled = true;

    try {
      const response = await fetch(window.QUESTBOARD_ASK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ question: question }),
      });
      const data = await response.json().catch(() => ({}));

      if (response.ok) {
        waiting.textContent = data.answer;
        waiting.className = "bubble bot";
      } else {
        // Ясно съобщение при грешка – напр. асистентът е изключен или е достигнат лимитът.
        waiting.textContent = data.detail || "Възникна грешка. Опитайте отново.";
        waiting.className = "bubble bot error";
      }
    } catch (error) {
      waiting.textContent = "Няма връзка със сървъра. Проверете интернета и опитайте отново.";
      waiting.className = "bubble bot error";
    } finally {
      sendButton.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    ask(question);
  });

  // Бутоните с примерни въпроси
  examples.addEventListener("click", function (event) {
    if (event.target.matches("button")) {
      ask(event.target.textContent);
    }
  });
})();
