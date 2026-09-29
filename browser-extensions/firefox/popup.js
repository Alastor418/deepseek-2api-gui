const browserAPI = typeof browser !== "undefined" ? browser : chrome;
const DEFAULT_SERVER = "http://127.0.0.1:8080";

const $status = document.getElementById("status");
const $serverUrl = document.getElementById("serverUrl");
const $sendBtn = document.getElementById("sendBtn");

async function loadState() {
    const s = await browserAPI.storage.local.get([
        "serverUrl",
        "lastSent",
        "lastStatus",
        "lastMessage",
    ]);
    $serverUrl.value = s.serverUrl || DEFAULT_SERVER;

    if (!s.lastSent) {
        $status.className = "status info";
        $status.textContent = "Ещё ничего не перехвачено. Открой chat.deepseek.com и отправь сообщение.";
        return;
    }

    const when = new Date(s.lastSent).toLocaleTimeString();
    if (s.lastStatus === "ok") {
        $status.className = "status ok";
        $status.textContent = `✓ ${when} — ${s.lastMessage || "OK"}`;
    } else {
        $status.className = "status error";
        $status.textContent = `✗ ${when} — ${s.lastMessage || "ошибка"}`;
    }
}

$serverUrl.addEventListener("change", async () => {
    const url = $serverUrl.value.trim() || DEFAULT_SERVER;
    await browserAPI.storage.local.set({ serverUrl: url });
    $serverUrl.value = url;
});

$sendBtn.addEventListener("click", async () => {
    $sendBtn.disabled = true;
    $sendBtn.textContent = "Отправка…";
    try {
        const resp = await new Promise((resolve) => {
            browserAPI.runtime.sendMessage({ type: "MANUAL_SEND" }, resolve);
        });
        if (resp?.ok) {
            $sendBtn.textContent = "Отправлено ✓";
        } else {
            $sendBtn.textContent = "Не удалось";
        }
    } catch (e) {
        $sendBtn.textContent = "Ошибка";
    }
    setTimeout(() => {
        $sendBtn.disabled = false;
        $sendBtn.textContent = "Отправить токен сейчас";
        loadState();
    }, 1500);
});

loadState();
