-- 0011: выбор площадок — с какими пользователь работает, а с какими нет.
--
-- Тариф площадки общий и лежит в app/data/platform_tariffs.json, а вот выбор «беру отсюда
-- заказы / не беру» — личное решение пользователя, поэтому он хранится в базе.
-- Отдельная таблица, а не настройка в settings: площадок может стать больше, и у каждой
-- есть своё состояние, а не одно число.

CREATE TABLE IF NOT EXISTS platform_preferences (
    platform_key TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_platform_preferences_enabled ON platform_preferences (enabled);
