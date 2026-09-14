# sinc-amn

Microservicio de sincronización entre Auron y Maisa/Noxus, desplegado en EKS.
Ver [ARCHITECTURE.md](./ARCHITECTURE.md) para el diseño de los dos flujos, las
decisiones pendientes y la estructura del proyecto.

## Estado

- **Implementado:** Flujo 1 completo, para ambos tenants (Maisa y Noxus,
  mismo diseño de tabla intermedia en los dos casos) —
  - "Funcionalidad 1": OpenPages → tabla intermedia (`AuronClient` con auth IAM
    + get/update de OpenPages, `UseCaseLabelRepository`/
    `NoxusUseCaseLabelRepository` sobre Postgres/RDS).
  - "Funcionalidad \*": tabla intermedia → Maisa/Noxus (`MaisaLabelSyncService`/
    `NoxusLabelSyncService`), aunque `MaisaClient`/`NoxusClient` (`create_label`/
    `update_label`) siguen siendo placeholders hasta tener el contrato REST
    real de cada uno.
- **Implementado:** Flujo 2 (workers D-1, ambos tenants) —
  `WorkerSyncService`, resuelve el owner del caso de uso vía la tabla
  intermedia correspondiente al tenant del worker.
- **Pendiente:** ver la sección "Pendiente de acordar" en ARCHITECTURE.md
  (contratos REST reales de Maisa/Noxus, backend de `MonitoringStore`,
  envío de email, etc.).

## Desarrollo local

Las dependencias se gestionan con `pipenv` (`Pipfile`/`Pipfile.lock`); es la
fuente de verdad tambien para el build de Docker. `pyproject.toml` solo se
usa para instalar el paquete `sinc_amn` en modo editable.

```bash
pip install pipenv
pipenv install --dev
pipenv run pip install -e .
pipenv run uvicorn sinc_amn.main:app --reload --app-dir grc
```

Variables de entorno requeridas (ver `grc/sinc_amn/config.py`), prefijo
`SINC_AMN_`: `AURON_API_KEY`, `AURON_ZEN_INSTANCE_ID`, `MAISA_BASE_URL`,
`MAISA_API_KEY`, `NOXUS_BASE_URL`, `NOXUS_API_KEY`, `GENERIC_USE_CASE_ID`,
`INTERMEDIATE_DB_DSN`, `MAISA_ORGANIZATION_ID`, `NOXUS_ORGANIZATION_ID`.
`AURON_BASE_URL` es opcional: si no se setea, se deriva de
`AURON_ZEN_INSTANCE_ID`
(`https://<zen_instance_id>.eu-de.openpages.cloud.ibm.com`); solo hace falta
fijarla a mano si el host real no sigue ese patrón.

Las migraciones de la tabla intermedia están en `db/migrations/` (aplicarlas
en orden: `0001_create_maisa_use_case_labels.sql`,
`0002_add_maisa_label_id_and_synced_status.sql`,
`0003_add_entity_to_maisa_use_case_labels.sql`,
`0004_create_use_case_sync_failures.sql`,
`0005_add_owner_to_maisa_use_case_labels.sql`,
`0006_create_noxus_use_case_labels.sql`) — aplicarlas contra la instancia de
RDS Postgres antes de levantar el servicio.

No commitear nunca valores reales de API key/token — son credenciales del
IAM de IBM Cloud, rotables desde su consola si se filtran.

## Despliegue

El despliegue en EKS lo gestiona el pipeline de CI/CD de Santander (no se generan
manifiestos de Kubernetes en este repositorio). El `Dockerfile` de la raíz
construye la imagen sobre la base UBI9 de Produban, instala las dependencias
del `Pipfile` vía `pipenv requirements` y arranca el servicio con
`entrypoint.sh` (uvicorn, host/puerto configurables con `SINC_AMN_HOST` /
`SINC_AMN_PORT`, por defecto `0.0.0.0:8080`).

Un despliegue independiente por entidad necesita, como mínimo:

- Variables de entorno con prefijo `SINC_AMN_` (ver `grc/sinc_amn/config.py`),
  propias de cada entidad (credenciales de Auron/Maisa/Noxus y su
  `generic_use_case_id`).
- Un trigger horario a `POST /flows/use-cases/sync` (Flujo 1).
- Un trigger diario a `POST /flows/workers/sync` (Flujo 2, procesa D-1).
- Un trigger periódico a `POST /flows/maisa-labels/sync` (tabla intermedia
  → Maisa).
- Un trigger periódico a `POST /flows/noxus-labels/sync` (tabla intermedia
  → Noxus).
