# Соответствие требованиям задачи

Документ для приёмки: каждое требование — где именно оно реализовано и чем проверено.

## Общие требования (файл «Общие требования для вып. проекта»)

### 1. Серверная часть: три точки доступа

| Требование | Реализация | Проверка |
|---|---|---|
| Точка 1 — «создать/запустить» | `app/api/routes/orders.py::create_order` → `POST /api/v1/orders` | `tests/integration/test_orders_api.py` (10 тестов) |
| Точка 2 — «витрина» | `app/api/routes/orders.py::list_orders` → `GET /api/v1/orders` (пагинация, фильтры) | `test_created_order_is_visible_in_the_showcase`, `test_pagination_and_filters` |
| Точка 3 — «ИИ-обработка» | `app/api/routes/analysis.py::analyze_order` → `POST /api/v1/orders/{id}/analyze`, ответ строго по схеме | `tests/integration/test_analyze_api.py` (9 тестов) |

### 2. База данных и аудит

| Требование | Реализация |
|---|---|
| Минимум SQLite | `app/infrastructure/database/database.py` (SQLAlchemy 2.0, SQLite) |
| 2–4 доменные таблицы | 4 таблицы: `orders`, `profiles`, `analyses`, `audit_runs` (`models.py`) |
| Таблица аудита с полями `action, input, output, status, error, duration_ms, created_at` | `AuditRunModel` + `AuditService.record()` |

Проверка: `tests/integration/test_analyze_api.py::test_analyze_writes_audit_record`,
`test_every_creation_is_audited`, `test_llm_timeout_marks_order_as_error_but_records_everything`.

### 3. Ручная проверка (обязательный элемент качества)

| Требование | Реализация | Проверка |
|---|---|---|
| Выставляет `needs_review=true` | `AnalysisService._apply_business_rules` (6 правил) | `tests/unit/test_business_rules.py` (9 тестов) |
| Сохраняет причину | `analyses.review_reason`, обязательность гарантирована валидатором `AnalysisResult` | `tests/unit/test_analysis_result_schema.py` |
| Показывает запись в разделе «требует проверки» | `frontend/streamlit/pages/review.py`, `GET /api/v1/review-queue` | `test_review_queue_contains_only_uncertain_results` |
| Возвращает безопасный результат без выдумываний | `match_score=null`, `draft_reply=null`, `recommendation="review"` — enforced схемой | `test_analyze_vague_order_is_safe_and_needs_review`, `test_review_result_must_be_safe` |

### 4. Веб-панель: минимум три экрана

| Требование | Реализация |
|---|---|
| Экран списка (витрина) | `frontend/streamlit/pages/orders.py` |
| Экран карточки записи (детали + сырой ввод/вывод) | `frontend/streamlit/pages/order_detail.py` (вкладки `raw_input` / `raw_output` / история) |
| Экран аудита/ошибок/ручной проверки | `frontend/streamlit/pages/audit.py` + `pages/review.py` |

Дополнительно: `pages/overview.py` (сводка) и `pages/metrics.py` (метрики и экономика) — 6 экранов вместо трёх.

### 5. Мини-экономика

Реализация: `app/domain/services/metrics_service.py::Metrics.economy()`,
отображение — `pages/metrics.py`, документация — `docs/ECONOMICS.md`.
Проверка: `test_metrics_on_empty_database_report_no_data` (в т.ч. 16,67 ч экономии на 100 заказов).

## Требования ТЗ выпускного проекта

| Раздел ТЗ | Пункт | Реализация |
|---|---|---|
| §4 | Структура проекта | `app/{api,domain,infrastructure}`, `frontend/streamlit`, `tests`, `prompts`, `scripts`, `docs` |
| §5.1 | Таблица `orders` + поле `source` заранее | `models.py::OrderModel` (11 полей + `raw_input`, `needs_review`) |
| §6 | `profiles` (один активный профиль) | `models.py::ProfileModel`, `ProfileRepository.ensure_default()` |
| §7 | `analyses` | `models.py::AnalysisModel` (+ `review_status` для решения человека) |
| §8 | `audit_runs` | `models.py::AuditRunModel` |
| §9–§11 | Три точки доступа | см. выше |
| §12 | Строгая Pydantic-схема + проверки `needs_review`/`review_reason` | `domain/models/analysis.py` (3 `model_validator`) |
| §13 | Придумывание данных запрещено | правило 1 + валидатор «безопасный результат» + промпт, п. 2 |
| §14 | Пять случаев автоматического `needs_review` | правила 1–6 в `analysis_service.py` |
| §15 | LLM не решает, что делать системе | правила живут в сервисе; `extra="forbid"` не даёт модели протащить `send_message`; тест `test_extra_fields_rejected` |
| §16 | Абстракция `LLMProvider` | `infrastructure/llm/base.py` (Protocol), `factory.py` |
| §17 | `MockProvider` для тестов без денег | `infrastructure/llm/mock_adapter.py`; все тесты идут на нём |
| §18 | Абстракция `OrderSource` + нормализатор | `infrastructure/sources/base.py` (`OrderSource`, `ExternalOrder`, `normalize_external_order`), `manual_source.py` |
| §19 | Задел `ActionExecutor` | Явно не реализован: в MVP реальных действий нет (ТЗ §22). Точка расширения описана в `docs/ARCHITECTURE.md` |
| §23–§26 | Четыре экрана панели | `pages/orders.py`, `order_detail.py`, `review.py`, `audit.py` |
| §27 | Фиксированный набор статусов | `domain/models/order.py::OrderStatus` + валидация фильтра в роуте |
| §28 | Жизненный цикл заказа | `analysis_service` переводит статусы; `review_service` — `approved`/`rejected` |
| §29.1–29.5 | Правила надёжности | 29.1 — правила в сервисе; 29.2 — `match_score=null`; 29.3 — `LLMInvalidResponseError`; 29.4 — аудит пишется всегда; 29.5 — `prompt_version` в `analyses` и аудите |
| §30 | Конфигурация, секреты не в Git | `app/config.py`, `.env.example`, `.gitignore`, `scripts/check_secrets.py` |
| §31 | Docker | `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml`, `docs/DOCKER.md` |
| §32 | Unit + integration + особый тест невалидного JSON | 113 тестов (покрытие app/ 96%), из них 31 — прогон набора `tests_data/`; особые — `test_invalid_json_from_llm_is_handled`, `test_llm_timeout_marks_order_as_error_but_records_everything` |
| §33 | Мини-экономика | `docs/ECONOMICS.md`, `Metrics.economy()`, экран метрик |
| §34 | Метрики | `MetricsService.collect()`, `GET /api/v1/metrics` |

## Осознанные отклонения от ТЗ (нужно знать на защите)

1. **`ActionExecutor` не создан.** ТЗ §19 предлагает заложить интерфейс, но §22 запрещает реальные
   действия в MVP. Интерфейс без реализации — код, который никто не вызывает; вместо него точка
   расширения описана документально. Если необходим именно интерфейс — это добавление
   одного файла с `Protocol`, бизнес-логика не меняется.

2. **Добавлена детерминированная независимая проверка (matching engine).** В ТЗ §12 этого нет,
   но §14.3 («не удалось определить соответствие профилю») иначе проверить нечем: мнение модели
   не с чем сверить. `app/domain/matching.py` даёт воспроизводимый score, который одновременно
   используется как независимая проверка ответа LLM.

3. **Правило 5 имеет исключение.** Заказ, где и модель, и расчёт по профилю дают низкое
   соответствие и модель говорит `skip`, НЕ отправляется на ручную проверку — иначе очередь
   «требует проверки» забивалась бы очевидно неподходящими заказами. Тест: `test_confident_skip_stays_skip`.

4. **`needs_review` есть и на уровне заказа.** В ТЗ флаг описан только у анализа (§12).
   Денормализация в `orders.needs_review` нужна для фильтра `?needs_review=true` в витрине (§10)
   и для отметки ⚠ в таблице (§23).

5. **Аудит пишется и на чтение витрины** (`list_orders`). ТЗ §29.4 требует писать любой запуск;
   в аудите это даёт записи `list_orders`, которые в сценарии защиты фильтруются по `action`.
