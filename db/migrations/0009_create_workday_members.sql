-- Datos de Workday de los empleados (CSV "Miembros, Business Unit,
-- Position Level 2, Functional Group 1, Country"), para decidir la
-- Business Entity (BE) del creador de un agente (ver
-- core/business_entity.py). Se recarga entera con
-- scripts/load_reference_data.py cada vez que llega un CSV nuevo.
--
-- email en minusculas (el CSV mezcla mayusculas). Las filas
-- "** No encontrado" no se cargan: el email queda sin datos y cae en el
-- fallback "Other".
CREATE TABLE IF NOT EXISTS workday_members (
    email               TEXT PRIMARY KEY,
    business_unit       TEXT,
    position_level_2    TEXT,
    functional_group_1  TEXT,
    country             TEXT,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
