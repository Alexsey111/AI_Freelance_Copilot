# Архитектура AI Freelance Copilot

## 1. Подход: модульный монолит

Микросервисы для учебного проекта избыточны, поэтому выбран модульный монолит с жёсткими
границами слоёв. Внутри кода есть возможность заменить любой компонент, не трогая остальные.

```mermaid
graph TD
    UI[Streamlit Web UI] -->|HTTP| API[FastAPI REST API]
    API --> OS[OrderService]
    API --> AS[AnalysisService]
    API --> RS[ReviewService]
    API --> MS[MetricsService]
    AS --> ME[Matching Engine]
    AS --> LLM[LLMProvider]
    OS --> REPO[Repository Layer]
    AS --> REPO
    RS --> REPO
    MS --> REPO
    REPO --> DB[(SQLite)]
    OS --> SRC[Order Source Adapter]
```

Слои и правило зависимостей:

| Слой | Каталог | Знает про |
|---|---|---|
| API | `app/api` | FastAPI, Pydantic-схемы, сервисы |
| Домен | `app/domain` | только свои модели и абстракции |
| Инфраструктура | `app/infrastructure` | SQLAlchemy, LLM SDK, HTTP |
| UI | `frontend/streamlit` | только HTTP API backend |

Домен не импортирует ни FastAPI, ни SQLAlchemy, ни конкретную LLM — поэтому `analysis_service.py`
не меняется ни при переходе `SQLite → PostgreSQL`, ни при замене `MockProvider → OpenAIProvider`.

## 2. Единая доменная модель

```mermaid
graph LR
    A[FL.ru] --> S[Source Adapter]
    B[Kwork] --> S
    C[Telegram] --> S
    D[RSS] --> S
    E[manual/API] --> S
    S --> N[Normalizer]
    N --> O[Order: единая модель]
```

Любой источник (сейчас `manual`, в будущем FL.ru, Kwork, Freelance.ru, Telegram, RSS, webhook)
приводит данные к `ExternalOrder`, а `normalize_external_order()` превращает их в доменный
`Order`. Бизнес-логика не знает, откуда пришёл заказ, и подключать новый источник означает
добавить один класс, а не ветвление в сервисах.

## 3. Жизненный цикл заказа

```text
NEW → ANALYZING → ┬→ ANALYZED → APPROVED
                  ├→ NEEDS_REVIEW → ┬→ APPROVED
                  │                 └→ REJECTED
                  └→ ERROR
```

Статусы зафиксированы в `OrderStatus` (ТЗ §27), произвольные строки не используются.

## 4. Строгий контракт с моделью

`AnalysisResult` (`app/domain/models/analysis.py`) — единственный формат, в котором
результат ИИ выходит из сервиса:

```python
class AnalysisResult(BaseModel):
    match_score: float | None
    recommendation: Literal["apply", "skip", "review"]
    reason: str
    matched_skills: list[str]
    missing_skills: list[str]
    draft_reply: str | None
    needs_review: bool
    review_reason: str | None
```

Три валидатора, которые делают схему не декоративной, а рабочей:

1. `needs_review=true` требует непустой `review_reason`; `needs_review=false` требует `review_reason=null`.
2. `needs_review=true` требует `recommendation="review"` и `draft_reply=null` — то есть результат,
   ушедший человеку, **по построению безопасен**: без выдуманного числа и без готового к отправке текста.
3. `extra="forbid"` — модель физически не может протащить лишнее поле вроде `send_message`.

Невалидный JSON от модели не «разбирается как получится»: он превращается в
`LLMInvalidResponseError`, то есть в ручную проверку (ТЗ §29.3).

## 5. Бизнес-правила поверх мнения модели

```mermaid
graph TD
    L[Ответ LLM] --> R1{Не хватает критичных данных?}
    R1 -->|да| RV[needs_review=true]
    R1 -->|нет| R2{Соответствие профилю определено?}
    R2 -->|нет| RV
    R2 -->|да| R3{Модель сама просит проверку?}
    R3 -->|да| RV
    R3 -->|нет| R4{apply без черновика отклика?}
    R4 -->|да| RV
    R4 -->|нет| R5{Уверенность ниже порога?}
    R5 -->|да| R6{Профиль тоже не подходит и модель говорит skip?}
    R6 -->|да| OK[Уверенный отказ: skip]
    R6 -->|нет| RV
    R5 -->|нет| R7{Оценка расходится с расчётом по профилю?}
    R7 -->|да| RV
    R7 -->|нет| OK2[Результат принимается]
```

Все шесть правил живут в `AnalysisService._apply_business_rules()`, и в аудит пишется список
сработавших правил (`business_rules_applied`) — решение системы всегда объяснимо.

Пороги настраиваются в `.env`: `MIN_DESCRIPTION_CHARS`, `MATCH_SCORE_REVIEW_THRESHOLD`,
`LLM_SCORE_CROSSCHECK_DELTA`, `MIN_DRAFT_REPLY_CHARS`.

## 6. Matching Engine: зачем второй, детерминированный расчёт

Если бы соответствие определяла только LLM, спорный результат невозможно было бы оспорить.
Поэтому есть независимый расчёт (`app/domain/matching.py`):

* лексикон навыков превращает текст заказа в список технологий (`Python`, `Telegram`, `Docker`, …);
* `match_score = |требования ∩ профиль| / |требования|`;
* если требований или профиля нет — возвращается `None`, а не `0`: «не смогли посчитать»
  и «ничего не совпало» — разные вещи.

Этот расчёт используется трижды: как оценка, как независимая проверка ответа модели (правило 6)
и как основа для рекомендации `skip` (правило 5).

## 7. Аудит

Таблица `audit_runs` фиксирует каждый запуск: `action`, `input`, `output`, `status`, `error`,
`duration_ms`. Ключевые свойства реализации:

* пишется **всё**, включая ошибки и неудачные попытки (ТЗ §29.4);
* при ошибке в БД не остаётся «полузаписи»: если обработчик вернул ошибку, сессия фиксируется,
  и запись аудита сохраняется — откатывается только настоящий внутренний сбой;
* чувствительные поля (`api_key`, `token`, `password`) маскируются в `AuditService`.

## 8. Будущее расширение (этапы 2–7 ТЗ)

| Этап | Что добавляется | Что НЕ меняется |
|---|---|---|
| 2. Реальные источники | `FlRuSource`, `KworkSource`, `RSSSource` | `OrderService`, домен |
| 3. Автосбор | планировщик + дедупликация | всё выше репозитория |
| 4. Профиль + RAG | векторный поиск по портфолио в генерации отклика | контракт `LLMProvider` |
| 5. Уведомления | `TelegramAction` через `ActionExecutor` | бизнес-логика |
| 6. Автодействия | `SendProposal` для явно разрешённых действий | правила §15 |
| 7. Агентная оболочка | OpenClaw/Hermes как клиент API | весь основной код остаётся своим |

## 9. Схема данных

Четыре таблицы, SQLite, создаются автоматически (`Database.create_all()`, ТЗ §31 MVP-миграции).

```mermaid
erDiagram
    PROFILES ||--o{ ANALYSES : "профиль исполнителя"
    ORDERS   ||--o{ ANALYSES : "может быть несколько запусков"
    ORDERS   ||--o{ AUDIT_RUNS : "журнал действий"
    ANALYSES ||--o{ AUDIT_RUNS : "в т.ч. решение человека"
```

**`orders` — заказы.**

| Поле | Тип | Смысл |
|---|---|---|
| `id` | int PK | идентификатор |
| `source` | enum | `manual` / `flru` / `kwork` / `freelance_ru` / `telegram` / `rss` / `webhook` |
| `external_id` | str | id во внешней системе; вместе с `source` даёт дедупликацию |
| `url` | str? | ссылка на заказ |
| `title`, `description` | str | нормализованный текст заказа |
| `budget_min`, `budget_max`, `currency` | number?, str | бюджет как пришёл; **не додумывается**, если пусто |
| `status` | enum | `new` → `analyzing` → `analyzed` / `needs_review` / `approved` / `rejected` / `error` |
| `needs_review` | bool | заказ в очереди ручной проверки (отдельно от статуса анализа) |
| `created_at`, `updated_at` | datetime | моменты создания и последнего изменения |

**`analyses` — результаты ИИ-анализа (один заказ — сколько угодно запусков).**

| Поле | Тип | Смысл |
|---|---|---|
| `id` | int PK | идентификатор анализа |
| `order_id`, `profile_id` | FK | что с чем сравнивали |
| `model_name`, `prompt_version` | str | какой моделью и какой версией промпта получен результат |
| `match_score` | float? | оценка соответствия (профиль) |
| `recommendation` | enum | `apply` / `skip` / `review` |
| `reason` | str | объяснение от модели |
| `matched_skills`, `missing_skills` | JSON | совпавшие и недостающие навыки |
| `draft_reply` | text? | черновик отклика; на ручной проверке — пусто |
| `needs_review` | bool | требуется человек |
| `review_reason` | text? | **причина** проверки (обязательна, если `needs_review`) |
| `raw_response` | text? | сырой ответ модели — для разбора инцидентов |
| `duration_ms` | int | сколько занял вызов |
| `reviewed_at`, `review_decision`, `review_comment` | datetime/enum/text | решение человека: `approved` / `rejected` |

**`audit_runs` — журнал каждого действия (доказательство работоспособности).**

| Поле | Тип | Смысл |
|---|---|---|
| `id` | int PK | идентификатор записи |
| `action` | enum | `create_order`, `list_orders`, `get_order`, `analyze_order`, `review_decision`, … |
| `order_id`, `analysis_id` | FK? | к чему относится действие |
| `status` | enum | `success` / `review` / `error` |
| `input_payload`, `output_payload` | JSON | что подали и что получили |
| `error` | text? | текст ошибки (например, `LLM timeout`) |
| `duration_ms` | int | длительность действия |
| `created_at` | datetime | когда |

**`profiles` — профиль исполнителя.**

| Поле | Тип | Смысл |
|---|---|---|
| `id` | int PK | профиль по умолчанию создаётся при старте (`DEFAULT_PROFILE_ID=1`) |
| `name`, `title`, `about` | str | кто исполнитель |
| `skills`, `normalized_skills` | JSON | навыки и их нормализованный вид для matching |
| `hourly_rate_rub` | float | ставка для мини-экономики |
| `is_default` | bool | профиль, применяемый по умолчанию |

Посмотреть данные напрямую:

```bash
./.venv/Scripts/python.exe -c "import sqlite3; con=sqlite3.connect('data/app.db'); print([r[0] for r in con.execute(\"select name from sqlite_master where type='table'\")])"
```

Или через API и панель: `docs/API.md`, экраны «Заказы», «Аудит и ошибки».
