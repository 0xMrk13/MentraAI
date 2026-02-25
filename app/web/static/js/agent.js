// static/js/agent.js
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // -----------------------------
  // Core elements
  // -----------------------------
  const launcher = $("mentraLauncher");
  const panel = $("mentraPanel");
  if (!launcher || !panel) return;

  const closeBtn = $("mentraCloseBtn");
  const body = $("mentraBody");
  const input = $("mentraInput");
  const sendBtn = $("mentraSendBtn");
  const stopBtn = $("mentraStopBtn");
  if (!closeBtn || !body || !input || !sendBtn || !stopBtn) return;
  document.body.classList.add("mentra-dock");
  // -----------------------------
  // State
  // -----------------------------
  let chatController = null;
  let busy = false;
  let tasksCompleted = false;
  let currentTaskIndex = 0;
  let dayTasks = [];
    // -----------------------------
  // Frontend memory (session-only)
  // -----------------------------
  const MEM_KEY = "mentra_mem_v1";
  const MAX_TURNS = 12;         
  const MAX_CHARS_EACH = 12000;  

  let memory = [];              
  let pinnedContext = "";      

  const clamp = (s, n) => {
    const t = String(s ?? "").trim();
    return t.length > n ? (t.slice(0, n) + "…") : t;
  };

  const loadMemory = () => {
    try {
      const raw = sessionStorage.getItem(MEM_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      if (Array.isArray(arr)) memory = arr;
    } catch { /* ignore */ }
  };

  const saveMemory = () => {
    try { sessionStorage.setItem(MEM_KEY, JSON.stringify(memory)); }
    catch { /* ignore */ }
  };

  const clearMemory = () => {
    memory = [];
    pinnedContext = "";
    try { sessionStorage.removeItem(MEM_KEY); } catch {}
  };
    function hardResetChatMemory(){
    try { sessionStorage.removeItem(MEM_KEY); } catch {}
    memory = [];
    pinnedContext = "";
  }

  const pushMem = (role, content) => {
    const item = { role, content: clamp(content, MAX_CHARS_EACH) };
    memory.push(item);
    if (memory.length > MAX_TURNS) memory = memory.slice(memory.length - MAX_TURNS);
    saveMemory();
  };

  const buildPrompt = (latestUserMsg) => {
    const lines = [];
    if (pinnedContext) {
      lines.push("CONTEXT (pinned):");
      lines.push(pinnedContext);
      lines.push("");
    }
    if (memory.length) {
      lines.push("CHAT HISTORY:");
      const recent = memory.slice(-4);
      for (const m of recent) {
        lines.push(`${m.role === "user" ? "User" : "Assistant"}: ${m.content}`);
      }
      lines.push("");
    }
    lines.push(`User: ${latestUserMsg}`);
    lines.push("Assistant:");
    return lines.join("\n");
  };


  loadMemory();


  const NORMAL_PLACEHOLDER = "Type a message...";

  // -----------------------------
  // Context (neutral)
  // -----------------------------
  function getCtx() {
    const qs = new URLSearchParams(window.location.search);
    const path = window.location.pathname || "/";

    let page = "app";
    if (path === "/") page = "home";
    else if (path.startsWith("/user/") || path === "/user") page = "user";
    else if (path.startsWith("/server/") || path === "/server") page = "server";
    else if (path.startsWith("/leaderboard")) page = "leaderboard";

    let user_id = "";
    const m = path.match(/^\/user\/(\d+)/);
    if (m) user_id = m[1];

    return {
      page,
      topic: qs.get("topic") || "",
      days: parseInt(qs.get("days") || "30", 10) || 30,
      user_id,
    };
  }

  // -----------------------------
  // UI helpers
  // -----------------------------
  function setOpenState(isOpen) {
    launcher.classList.toggle("open", !!isOpen);
  }

  function scrollBottom() {
    body.scrollTop = body.scrollHeight;
  }

  function setBusy(isBusy) {
    busy = !!isBusy;
    input.disabled = busy;

    if (busy) {
      sendBtn.hidden = true;
      stopBtn.hidden = false;
    } else {
      stopBtn.hidden = true;
      sendBtn.hidden = false;
    }
  }
  function lockChatAfterCompletion() {
    tasksCompleted = true;
    input.disabled = true;
    sendBtn.disabled = true;
  }

  function resetAfterCompletion() {
    // segna completato
    tasksCompleted = true;

    // reset logica day
    currentTaskIndex = 0;
    dayTasks = [];

    // reset memoria e contesto
    memory = [];
    pinnedContext = "";

    try { sessionStorage.removeItem(MEM_KEY); } catch {}

    input.placeholder = NORMAL_PLACEHOLDER;
  }


  // -----------------------------
  // Thinking bubble
  // -----------------------------
  function makeThinkingBubble() {
    const id = "t_" + Math.random().toString(16).slice(2);
    const wrap = document.createElement("div");
    wrap.className = "mentra-msg mentra-assistant";
    wrap.id = id;
    wrap.innerHTML = `
      <div class="mentra-thinking">
        <span class="dots"><i></i><i></i><i></i></span>
      </div>
    `;
    body.appendChild(wrap);
    scrollBottom();
    return id;
  }

  function removeThinking(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  // -----------------------------
  // Rendering
  // -----------------------------
  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderMiniMarkdown(text) {
    let t = escapeHtml((text || "").trim());
    t = t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/\n/g, "<br>");
    return t;
  }

  function append(role, text) {
    const wrap = document.createElement("div");
    wrap.className = "mentra-msg " + (role === "user" ? "mentra-user" : "mentra-assistant");

    const bubble = document.createElement("div");
    bubble.className = "mentra-bubble";

    if (role === "user") bubble.textContent = (text || "").trim();
    else bubble.innerHTML = renderMiniMarkdown(text);

    wrap.appendChild(bubble);
    body.appendChild(wrap);
    scrollBottom();
  }

  // -----------------------------
  // Auto-resize input
  // -----------------------------
  function autoResize() {
    input.style.height = "auto";
    const cap = 160;
    input.style.height = Math.min(input.scrollHeight, cap) + "px";
  }
  input.addEventListener("input", autoResize);

  function resetInputBox() {
    input.value = "";
    input.style.height = "auto";
    autoResize();
  }

  // -----------------------------
  // Chat send/stop
  // -----------------------------
  async function doSendChat(messageOverride, opts) {
    const msg = (messageOverride ?? input.value ?? "").trim();
    if (!msg || busy) return;

    if (tasksCompleted) {
      memory = [];
      pinnedContext = "";
      dayTasks = [];
      currentTaskIndex = 0;
      tasksCompleted = false;
    }

    // show user message
    append("user", msg);
    resetInputBox();

    setBusy(true);

    if (chatController) chatController.abort();
    chatController = new AbortController();

    const thinkingId = makeThinkingBubble();

    try {
      const ctx = getCtx();

      const raw = !!(opts && opts.raw);
      const composed = raw ? msg : buildPrompt(msg);
      const payload = { message: composed, page: ctx.page };
      if (ctx.topic) payload.topic = ctx.topic;
      if (ctx.days != null) payload.days = ctx.days;
      if (ctx.user_id) payload.user_id = ctx.user_id;

      const r = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: chatController.signal,
        body: JSON.stringify(payload),
      });

      const data = await r.json().catch(() => ({}));
      removeThinking(thinkingId);

      if (!r.ok) {
        append("assistant", data.error || `Error (${r.status})`);
      } else {
        const reply = (data.reply || "").trim();
        append("assistant", reply || "…");

        if (/tasks?\s+completed/i.test(reply) || /day\s+\d+\s+completed/i.test(reply)) {
          lockChatAfterCompletion();
      }


        // save memory (only on success)
        pushMem("user", msg);
        pushMem("assistant", reply || "…");

        // simple completion detection
        if (!tasksCompleted && dayTasks.length) {
          const text = msg.trim().toLowerCase();

          // accept only short confirmations
          const isConfirmation =
            text === "ok" ||
            text === "done" ||
            text === "yes" ||
            text === "y" ||
            text === "ok done";

          if (isConfirmation) {
            currentTaskIndex++;

          if (currentTaskIndex >= dayTasks.length) {
            append("assistant", "Good. Day tasks completed.");
            resetAfterCompletion();
          }
          }
        } 
      }
    } catch (e) {
      removeThinking(thinkingId);
      if (e && e.name === "AbortError") append("assistant", "Stopped.");
      else append("assistant", "Network error. Try again.");
    } finally {
      chatController = null;
      setBusy(false);
      input.focus();
    }
  }

  function doStop() {
    if (chatController) {
      chatController.abort();
      chatController = null;
    }
    setBusy(false);
  }

  // -----------------------------
  // Panel open/close
  // -----------------------------
  function openPanel() {
    panel.classList.add("show");
    document.body.classList.add("mentra-open");
    setOpenState(true);
    input.placeholder = NORMAL_PLACEHOLDER;
    input.focus();
    scrollBottom();
  }

  function closePanel() {
    panel.classList.remove("show");
    document.body.classList.remove("mentra-open");
    setOpenState(false);
    doStop();

    hardResetChatMemory();

    // optional: clear UI bubbles too
    body.innerHTML = "";
  }


  // -----------------------------
  //  -> Mentra (Start Day hook)
  // -----------------------------
  function buildStartDayMessage(detail) {
    const day = Number(detail?.day || 0);
    const intent = String(detail?.intent || "");
    const plan = detail?.plan;
    const d = plan?.days?.find?.((x) => Number(x.day) === day) || null;

    if (!day || !d) return `Start Day ${day || ""}.`;

    const goal = String(d.goal || "").trim();
    const tasks = Array.isArray(d.tasks) ? d.tasks : [];
    const taskLines = tasks.map((t) => `- ${String(t).trim()}`).join("\n");

    if (intent === "help_overview") {
      return [
        "HELP_OVERVIEW",
        `Day: ${day}`,
        goal ? `Goal: ${goal}` : "",
        tasks.length ? `Tasks:\n${taskLines}` : "",
        "",
        "INSTRUCTION:",
        "Explain ALL tasks together in ONE coherent answer.",
        "Give: overview of how they connect + steps for each + common pitfalls + quick checklist.",
        "Keep it concise and practical. Do not end with a question."
      ].filter(Boolean).join("\n");
    }

    return [
      "START_DAY",
      `Day: ${day}`,
      goal ? `Goal: ${goal}` : "",
      tasks.length ? `Tasks:\n${taskLines}` : ""
    ].filter(Boolean).join("\n");
  }



  window.addEventListener("mentrascan:startDay", (e) => {
    try {
      openPanel();

      // reset stato chat
      tasksCompleted = false;
      input.disabled = false;
      sendBtn.disabled = false;
      input.placeholder = NORMAL_PLACEHOLDER;

      // hard reset memoria
      hardResetChatMemory();

      const detail = e?.detail;
      const plan = detail?.plan;
      const day = Number(detail?.day || 0);
      const d = plan?.days?.find?.((x) => Number(x.day) === day) || null;

      // salva tasks reali
      dayTasks = Array.isArray(d?.tasks) ? d.tasks : [];
      currentTaskIndex = 0;

      const msg = buildStartDayMessage(detail);
      pinnedContext = msg;

      doSendChat(msg, { raw: true });

    } catch {
      openPanel();

      tasksCompleted = false;
      input.disabled = false;
      sendBtn.disabled = false;
      input.placeholder = NORMAL_PLACEHOLDER;

      hardResetChatMemory();
      pinnedContext = "Start day.";
      doSendChat("Start day.", { raw: true });
      if (String(detail?.intent || "") === "help_overview") pinnedContext = "";
    }
  });




  // -----------------------------
  // Wiring
  // -----------------------------
  launcher.addEventListener("click", () => {
    panel.classList.contains("show") ? closePanel() : openPanel();
  });

  closeBtn.addEventListener("click", closePanel);
  sendBtn.addEventListener("click", () => doSendChat());
  stopBtn.addEventListener("click", doStop);

  // Enter behavior: Enter sends, Shift+Enter newline
  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    if (!e.shiftKey) {
      e.preventDefault();
      doSendChat();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && panel.classList.contains("show")) closePanel();
  });

  document.addEventListener("mousedown", (e) => {
    if (!panel.classList.contains("show")) return;
    const t = e.target;
    if (panel.contains(t) || launcher.contains(t)) return;
    closePanel();
  });

  setOpenState(panel.classList.contains("show"));
})();
