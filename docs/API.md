# API AI Freelance Copilot (v1)

Базовый адрес: `http://127.0.0.1:8000`. Интерактивная документация: `/docs`.

Почему не `localhost`: на Windows это имя разрешается сначала в IPv6 (`::1`), и если порт 8000
на `::1` занят ретранслятором Docker (чужой контейнер), запрос уходит не в наше приложение —
в ответ приходит `{"detail":"Not Found"}`. С `127.0.0.1` адресат однозначен.

Три обязательные точки доступа плюс вспомогательные.

## Точка 1 — создание заказа

`POST /api/v1/orders` → `201`

```json
{
  "title": "Разработка Telegram-бота",
  "description": "Нужен Telegram-бот на Python...",
  "budget_min": 30000,
  "budget_max": 50000,
  "currency": "RUB",
  "url": "https://example.com/order/123",
  "source": "manual"
}
```

Ответ:

```json
{"id": 15, "status": "new", "needs_review": false, "created_at": "2026-10-06T09:00:00Z"}
```

Если данных не хватает (нет бюджета или описание короче `MIN_DESCRIPTION_CHARS`),
заказ всё равно создаётся, но сразу получает `needs_review=true` — это входной фильтр,
окончательное решение принимает бизнес-логика при анализе.

Ошибки: `422` — неизвестный источник, `budget_max < budget_min`, пустой заголовок.

## Точка 2 — витрина заказов

`GET /api/v1/orders?page=1&page_size=20&status=new&needs_review=true&source=manual&recommendation=apply&search=python`

Ответ:

```json
{"items": [], "total": 42, "page": 1, "page_size": 20}
```

Каждый элемент содержит `latest_analysis` (последний анализ заказа), если он был.

Служебные точки: `GET /api/v1/orders/{id}` (карточка, включая `raw_input`),
`GET /api/v1/orders/{id}/analyses` (история всех запусков ИИ),
`GET /api/v1/orders/{id}/analysis` (последний результат).

## Точка 3 — ИИ-обработка

`POST /api/v1/orders/{order_id}/analyze`

```json
{"profile_id": 1}
```

`profile_id` необязателен: без него берётся активный профиль.

Ответ (поле `result` — строго схема ТЗ §12):

```json
{
  "order_id": 15,
  "order_status": "analyzed",
  "analysis_id": 7,
  "duration_ms": 4210,
  "provider": "mock",
  "model": "mock-model",
  "audit_status": "success",
  "result": {
    "match_score": 0.87,
    "recommendation": "apply",
    "reason": "Заказ соответствует профилю исполнителя",
    "matched_skills": ["Python", "Telegram", "API"],
    "missing_skills": [],
    "draft_reply": "Здравствуйте! ...",
    "needs_review": false,
    "review_reason": null
  }
}
```

Когда система не уверена, возвращается безопасный результат — без выдуманных данных
и без готового отклика:

```json
{
  "result": {
    "match_score": null,
    "recommendation": "review",
    "reason": "Недостаточно данных для надёжной оценки",
    "matched_skills": [],
    "missing_skills": [],
    "draft_reply": null,
    "needs_review": true,
    "review_reason": "описание слишком короткое / не указан объём работ; не указан бюджет"
  }
}
```

`audit_status`: `success` — принято, `review` — ушло человеку (включая невалидный JSON модели),
`error` — инфраструктурная ошибка (нет ключа, timeout, сеть); заказ получает статус `error`,
но запись в аудите всё равно остаётся.

## Ручная проверка

`GET /api/v1/review-queue?review_status=pending` — очередь сомнительных результатов
с причиной проверки.

`POST /api/v1/analyses/{analysis_id}/review`

```json
{"decision": "approved", "comment": "Проверил, заказ берём"}
```

Ответ: `review_status`, `order_status`. Решение пишется в аудит. Никаких действий
(отправка отклика) в MVP не выполняется — ТЗ §22.

## Аудит, метрики, система

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/v1/audit` | журнал: `action`, `status`, `order_id`, постранично |
| `GET` | `/api/v1/audit/actions` | какие действия писались и со счётчиками |
| `GET` | `/api/v1/metrics?hourly_rate_rub=1500` | KPI + мини-экономика |
| `GET` | `/api/v1/health` | живость, активный провайдер, версия промпта |
| `GET` | `/api/v1/profiles/active` | активный профиль исполнителя |
| `POST` | `/api/v1/profiles/{id}/skills` | заменить навыки профиля (демонстрация) |

В `/api/v1/metrics` значение `null` означает **«нет данных»**, а не ноль: доля корректных JSON
при нуле анализов не равна 0 %, она не определена.

## Ошибки

Единый формат ответа об ошибке:

```json
{"detail": "Заказ #42 не найден", "code": null}
```

`404` — объект не найден, `422` — ошибка валидации, `500` — внутренняя ошибка
(в аудит попадает запись об ошибке).
