-- entity: entidad del agente en el proveedor (Maisa: `worker_manager.entity`,
-- p.ej. "Spain"). Decide el caso de uso generico cuando el worker no tiene
-- label valido (core/business_entity.py). Se guarda en la foto del Worker
-- igual que el resto de campos, para que el reintento vaya al mismo
-- generico sin volver a consultar Maisa.
ALTER TABLE worker_sync_failures
    ADD COLUMN entity TEXT;
