# Telegram Bot AI Integrator (Puzzlebot)

Бекенд + веб‑интерфейс для интеграции LLM в Telegram‑боты, собранные через `puzzlebot.top`.

Идея: Puzzlebot умеет делать запросы (webhook), но не умеет обработать ответ. Этот сервис принимает запрос, **сам** получает ответ от LLM по заранее настроенному промту и **сам** отправляет результат в Telegram‑чат нужному пользователю через Bot API.

## Возможности

- UI для управления промтами (CRUD)
- API‑эндпоинт для Puzzlebot: `prompt_id + params + user_id + bot_api_key`
- Запрос к LLM (OpenAI‑compatible API)
- Отправка сообщения или брендированного PDF пользователю через Telegram Bot API
- Сохранение настроек и логов в БД (SQLite по умолчанию)
- Асинхронная обработка (готово для сотен одновременных запросов на одном инстансе)

## Быстрый старт

1) Установить зависимости:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Создать `.env` (см. `.env.example`)

3) Запуск:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Открыть UI: `http://localhost:8080/ui/`  
Swagger: `http://localhost:8080/docs`

## Интеграционный эндпоинт для Puzzlebot

`POST /api/v1/puzzlebot/ai`

### Вариант A (рекомендуется): отправлять готовый промт (меньше параметров)

```json
{
  "prompt": "Сделай краткий гороскоп на сегодня для знака Овен. 3 пункта.",
  "chat_id": 123456789,
  "bot_api_key": "123456:ABCDEF...",
  "send_pdf": true
}
```

### Вариант B (legacy): `prompt_id + params`

```json
{
  "prompt_id": "welcome",
  "params": {"name": "Иван"},
  "bot_api_key": "123456:ABCDEF...",
  "chat_id": 123456789,
  "send_pdf": false
}
```

Ответ (теперь синхронный: 200 только после отправки в Telegram):

```json
{ "status": "ok", "request_id": "...", "llm_ok": true, "telegram_ok": true }
```

## Хранение данных

- По умолчанию используется SQLite файл в `./data/app.db`
- Можно переключить на Postgres через `DATABASE_URL`

## Безопасность (минимум для MVP)

UI защищён админ‑логином (сессия). Пароль задаётся через переменные окружения.

## Переменные окружения

Смотрите `.env.example`:

- **UI**: `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- **LLM**: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_DEFAULT_MODEL`, `LLM_AUTH_HEADER`, `LLM_AUTH_PREFIX`
- **DB**: `DATABASE_URL`
- **PDF**: `PDF_LOGO_PATH`, `PDF_FONT_PATH`, `PDF_FONT_BOLD_PATH`, `PDF_BODY_FONT_PATH`, `PDF_BODY_FONT_BOLD_PATH`, `PDF_BODY_FONT_ITALIC_PATH`, `PDF_BODY_FONT_BOLD_ITALIC_PATH` (по умолчанию фон в `app/static/dailymind-hero.jpg`)

### Частая ошибка с Timeweb Agents

Если вы используете `agent.timeweb.cloud`, то:

- `LLM_BASE_URL` обычно уже заканчивается на `/v1`
- `LLM_API_KEY` должен быть **реальным Bearer-токеном** (JWT/API token), как в рабочем `curl ... --header 'Authorization: Bearer <token>'`
- `LLM_API_KEY` **не** должен быть id агента (UUID)
