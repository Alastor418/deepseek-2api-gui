const $ = (id) => document.getElementById(id);

// ============================================================
// Статус
// ============================================================
async function refreshStatus() {
  try {
    const r = await fetch("/gui/status");
    if (!r.ok) throw new Error("status " + r.status);
    const d = await r.json();

    const dot = $("status-dot");
    const text = $("status-text");

    dot.className = "dot";
    if (d.login_in_progress) {
      dot.classList.add("pending");
      text.textContent = "Ожидание входа в браузере…";
    } else if (d.authenticated) {
      dot.classList.add("active");
      text.textContent = `API готов · активных аккаунтов: ${d.accounts_active}/${d.accounts_total}`;
    } else {
      dot.classList.add("error");
      text.textContent = "Не авторизован";
    }

    $("version").textContent = "v" + d.version;
    $("api-url").textContent = d.api_url;
    $("api-key").textContent = d.api_key;
    $("accounts-count").textContent = d.accounts_total;

    const chips = $("models-list");
    chips.innerHTML = "";
    for (const m of d.models || []) {
      const el = document.createElement("span");
      el.className = "chip";
      el.textContent = m;
      chips.appendChild(el);
    }
    for (const a of Object.keys(d.aliases || {})) {
      const el = document.createElement("span");
      el.className = "chip alias";
      el.textContent = a + " → " + (d.aliases[a].model || "chat");
      chips.appendChild(el);
    }

    $("curl-example").textContent =
      `curl ${d.api_url}/chat/completions \\\\\n` +
      `  -H "Content-Type: application/json" \\\\\n` +
      `  -H "Authorization: Bearer ${d.api_key}" \\\\\n` +
      `  -d '{\n` +
      `    "model": "deepseek-reasoner",\n` +
      `    "messages": [{"role":"user","content":"Сколько будет 17*23?"}],\n` +
      `    "stream": true\n` +
      `  }'`;

    $("login-btn").disabled = d.login_in_progress || d.authenticated;
    $("logout-btn").disabled = !d.authenticated && d.accounts_total === 0;
  } catch (e) {
    console.error(e);
  }
}

// ============================================================
// Аккаунты
// ============================================================
async function refreshAccounts() {
  try {
    const r = await fetch("/gui/accounts");
    if (!r.ok) throw new Error("accounts " + r.status);
    const d = await r.json();
    const list = $("accounts-list");
    list.innerHTML = "";

    if (!d.accounts || d.accounts.length === 0) {
      const empty = document.createElement("div");
      empty.style.color = "var(--dim)";
      empty.style.fontSize = "13px";
      empty.style.padding = "8px 0";
      empty.textContent =
        "Нет аккаунтов. Нажмите «Войти в Deepseek» или добавьте вручную.";
      list.appendChild(empty);
      return;
    }

    for (const a of d.accounts) {
      const row = document.createElement("div");
      row.className = "account";

      const left = document.createElement("div");
      left.className = "account-left";

      const st = document.createElement("div");
      st.className = "account-status status-" + a.status;
      left.appendChild(st);

      const info = document.createElement("div");
      const label = document.createElement("div");
      label.className = "account-label";
      label.textContent = a.label || a.id;
      info.appendChild(label);

      const meta = document.createElement("div");
      meta.className = "account-meta";
      const when = a.last_used_at
        ? new Date(a.last_used_at * 1000).toLocaleString()
        : "—";
      meta.textContent = `${a.status} · использован: ${when}`;
      if (a.last_error) meta.textContent += " · " + a.last_error.slice(0, 60);
      info.appendChild(meta);
      left.appendChild(info);
      row.appendChild(left);

      const actions = document.createElement("div");
      actions.className = "account-actions";

      if (a.status !== "active") {
        const reBtn = document.createElement("button");
        reBtn.textContent = "Активировать";
        reBtn.onclick = async () => {
          await fetch(`/gui/accounts/${a.id}/reactivate`, { method: "POST" });
          refreshAccounts();
        };
        actions.appendChild(reBtn);
      }

      const delBtn = document.createElement("button");
      delBtn.className = "danger";
      delBtn.textContent = "Удалить";
      delBtn.onclick = async () => {
        if (!confirm(`Удалить аккаунт ${a.label || a.id}?`)) return;
        await fetch(`/gui/accounts/${a.id}`, { method: "DELETE" });
        refreshAccounts();
        refreshStatus();
      };
      actions.appendChild(delBtn);

      row.appendChild(actions);
      list.appendChild(row);
    }
  } catch (e) {
    console.error(e);
  }
}

// ============================================================
// Кнопки
// ============================================================
$("login-btn").onclick = async () => {
  $("login-btn").disabled = true;
  await fetch("/gui/login", { method: "POST" });
  setTimeout(() => {
    refreshStatus();
    refreshAccounts();
  }, 400);
};

$("logout-btn").onclick = async () => {
  await fetch("/gui/logout", { method: "POST" });
  refreshStatus();
  refreshAccounts();
};

$("pool-clear-btn").onclick = async () => {
  if (!confirm("Удалить ВСЕ аккаунты из пула? Это необратимо.")) return;
  const r = await fetch("/gui/pool/clear", { method: "POST" });
  if (r.ok) {
    refreshStatus();
    refreshAccounts();
  }
};

$("refresh-accounts").onclick = () => {
  refreshAccounts();
  refreshStatus();
};

$("add-account-btn").onclick = async () => {
  const label = $("acc-label").value.trim();
  const authorization = $("acc-auth").value.trim();
  const cookie = $("acc-cookie").value.trim();
  if (!authorization.startsWith("Bearer ")) {
    alert("Authorization должен начинаться с 'Bearer '");
    return;
  }
  const r = await fetch("/gui/accounts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, authorization, cookie }),
  });
  if (r.ok) {
    $("acc-label").value = "";
    $("acc-auth").value = "";
    $("acc-cookie").value = "";
    refreshAccounts();
    refreshStatus();
  } else {
    const err = await r.json().catch(() => ({}));
    alert("Ошибка: " + (err.detail || r.status));
  }
};

$("clear-logs").onclick = () => {
  $("logs").innerHTML = "";
};

// ============================================================
// Копирование
// ============================================================
document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".copy-btn");
  if (!btn) return;
  const id = btn.dataset.copy;
  const text = $(id).textContent;
  try {
    await navigator.clipboard.writeText(text);
    const orig = btn.textContent;
    btn.textContent = "Скопировано";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = orig;
      btn.classList.remove("copied");
    }, 1400);
  } catch (err) {
    console.error(err);
  }
});

// ============================================================
// Логи (SSE)
// ============================================================
const LOG_LEVEL_RE = /\|\s*(INFO|WARNING|ERROR|SUCCESS|DEBUG|CRITICAL)\s*\|/;

function classifyLogLine(line) {
  const m = line.match(LOG_LEVEL_RE);
  if (m) {
    const lvl = m[1];
    if (lvl === "ERROR" || lvl === "CRITICAL") return "error";
    if (lvl === "WARNING") return "warning";
    if (lvl === "SUCCESS") return "success";
    return null;
  }
  if (line.includes("✗")) return "error";
  if (line.includes("⚠")) return "warning";
  if (line.includes("✓")) return "success";
  return null;
}

function connectLogs() {
  const es = new EventSource("/gui/logs");
  const logs = $("logs");

  es.onmessage = (e) => {
    let line;
    try {
      line = JSON.parse(e.data);
    } catch (_err) {
      line = e.data;
    }
    const div = document.createElement("div");
    div.className = "line";
    const cls = classifyLogLine(line);
    if (cls) div.classList.add(cls);
    div.textContent = line;
    logs.appendChild(div);
    logs.scrollTop = logs.scrollHeight;
    while (logs.children.length > 500) logs.removeChild(logs.firstChild);
  };

  es.onerror = () => {
    es.close();
    setTimeout(connectLogs, 3000);
  };
}

refreshStatus();
refreshAccounts();
setInterval(refreshStatus, 3000);
setInterval(refreshAccounts, 5000);
connectLogs();
