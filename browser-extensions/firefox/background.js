// DeepSeek 2API Token Capture — Firefox (MV2)

const DEFAULT_SERVER = "http://127.0.0.1:8080";
const DEEPSEEK_PATTERN = "https://chat.deepseek.com/api/*";
const THROTTLE_MS = 60000;
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
    try {
        browserAPI.browserAction.setBadgeText({ text: ok ? "✓" : "!" });
        browserAPI.browserAction.setBadgeBackgroundColor({
            color: ok ? "#10b981" : "#ef4444",
        });
        setTimeout(() => browserAPI.browserAction.setBadgeText({ text: "" }), 3000);
    } catch (_e) {}
}

async function sendToServer(authorization, cookie) {
    const server = await getServerUrl();
    try {
        const resp = await fetch(`${server}/gui/accounts`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label: "extension-ff", authorization, cookie }),
        });
        const body = await resp.text();
        await setStatus(resp.ok, resp.ok ? `OK: ${body.slice(0, 200)}` : `HTTP ${resp.status}: ${body.slice(0, 200)}`);
        return resp.ok;
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
    if (!authHeader?.value?.startsWith("Bearer ")) return;

    const cookie = await readCookies();
    await browserAPI.storage.local.set({
        lastAuthorization: authHeader.value,
        lastCookie: cookie,
    });

    const state = await browserAPI.storage.local.get(["lastSent"]);
    if (state.lastSent && Date.now() - state.lastSent < THROTTLE_MS) return;

    await sendToServer(authHeader.value, cookie);
}

browserAPI.webRequest.onSendHeaders.addListener(
    onRequest,
    { urls: [DEEPSEEK_PATTERN] },
    ["requestHeaders"]
);

browserAPI.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg?.type === "MANUAL_SEND") {
        browserAPI.storage.local
            .get(["lastAuthorization", "lastCookie"])
            .then(({ lastAuthorization, lastCookie }) => {
                if (!lastAuthorization) {
                    sendResponse({ ok: false, error: "Нет сохранённого токена" });
                    return;
                }
                sendToServer(lastAuthorization, lastCookie || "").then((ok) =>
                    sendResponse({ ok })
                );
            });
        return true;
    }
    return false;
});

console.log("[DeepSeek 2API] Firefox background запущен");
