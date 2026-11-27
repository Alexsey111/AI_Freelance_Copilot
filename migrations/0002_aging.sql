-- 0002: возраст заказа и возраст в очереди.
--
-- Зачем: «заказ висит больше суток — смотреть не стоит» нельзя посчитать, пока в базе
-- есть только created_at (когда мы завели запись). Возраст заказа на бирже и наш долг
-- в очереди — разные величины, и смешивать их значит измерять не то:
--   published_at — когда заказ опубликован на площадке (конкуренция растёт с ним);
--   queued_at    — когда решение ушло человеку (наш собственный долг в проверке).
-- Оба поля nullable: у старых заказов и у ручных записей их нет, и это честнее,
-- чем подставлять created_at и притворяться, что возраст известен.

ALTER TABLE orders ADD COLUMN published_at DATETIME;
ALTER TABLE orders ADD COLUMN queued_at DATETIME;

CREATE INDEX IF NOT EXISTS ix_orders_published_at ON orders (published_at);
CREATE INDEX IF NOT EXISTS ix_orders_queued_at ON orders (queued_at);
