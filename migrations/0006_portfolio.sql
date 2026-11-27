-- 0006: срок сдачи и режим набора заказов.
--
-- Гибкий режим («набрать заказов на неделю») без срока сдачи невозможен: окно, в которое
-- складываются заказы, — это календарь дедлайнов, а не календарь публикации.
-- Поэтому две даты: когда заказ взят в работу и когда его надо сдать.
-- Обе nullable: у старых записей их нет, и окно для них считается по умолчанию.

ALTER TABLE orders ADD COLUMN deadline_at DATETIME;
ALTER TABLE orders ADD COLUMN accepted_at DATETIME;

CREATE INDEX IF NOT EXISTS ix_orders_deadline_at ON orders (deadline_at);
