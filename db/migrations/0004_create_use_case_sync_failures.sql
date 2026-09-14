-- Tracking de fallos aislados de Flujo 1 (UseCaseSyncService), para poder
-- reintentar por Resource ID sin depender de que el item siga cayendo
-- dentro de la ventana settings.auron_use_cases_since (D-1 se desplaza
-- cada dia, asi que un fallo sin resolver antes de medianoche se perderia
-- del todo sin esta tabla).
--
-- resource_id como PK: cada despliegue habla con un unico Auron/OpenPages,
-- asi que no hace falta cualificar por organization_id como en
-- maisa_use_case_labels (esa tabla lo necesita por el propio esquema de
-- Maisa, no por ambiguedad de resource_id en origen).
CREATE TABLE IF NOT EXISTS use_case_sync_failures (
    resource_id     TEXT PRIMARY KEY,
    tenant          TEXT NOT NULL,
    error           TEXT,
    attempts        INTEGER NOT NULL DEFAULT 1,
    first_failed_at TIMESTAMPTZ NOT NULL,
    last_attempt_at TIMESTAMPTZ NOT NULL,
    resolved_at     TIMESTAMPTZ
);

-- Acelera la consulta de pendientes (resolved_at IS NULL) en cada run.
CREATE INDEX IF NOT EXISTS use_case_sync_failures_pending_idx
    ON use_case_sync_failures (tenant)
    WHERE resolved_at IS NULL;
