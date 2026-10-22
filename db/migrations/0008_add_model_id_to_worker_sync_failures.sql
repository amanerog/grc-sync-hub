-- model_id: id tecnico del modelo LLM de la version DEPLOYED del worker
-- (Maisa: `worker.model.name`, p.ej. eu.anthropic.claude-opus-4-5-...).
-- Va al field "3408" (Santander Fields:API ID) del Agent. Se guarda en la
-- foto del Worker igual que el resto de campos, para que el reintento lo
-- reenvie sin volver a consultar Maisa.
ALTER TABLE worker_sync_failures
    ADD COLUMN model_id TEXT;
