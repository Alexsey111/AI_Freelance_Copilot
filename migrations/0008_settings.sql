-- 0008: правила работы в базе, а не в файле конфигурации.
--
-- Владелец системы — не разработчик. Ставка, часы в неделю, цель недели, пороги возраста
-- и конкуренции — это пользовательские настройки, а не инфраструктура: их меняют в окне
-- программы, без перезапуска и без похода в app/config.py.
--
-- Конфиг остаётся для того, что относится к запуску: адрес базы, ключ провайдера, порт.
-- Приоритет чтения: база -> переменные окружения -> значения по умолчанию.
--
-- settings_audit хранит историю: без неё на вопрос «кто поставил ставку 500 ₽/ч»
-- ответить нечем, а для дипломной работы это обязательная часть (аудит изменений).

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT NOT NULL DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS settings_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by TEXT NOT NULL DEFAULT 'user'
);

CREATE INDEX IF NOT EXISTS ix_settings_audit_key ON settings_audit (key, changed_at);
