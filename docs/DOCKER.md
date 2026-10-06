# Docker: backend + frontend (ТЗ §31)

## Запуск

```bash
cd "D:\\python projects\\AI_Freelance_Copilot"
docker compose up --build
```

* Backend (FastAPI): `http://localhost:8000`, документация `/docs`
* Веб-панель (Streamlit): `http://localhost:8501`
* Файл SQLite лежит в именованном volume `copilot-data` → данные переживают пересборку.

Если порты заняты (на этой машине `8000` уже слушает другой проект — `faceid-core-api`),
переопределите их:

```bash
BACKEND_PORT=8300 FRONTEND_PORT=8601 docker compose up --build -d
```

Остановить: `docker compose down` (с удалением данных — `docker compose down -v`).

## Конфигурация

По умолчанию контейнеры поднимаются на `LLM_PROVIDER=mock`: без ключей, без сети, без затрат.
Чтобы включить реальную модель, достаточно переменных окружения при запуске:

```bash
LLM_PROVIDER=openai LLM_BASE_URL=https://api.proxyapi.ru/deepseek/v1 LLM_MODEL=deepseek-chat \
LLM_API_KEY=... docker compose up --build
```

Файл `.env` при этом не требуется — значения подставляются в сервисы из окружения.

## Что проверено запуском

```text
docker compose up --build -d
  Image ai_freelance_copilot-backend Built
  Image ai_freelance_copilot-frontend Built

docker compose ps
  copilot-backend    Up (healthy)   0.0.0.0:8300->8000/tcp
  copilot-frontend   Up             0.0.0.0:8601->8501/tcp

curl http://localhost:8300/api/v1/health
  {"status":"ok","app_env":"production","database":"sqlite", ..., "provider":{"name":"mock", ...}}

POST /api/v1/orders              → 201 {"id":1,"status":"new"}
GET  /api/v1/orders              → {"items":[...],"total":1,"page":1,"page_size":5}
POST /api/v1/orders/1/analyze    → {"order_status":"analyzed","duration_ms":8,
                                    "audit_status":"success",
                                    "result":{"match_score":1.0,"recommendation":"apply", ...}}

docker compose exec -T backend python -c "...count..."
  orders: 1  analyses: 1  audit: 4
```

Панель в контейнере (`http://localhost:8601`) тоже открыта и отдаёт данные из контейнерного
backend: `Backend: ok · БД: sqlite · LLM: mock`.

## Почему два Dockerfile

`Dockerfile.backend` и `Dockerfile.frontend` разделены намеренно:

* у backend есть `HEALTHCHECK` на `/api/v1/health`, и compose ждёт `service_healthy`
  перед стартом frontend;
* если собирать оба контейнера из одного образа, Streamlit **наследует** healthcheck backend
  и навсегда остаётся в статусе `unhealthy`, хотя работает. Это не косметика: по такому
  контейнеру нельзя судить о живости системы.

## Полезные команды

```bash
docker compose ps                        # статус (backend должен быть healthy)
docker compose logs -f backend           # логи backend
curl http://localhost:8000/api/v1/health # проверка живости
docker compose exec -T backend python -c "import sqlite3;c=sqlite3.connect('/app/data/app.db');print(c.execute('select count(*) from orders').fetchone())"
docker compose down -v                   # остановить и удалить volume с данными
```

## Ограничения MVP-обвязки

* PostgreSQL не подключён: SQLite в volume. Repository Layer к SQLite не привязан, переход
  на PostgreSQL — правка `DATABASE_URL` и инфраструктурного слоя.
* HTTPS, reverse-proxy и аутентификация не настраивались: это следующий этап, в MVP не требуется.
* Порты по умолчанию (`8000`/`8501`) могут конфликтовать с другими вашими проектами —
  используйте `BACKEND_PORT`/`FRONTEND_PORT`.
