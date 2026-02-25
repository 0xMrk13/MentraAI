(function () {
  const params = new URLSearchParams(window.location.search);

  const cfgEl = document.getElementById("lbDefaults");
  const defaults = {
    days: parseInt(cfgEl?.dataset.days || "30", 10),
    limit: parseInt(cfgEl?.dataset.limit || "10", 10),
    currentUsername: (cfgEl?.dataset.currentUsername || "").trim(),
  };

  const days = parseInt(params.get("days") || String(defaults.days), 10);
  const limit = parseInt(params.get("limit") || String(defaults.limit), 10);
  const topic = (params.get("topic") || "").trim();
  const page = parseInt(params.get("page") || "1", 10);

  const skel = document.getElementById("lbSkeleton");
  const table = document.getElementById("lbTable");
  const tbody = document.getElementById("lbBody");
  const pager = document.getElementById("lbPager");
  const podium = document.getElementById("podium");

  const pod1 = document.getElementById("pod1");
  const pod2 = document.getElementById("pod2");
  const pod3 = document.getElementById("pod3");

  if (!skel || !table || !tbody || !pager) return;

  const PODIUM_COUNT = 3;

  function escapeHtml(s){
    return String(s ?? "")
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;")
      .replace(/'/g,"&#039;");
  }

  function qsApi() {
    const u = new URLSearchParams();
    u.set("days", String(days));
    u.set("limit", String(limit));
    u.set("page", String(page));
    if (topic) u.set("topic", topic);
    return "/api/leaderboard?" + u.toString();
  }

  function buildHref(p) {
    const u = new URL(window.location.href);
    u.searchParams.set("page", String(p));
    u.searchParams.set("days", String(days));
    u.searchParams.set("limit", String(limit));
    if (topic) u.searchParams.set("topic", topic);
    else u.searchParams.delete("topic");
    return u.pathname + "?" + u.searchParams.toString();
  }

  function setPager(cur, totalPages) {
    pager.innerHTML = "";

    const add = (label, p, disabled = false, active = false, dots = false) => {
      const li = document.createElement("li");
      li.className =
        "page-item" + (disabled ? " disabled" : "") + (active ? " active" : "");

      const a = document.createElement("a");
      a.className = "page-link";

      if (dots) {
        a.href = "#";
        a.tabIndex = -1;
        a.setAttribute("aria-disabled", "true");
        a.textContent = "…";
        li.classList.add("disabled");
      } else {
        a.href = disabled ? "#" : buildHref(p);
        a.textContent = label;
        a.setAttribute("aria-label", label === "‹" ? "Previous" : (label === "›" ? "Next" : `Page ${label}`));
      }

      li.appendChild(a);
      pager.appendChild(li);
    };

    const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
    const last = Math.max(1, parseInt(totalPages || 1, 10));
    cur = clamp(parseInt(cur || 1, 10), 1, last);

    add("‹", clamp(cur - 1, 1, last), cur === 1);

    add("1", 1, false, cur === 1);

    if (last >= 2) {
      const start = clamp(cur - 2, 2, last - 1);
      const end = clamp(cur + 2, 2, last - 1);

      if (start > 2) add("…", 0, true, false, true);
      for (let p = start; p <= end; p++) add(String(p), p, false, p === cur);
      if (end < last - 1) add("…", 0, true, false, true);

      if (last !== 1) add(String(last), last, false, cur === last);
    }

    add("›", clamp(cur + 1, 1, last), cur === last);
  }

  function fmt(n) {
    try {
      return new Intl.NumberFormat("en-US").format(n);
    } catch {
      return String(n);
    }
  }

  function avatarUrl(it) {
    const raw = String(it?.avatar_url ?? "").trim();
    const low = raw.toLowerCase();

    if (raw && low !== "none" && low !== "null" && low !== "undefined" && (low.startsWith("http://") || low.startsWith("https://"))) {
      return raw;
    }

    const uid = it?.user_id ? String(it.user_id) : "";
    if (uid) {
      let mod = 0;
      try { mod = Number(BigInt(uid) % 5n); }
      catch { mod = (parseInt(uid, 10) || 0) % 5; }
      return "https://cdn.discordapp.com/embed/avatars/" + mod + ".png";
    }
    return "https://cdn.discordapp.com/embed/avatars/0.png";
  }

  function profileHref(it, daysVal) {
    const u = new URLSearchParams();
    u.set("user_id", String(it?.user_id || ""));
    u.set("days", String(daysVal ?? days));
    return "/user?" + u.toString();
  }

  function setClickable(el, href) {
    if (!el || !href) return;
    el.classList.add("row-click");
    el.setAttribute("role", "link");
    el.setAttribute("tabindex", "0");
    el.addEventListener("click", () => (window.location.href = href));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        window.location.href = href;
      }
    });
  }

  function crownHTML(rank) {
    const cls = rank === 1 ? "crown-1" : (rank === 2 ? "crown-2" : "crown-3");
    return `
      <span class="podium-crown ${cls}" aria-hidden="true">
        <img class="crown-img" src="/static/img/crown.svg" alt="">
      </span>
    `;
  }

  function podiumCardHTML(rank, it) {
    return `
      <div class="podium-bg"></div>

      <div class="podium-avatar-wrap">
        <img class="podium-avatar" src="${avatarUrl(it)}" alt="">
        ${crownHTML(rank)}
      </div>

      <h3 class="podium-name">${escapeHtml(it?.username || "UNKNOWN")}</h3>

      <div class="podium-score">
        <span class="coin"></span>
        <span>${fmt(it?.points || 0)}</span>
      </div>
    `;
  }

  function rankChipClass(rank) {
    return "rank-chip";
  }

  function appendRow(it, rank, daysVal, markMe) {
    const tr = document.createElement("tr");
    if (markMe) tr.classList.add("row-you");

    tr.innerHTML = `
      <th scope="row" class="lb-rank-cell">
        <span class="${rankChipClass(rank)}">${rank}</span>
      </th>

      <td>
        <div class="d-flex align-items-center gap-3">
          <img class="avatar" src="${avatarUrl(it)}" alt="">
          <div class="lb-username">${escapeHtml(it?.username || "UNKNOWN")}</div>
        </div>
      </td>

      <td>
        <div class="points-pack">
          <span class="coin"></span>
          <span>${fmt(it?.points || 0)}</span>
        </div>
      </td>

      <td>${fmt(it?.accuracy_pct || 0)}%</td>
      <td>${fmt(it?.quizzes || 0)}</td>
    `;

    setClickable(tr, profileHref(it, daysVal));
    tbody.appendChild(tr);
  }

  function appendYourPositionPill() {
    const tr = document.createElement("tr");
    tr.className = "your-pos-row";
    tr.innerHTML = `
      <td colspan="5">
        <span class="your-pos-pill">Your position</span>
      </td>
    `;
    tbody.appendChild(tr);
  }

  fetch(qsApi())
    .then((r) => r.json())
    .then((data) => {
      tbody.innerHTML = "";

      const items = Array.isArray(data?.items) ? data.items : [];
      const curPage = Math.max(1, parseInt(data?.page || page || 1, 10));
      const pageLimit = Math.max(1, parseInt(data?.limit || limit || 10, 10));
      const offset = (curPage - 1) * pageLimit;

      if (podium && curPage === 1 && items.length >= PODIUM_COUNT) {
        podium.classList.remove("d-none");

        if (pod1) pod1.innerHTML = podiumCardHTML(1, items[0]);
        if (pod2) pod2.innerHTML = podiumCardHTML(2, items[1]);
        if (pod3) pod3.innerHTML = podiumCardHTML(3, items[2]);

        setClickable(pod1, profileHref(items[0], data?.days));
        setClickable(pod2, profileHref(items[1], data?.days));
        setClickable(pod3, profileHref(items[2], data?.days));
      } else if (podium) {
        podium.classList.add("d-none");
      }

      const sliceStart = curPage === 1 ? PODIUM_COUNT : 0;
      const rest = items.slice(sliceStart);

      const me = data?.me || null;
      const meInPage = data?.me_in_page === true;
      const currentName = defaults.currentUsername;

      rest.forEach((it, idx) => {
        const rank = offset + sliceStart + idx + 1;
        const isMe =
          it?.is_me === true || (currentName && it?.username === currentName);
        appendRow(it, rank, data?.days, isMe);
      });

      if (me && !meInPage) {
        appendYourPositionPill();
        appendRow(me, parseInt(me.rank || 0, 10) || 0, data?.days, true);
      }

      setPager(curPage, data?.total_pages);

      skel.classList.add("d-none");
      table.classList.remove("d-none");
      document.querySelector(".lb-content")?.classList.add("show");
    })
    .catch(() => {
      skel.innerHTML = `<div class="muted" style="padding:14px 0;">Failed to load leaderboard.</div>`;
    });
})();
