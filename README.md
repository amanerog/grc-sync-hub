# sinc-amn

Microservicio de sincronización entre Auron y Maisa/Noxus, desplegado en EKS.
Ver [ARCHITECTURE.md](./ARCHITECTURE.md) para el diseño de los dos flujos, las
decisiones pendientes y la estructura del proyecto.

## Estado

- **Implementado:** Flujo 1, "Funcionalidad 1" — OpenPages → tabla
  intermedia, para ambos tenants (`AuronClient` con auth IAM + get/update
  de OpenPages, `UseCaseLabelRepository`/`NoxusUseCaseLabelRepository`
  sobre Postgres/RDS).
- **Confirmado explícitamente fuera de alcance (lado Maisa): "Funcionalidad
  \*"** (tabla intermedia → Maisa) — el envío de labels hacia Maisa lo
  regulariza a mano el propio equipo de Maisa, no este microservicio.
  `MaisaLabelSyncService` y el endpoint `POST /flows/maisa-labels/sync` se
  han eliminado (recuperables del historial de git si se retoma más
  adelante). La tabla intermedia se sigue poblando igual, solo para dejar
  constancia. **Noxus sigue teniendo su propia "Funcionalidad \* - Noxus"**
  (`NoxusLabelSyncService`, `POST /flows/noxus-labels/sync`) — esta parte
  no se ha tocado, sigue bloqueada por el contrato REST real de Noxus
  (`NoxusClient.create_label`/`update_label`, placeholders).
- **Implementado:** Flujo 2 (workers D-1, ambos tenants) —
  `WorkerSyncService`, resuelve el owner del caso de uso vía la tabla
  intermedia correspondiente al tenant del worker, con reintento por
  worker fallido (`WorkerSyncFailureRepository`, guarda una foto del
  `Worker` porque Maisa/Noxus no ofrecen un lookup por ID) y monitorización
  vía `MonitoringStore` (log JSON estructurado, recogido por CloudWatch).
  `AuronClient.create_agent`/`update_agent`/`dissociate` implementados
  (confirmado que el caso de uso vinculado a un Agent no se puede
  reasignar via `PUT` — se borra la asociación y se crea la nueva vía
  `dissociate`+`associate`, sin recrear el Agent); `get_agent_by_worker_id`
  sigue en placeholder.
- **Pendiente:** ver la sección "Pendiente de acordar" en ARCHITECTURE.md
  (contratos REST reales de Maisa/Noxus, `get_agent_by_worker_id`,
  mecanismo de envío de email, etc.).

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
`SINC_AMN_`: `AURON_API_KEY`, `AURON_ZEN_INSTANCE_ID`, `MAISA_DOCUMENTDB_DSN`,
`NOXUS_BASE_URL`, `NOXUS_API_KEY`, `GENERIC_USE_CASE_ID`,
`INTERMEDIATE_DB_DSN`, `MAISA_ORGANIZATION_ID`, `NOXUS_ORGANIZATION_ID`.
`MAISA_DOCUMENTDB_DSN` es la cadena de conexión completa (con credenciales
y opciones, p.ej. `tls=true&tlsCAFile=global-bundle.pem&replicaSet=rs0`)
a la BBDD de Maisa (AWS DocumentDB/MongoDB) — confirmado que
`get_updated_workers` (Flujo 2, lectura de workers) no es REST, es una
consulta directa a esa BBDD; el `global-bundle.pem` que referencia lo
descarga el `Dockerfile` en build time, no hace falta proveerlo aparte.
No hace falta ninguna credencial de Maisa aparte de esta — el envío de
labels hacia Maisa ya no lo hace este microservicio (ver sección "Estado").
`AWS_ACCOUNT_ID` (opcional y sin uso hoy — field `"3405"` del caso de uso
en OpenPages, pendiente del PUT al caso de uso de Flujo 2). `AURON_BASE_URL` es opcional: si no se setea, se
deriva de `AURON_ZEN_INSTANCE_ID`
(`https://<zen_instance_id>.eu-de.openpages.cloud.ibm.com`); solo hace falta
fijarla a mano si el host real no sigue ese patrón.

Las migraciones de la tabla intermedia están en `db/migrations/` (aplicarlas
en orden: `0001_create_maisa_use_case_labels.sql`,
`0002_add_maisa_label_id_and_synced_status.sql`,
`0003_add_entity_to_maisa_use_case_labels.sql`,
`0004_create_use_case_sync_failures.sql`,
`0005_add_owner_to_maisa_use_case_labels.sql`,
`0006_create_noxus_use_case_labels.sql`,
`0007_create_worker_sync_failures.sql`,
`0008_add_model_id_to_worker_sync_failures.sql`,
`0009_create_workday_members.sql`) — aplicarlas contra la instancia de
RDS Postgres antes de levantar el servicio. Desde el pod, con
`scripts/apply_migrations.py`:

```
kubectl exec -n <ns> <pod> -- python scripts/apply_migrations.py db/migrations/0009_create_workday_members.sql
```

Flujo 2 necesita además los datos de Workday (`workday_members`) para
elegir el caso de uso genérico de cada Business Entity. Se cargan desde el
CSV con `scripts/load_reference_data.py`; el CSV llega por stdin, no se
copia al pod ni se commitea (tiene datos personales). Cada carga sustituye
entera la tabla:

```
kubectl exec -i -n <ns> <pod> -- python scripts/load_reference_data.py workday < miembros.csv
```

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
- Un trigger periódico a `POST /flows/noxus-labels/sync` (tabla intermedia
  → Noxus). No existe equivalente para Maisa — ese envío se hace a mano,
  fuera de este microservicio (ver sección "Estado").
