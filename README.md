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
| Экспорт результатов в JSON и CSV (витрина, аудит, сценарии, метрики) | ✅ |
| Веб-панель (Streamlit): 6 экранов | ✅ |
| Docker: backend + frontend одним `docker compose up` | ✅ (backend `healthy`, панель на 8501) |
| Набор тестовых данных `tests_data/` + 15 сквозных сценариев (31 тест) | ✅ |
| Unit- и integration-тесты, линтер | ✅ 121 тест, покрытие app/ 96%, ruff чист |

Чего в MVP **сознательно нет** (по ТЗ §22): реального парсинга площадок, автоотправки откликов,
RAG/векторной базы, Redis, Celery, Kubernetes, микросервисов, OpenClaw/Hermes.
Вместо этого заложены интерфейсы под них — `OrderSource`, `LLMProvider`, `Repository`.

## Быстрый старт

### 1. Установка зависимостей

```bash
git clone <ссылка на репозиторий>
cd AI_Freelance_Copilot

py -3.13 -m venv .venv                                              # Windows
./.venv/Scripts/python.exe -m pip install -r requirements.txt

# Linux/macOS:
# python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt
```

### 2. Переменные окружения

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

`.env` в Git не попадает (`.gitignore`), ключи хранятся только локально.

### 3. Backend (FastAPI)

```bash
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Backend поднимется на `http://127.0.0.1:8000`, документация — `http://127.0.0.1:8000/docs`.

Важно: адрес именно `127.0.0.1`, а не `localhost`. На Windows `localhost` разрешается сначала
в IPv6 (`::1`), и если порт 8000 там занят ретранслятором Docker от другого контейнера, запрос
уходит не в это приложение и возвращается `{"detail":"Not Found"}`.
База SQLite создаётся автоматически в `data/app.db`, профиль исполнителя — тоже.

### 4. Демонстрационные данные (необязательно, но удобно для защиты)

```bash
./.venv/Scripts/python.exe scripts/seed_demo.py
```

Скрипт создаёт 4 заказа (подходящий, «пустой» без бюджета, неподходящий и ещё один подходящий)
и прогоняет по ним ИИ-анализ, печатая результат и метрики.

### 5. Веб-панель (Streamlit)

```bash
./.venv/Scripts/python.exe -m streamlit run frontend/streamlit/app.py
```

Панель на `http://127.0.0.1:8501`. Экраны: Обзор, Заказы, Карточка заказа,
Требуют проверки, Аудит и ошибки, Метрики и экономика.

### 6. Docker (backend + frontend)

```bash
docker compose up --build
```

Backend — `http://127.0.0.1:8000`, панель — `http://127.0.0.1:8501`, БД в volume `copilot-data`.
Если эти порты заняты другими проектами: `BACKEND_PORT=8300 FRONTEND_PORT=8601 docker compose up -d`.
Детали и результаты проверки в контейнере — `docs/DOCKER.md`.

## Переменные окружения

Все переменные читаются из `.env` (или из окружения — в Docker ключ передаётся только так).
Полный список с комментариями — `.env.example`; значения по умолчанию заданы в `app/config.py`.

| Переменная | По умолчанию | Что задаёт |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` — офлайн-провайдер без сети и денег; `openai` — любой OpenAI-совместимый шлюз (`proxyapi` принимается как алиас) |
| `LLM_MODEL` | `mock-model` | имя модели, например `gpt-4o-mini` или `deepseek-chat` |
| `LLM_API_KEY` | — | ключ провайдера; **не коммитится**, только локально или через окружение |
| `LLM_BASE_URL` | — | префикс эндпоинта, например `https://api.proxyapi.ru/openai/v1`; код сам добавляет `/chat/completions` |
| `LLM_TIMEOUT_S` | `60` | таймаут запроса; при холодном DNS разумно `90` |
| `LLM_TEMPERATURE` | `0.0` | температура генерации: анализ должен быть воспроизводимым |
| `DATABASE_URL` | `sqlite:///./data/app.db` | строка подключения; для демо-прогона удобно `sqlite:///./artifacts/demo.db` |
| `BACKEND_URL` | `http://127.0.0.1:8000` | адрес backend для панели Streamlit |
| `APP_ENV` | `development` | окружение, попадает в `/api/v1/health` |
| `APP_NAME` | `AI Freelance Copilot` | имя приложения в `/api/v1/health` |
| `LOG_LEVEL` | `INFO` | уровень логирования |
| `DB_ECHO` | `false` | печатать SQL-запросы (отладка) |
| `DEFAULT_PROFILE_ID` | `1` | профиль исполнителя, применяемый по умолчанию |
| `MIN_DESCRIPTION_CHARS` | `40` | короче — заказ уходит на ручную проверку (§14.1) |
| `MATCH_SCORE_REVIEW_THRESHOLD` | `0.35` | порог уверенности: ниже — заказ уходит на ручную проверку |
| `LLM_SCORE_CROSSCHECK_DELTA` | `0.5` | допустимое расхождение оценки модели и расчёта по профилю |
| `MIN_DRAFT_REPLY_CHARS` | `80` | короче — черновик считается несформированным (§14.4) |
| `LLM_MAX_OUTPUT_TOKENS` | `1500` | ограничение длины ответа модели |
| `BACKEND_PORT` / `FRONTEND_PORT` | `8000` / `8501` | внешние порты Docker-контейнеров (только compose) |

Ставка для мини-экономики задаётся в коде: `DEFAULT_HOURLY_RATE_RUB = 1500`
(`app/domain/services/metrics_service.py`).

Проверить, какой провайдер активен и не тратятся ли деньги:

```bash
curl -s http://127.0.0.1:8000/api/v1/health
```

```json
{"status":"ok","app_env":"development","database":"sqlite","api_version":"v1",
 "provider":{"name":"mock","model":"mock-model","prompt_version":"v1.0","is_live":false,
 "warning":"Активен mock-провайдер: сеть и деньги не используются."}}
```

`"is_live": true` означает, что включён **реальный** провайдер и каждый анализ тратит деньги.

## Примеры запросов (curl)

**1. Создать заказ (точка 1 — вход контура).**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Разработка Telegram-бота на Python с ИИ-ассистентом",
    "description": "Нужен Telegram-бот на Python с интеграцией LLM (GPT). Требуется опыт FastAPI, REST API, Docker и PostgreSQL. Бюджет 30000-50000 руб, срок 3 недели.",
    "budget_min": 30000, "budget_max": 50000, "currency": "RUB",
    "source": "manual", "external_id": "readme-01", "client_name": "Иван"
  }'
```

**2. Запустить ИИ-анализ (точка 3 — решение системы).**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/orders/1/analyze \
  -H "Content-Type: application/json" -d '{}'
```

Ответ содержит оценку соответствия, рекомендацию, черновик отклика, а также `needs_review`,
`review_reason`, `audit_status` и `duration_ms`.

**3. Посмотреть витрину с фильтрами (точка 2).**

```bash
curl -s "http://127.0.0.1:8000/api/v1/orders?recommendation=apply&status=analyzed&page_size=10"
curl -s "http://127.0.0.1:8000/api/v1/orders?needs_review=true"      # очередь на ручную проверку
curl -s "http://127.0.0.1:8000/api/v1/orders?search=Tilda"           # поиск по тексту и заголовку
```

**4. Закрыть ручную проверку (решение человека).**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/analyses/1/review \
  -H "Content-Type: application/json" \
  -d '{"decision": "approved", "comment": "Стек совпадает, беру в работу"}'
```

**5. Аудит и метрики.**

```bash
curl -s "http://127.0.0.1:8000/api/v1/audit?action=analyze_order&page_size=20"
curl -s http://127.0.0.1:8000/api/v1/audit/actions
curl -s http://127.0.0.1:8000/api/v1/metrics
```

## Где лежит база данных и как посмотреть данные и аудит

| Что | Где |
|---|---|
| Файл БД (локальный запуск) | `data/app.db` — SQLite, создаётся автоматически при старте |
| Файл БД (Docker) | volume `copilot-data`, внутри контейнера `/app/data/app.db` |
| Таблицы | `orders`, `analyses`, `audit_runs`, `profiles` |
| Витрина данных | `GET /api/v1/orders` или экраны «Заказы» / «Требуют проверки» в панели |
| Журнал аудита | `GET /api/v1/audit` + `GET /api/v1/audit/actions`, экран «Аудит и ошибки» |
| Экспорт | `artifacts/`: `showcase-*.json/.csv`, `audit-*.json/.csv`, `scenarios-*.json/.csv`, `metrics-*.json` |

Посмотреть данные напрямую в SQLite:

```bash
./.venv/Scripts/python.exe -c "import sqlite3; [print(r) for r in sqlite3.connect('data/app.db').execute('select id, action, order_id, status, duration_ms from audit_runs order by id desc limit 10')]"
```

Схема данных с полями и связями — `docs/ARCHITECTURE.md` (раздел «Схема данных»).

### Переключение между базами (важно при демонстрации)

Панель показывает **ту базу, которую читает backend**. Если поднять backend с другим `DATABASE_URL`,
панель этого не заметит — она просто покажет старые данные из `data/app.db` с другого порта.
Поэтому для показа прогона на реальной модели нужна своя пара «backend + панель»:

```bash
# демонстрация (mock, база data/app.db, порты 8000/8501)
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
./.venv/Scripts/python.exe -m streamlit run frontend/streamlit/app.py

# живой прогон на реальной модели (база artifacts/live.db, порты 8600/8602)
DATABASE_URL="sqlite:///./artifacts/live.db" LLM_PROVIDER=openai \
  ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8600
BACKEND_URL="http://127.0.0.1:8600" \
  ./.venv/Scripts/python.exe -m streamlit run frontend/streamlit/app.py --server.port 8602

# прогон набора тестовых данных (15 сценариев, база artifacts/demo.db)
DATABASE_URL="sqlite:///./artifacts/demo.db" \
  ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8400
```

Панель пишет в подвале адрес своего backend — по нему видно, к какой базе она подключена.

## Тестовые данные (папка `tests_data/`)

| Файл | Содержимое |
|---|---|
| `inputs.jsonl` | 15 входных заказов (id, пояснение правила, тело запроса) |
| `specs.jsonl` | ожидаемый результат каждого сценария: рекомендация, оценка, `needs_review`, статус аудита, причина |
| `events.jsonl` | ожидаемое событие аудита на каждое ключевое действие |
| `queries.jsonl` | 10 запросов витрины с ожидаемым `total` (фильтры, поиск, пагинация, ошибочный фильтр) |

**8 из 15 сценариев приводят к ручной проверке** — с разными причинами, а не одним и тем же случаем:

| Сценарий | Причина ручной проверки | Правило ТЗ |
|---|---|---|
| `S07_no_budget_long` | не указан бюджет | §14.1 |
| `S08_vague_short` | нет ни бюджета, ни объёма работ | §14.1 |
| `S09_partial_match` | уверенность модели ниже порога (`score 0.10 < 0.35`) | §14.3 |
| `S11_analytics_borderline` | модель сама сообщила о неуверенности | §14.3 |
| `S12_llm_bad_json` | модель вернула невалидный JSON | §14.2 |
| `S13_llm_timeout` | ошибка LLM (timeout) → заказ в `error` | §14.5 |
| `S14_llm_no_draft` | `apply` без черновика отклика понижен до `review` | §14.4 |
| `S15_llm_inflated` | оценка модели расходится с расчётом по профилю (`0.99` против `0.00`) | §14.6 |

Сценарии `S12`–`S15` включаются триггерами в заголовке (`MOCK_BAD_JSON`, `MOCK_TIMEOUT`,
`MOCK_NO_DRAFT`, `MOCK_INFLATED`) — так аварийные ветки проверяются сквозь API, а не только
юнит-тестом на внутреннем методе.

## Тесты и линтер

```bash
./.venv/Scripts/python.exe -m pytest               # 104 теста, сеть и деньги не используются
./.venv/Scripts/python.exe -m ruff check .        # линтер
./.venv/Scripts/python.exe scripts/check_secrets.py   # ключи не должны попасть в Git
```

Все тесты идут на `MockProvider` (ТЗ §17): ни одного сетевого вызова, ни одного потраченного рубля.

### Как воспроизвести «ручную проверку»

Ручная проверка — это сценарий из набора данных, воспроизводится одним тестом:

```bash
# один конкретный случай ручной проверки
./.venv/Scripts/python.exe -m pytest "tests/integration/test_tests_data_suite.py::test_cases_requiring_manual_review_are_flagged"

# весь набор 15 сценариев через API
./.venv/Scripts/python.exe -m pytest tests/integration/test_tests_data_suite.py -q
```

Тест `test_cases_requiring_manual_review_are_flagged` требует, чтобы у каждого такого сценария
были: `needs_review=true`, непустая `review_reason` и **отсутствующий** черновик отклика
(на ручную проверку уходит безопасный результат, а не готовый текст клиенту).

Чтобы увидеть то же самое глазами и получить артефакты для отчёта, нужен поднятый backend:

```bash
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000   # терминал 1
./.venv/Scripts/python.exe scripts/run_tests_data.py                              # терминал 2
```

Скрипт заливает все 15 заказов, прогоняет анализ, сверяет факт со `specs.jsonl`, выполняет
запросы витрины, печатает таблицу «сценарий → решение → причина → статус аудита» и
выгружает JSON + CSV в `artifacts/`. Ненулевой код возврата означает расхождение с ожиданиями.

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
tests_data/             набор тестовых данных: inputs/specs/events/queries.jsonl
tests/                  unit + integration (+ fixtures для набора данных)
scripts/                seed_demo.py, run_tests_data.py, check_secrets.py
artifacts/              экспорт прогона: JSON и CSV (создаётся скриптом)
docs/                   архитектура, API, сценарий защиты, экономика, Docker
Dockerfile.backend, Dockerfile.frontend, docker-compose.yml
```

## Документация

| Файл | О чём |
|---|---|
| `docs/REQUIREMENTS_MAPPING.md` | каждое требование → где реализовано и чем проверено; осознанные отклонения от ТЗ |
| `docs/ARCHITECTURE.md` | слои, диаграммы, схема данных, контракт с моделью, шесть бизнес-правил |
| `docs/API.md` | все точки доступа с примерами запросов и ответов |
| `docs/DEFENSE_SCENARIO.md` | сценарий защиты 5–7 минут по шаблону урока: тайминг, что говорить, что показывать |
| `docs/DEMO_SCENARIO.md` | пошаговый сценарий демонстрации и записи видео + частые вопросы |
| `docs/ECONOMICS.md` | мини-экономика и метрики, правило «нет данных ≠ ноль» |
| `docs/DOCKER.md` | запуск и проверка контейнеров |
| `docs/CHECKLIST.md` | чек-лист приёмки: что проверено, что требует вашего участия |
| `docs/PROJECT_JOURNAL.md` | журнал решений и найденных дефектов |
| `docs/REPORT.md` | готовый отчёт по шаблону урока: ценность, сценарии, схема данных, ИИ-операция, качество, экономика, риски, план |
| `docs/REPORT_TEMPLATE.md` | отчёт по шаблону: ценность, сценарии, схема данных, качество, экономика, риски, развитие |
