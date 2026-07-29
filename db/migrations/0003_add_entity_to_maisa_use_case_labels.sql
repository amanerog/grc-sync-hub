-- entity: [Register].[Santander Fields:ECB AI Category] en Auron/OpenPages.
-- Nullable: no confirmado que el campo venga siempre relleno en origen.
ALTER TABLE maisa_use_case_labels
    ADD COLUMN entity TEXT;
