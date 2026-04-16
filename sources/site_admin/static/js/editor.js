document.addEventListener("DOMContentLoaded", () => {
  const textarea = document.querySelector("textarea[name='content']");
  const toolbar = document.getElementById("md-toolbar");
  const editorWrapper = document.getElementById("editor-wrapper");
  const bgInput = document.querySelector("input[name='background_color']");
  const textInput = document.querySelector("input[name='text_color']");

  if (!textarea || !toolbar || !editorWrapper) return;

  // live‑цвета
  function applyColors() {
    if (bgInput) editorWrapper.style.backgroundColor = bgInput.value || "#ffffff";
    if (textInput) editorWrapper.style.color = textInput.value || "#222222";
  }
  applyColors();
  bgInput && bgInput.addEventListener("input", applyColors);
  textInput && textInput.addEventListener("input", applyColors);

  // показать панель при фокусе
  textarea.addEventListener("focus", () => {
    toolbar.classList.remove("hidden");
    positionToolbar();
  });
  textarea.addEventListener("keyup", positionToolbar);
  textarea.addEventListener("click", positionToolbar);

  function positionToolbar() {
    const rect = textarea.getBoundingClientRect();
    const line = textarea.value.slice(0, textarea.selectionStart).split("\n").length - 1;
    const lineHeight = 22;
    const top = rect.top + window.scrollY + 8 + line * lineHeight;
    toolbar.style.top = top + "px";
  }

  function wrapSelection(before, after) {
    const value = textarea.value;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = value.slice(start, end);
    const insertion = before + selected + after;
    textarea.value = value.slice(0, start) + insertion + value.slice(end);
    const pos = start + insertion.length;
    textarea.focus();
    textarea.setSelectionRange(pos, pos);
  }

  function prefixLine(prefix) {
    const value = textarea.value;
    const start = textarea.selectionStart;
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    const lineEndIndex = value.indexOf("\n", start);
    const lineEnd = lineEndIndex === -1 ? value.length : lineEndIndex;
    const line = value.slice(lineStart, lineEnd);
    const newLine = prefix + " " + line.replace(/^(\s*#+\s*)?/, "");
    textarea.value = value.slice(0, lineStart) + newLine + value.slice(lineEnd);
    const pos = lineStart + newLine.length;
    textarea.focus();
    textarea.setSelectionRange(pos, pos);
  }

  function insertAtCaret(text) {
    const value = textarea.value;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    textarea.value = value.slice(0, start) + text + value.slice(end);
    const pos = start + text.length;
    textarea.focus();
    textarea.setSelectionRange(pos, pos);
  }

  toolbar.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    e.preventDefault();
    const action = btn.dataset.action;

    switch (action) {
      case "bold":
        wrapSelection("**", "**");
        break;
      case "italic":
        wrapSelection("*", "*");
        break;
      case "h1":
        prefixLine("#");
        break;
      case "h2":
        prefixLine("##");
        break;
      case "h3":
        prefixLine("###");
        break;
      case "quote":
        prefixLine(">");
        break;
      case "code":
        wrapSelection("`", "`");
        break;
      case "link": {
        const url = prompt("Вставьте URL ссылки:");
        if (!url) return;
        const value = textarea.value;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const selected = value.slice(start, end) || "текст";
        const md = `[${selected}](${url})`;
        textarea.value = value.slice(0, start) + md + value.slice(end);
        const pos = start + md.length;
        textarea.focus();
        textarea.setSelectionRange(pos, pos);
        break;
      }
      case "image": {
        const choice = prompt("1 — загрузить файл, 2 — вставить URL");
        if (choice === "2") {
          const url = prompt("URL изображения:");
          if (!url) return;
          insertAtCaret(`\n![image](${url})\n`);
        } else {
          alert("Выберите файл в поле «Фото» ниже, затем ещё раз нажмите Publish.");
        }
        break;
      }
      case "video": {
        const choice = prompt("1 — загрузить файл, 2 — вставить URL");
        if (choice === "2") {
          const url = prompt("URL видео (YouTube, Vimeo или .mp4):");
          if (!url) return;
          if (/youtube\.com|youtu\.be|vimeo\.com/.test(url)) {
            insertAtCaret(`\n> video: ${url}\n`);
          } else {
            insertAtCaret(`\n<video src="${url}" controls></video>\n`);
          }
        } else {
          alert("Выберите файл в поле «Видео» ниже, затем ещё раз нажмите Publish.");
        }
        break;
      }
      default:
        break;
    }
  });
});

