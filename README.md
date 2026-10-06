# AI Freelance Copilot — MVP ядра системы автоматизации фриланса

Учебный выпускной проект: **не просто «LLM отвечает на запрос»**, а рабочий контур
`ЗАКАЗ → ИИ-АНАЛИЗ → РЕШЕНИЕ → (человек) → АУДИТ`, спроектированный так, чтобы после защиты
дорасти до полноценной автоматизации фриланса без переписывания основы.

## Что уже работает

| Возможность | Статус |
|---|---|
| Точка 1: `POST /api/v1/orders` — создание и нормализация заказа | ✅ |
| Точка 2: `GET /api/v1/orders` — витрина с фильтрами и пагинацией | ✅ |
| Точка 3: `POST /api/v1/orders/{id}/analyze` — ИИ-обработка, строгий JSON | ✅ |
| Строгая схема результата (`AnalysisResult`, Pydantic) | ✅ |
| `needs_review=true` + причина проверки + безопасный результат | ✅ |
| Ручная проверка: подтвердить / отклонить, решение в аудите | ✅ |
| Журнал аудита `audit_runs`: вход, выход, статус, ошибка, длительность | ✅ |
| Метрики проекта и мини-экономика | ✅ |
| Веб-панель (Streamlit): 6 экранов | ✅ |
| Docker: backend + frontend одним `docker compose up` | ✅ (backend `healthy`, панель на 8501) |
| Unit- и integration-тесты, линтер | ✅ 82 теста, покрытие app/ 95%, ruff чист |

Чего в MVP **сознательно нет** (по ТЗ §22): реального парсинга площадок, автоотправки откликов,
RAG/векторной базы, Redis, Celery, Kubernetes, микросервисов, OpenClaw/Hermes.
Вместо этого заложены интерфейсы под них — `OrderSource`, `LLMProvider`, `Repository`.

## Быстрый старт

### 1. Backend (FastAPI)

```bash
py -3.13 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt      # Windows
# python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt   # Linux/macOS

cp .env.example .env                                                  # ключи в .env, не в git
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Backend поднимется на `http://localhost:8000`, документация — `http://localhost:8000/docs`.
База SQLite создаётся автоматически в `data/app.db`, профиль исполнителя — тоже.

### 2. Демонстрационные данные (необязательно, но удобно для защиты)

```bash
./.venv/Scripts/python.exe scripts/seed_demo.py
```

Скрипт создаёт 4 заказа (подходящий, «пустой» без бюджета, неподходящий и ещё один подходящий)
и прогоняет по ним ИИ-анализ, печатая результат и метрики.

### 3. Веб-панель (Streamlit)

```bash
./.venv/Scripts/python.exe -m streamlit run frontend/streamlit/app.py
```

Панель на `http://localhost:8501`. Экраны: Обзор, Заказы, Карточка заказа,
Требуют проверки, Аудит и ошибки, Метрики и экономика.

### 4. Docker (backend + frontend)

```bash
docker compose up --build
```

Backend — `http://localhost:8000`, панель — `http://localhost:8501`, БД в volume `copilot-data`.
Если эти порты заняты другими проектами: `BACKEND_PORT=8300 FRONTEND_PORT=8601 docker compose up -d`.
Детали и результаты проверки в контейнере — `docs/DOCKER.md`.

## Тесты и линтер

```bash
./.venv/Scripts/python.exe -m pytest               # 82 теста, сеть и деньги не используются
./.venv/Scripts/python.exe -m ruff check .        # линтер
./.venv/Scripts/python.exe scripts/check_secrets.py   # ключи не должны попасть в Git
```

Все тесты идут на `MockProvider` (ТЗ §17): ни одного сетевого вызова, ни одного потраченного рубля.

## Как устроено

```
                ┌──────────────────┐
                │   Web UI         │   frontend/streamlit (6 экранов)
                │   Streamlit      │
                └────────┬─────────┘
                         │ HTTP (api_client.py)
                         ▼
                ┌──────────────────┐
                │     FastAPI      │   app/api (роуты, Pydantic-схемы)
                │   REST API       │
                └────────┬─────────┘
                         ▼
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   OrderService    AnalysisService    ReviewService     app/domain/services
   (заказы)        (ИИ + правила)     (ручная проверка)
        └────────────────┼────────────────┘
                         ▼
                   Repository Layer                     app/infrastructure/database
                         ▼
                     SQLite
                         ▲
                         │
                  LLMProvider (mock | OpenAI-совместимый)   app/infrastructure/llm
                  OrderSource (manual → flru/kwork/rss/…)    app/infrastructure/sources
```

Разбор решений и диаграммы — `docs/ARCHITECTURE.md`. Описание API с примерами — `docs/API.md`.

## Главный архитектурный принцип

LLM говорит, **что система считает**. Что системе **разрешено делать** — решает бизнес-логика
(`app/domain/services/analysis_service.py`). Модель не может «попросить» отправить отклик:
её ответ проходит шесть правил, и любое сомнение ведёт к `needs_review=true` с человеческим
решением. Подробнее — `docs/ARCHITECTURE.md`, раздел «Бизнес-правила».

## Подключение реальной модели

По умолчанию `LLM_PROVIDER=mock`: офлайн, детерминированно, бесплатно. Чтобы пойти в реальную
модель, достаточно правок в `.env` — код не меняется:

```env
LLM_PROVIDER=openai
LLM_MODEL=deepseek-chat
LLM_API_KEY=...
LLM_BASE_URL=https://api.proxyapi.ru/deepseek/v1
```

Провайдер OpenAI-**совместимый**, поэтому подходит любой шлюз (OpenAI, proxyapi.ru, DeepSeek,
локальная ollama с `/v1`). Тесты при этом продолжают идти на mock — их меняют только осознанно.

## Промпты

Промпт анализа лежит в `prompts/order_analysis.txt` и версионируется (`PROMPT_VERSION = "v1.0"`).
Версия сохраняется в каждом результате анализа и в аудите, поэтому результаты разных версий
промпта потом можно сравнивать между собой.

## Что дальше (этапы после защиты)

1. **Реальные источники** — `FlRuSource`, `KworkSource`, `RSSSource` через существующий `OrderSource`.
2. **Автосбор** — планировщик → нормализация → дедупликация → `orders`.
3. **Профиль + RAG** — выбор реальных проектов из портфолио при генерации отклика.
4. **Уведомления** — Telegram-действие (`ActionExecutor`).
5. **Автоматические действия** — только после того, как human-in-the-loop доказал надёжность.

## Структура репозитория

```
app/                    backend (модульный монолит)
  api/                  роуты и Pydantic-схемы
  domain/               модели, бизнес-логика, matching engine, метрики
  infrastructure/       БД, репозитории, LLM-провайдеры, источники заказов
frontend/streamlit/     веб-панель
prompts/                версионированные промпты
tests/                  unit + integration
scripts/                seed_demo.py, check_secrets.py
docs/                   архитектура, API, сценарий защиты, экономика, Docker
Dockerfile.backend, Dockerfile.frontend, docker-compose.yml
```

## Документация

| Файл | О чём |
|---|---|
| `docs/REQUIREMENTS_MAPPING.md` | каждое требование → где реализовано и чем проверено; осознанные отклонения от ТЗ |
| `docs/ARCHITECTURE.md` | слои, диаграммы, контракт с моделью, шесть бизнес-правил |
| `docs/API.md` | все точки доступа с примерами запросов и ответов |
| `docs/DEMO_SCENARIO.md` | пошаговый сценарий демонстрации на защите + частые вопросы |
| `docs/ECONOMICS.md` | мини-экономика и метрики, правило «нет данных ≠ ноль» |
| `docs/DOCKER.md` | запуск и проверка контейнеров |
| `docs/CHECKLIST.md` | чек-лист приёмки: что проверено, что требует вашего участия |
| `docs/PROJECT_JOURNAL.md` | журнал решений и найденных дефектов |
