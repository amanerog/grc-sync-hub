-- Soporte para "Funcionalidad *": push de la tabla intermedia a Maisa (DocumentDB).
ALTER TABLE maisa_use_case_labels
    ADD COLUMN maisa_label_id TEXT;

ALTER TABLE maisa_use_case_labels
    DROP CONSTRAINT maisa_use_case_labels_status_chk;

ALTER TABLE maisa_use_case_labels
    ADD CONSTRAINT maisa_use_case_labels_status_chk
        CHECK (status IN ('new', 'modified', 'synced', 'deprecated'));

-- Acelera la consulta de pendientes de "Funcionalidad *" (status new/modified).
CREATE INDEX IF NOT EXISTS maisa_use_case_labels_pending_idx
    ON maisa_use_case_labels (organization_id, status)
    WHERE status IN ('new', 'modified');
