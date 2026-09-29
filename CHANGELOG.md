# Changelog

Все значимые изменения проекта. Формат основан на
[Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).

## [3.3.1] - 2026-09-29

### Added
- **Tool bridge** (`app/providers/tool_bridge.py`) - универсальный парсер
  `tool_calls` в OpenAI-формат:
  - `<tool_call>{json}</tool_call>` (OpenAI-стиль)
  - `<invoke name=...><parameter name=...>value</parameter></invoke>` (Anthropic-стиль)
  - DSML-маркеры (`| |DSML| |`) - вычищаются на выходе
  - Компактное описание tools в system prompt (вместо полной JSON-схемы)
- **Streaming tool detection** в `_handle_stream` - ловит `invoke ` в буфере,
  переключается в `tool_mode`, парсит блок в `tool_calls`
- **`FORCE_THINKING`** и **`FORCE_SEARCH`** в `config.py` - жёстко включают
  reasoning и web search для всех запросов

### Fixed
- **Request serialization** - `_request_lock` перенесён вокруг `_with_retry`,
  чтобы два параллельных запроса от Harness (main + title generation) не
  создавали две сессии DeepSeek одновременно
- **Throttle 2 секунды** между запросами (`_min_interval`) - DeepSeek
  отклоняет параллельные сессии на одном аккаунте
- **`_NoAccounts`** -> HTTP 503 без шумных traceback'ов
- **Stream cleanup** через `contextlib.aclosing` + `GeneratorExit` -
  правильно закрывает SSE при disconnect клиента

### Verified
- End-to-end через DeepSeek Harness UI: модель **создала `snake.py`**
  (136 строк) через `write` tool
- 47 тестов pytest - все зелёные
- ruff clean, mypy clean

## [3.2.0] - 2026-09-29

### Added
- **Browser extensions** (Chrome MV3 + Firefox MV2) - перехватывают
  `Authorization`/`Cookie` из `chat.deepseek.com` и POST-ят в `/gui/accounts`.
  Обход hCaptcha.
- **CORS middleware** для `chrome-extension://` и `moz-extension://`
- **DeepSeek Harness integration** в installer:
  - Автогенерация `~/.dsh/.env`
  - Автогенерация `~/.dsh/profiles/web/cordis.patch.yml` с провайдером `deepseek-2api`
  - systemd unit для `deepseek-harness.service`
  - `--allow-scripts` для npm install (koffi, node-pty, dsh-subprocess-local)
- **`AUTO_WEB_SEARCH`** флаг - автовключение search при tool `web_search`

### Fixed
- Пропущенный `raise from err` в `capture.py`
- `SIM105`, `B904` - все ruff-ошибки

## [3.1.0] - 2026-09-29

### Added
- **Atomic writes** (tmp -> fsync -> rename) для `storage.py` и `accounts.py`
- **Thread-safe AccountPool** (`RLock`)
- **Singleton PowSolver** с sanity-check на WASM-экспорты
- **Pydantic schemas** для `ChatCompletionRequest`, `AccountCreate`
- **`pyproject.toml`** с ruff, mypy, pytest
- **47 тестов**: storage, accounts, extract_delta, schemas, api, pow
- **`install.sh`** - установщик одной командой
- **`UNINSTALL.sh`** - полное удаление
- **`verify.sh`** - 22 health-check
- **`QUICKSTART.txt`** - шпаргалка
- **`INSTALL-COMPLETE.md`** - 1027 строк полного мануала

### Fixed (13 критических)
- `_raw_stream` - мёртвая проверка токена (`r.text if False else ""`) -
  тихо глотал 200-OK-with-error
- `_handle_stream::finally` - маскировал ошибки под `finish_reason: stop`
- `verify_api_key` - fail-open при `API_MASTER_KEY=None` -> fail-closed
- `mark_error` - не помечал аккаунт мёртвым после первой ошибки -> зацикливание
- Race conditions в `AccountPool`
- `_lifespan` - tasks без ссылок, GC убивал их
- `/gui/*` был доступен с любого хоста -> только localhost
- `verify_api_key` без `secrets.compare_digest`
- `_lifespan` timeout при shutdown -> SIGKILL через 16 сек
- Порт 8080 занят после перезапуска

## [3.0.0] - 2025-09-29

Начальная версия. Базовый функционал:
- OpenAI-совместимый прокси для DeepSeek
- Автологин через Playwright
- PoW через WASM
- `deepseek-chat` и `deepseek-reasoner`
- Веб-GUI

---

## Легенда

- **Added** - новый функционал
- **Changed** - изменения существующего
- **Deprecated** - устарело, будет удалено
- **Removed** - удалено
- **Fixed** - исправления
- **Security** - безопасность
- **Verified** - что проверено
