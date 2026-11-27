-- 0007: расход прогона — токены, время, деньги.
--
-- До этого `usage` из ответа модели выбрасывался, и вопрос «сколько стоил прогон»
-- решался только внешним скриптом замера. Пишем то, что вернул провайдер:
-- токены входа/выхода и время ответа. Деньги считаются отдельно и только при заданном
-- прайсе: у облачной ollama usage есть, цены нет; у локальной модели нет ни того, ни другого.
--
-- cost_rub NULL означает «цена не задана», а не «бесплатно».

ALTER TABLE runs ADD COLUMN tokens_in INTEGER;
ALTER TABLE runs ADD COLUMN tokens_out INTEGER;
ALTER TABLE runs ADD COLUMN latency_ms INTEGER;
ALTER TABLE runs ADD COLUMN cost_rub REAL;
