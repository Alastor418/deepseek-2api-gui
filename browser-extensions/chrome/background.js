// DeepSeek 2API Token Capture — Chrome (MV3)
// Слушает запросы к chat.deepseek.com/api/*, вытаскивает Authorization
// и Cookie, POST-ит их на локальный DeepSeek-2API.

const DEFAULT_SERVER = "http://127.0.0.1:8080";
const DEEPSEEK_PATTERN = "https://chat.deepseek.com/api/*";
const THROTTLE_MS = 60000; // не чаще раза в 10 секунд
const browserAPI = typeof browser !== "undefined" ? browser : chrome;

async function getServerUrl() {
    const stored = await browserAPI.storage.local.get(["serverUrl"]);
    return stored.serverUrl || DEFAULT_SERVER;
}

async function setStatus(ok, message) {
    await browserAPI.storage.local.set({
        lastSent: Date.now(),
        lastStatus: ok ? "ok" : "error",
        lastMessage: message,
    });
    const text = ok ? "✓" : "!";
    const color = ok ? "#10b981" : "#ef4444";
    try {
        await browserAPI.action.setBadgeText({ text });
        await browserAPI.action.setBadgeBackgroundColor({ color });
        setTimeout(() => {
            browserAPI.action.setBadgeText({ text: "" }).catch(() => {});
        }, 3000);
    } catch (_e) {}
}

async function sendToServer(authorization, cookie) {
    const server = await getServerUrl();
    const url = `${server}/gui/accounts`;
    try {
        const resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                label: "extension",
                authorization,
                cookie,
            }),
        });
        const body = await resp.text();
        if (resp.ok) {
            await setStatus(true, `OK: ${body.slice(0, 200)}`);
            return true;
        }
        await setStatus(false, `HTTP ${resp.status}: ${body.slice(0, 200)}`);
        return false;
    } catch (e) {
        await setStatus(false, `Network: ${String(e)}`);
        return false;
    }
}

async function readCookies() {
    try {
        const cookies = await browserAPI.cookies.getAll({ domain: "deepseek.com" });
        return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    } catch (_e) {
        return "";
    }
}

async function onRequest(details) {
    const headers = details.requestHeaders || [];
    const authHeader = headers.find(
        (h) => (h.name || "").toLowerCase() === "authorization"
    );
    if (!authHeader || !authHeader.value) return;
    if (!authHeader.value.startsWith("Bearer ")) return;

    // throttle
    const state = await browserAPI.storage.local.get(["lastSent"]);
    if (state.lastSent && Date.now() - state.lastSent < THROTTLE_MS) return;

    const cookie = await readCookies();
    await sendToServer(authHeader.value, cookie);
}

// --- подписка на webRequest ---
// В MV3 работает как read-only слушатель. extraHeaders нужен чтобы видеть
// заголовок Authorization (иначе Chrome его скрывает для безопасности).
browserAPI.webRequest.onSendHeaders.addListener(
    onRequest,
    { urls: [DEEPSEEK_PATTERN] },
    ["requestHeaders", "extraHeaders"]
);

// --- Сообщения из popup ---
browserAPI.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg?.type === "MANUAL_SEND") {
        // popup попросит отправить последний сохранённый токен
        browserAPI.storage.local
            .get(["lastAuthorization", "lastCookie"])
            .then(({ lastAuthorization, lastCookie }) => {
                if (!lastAuthorization) {
                    sendResponse({ ok: false, error: "Нет сохранённого токена" });
                    return;
                }
                sendToServer(lastAuthorization, lastCookie || "").then((ok) => {
                    sendResponse({ ok });
                });
            });
        return true; // async response
    }
    return false;
});

// --- Запоминаем последний токен (для кнопки "Отправить сейчас") ---
// Немного хака: вместо отдельного listener, дублируем логику сохранения
// в том же onSendHeaders. Но проще: сохранять в sendToServer. Сейчас
// сохраняем прямо в onRequest через storage.
const _origOnRequest = onRequest;
async function onRequestWithSave(details) {
    const headers = details.requestHeaders || [];
    const authHeader = headers.find(
        (h) => (h.name || "").toLowerCase() === "authorization"
    );
    if (authHeader?.value?.startsWith("Bearer ")) {
        const cookie = await readCookies();
        await browserAPI.storage.local.set({
            lastAuthorization: authHeader.value,
            lastCookie: cookie,
        });
    }
    return _origOnRequest(details);
}
// Перезаписываем listener
browserAPI.webRequest.onSendHeaders.removeListener(onRequest);
browserAPI.webRequest.onSendHeaders.addListener(
    onRequestWithSave,
    { urls: [DEEPSEEK_PATTERN] },
    ["requestHeaders", "extraHeaders"]
);

console.log("[DeepSeek 2API] background service worker запущен");
