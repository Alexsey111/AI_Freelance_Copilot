-- 0001: понятие прогона (runs) и привязка решений/аудита к прогону.
--
-- Зачем: до этой миграции нельзя было ответить на два вопроса из урока 2 —
-- «сколько стоил прогон» и «что изменилось между прогонами»: решения (analyses)
-- и записи аудита (audit_runs) не знали, к какому запуску они относятся,
-- а параметры запуска (модель, версия промпта, профиль) нигде не хранились.
--
-- Миграция аддитивная: существующие строки остаются с run_id = NULL
-- (исторические данные, до появления прогонов). Ничего не удаляется.

CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY,
    kind           VARCHAR(32)  NOT NULL DEFAULT 'analyze_batch',
    model          VARCHAR(128),
    prompt_version VARCHAR(32),
    profile_id     INTEGER REFERENCES profiles(id),
    orders_total   INTEGER NOT NULL DEFAULT 0,
    orders_review  INTEGER NOT NULL DEFAULT 0,
    status         VARCHAR(16)  NOT NULL DEFAULT 'running',
    note           TEXT,
    started_at     DATETIME NOT NULL,
    finished_at    DATETIME
);

CREATE INDEX IF NOT EXISTS ix_runs_started_at ON runs (started_at);

-- Решение привязано к прогону: без этого «что изменилось между прогонами» не отвечается.
ALTER TABLE analyses ADD COLUMN run_id INTEGER REFERENCES runs(id);
CREATE INDEX IF NOT EXISTS ix_analyses_run_id ON analyses (run_id);

-- Аудит привязан к тому же прогону: по инциденту видно и правило, и условия запуска.
ALTER TABLE audit_runs ADD COLUMN run_id INTEGER REFERENCES runs(id);
CREATE INDEX IF NOT EXISTS ix_audit_runs_run_id ON audit_runs (run_id);

-- Аудит читается по времени («что было вчера»), значит нужен индекс по created_at.
CREATE INDEX IF NOT EXISTS ix_audit_runs_created_at ON audit_runs (created_at);
