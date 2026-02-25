(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const text = $("tsText");
  const file = $("tsFile");
  const uploadBtn = $("tsUploadPdf");
  const sendBtn = $("tsGenerate");
  const out = $("tsResult") || $("tsOutput");

  if (!text || !file || !uploadBtn || !sendBtn || !out) {
    console.warn("[MentraScan] Missing DOM nodes", { text, file, uploadBtn, sendBtn, out });
    return;
  }

  let busy = false;
  let currentPlanId = null;
  let currentPlanJson = null;

  const escapeHtml = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");

  const autoGrow = (el) => {
    const cs = getComputedStyle(el);
    const min = parseFloat(cs.minHeight) || 0;
    const max = parseFloat(cs.maxHeight) || 900;
    el.style.height = "auto";
    const next = Math.max(el.scrollHeight, min);
    el.style.height = Math.min(next, max) + "px";
  };

  const setBusy = (on) => {
    busy = !!on;
    sendBtn.disabled = busy;
    uploadBtn.disabled = busy;
    text.disabled = busy;
  };

  const showEmpty = () => {
    out.innerHTML = `<div class="ts-empty">Your plan will appear here.</div>`;
  };

  const showError = (msg) => {
    out.innerHTML = `<div class="ts-error">${escapeHtml(msg || "Error")}</div>`;
  };

  const renderSkeleton = () => {
    out.innerHTML = `
      <div class="ts-skel">
        <div class="ts-skel-line w40"></div>
        <div class="ts-skel-line w85"></div>
        <div class="ts-skel-line w65"></div>
      </div>
    `;
  };

  const hashStr = (s) => {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(16);
  };

  const getPlanMeta = (planId) => {
    try {
      return JSON.parse(localStorage.getItem(`ts_meta_${planId}`) || "{}");
    } catch {
      return {};
    }
  };

  const setPlanMeta = (planId, meta) => {
    localStorage.setItem(`ts_meta_${planId}`, JSON.stringify(meta || {}));
  };

  const todayIndexFromStart = (startISO) => {
    if (!startISO) return 1;
    const start = new Date(startISO);
    const now = new Date();
    start.setHours(0, 0, 0, 0);
    now.setHours(0, 0, 0, 0);
    const diffDays = Math.floor((now - start) / (24 * 60 * 60 * 1000));
    return Math.min(7, Math.max(1, diffDays + 1));
  };

  const computeProgress = (planJson, checks) => {
    let total = 0;
    let done = 0;

    for (const d of planJson?.days || []) {
      const dayKey = String(d.day);
      const t = Array.isArray(d.tasks) ? d.tasks.length : 0;
      total += t;

      const dayChecks = checks?.[dayKey] || {};
      done += Object.values(dayChecks).filter(Boolean).length;
    }

    return { total, done, pct: total ? Math.round((done / total) * 100) : 0 };
  };

  const fetchChecks = async (planId) => {
    const r = await fetch(`/api/mentrascan/checks?plan_id=${encodeURIComponent(planId)}`);
    const data = await r.json().catch(() => ({}));
    return data.checks || {};
  };

  const postCheck = async (planId, day, idx, checked) => {
    await fetch("/api/mentrascan/checks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_id: planId, day, idx, checked }),
    });
  };

  const resetDayChecks = async (planId, day) => {
    await fetch("/api/mentrascan/reset_day", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_id: planId, day }),
    });
  };

  const isDayDone = (checks, dayNum, tasks) => {
    const dayKey = String(dayNum);
    const dayChecks = checks?.[dayKey] || {};
    const n = Array.isArray(tasks) ? tasks.length : 0;
    if (!n) return false;
    for (let i = 0; i < n; i++) {
      if (!dayChecks[String(i)]) return false;
    }
    return true;
  };

  const renderPlanJson = async (planJson) => {
    const days = planJson?.days;
    if (!Array.isArray(days) || !days.length) {
      showError("Invalid plan.");
      return;
    }

    const planId = hashStr(JSON.stringify(planJson));
    currentPlanId = planId;
    currentPlanJson = planJson;

    const meta = getPlanMeta(planId);
    if (!meta.startISO) {
      meta.startISO = new Date().toISOString();
      setPlanMeta(planId, meta);
    }

    const todayDay = todayIndexFromStart(meta.startISO);
    const checks = await fetchChecks(planId);
    const prog = computeProgress(planJson, checks);

    const progressHtml = `
      <div class="ts-progress">
        <div class="ts-progress-title">Week progress</div>
        <div class="ts-progressbar" role="progressbar" aria-valuenow="${prog.pct}" aria-valuemin="0" aria-valuemax="100">
          <i style="width:${prog.pct}%;"></i>
        </div>
        <div class="ts-progress-meta">${prog.done}/${prog.total}</div>
        <div class="ts-progress-pill">${prog.pct}%</div>
      </div>
    `;

    const cardsHtml = days
      .map((d) => {
        const dayNum = Number(d.day);
        const done = isDayDone(checks, dayNum, d.tasks);
        const isToday = dayNum === todayDay;

        const tb = "";
        const status = done ? "DONE" : isToday ? "TODAY" : "";
        const statusPill = status ? `<span class="ts-status ${done ? "done" : "today"}">${status}</span>` : "";

        const tasksHtml = (d.tasks || [])
          .map((t, i) => {
            const checked = !!checks?.[String(dayNum)]?.[String(i)];
            const inputId = `tsc_${planId}_${dayNum}_${i}`;
            return `
              <li class="ts-task ${checked ? "is-checked" : ""}">
                <input
                  id="${inputId}"
                  class="ts-check-input"
                  type="checkbox"
                  data-ts="check"
                  data-day="${dayNum}"
                  data-idx="${i}"
                  ${checked ? "checked" : ""}/>
                <label class="ts-check" for="${inputId}">
                  <span class="ts-checkbox" aria-hidden="true"></span>
                  <span class="txt">${escapeHtml(t)}</span>
                </label>
              </li>
            `;
          })
          .join("");

        const quizHtml = (d.quiz || []).map((q) => `<li>${escapeHtml(q)}</li>`).join("");

        return `
          <article class="ts-plan-card ${isToday ? "is-today" : ""} ${done ? "is-done" : ""}">
            <div class="ts-cardtop">
              <div class="ts-badge">Day ${dayNum}</div>
              ${statusPill}
            </div>

            <div class="ts-block">
              <div class="ts-sec-title">Goal</div>
              <div class="ts-goal">${escapeHtml(d.goal || "")}</div>
            </div>

            <hr class="ts-divider" />

            <div class="ts-block">
              <div class="ts-sec-title">Tasks</div>
              <ul class="ts-list ts-checklist">${tasksHtml}</ul>
            </div>

            <hr class="ts-divider" />

            <div class="ts-block">
              <div class="ts-sec-title">Quiz</div>
              <ul class="ts-list ts-quiz">${quizHtml}</ul>
            </div>

            <div class="ts-actions">
              <button class="ts-action-link" data-ts="start" data-day="${dayNum}" type="button">Help</button>
              <button class="ts-action-link danger" data-ts="reset" data-day="${dayNum}" type="button">Reset</button>
            </div>
          </article>
        `;
      })
      .join("");

    out.innerHTML = `<div class="ts-cards">${progressHtml}${cardsHtml}</div>`;
  };

  out.addEventListener("click", async (e) => {
    const btn = e.target instanceof HTMLElement ? e.target.closest("[data-ts]") : null;
    if (!btn || !currentPlanId) return;

    const action = btn.getAttribute("data-ts");
    const day = Number(btn.getAttribute("data-day") || 0);

    if (action === "start") {
      window.dispatchEvent(new CustomEvent("mentrascan:startDay", { detail: { day, plan: currentPlanJson } }));
      text.focus();
      return;
    }

    if (action === "reset") {
      await resetDayChecks(currentPlanId, day);
      await renderPlanJson(currentPlanJson);
    }
  });

  out.addEventListener("change", async (e) => {
    const t = e.target;
    if (!(t instanceof HTMLInputElement)) return;
    if (t.getAttribute("data-ts") !== "check") return;
    if (!currentPlanId) return;

    const day = Number(t.getAttribute("data-day") || 0);
    const idx = Number(t.getAttribute("data-idx") || 0);

    await postCheck(currentPlanId, day, idx, !!t.checked);
    await renderPlanJson(currentPlanJson);
  });

  const postPlan = async (endpoint, fd) => {
    if (busy) return;
    setBusy(true);
    renderSkeleton();

    try {
      const r = await fetch(endpoint, { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));

      if (!r.ok) throw new Error(data.error || data.detail || `HTTP ${r.status}`);

      const planJson = data.plan_json;
      if (!planJson || !Array.isArray(planJson.days)) throw new Error("Invalid plan_json from server.");

      await renderPlanJson(planJson);
    } catch (e) {
      showError(e?.message || String(e));
    } finally {
      setBusy(false);
      autoGrow(text);
    }
  };

  const generateFromText = () => {
    const t = (text.value || "").trim();
    if (!t) return showError("Paste notes first.");

    const fd = new FormData();
    fd.append("days", "7");
    fd.append("title", "Pasted notes");
    fd.append("content", t);

    postPlan("/api/mentrascan/plan_text", fd);
  };

  const generateFromPdf = (f) => {
    const fd = new FormData();
    fd.append("days", "7");
    fd.append("title", f.name || "Uploaded PDF");
    fd.append("file", f);

    postPlan("/api/mentrascan/plan_pdf", fd);
  };

  autoGrow(text);
  text.addEventListener("input", () => autoGrow(text));

  sendBtn.addEventListener("click", (e) => {
    e.preventDefault();
    generateFromText();
  });

  text.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      generateFromText();
    }
  });

  uploadBtn.addEventListener("click", (e) => {
    e.preventDefault();
    if (busy) return;
    file.click();
  });

  file.addEventListener("change", () => {
    const f = file.files && file.files[0];
    if (!f) return;

    if (f.type !== "application/pdf") {
      showError("Only PDF files are allowed.");
      file.value = "";
      return;
    }

    generateFromPdf(f);
    file.value = "";
  });

  (async () => {
    try {
      const r = await fetch("/api/mentrascan/active_plan");
      const data = await r.json().catch(() => ({}));
      if (data?.plan_json?.days?.length) {
        await renderPlanJson(data.plan_json);
      } else {
        showEmpty();
      }
    } catch {
      showEmpty();
    }
  })();
})();
