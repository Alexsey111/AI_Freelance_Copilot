-- 0010: журнал откликов и цена отклика.
--
-- Автоотправка на биржах — не техническая, а договорная проблема: у каждой площадки свой
-- лимит откликов, своя цена за отклик (кредиты, «соединения», платные предложения), и почти
-- везде автоматическая отправка запрещена правилами. Поэтому в системе храним не «кнопку
-- отправить всё», а факт и цену каждого отклика — чтобы можно было посчитать, сколько
-- стоит один найм, и решать по деньгам, а не по ощущению.
--
-- status: sent (отправлен), replied (клиент ответил), hired (взял в работу),
-- declined (отказ), silent (тишина).

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    platform TEXT NOT NULL DEFAULT 'manual',
    sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cost_rub REAL,
    status TEXT NOT NULL DEFAULT 'sent',
    note TEXT
);

CREATE INDEX IF NOT EXISTS ix_responses_order_id ON responses (order_id);
CREATE INDEX IF NOT EXISTS ix_responses_sent_at ON responses (sent_at);
