-- Tabla intermedia que sirve de vinculo entre OpenPages y Maisa ("Funcionalidad 1").
-- Un registro unico por caso de uso (organization_id + source_resource_id).
CREATE TABLE IF NOT EXISTS maisa_use_case_labels (
    id                  UUID PRIMARY KEY,
    source_resource_id  TEXT NOT NULL,
    name                TEXT NOT NULL,
    name_lower          TEXT NOT NULL,
    organization_id     TEXT NOT NULL,
    worker_count        INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'new',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,
    is_deleted          BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT maisa_use_case_labels_source_uk
        UNIQUE (organization_id, source_resource_id),
    CONSTRAINT maisa_use_case_labels_status_chk
        CHECK (status IN ('new', 'modified', 'deprecated'))
);

CREATE INDEX IF NOT EXISTS maisa_use_case_labels_name_lower_idx
    ON maisa_use_case_labels (organization_id, name_lower);
