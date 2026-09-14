-- Tabla intermedia que sirve de vinculo entre OpenPages y Noxus
-- ("Funcionalidad 1 - Noxus"), mismo diseño que maisa_use_case_labels
-- (ver 0001/0002/0003/0005 - se crea ya con el esquema final, sin replicar
-- cada incremento por separado) con dos diferencias confirmadas:
-- workspace_id (Noxus si lo tiene asociado al caso de uso, Maisa no; sin
-- confirmar en que paso se rellena - ver models/noxus_use_case_label.py) y
-- noxus_label_id (en vez de maisa_label_id).
CREATE TABLE IF NOT EXISTS noxus_use_case_labels (
    id                  UUID PRIMARY KEY,
    source_resource_id  TEXT NOT NULL,
    name                TEXT NOT NULL,
    name_lower          TEXT NOT NULL,
    entity              TEXT,
    owner               TEXT,
    workspace_id        TEXT,
    organization_id     TEXT NOT NULL,
    worker_count        INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'new',
    noxus_label_id      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,
    is_deleted          BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT noxus_use_case_labels_source_uk
        UNIQUE (organization_id, source_resource_id),
    CONSTRAINT noxus_use_case_labels_status_chk
        CHECK (status IN ('new', 'modified', 'synced', 'deprecated'))
);

CREATE INDEX IF NOT EXISTS noxus_use_case_labels_name_lower_idx
    ON noxus_use_case_labels (organization_id, name_lower);

-- Acelera la consulta de pendientes de "Funcionalidad * - Noxus"
-- (status new/modified).
CREATE INDEX IF NOT EXISTS noxus_use_case_labels_pending_idx
    ON noxus_use_case_labels (organization_id, status)
    WHERE status IN ('new', 'modified');
