-- Tracking de fallos aislados de Flujo 2 (WorkerSyncService), mismo
-- proposito que use_case_sync_failures (0004) para Flujo 1: sin esto, un
-- worker que falla se pierde en cuanto el D-1 se desplaza al dia
-- siguiente (get_updated_workers solo cubre el D-1 concreto de cada run).
--
-- Diferencia con Flujo 1: aqui no hay forma confirmada de re-pedir un
-- worker por ID a Maisa/Noxus (su contrato REST solo ofrece
-- get_updated_workers(dia), no un lookup por ID), asi que se guarda una
-- foto completa del Worker en el momento del fallo (workspace_id, tenant,
-- use_case_id, agent_*) para reconstruirlo directamente en el reintento
-- sin volver a llamar a Maisa/Noxus. Riesgo aceptado: si el dato cambio
-- en origen tras el fallo, el reintento usa la version vieja.
--
-- Confirmado: esta tabla NO guarda los exitos, solo incidentes - se
-- mantiene pequena de forma natural, sin necesitar limpieza periodica.
-- Los exitos se auditan aparte via CloudWatch (logs estructurados del pod
-- en EKS), no en Postgres.
CREATE TABLE IF NOT EXISTS worker_sync_failures (
    worker_id           TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL,
    tenant              TEXT NOT NULL,
    use_case_id         TEXT,
    worker_updated_at   DATE NOT NULL,
    agent_name          TEXT,
    agent_description   TEXT,
    agent_owner         TEXT,
    provider_version_id TEXT,
    error               TEXT,
    attempts            INTEGER NOT NULL DEFAULT 1,
    first_failed_at     TIMESTAMPTZ NOT NULL,
    last_attempt_at     TIMESTAMPTZ NOT NULL,
    resolved_at         TIMESTAMPTZ
);

-- Acelera la consulta de pendientes (resolved_at IS NULL) en cada run.
CREATE INDEX IF NOT EXISTS worker_sync_failures_pending_idx
    ON worker_sync_failures (tenant)
    WHERE resolved_at IS NULL;
