
with open("app/gui/server.py") as f:
    content = f.read()

bad = """    try:
        if provider._client is None:
            return False
        r = await provider._client.post(
            f"{provider.BASE_URL}/chat_session/create",
            headers=headers,
            json={},
            timeout=10,
        )
            try:
                parsed = r.json()
            except Exception:
                parsed = None

            if _is_dead_session(r.status_code, r.text, parsed):
                logger.info(f"   [startup] dead session: {r.text[:120]}")
                return False
            if not isinstance(parsed, dict):
                return False
            data = parsed.get("data")
            if not isinstance(data, dict):
                return False
            biz = data.get("biz_data")
            if not isinstance(biz, dict):
                return False
            return bool(biz.get("id"))
    except Exception as e:"""

good = """    try:
        if provider._client is None:
            return False
        r = await provider._client.post(
            f"{provider.BASE_URL}/chat_session/create",
            headers=headers,
            json={},
            timeout=10,
        )
        try:
            parsed = r.json()
        except Exception:
            parsed = None

        if _is_dead_session(r.status_code, r.text, parsed):
            logger.info(f"   [startup] dead session: {r.text[:120]}")
            return False
        if not isinstance(parsed, dict):
            return False
        data = parsed.get("data")
        if not isinstance(data, dict):
            return False
        biz = data.get("biz_data")
        if not isinstance(biz, dict):
            return False
        return bool(biz.get("id"))
    except Exception as e:"""

content = content.replace(bad, good)

with open("app/gui/server.py", "w") as f:
    f.write(content)
