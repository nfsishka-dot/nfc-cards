/**
 * Hexgraph editor: autosave (save-draft), state machine, offline, localStorage buffer, recovery.
 * init({ quill, getHtmlForSave, saveDraftUrl, getCsrfToken, statusElement, actionsElement,
 *        debounceMs, formRoot, cardToken, recoveryRoot?, onApplyBuffer? })
 */
(function (global) {
  "use strict";

  var BUFFER_PREFIX = "hexgraph:draft-buffer:";
  var BUFFER_VERSION = 1;

  function norm(s) {
    return s == null ? "" : String(s);
  }

  function readPasswordPart(root) {
    var form = root || document;
    var useEl = form.querySelector('[name="use_view_password"]');
    var p1 = form.querySelector('[name="view_password"]');
    var p2 = form.querySelector('[name="view_password_confirm"]');
    if (!useEl) {
      return { use: "0", p1: "", p2: "" };
    }
    var use =
      useEl.type === "checkbox" || useEl.type === "radio"
        ? useEl.checked
          ? "1"
          : "0"
        : norm(useEl.value) === "1"
          ? "1"
          : "0";
    return {
      use: use,
      p1: use === "1" && p1 ? norm(p1.value) : "",
      p2: use === "1" && p2 ? norm(p2.value) : "",
    };
  }

  function pwFromBufferObj(b) {
    return {
      use: norm(b && b.use_view_password) === "1" ? "1" : "0",
      p1: b && b.view_password != null ? norm(b.view_password) : "",
      p2: b && b.view_password_confirm != null ? norm(b.view_password_confirm) : "",
    };
  }

  function buildSignature(title, bgVal, html, pw) {
    return JSON.stringify([norm(title), norm(bgVal), norm(html), pw.use, pw.p1, pw.p2]);
  }

  function baselineFromRestoreJson(obj) {
    if (!obj || typeof obj !== "object") {
      return { title: "", content: "", background_value: "{}" };
    }
    var bv =
      obj.background_value != null
        ? norm(obj.background_value)
        : JSON.stringify(obj.background || { type: "color", value: "#ffffff" });
    return {
      title: norm(obj.title),
      content: norm(obj.content),
      background_value: bv,
    };
  }

  function baselineSig(restoreObj) {
    var b = baselineFromRestoreJson(restoreObj);
    return buildSignature(b.title, b.background_value, b.content, { use: "0", p1: "", p2: "" });
  }

  function bufferStorageKey(token) {
    return BUFFER_PREFIX + token;
  }

  function init(options) {
    var quill = options.quill;
    var getHtmlForSave = options.getHtmlForSave;
    var saveDraftUrl = options.saveDraftUrl;
    var getCsrfToken = options.getCsrfToken || function () {
      return "";
    };
    var statusEl = options.statusElement;
    var actionsEl = options.actionsElement || null;
    var debounceMs = options.debounceMs || 2500;
    var formRoot = options.formRoot || document.getElementById("editor-main-form") || document;
    var cardToken = options.cardToken || "";
    var recoveryRoot = options.recoveryRoot || document.getElementById("editor-draft-recover");
    var savedVisibleMs = options.savedVisibleMs || 2800;
    var bufferWriteMs = options.bufferWriteMs || 500;

    if (!quill || typeof getHtmlForSave !== "function" || !saveDraftUrl || !cardToken) {
      return;
    }

    var storageKey = bufferStorageKey(cardToken);
    var restoreJsonEl = document.getElementById("editor-restore-json");
    var serverRestore = {};
    try {
      serverRestore = restoreJsonEl ? JSON.parse(restoreJsonEl.textContent || "{}") : {};
    } catch (_e) {
      serverRestore = {};
    }
    var serverBaselineSig = baselineSig(serverRestore);

    var phase = "idle";
    var lastSavedSig;
    var saveGeneration = 0;
    var debounceTimer = null;
    var bufferTimer = null;
    var savedTimer = null;
    var lastRetryPayload = null;
  var autosaveActive = false;
  var suppressBeforeUnloadUntil = 0;

    function titleVal() {
      var el = document.getElementById("post-title");
      return el ? el.value : "";
    }

    function bgVal() {
      var el = document.getElementById("background_value");
      return el ? el.value : "";
    }

    function currentHtml() {
      try {
        return getHtmlForSave();
      } catch (e) {
        return quill.root ? quill.root.innerHTML : "";
      }
    }

    function currentSig() {
      return buildSignature(titleVal(), bgVal(), currentHtml(), readPasswordPart(formRoot));
    }

    function isDirty() {
      return currentSig() !== lastSavedSig;
    }

    function isOnline() {
      return global.navigator && global.navigator.onLine !== false;
    }

    function setStatus(text, dataState) {
      if (!statusEl) return;
      statusEl.textContent = text == null ? "" : text;
      if (dataState) {
        statusEl.setAttribute("data-state", dataState);
      } else {
        statusEl.removeAttribute("data-state");
      }
    }

    function clearSavedTimer() {
      if (savedTimer) {
        clearTimeout(savedTimer);
        savedTimer = null;
      }
    }

    function setPhase(next, message) {
      phase = next;
      if (message != null) {
        setStatus(message, next);
      }
    }

    function renderRetry(show) {
      if (!actionsEl) return;
      actionsEl.innerHTML = "";
      if (!show) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "editor-autosave-retry";
      btn.textContent = "Повторить";
      btn.addEventListener("click", function () {
        if (lastRetryPayload) {
          runSaveWithObject(lastRetryPayload, false);
        }
      });
      actionsEl.appendChild(btn);
    }

    function enterIdle() {
      clearSavedTimer();
      phase = "idle";
      setStatus("", "idle");
      renderRetry(false);
    }

    function enterDirty() {
      clearSavedTimer();
      phase = "dirty";
      if (!isOnline()) {
        phase = "offline";
        setStatus("Нет соединения, изменения не сохранены", "offline");
        renderRetry(false);
        return;
      }
      setStatus("Есть несохранённые изменения", "dirty");
      renderRetry(false);
    }

    function enterSaving() {
      clearSavedTimer();
      phase = "saving";
      setStatus("Сохранение...", "saving");
      renderRetry(false);
    }

    function enterSaved() {
      phase = "saved";
      setStatus("Сохранено", "saved");
      renderRetry(false);
      clearSavedTimer();
      savedTimer = setTimeout(function () {
        savedTimer = null;
        if (!isDirty() && phase === "saved") {
          enterIdle();
        }
      }, savedVisibleMs);
    }

    function enterError(msg) {
      clearSavedTimer();
      phase = "error";
      setStatus(msg || "Ошибка сохранения", "error");
      renderRetry(true);
    }

    function enterOfflineFromDirty() {
      clearSavedTimer();
      phase = "offline";
      setStatus("Нет соединения, изменения не сохранены", "offline");
      renderRetry(false);
    }

    function reflectUserEdit() {
      if (!autosaveActive) return;
      if (phase === "saving") {
        scheduleBufferWrite();
        return;
      }
      if (phase === "saved" || phase === "idle" || phase === "error") {
        if (isDirty()) {
          enterDirty();
        }
      } else if (phase === "dirty" || phase === "offline") {
        if (isDirty()) {
          if (!isOnline()) {
            enterOfflineFromDirty();
          } else if (phase === "offline") {
            enterDirty();
          } else {
            setStatus("Есть несохранённые изменения", "dirty");
          }
        }
      }
      scheduleBufferWrite();
      scheduleDebouncedSave();
    }

    function payloadObjectFromDom() {
      var pw = readPasswordPart(formRoot);
      return {
        content: currentHtml(),
        title: titleVal(),
        background_value: bgVal(),
        use_view_password: pw.use,
        view_password: pw.p1,
        view_password_confirm: pw.p2,
      };
    }

    function formDataFromPayload(obj) {
      var fd = new FormData();
      fd.append("content", obj.content);
      fd.append("title", obj.title);
      fd.append("background_value", obj.background_value);
      fd.append("use_view_password", obj.use_view_password);
      fd.append("view_password", obj.view_password);
      fd.append("view_password_confirm", obj.view_password_confirm);
      fd.append("csrfmiddlewaretoken", getCsrfToken());
      return fd;
    }

    function clearDebounce() {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
        debounceTimer = null;
      }
    }

    function clearBufferDebounce() {
      if (bufferTimer) {
        clearTimeout(bufferTimer);
        bufferTimer = null;
      }
    }

    function writeBufferNow() {
      if (!global.localStorage) return;
      if (!isDirty()) {
        try {
          global.localStorage.removeItem(storageKey);
        } catch (_e) {}
        return;
      }
      var po = payloadObjectFromDom();
      var rec = {
        v: BUFFER_VERSION,
        updatedAt: Date.now(),
        sessionBaselineSig: serverBaselineSig,
        title: po.title,
        content: po.content,
        background_value: po.background_value,
        use_view_password: po.use_view_password,
        view_password: po.view_password,
        view_password_confirm: po.view_password_confirm,
      };
      try {
        global.localStorage.setItem(storageKey, JSON.stringify(rec));
      } catch (_e2) {}
    }

    function scheduleBufferWrite() {
      clearBufferDebounce();
      bufferTimer = setTimeout(function () {
        bufferTimer = null;
        writeBufferNow();
      }, bufferWriteMs);
    }

    function clearLocalBuffer() {
      try {
        global.localStorage.removeItem(storageKey);
      } catch (_e) {}
    }

    function scheduleDebouncedSave() {
      clearDebounce();
      if (!autosaveActive) return;
      if (!isDirty()) {
        if (phase === "dirty" || phase === "offline") {
          enterIdle();
        }
        return;
      }
      if (!isOnline()) {
        enterOfflineFromDirty();
        return;
      }
      if (phase === "dirty" || phase === "offline") {
        if (isOnline() && phase === "offline") {
          enterDirty();
        }
      }
      debounceTimer = setTimeout(function () {
        debounceTimer = null;
        if (!autosaveActive || !isDirty() || !isOnline()) {
          if (!isOnline() && isDirty()) {
            enterOfflineFromDirty();
          }
          return;
        }
        runSaveWithObject(payloadObjectFromDom(), false);
      }, debounceMs);
    }

    function flushSave() {
      clearDebounce();
      if (!autosaveActive || !isDirty() || !isOnline()) {
        return;
      }
      runSaveWithObject(payloadObjectFromDom(), false);
    }

    function runSaveWithObject(payloadObj, isUnload) {
      if (isUnload && !isDirty()) {
        return;
      }
      if (!isDirty() && !isUnload) {
        if (phase === "saving") {
          return;
        }
        enterIdle();
        return;
      }

      var sigPayload = buildSignature(
        payloadObj.title,
        payloadObj.background_value,
        payloadObj.content,
        {
          use: payloadObj.use_view_password,
          p1: payloadObj.view_password,
          p2: payloadObj.view_password_confirm,
        }
      );

      var fd = formDataFromPayload(payloadObj);
      var headers = { "X-CSRFToken": getCsrfToken(), "X-Requested-With": "XMLHttpRequest" };
      var fetchOpts = {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: headers,
      };

      if (isUnload) {
        fetchOpts.keepalive = true;
        fetch(saveDraftUrl, fetchOpts);
        return;
      }

      if (!isOnline()) {
        enterOfflineFromDirty();
        return;
      }

      lastRetryPayload = payloadObj;
      var myGen = ++saveGeneration;
      enterSaving();

      fetch(saveDraftUrl, fetchOpts)
        .then(function (res) {
          return res.json().then(function (data) {
            return { res: res, data: data || {} };
          });
        })
        .then(function (out) {
          if (myGen !== saveGeneration) {
            return;
          }
          if (out.res.ok && out.data.ok) {
            lastSavedSig = sigPayload;
            clearLocalBuffer();
            clearBufferDebounce();
            if (currentSig() !== lastSavedSig) {
              enterDirty();
              scheduleDebouncedSave();
            } else {
              enterSaved();
            }
          } else {
            var msg = "Ошибка сохранения";
            if (out.data && out.data.errors) {
              var e = out.data.errors;
              if (e._html) msg = e._html;
              else if (e.view_password) msg = e.view_password;
              else if (e.view_password_confirm) msg = e.view_password_confirm;
            }
            enterError(msg);
          }
        })
        .catch(function () {
          if (myGen !== saveGeneration) {
            return;
          }
          enterError("Ошибка сохранения");
        });
    }

    function runSaveUnload() {
      if (!isDirty()) return;
      runSaveWithObject(payloadObjectFromDom(), true);
    }

    function applyBufferToEditor(buf) {
      var titleEl = document.getElementById("post-title");
      if (titleEl) titleEl.value = norm(buf.title);
      var hi = document.getElementById("background_value");
      if (hi) hi.value = norm(buf.background_value);
      var useEl = formRoot.querySelector('[name="use_view_password"]');
      var p1 = formRoot.querySelector('[name="view_password"]');
      var p2 = formRoot.querySelector('[name="view_password_confirm"]');
      if (useEl) {
        if (useEl.type === "checkbox" || useEl.type === "radio") {
          useEl.checked = norm(buf.use_view_password) === "1";
        } else {
          useEl.value = norm(buf.use_view_password) === "1" ? "1" : "0";
        }
      }
      if (p1 && buf.view_password != null) p1.value = norm(buf.view_password);
      if (p2 && buf.view_password_confirm != null) p2.value = norm(buf.view_password_confirm);
      var html = norm(buf.content);
      if (!html.replace(/\s+/g, "")) {
        quill.setText("");
      } else {
        try {
          var delta = quill.clipboard.convert({ html: html });
          quill.setContents(delta, "silent");
        } catch (_e) {
          quill.root.innerHTML = html;
        }
      }
      if (typeof global.hexgraphEditorRestoreBackground === "function") {
        global.hexgraphEditorRestoreBackground();
      }
      if (typeof options.onApplyBuffer === "function") {
        options.onApplyBuffer(buf);
      }
    }

    function maybeOfferRecovery(thenFn) {
      if (!global.localStorage) {
        thenFn({});
        return;
      }
      var raw;
      try {
        raw = global.localStorage.getItem(storageKey);
      } catch (_e) {
        thenFn({});
        return;
      }
      if (!raw) {
        thenFn({});
        return;
      }
      var buf;
      try {
        buf = JSON.parse(raw);
      } catch (_e2) {
        clearLocalBuffer();
        thenFn({});
        return;
      }
      if (!buf || buf.v !== BUFFER_VERSION || norm(buf.sessionBaselineSig) !== serverBaselineSig) {
        clearLocalBuffer();
        thenFn({});
        return;
      }
      var pwB = pwFromBufferObj(buf);
      var bufSig = buildSignature(buf.title, buf.background_value, buf.content, pwB);
      if (bufSig === serverBaselineSig) {
        clearLocalBuffer();
        thenFn({});
        return;
      }
      if (bufSig === currentSig()) {
        clearLocalBuffer();
        thenFn({});
        return;
      }
      if (!recoveryRoot) {
        clearLocalBuffer();
        thenFn({});
        return;
      }
      recoveryRoot.hidden = false;
      var yes = document.getElementById("editor-draft-recover-yes");
      var no = document.getElementById("editor-draft-recover-no");

      function cleanup() {
        recoveryRoot.hidden = true;
        if (yes) yes.onclick = null;
        if (no) no.onclick = null;
      }

      function onYes() {
        applyBufferToEditor(buf);
        lastSavedSig = serverBaselineSig;
        cleanup();
        thenFn({ restored: true });
      }

      function onNo() {
        clearLocalBuffer();
        cleanup();
        thenFn({});
      }

      if (yes) yes.onclick = function () {
        onYes();
      };
      if (no) no.onclick = function () {
        onNo();
      };
    }

    function wireListeners() {
      quill.on("text-change", reflectUserEdit);

      formRoot.addEventListener(
        "input",
        function () {
          reflectUserEdit();
        },
        true
      );

      formRoot.addEventListener(
        "change",
        function () {
          reflectUserEdit();
        },
        true
      );

      document.addEventListener("hg-editor-field-changed", reflectUserEdit);

      var qlEditor = document.querySelector("#editor-container .ql-editor");
      if (qlEditor) {
        qlEditor.addEventListener(
          "blur",
          function () {
            flushSave();
          },
          true
        );
      }

      document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "hidden") {
          flushSave();
        }
      });

      global.addEventListener("online", function () {
        if (!autosaveActive) return;
        if (isDirty()) {
          enterDirty();
          flushSave();
        } else if (phase === "offline") {
          enterIdle();
        }
      });

      global.addEventListener("offline", function () {
        if (!autosaveActive) return;
        clearDebounce();
        if (isDirty()) {
          enterOfflineFromDirty();
        }
      });

      global.addEventListener("beforeunload", function (e) {
        if (Date.now() < suppressBeforeUnloadUntil) {
          return;
        }
        if (!isDirty()) {
          return;
        }
        writeBufferNow();
        runSaveUnload();
        e.preventDefault();
        e.returnValue = "";
      });
    }

    function start(flags) {
      if (!flags || !flags.restored) {
        lastSavedSig = currentSig();
      }
      autosaveActive = true;
      if (isDirty()) {
        enterDirty();
        scheduleDebouncedSave();
      } else {
        enterIdle();
      }
      wireListeners();
    }

    maybeOfferRecovery(start);
  }

  /* _forceSave() — принудительное немедленное сохранение черновика.
     Вызывается кнопкой «Дальше» перед переходом в preview. Гарантирует,
     что при возврате назад редактор откроется с актуальными данными. */
  function forceSave() {
    return new Promise(function (resolve) {
      if (!autosaveActive) {
        resolve(false);
        return;
      }
      clearDebounce();
      var po = payloadObjectFromDom();
      var fd = formDataFromPayload(po);
      var headers = { "X-CSRFToken": getCsrfToken(), "X-Requested-With": "XMLHttpRequest" };
      fetch(saveDraftUrl, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: headers,
      })
        .then(function (res) {
          return res.json().then(function (data) {
            if (res.ok && data && data.ok) {
              lastSavedSig = currentSig();
              clearLocalBuffer();
            }
            resolve(res.ok && !!(data && data.ok));
          });
        })
        .catch(function () {
          resolve(false);
        });
    });
  }

  global.HexgraphEditorAutosave = {
    init: init,
    _forceSave: forceSave,
    _suppressBeforeUnload: function (ms) {
      var ttl = Number(ms) || 4000;
      suppressBeforeUnloadUntil = Date.now() + Math.max(500, ttl);
    },
  };
})(typeof window !== "undefined" ? window : this);
