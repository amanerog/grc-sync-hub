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
`INTERMEDIATE_DB_DSN`, `MAISA_ORGANIZATION_ID`. Las de Noxus
(`NOXUS_BASE_URL`, `NOXUS_API_KEY`, `GENERIC_USE_CASE_ID`,
`NOXUS_ORGANIZATION_ID`) son opcionales mientras Noxus siga apagado.
`MAISA_DOCUMENTDB_DSN` es la cadena de conexión completa (con credenciales
y opciones, p.ej. `tls=true&tlsCAFile=global-bundle.pem&replicaSet=rs0`)
a la BBDD de Maisa (AWS DocumentDB/MongoDB) — confirmado que
`get_updated_workers` (Flujo 2, lectura de workers) no es REST, es una
consulta directa a esa BBDD; el `global-bundle.pem` que referencia lo
descarga el `Dockerfile` en build time, no hace falta proveerlo aparte.
No hace falta ninguna credencial de Maisa aparte de esta — el envío de
labels hacia Maisa ya no lo hace este microservicio (ver sección "Estado").
`AWS_ACCOUNT_ID` (opcional — field `"3405"` del caso de uso en OpenPages;
sin valor, Flujo 2 no lo envía). `AURON_BASE_URL` es opcional: si no se setea, se
deriva de `AURON_ZEN_INSTANCE_ID`
(`https://<zen_instance_id>.eu-de.openpages.cloud.ibm.com`); solo hace falta
fijarla a mano si el host real no sigue ese patrón.
`AURON_AGENT_AUTONOMY_LEVEL` (opcional, por defecto `Assistive`) es el valor,
por nombre, del enum obligatorio `"172"` ("Autonomy Level") del Agent: se pone
en el alta y en los Agents que aún no lo tienen. `AURON_AGENT_ROLE` (por
defecto `Worker`) hace lo mismo con el enum `"3333"` ("Agent Role").
`AURON_RATE_LIMIT_POINTS_PER_MINUTE` (por defecto `180`) es el límite de
OpenPages por usuario que el cliente respeta antes de llamar: un GET cuesta 1
punto y un PUT/POST/DELETE (incluida la Query API) 5, en ventanas de 60s. Si
aun así llega un 429, se reintenta con pausas crecientes.
`AURON_OPENPAGES_ENVIRONMENT` (`PRE` por defecto, o `PRO`) elige la tabla de
ids de fields y asociaciones de `core/openpages_ids.py`, que cambian entre
instancias de OpenPages. Los ids de PRO que aún faltan se sacan con
`scripts/map_openpages_ids.py`. Para PRO hay que fijar también
`AURON_ZEN_INSTANCE_ID`, `AURON_API_KEY`, `AURON_MAISA_AI_SOLUTION_ID` (`4077`),
`AURON_NOXUS_AI_SOLUTION_ID` (`5046`) y `AURON_GENERIC_USE_CASE_PARENT_ID`.

Las migraciones de la tabla intermedia están en `db/migrations/` (aplicarlas
en orden: `0001_create_maisa_use_case_labels.sql`,
`0002_add_maisa_label_id_and_synced_status.sql`,
`0003_add_entity_to_maisa_use_case_labels.sql`,
`0004_create_use_case_sync_failures.sql`,
`0005_add_owner_to_maisa_use_case_labels.sql`,
`0006_create_noxus_use_case_labels.sql`,
`0007_create_worker_sync_failures.sql`,
`0008_add_model_id_to_worker_sync_failures.sql`,
`0009_create_workday_members.sql`,
`0010_add_entity_to_worker_sync_failures.sql`) — aplicarlas contra la
instancia de RDS Postgres antes de levantar el servicio. Desde el pod, con
`scripts/apply_migrations.py`:

```
kubectl exec -n <ns> <pod> -- python scripts/apply_migrations.py db/migrations/0010_add_entity_to_worker_sync_failures.sql
```

La tabla `workday_members` (0009) ya no la usa ningún flujo: el caso de uso
genérico de Flujo 2 sale de la `entity` del agente en Maisa
(`core/business_entity.py`).

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

## Checkpoints del pipeline de CI/CD

Endpoints para el pipeline de los agentes de Maisa. Van detrás del gateway;
el micro no autentica. Consultan Maisa/OpenPages en vivo. Todos son de solo
lectura salvo el de pase de entorno, que escribe en OpenPages.

- `GET /checkpoints/agents/{worker_id}` (CP1). `worker_id` es el id de la
  versión de Maisa (`lastVersionId`); se resuelve a su `worker_manager`, que
  es lo que lleva el Agent en `PlatformAgentID`. Devuelve `worker_id`,
  `worker_manager_id`, `agent_id`, `use_case_id`, `use_case_name`,
  `use_case_status` e `is_generic_use_case`. `agent_id: null` = el Agent aún
  no existe (Flujo 2 no ha corrido o el agente no pasa sus filtros);
  `use_case_id: null` = existe pero no cuelga de un caso de uso del
  Engagement de Maisa. 404 si la versión no existe en Maisa.
- `GET /checkpoints/use-cases/{use_case_id}` (CP2/CP3). Devuelve
  `use_case_id`, `name`, `status` (`Santander Fields:Status`) y `owner`.
  404 si no existe.

- `POST /checkpoints/agents/{worker_id}/promotion` (pase de DEV a PRE o de
  PRE a PRO). Body `{"environment": "PRE"|"PRO", "account_id": "..."}`:
  escribe `account_id` en el campo Account ID PRE o Account ID PRO del caso
  de uso del que cuelga el Agent (ids por instancia en
  `core/openpages_ids.py`). `account_id` es opcional: sin él no se actualiza
  nada en OpenPages. Devuelve `worker_id`, `use_case_id`, `environment` y
  `updated` (`false` = no venía `account_id` o ya tenía ese valor). 404 si la versión
  no existe en Maisa; 409 si el Agent no está en OpenPages, no cuelga de un
  caso de uso o cuelga de un genérico; 422 si `environment` no es PRE ni PRO.

Todos devuelven 502 si falla Maisa u OpenPages.
