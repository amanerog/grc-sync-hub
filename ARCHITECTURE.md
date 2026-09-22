# sinc-amn — Microservicio de sincronización Auron ⇄ Maisa/Noxus

Microservicio desplegado en EKS que implementa dos flujos de sincronización entre
**Auron** (alias interno del conjunto IBM: **OpenPages** + WxG + WxO, dentro de una
cuenta SaaS) y **Maisa/Noxus** (herramientas de explotación de agentes IA).

> Diseño verificado contra el PPT "Sincro auron" (2 diagramas, escenario "time 0:
> Bulk data load", fases I/II/III). Confirmado que **este mismo diseño aplica también
> en régimen recurrente**, no solo para la carga inicial.

Stack: Python (FastAPI), scheduling vía **CronJob de Kubernetes**, **un despliegue
independiente por entidad** (namespace/release propio con sus credenciales de
Auron/Maisa/Noxus).

Todas las llamadas de creación/asociación de Use Case y Agent se hacen sobre
**OpenPages**; WxG y WxO conviven en la misma cuenta SaaS de IBM pero son solo
consumidores, no reciben llamadas de creación del microservicio.

---

## Flujo 1 — Auron → Maisa/Noxus (publicación de casos de uso)

**Frecuencia:** cada hora (CronJob de K8s). El diagrama etiqueta el endpoint como
"Trigger: Manual go on" pero eso describe solo la migración inicial (time 0);
confirmado que en régimen el disparo es automático por CronJob horario.

**Pasos comunes:**

1. Un usuario crea el AI Use Case en OpenPages con la información mínima (proceso
   manual, fuera del microservicio — precondición, no algo que orqueste el servicio).
2. `AuronClient.get_use_cases(tenants=["maisa", "noxus"])` — POST a la Query API de
   OpenPages GRC v2 (`{auron_base_url}/opgrc/api/v2/query`, confirmada), una consulta
   por tenant que trae `Resource ID`, `Name`, `Santander Fields:aux_Business Entity`
   (→ `UseCase.entity`; renombrado desde `Santander Fields:ECB AI Category`, mismo
   campo), `Santander Fields:Country`, `Santander Fields:Owner` (→ `UseCase.owner`),
   `Creation Date` (→ `UseCase.created_at`) y `Last Modification Date` (→
   `UseCase.updated_at`), con `WHERE [Engagement].[Name] LIKE 'Maisa%'` (o
   `'Noxus%'`) `AND [Register].[Last Modification Date] > '<fecha>'` y, si
   `settings.auron_use_cases_country` está seteada, `AND [Register].[Santander
   Fields:Country] = '<pais>'` (sin setear: todos los países). Mismo set de columnas
   para ambos tenants (Maisa/Noxus) aunque el ejemplo real que confirmó `Owner`/
   `Creation Date` era solo de Maisa — sin confirmar si Noxus los trae rellenos,
   `UseCase.entity`/`owner` ya toleran venir vacíos. `owner` **se persiste en la
   tabla intermedia de cada tenant** (`UseCaseLabel.owner` para Maisa,
   `NoxusUseCaseLabel.owner` para Noxus — ambas tablas, ver más abajo) — lo
   necesita Flujo 2 para el field `"3261"` del Agent. `created_at` sigue
   viviendo solo en `UseCase`, no se persiste. Paginada via `offset`/`next`.
   La fecha la resuelve
   `settings.auron_use_cases_since`: `"D-1"` (default, se recalcula en cada
   llamada), `"All"` (sin filtro de fecha) o un literal de fecha fijo. Auth: API
   key → token OAuth2 vía IBM Cloud IAM. Protocolo: HTTPS. Formatos: JSON/JSON.
3. El microservicio valida y transforma el dato de OpenPages al modelo de datos de
   la solución IA.
4. **A partir de aquí el tratamiento diverge por destino — el diagrama solo dibuja
   el path de Maisa; Noxus sigue un patrón distinto (confirmado):**

### 4a. Destino Maisa — "Funcionalidad 1": tabla intermedia + asignación manual

**Implementado** (ver diapositivas 3-4 del PPT, "SubTask"). Alcance confirmado:
esta pieza llega hasta OpenPages → tabla intermedia. El envío real de la
colección resultante a la instalación de Maisa (su BBDD, **AWS DocumentDB**)
lo hace otro componente, **"Funcionalidad \*"**, descrito más abajo.

- `UseCaseLabelRepository.upsert_from_use_case(use_case, organization_id)` —
  persiste en una **tabla intermedia sobre RDS Postgres** (`maisa_use_case_labels`,
  ver `db/migrations/0001_create_maisa_use_case_labels.sql`), no vía REST a Maisa.
  El repositorio hace insert si el `resource_id` de OpenPages es nuevo para esa
  `organization_id`, o update si ya existía (matching por
  `(organization_id, source_resource_id)` — se añadió `source_resource_id` al
  esquema respecto al dado en el PPT para no depender del nombre, que si
  cambia en OpenPages generaría un falso "nuevo").
- Esquema del registro (`UseCaseLabel`): `id`, `source_resource_id`, `name`,
  `name_lower` (clave de igualdad/unicidad que exige Maisa), `entity` (`[Register].
  [Santander Fields:aux_Business Entity]` en Auron, ver `db/migrations/0003_add_entity_
  to_maisa_use_case_labels.sql` — nullable, no confirmado que venga siempre relleno
  en origen), `owner` (`[Register].[Santander Fields:Owner]` en Auron, ver
  `db/migrations/0005_add_owner_to_maisa_use_case_labels.sql` — se añadió
  específicamente para que Flujo 2 lo lea sin GET adicional a OpenPages al
  completar el field `"3261"` del Agent, ver Flujo 2 más abajo),
  `organization_id` (entidad/entorno — viene de
  `settings.maisa_organization_id`, no de OpenPages, porque el microservicio ya se
  despliega por entidad), `worker_count` (**lo mantiene Maisa** vía
  asignación/desasignación de workers; la ingesta desde OpenPages nunca lo toca
  salvo al crear el registro, que arranca en 0), `status`
  (`new`/`modified`/`synced`/`deprecated` — `synced` lo añadimos para la
  coordinación con "Funcionalidad \*", ver abajo) y el bloque de auditoría
  (`created_at`/`updated_at`/`deleted_at`/`is_deleted`).
- Un **humano**, desde el front de Maisa, asigna manualmente el caso de uso a cada
  worker una vez la colección llega a Maisa. Esa asignación **no la hace el
  microservicio**.
- El front de Maisa **sí filtra los casos de uso mostrados por país/entidad**
  (confirmado) — responsabilidad del front de Maisa, no del microservicio. La
  ingesta desde OpenPages también puede filtrar por país en origen, opcionalmente,
  vía `settings.auron_use_cases_country` (ver paso 2 más arriba) — son dos filtros
  independientes, no relacionados entre sí.
- **Autenticación confirmada** (ejemplos de código reales del equipo): dos
  pasos — `POST {auron_iam_url}` con `grant_type=apikey` + el API key cambia
  por un token OAuth2 (IBM Cloud IAM); ese token se usa como Bearer en las
  llamadas a OpenPages junto con el header `ZEN-Service-Instance-Id`. El token
  se cachea en memoria y se renueva según `expires_in` (`AuronClient`).
- **Get/update de un caso de uso concreto: confirmado y implementado** vía
  `GET`/`PUT` a `{auron_base_url}/grc/api/contents/{resource_id}`
  (`AuronClient.get_use_case_content` / `AuronClient.update_use_case`).
  `update_use_case` no la usa "Funcionalidad 1" (solo lee), se deja lista para
  cuando haga falta escribir de vuelta en OpenPages.
- **Consulta masiva: confirmada e implementada.** Query API de OpenPages GRC v2
  (`POST {auron_base_url}/opgrc/api/v2/query`) — una query por tenant, paginada via
  `offset`/`next` (`AuronClient.get_use_cases`/`_fetch_tenant_use_cases`/
  `_use_cases_query`). Ver "Ventana de fechas" más abajo para el filtro incremental
  y el punto 2 de "Pasos comunes" para el filtro opcional de país.

### "Funcionalidad \*" — tabla intermedia → Maisa (DocumentDB)

**Implementado** (ver diapositivas 5-6 del PPT, "SubTask"). Endpoint:
`POST /flows/maisa-labels/sync`, mismo cadencia horaria que "Funcionalidad 1".

- La BBDD real de Maisa es **AWS DocumentDB** (compatible Mongo), colección
  `labels`, backend en Go (`labels.go`/`label.go` según el PPT), expuesta vía
  lo que el equipo de Maisa llama su "Studio API" (`settings.maisa_base_url`).
- **`create_label`: confirmado e implementado**, vía ejemplo real (script
  bash del equipo de Maisa) — confirmado que `/organizations/{org_id}/labels`
  es esta misma colección `labels` (no otra funcionalidad distinta de
  Maisa, aunque el ejemplo en sí solo creaba labels de prueba tipo
  entorno/departamento, no casos de uso reales). `POST
  {maisa_base_url}/organizations/{organization_id}/labels` — `organization_id`
  va en la URL, no en el body; auth `Bearer` (coincide con lo que el
  cliente ya hacía); body mínimo `{"name": ...}`, sin confirmar si admite
  más campos; la respuesta trae `id` (el `maisa_label_id` a persistir).
  `update_label` **sigue sin confirmar** — el ejemplo solo cubre creación,
  no actualización (`MaisaClient.update_label` sigue en placeholder,
  hipótesis sin confirmar: mismo patrón de URL con método `PUT`/`PATCH`).
- `MaisaLabelSyncService.run()`: pide a `UseCaseLabelRepository.get_pending_for_maisa`
  los registros con `status IN ('new','modified')`; por cada uno, si no tiene
  `maisa_label_id` llama a `create_label` (alta), si ya lo tiene llama a
  `update_label`; luego marca el registro `synced` guardando el
  `maisa_label_id` devuelto por Maisa (`UseCaseLabelRepository.mark_synced`,
  con chequeo optimista de `status` para no pisar un `modified` más reciente
  escrito por "Funcionalidad 1" mientras se procesaba el push).
- **Confirmado explícitamente fuera de alcance por ahora:** escribir de vuelta
  el `maisa_label_id` en OpenPages (aunque el propio PPT lo sugiere — "para que
  pueda ser enviado a open page" — se decidió posponerlo; `AuronClient.update_use_case`
  ya está listo para cuando se retome).
- Restricciones conocidas del lado Maisa (key design points del PPT, no
  aplicadas por nuestro cliente sino que las valida Maisa): `nameLower` existe
  porque DocumentDB no soporta collation de Mongo (toda igualdad/unicidad/orden
  corre sobre `nameLower`, `name` es solo para mostrar); índice único
  `(organizationId, nameLower)`; `workerCount` es un contador denormalizado que
  Maisa mantiene con `$inc`, no se calcula desde los workers; borrado físico
  (hard delete) pese a que el esquema tenga bloque de auditoría con
  `deletedAt`/`isDeleted`; el vínculo worker↔label vive en el lado de Maisa
  (`worker_manager.labelIds`); `name` debe tener 3–50 caracteres, trimmed.
- Camino alternativo mencionado en el PPT si Maisa no expone API: descarga
  diaria + carga separada por entidad/entorno (no implementado, solo
  documentado — ver "Pendiente de acordar").

### 4b. Destino Noxus — "Funcionalidad 1 - Noxus": tabla intermedia (corrige diseño anterior)

**Confirmado: Noxus también usa tabla intermedia, mismo patrón que Maisa.**
Este diseño **reemplaza** una versión anterior de este documento, que
describía Noxus como "push automático" directo (`NoxusClient.push_use_case`,
sin tabla intermedia). Esa versión anterior quedó descartada — Noxus repite
exactamente la estructura de dos fases de Maisa (4a + "Funcionalidad \*"),
con dos diferencias puntuales:

- `NoxusUseCaseLabelRepository.upsert_from_use_case(use_case, organization_id,
  workspace_id=None)` — persiste en su propia **tabla intermedia sobre RDS
  Postgres** (`noxus_use_case_labels`, `db/migrations/0006_create_noxus_use_
  case_labels.sql`), no vía REST a Noxus directamente. Misma lógica de
  insert/update por `(organization_id, source_resource_id)` que Maisa.
- Esquema del registro (`NoxusUseCaseLabel`): **idéntico** a `UseCaseLabel`
  (Maisa) salvo dos diferencias confirmadas:
  - **`workspace_id`** (nuevo, no existe en `UseCaseLabel`): Noxus sí tiene
    workspace_id asociado al caso de uso (Maisa no, ver "Ventana de fechas"
    más abajo y Flujo 2). **Confirmado e implementado: el dato no llega por
    Flujo 1** (`UseCase`/OpenPages no lo trae — el parámetro opcional
    `workspace_id` de `upsert_from_use_case` queda sin usar en la práctica,
    nadie lo pasa desde ahí), **sino por Flujo 2**, la primera vez que
    `WorkerSyncService` procesa un worker de Noxus para ese caso de uso
    (`Worker.workspace_id`). Implementado como backfill:
    `NoxusUseCaseLabelRepository.set_workspace_id_if_missing` solo escribe
    si el campo está a `NULL` (confirmado — no se sobreescribe si varios
    workers de distintos workspaces comparten el mismo caso de uso; el
    primero en procesarse "gana"), y no toca `status` (no es un dato que
    haya que reenviar a Noxus).
  - **`noxus_label_id`** en vez de `maisa_label_id` — mismo rol (id externo
    devuelto al hacer el push), solo renombrado.
  - El resto de columnas (`entity`, `owner`, `worker_count`, `status`,
    bloque de auditoría) son estructuralmente idénticas y con el mismo
    tratamiento que en Maisa (`worker_count` arranca en 0 y la ingesta
    desde OpenPages nunca lo toca — **confirmado que Noxus lo mantiene por
    su lado, igual que Maisa con su `$inc`**, aunque el mecanismo exacto de
    Noxus tampoco está confirmado).
- `organization_id` aquí usa `settings.noxus_organization_id` (nueva
  variable, opcional/sin valor por defecto) — no `maisa_organization_id`,
  que es el identificador propio de Maisa. **Sin confirmar** si Noxus tiene
  un concepto de "organizationId" equivalente al de Maisa, ni su valor real.

### "Funcionalidad \* - Noxus" — tabla intermedia → Noxus

**Mismo diseño que "Funcionalidad \*" (Maisa), aplicado a Noxus.** Endpoint:
`POST /flows/noxus-labels/sync`.

- Contrato REST de Noxus **aún no confirmado** (mismo estado que Maisa antes
  de tener ejemplos reales) — `NoxusClient.create_label`/`update_label` son
  placeholders con `NotImplementedError` (reemplazan al antiguo
  `push_use_case`, ya eliminado).
- `NoxusLabelSyncService.run()`: mismo algoritmo que `MaisaLabelSyncService`
  — pide a `NoxusUseCaseLabelRepository.get_pending_for_noxus` los registros
  `new`/`modified`, crea o actualiza en Noxus según tenga o no
  `noxus_label_id`, y marca `synced` guardando el id devuelto
  (`mark_synced`, mismo chequeo optimista de `status` que Maisa).
- Restricciones del lado Noxus (equivalentes a las "key design points" que
  el PPT documenta para Maisa) **no confirmadas** — no tenemos aún el
  equivalente de esa información para Noxus.

### Ventana de fechas

- **Ya no hay checkpoint persistido.** Se descartó `CheckpointStore` (quedó sin
  usar, placeholder en `core/checkpoint.py`) a favor de un filtro de fecha
  configurable por variable de entorno (`settings.auron_use_cases_since`),
  aplicado directamente en el `WHERE` de la Query API: `"D-1"` (default, el
  día anterior calculado en cada ejecución), `"All"` (trae todo, útil para
  cargas iniciales/backfill) o un literal de fecha fijo.
- **Estrategia de fallo parcial: confirmada e implementada (aislamiento por
  item).** Un caso de uso que falle no interrumpe el resto del batch — se
  loguea (`logger.exception`) y se continúa con el siguiente. Maisa y Noxus
  quedan independientes por construcción (cada item se despacha a su propio
  destino dentro de la misma iteración): un fallo en uno no afecta al otro.
  `UseCaseSyncService.run()` devuelve un resumen `{total, succeeded,
  failed}`; el endpoint (`POST /flows/use-cases/sync`) responde `202` si
  `failed == 0`, o `207 Multi-Status` si hubo algún fallo aislado, para que
  el CronJob/alerting lo distinga de un run limpio sin tener que parsear el
  body. Mismo criterio aplicado también a "Funcionalidad \*"
  (`MaisaLabelSyncService`/`NoxusLabelSyncService`) y al Flujo 2
  (`WorkerSyncService`, ver abajo).
- **Tracking de fallos: confirmado e implementado, tanto en Flujo 1 como en
  Flujo 2.** "Funcionalidad \*"/"Funcionalidad \* - Noxus" ya son robustas
  por diseño (reintentan indefinidamente vía `status IN ('new',
  'modified')`, sin ventana de tiempo de por medio) — no necesitan este
  mecanismo. El hueco real (Flujo 1 y Flujo 2 por igual): la ventana `D-1`
  se desplaza cada día, así que un item que falla y no se arregla antes de
  medianoche podía dejar de aparecer en el filtro para siempre, sin más
  reintento posible.
  - **Flujo 1:** `use_case_sync_failures` (Postgres,
    `db/migrations/0004_...sql`, `UseCaseSyncFailureRepository`) — cada
    fallo aislado se registra ahí (`resource_id`, `tenant`, `error`,
    `attempts`, `first_failed_at`, `last_attempt_at`, `resolved_at`). En
    cada `run()`, además del batch normal, se relee `WHERE resolved_at IS
    NULL` y se reintenta por **Resource ID explícito** vía
    `AuronClient.get_use_cases_by_resource_ids` (mismo parseo de filas que
    `get_use_cases`, pero sin filtro de fecha ni de Engagement — usa
    `[Register].[Resource ID] IN (...)`, sintaxis sin confirmar contra una
    respuesta real, ver TODO en `_resource_ids_query`).
  - **Flujo 2:** `worker_sync_failures` (Postgres,
    `db/migrations/0007_...sql`, `WorkerSyncFailureRepository`) — mismo
    patrón, pero con una diferencia de diseño obligada: Maisa/Noxus solo
    ofrecen `get_updated_workers(día)`, no un lookup por ID, así que no hay
    forma de "re-pedir" un worker fallido como sí se hace en Flujo 1. En su
    lugar, se guarda una **foto completa del `Worker`** en el momento del
    fallo (`workspace_id`, `tenant`, `use_case_id`, `worker_updated_at`,
    `agent_name`, `agent_description`, `agent_owner`) y el reintento
    reconstruye el `Worker` directamente desde esa foto, sin volver a
    llamar a Maisa/Noxus — riesgo aceptado: si el dato cambió en origen
    tras el fallo, el reintento usa la versión vieja.
  - **Confirmado: ninguna de las dos tablas guarda los éxitos, solo
    incidentes** — se mantienen pequeñas de forma natural (un éxito borra
    su propio registro vía `mark_resolved`/`resolved_at`), sin necesitar
    limpieza periódica. La auditoría de éxitos de Flujo 2 se resuelve
    aparte, vía CloudWatch (logs estructurados del pod en EKS), no en
    Postgres — ver "Ya resueltos e implementados" en "Pendiente de
    acordar" para el estado de `MonitoringStore`.
  - En ambos casos: un éxito marca `resolved_at`; un fallo (incluida la
    propia escritura en la tabla de tracking) se aísla igual que cualquier
    otro item, sin tumbar el resto del batch. `attempts` se trackea pero no
    hay backoff/límite todavía — candidato para alertar ("N intentos sin
    resolver") más adelante.

**Endpoint expuesto:** `POST /flows/use-cases/sync`

---

## Flujo 2 — Maisa/Noxus → Auron (sincronización de workers)

**Frecuencia:** diaria, procesa datos de "D-1".

**Modelo de datos:** el diagrama distingue terminológicamente "workers" (Maisa) de
"workspaces y agents metadata" (Noxus), pero **confirmado que es solo diferencia de
nombre — mismo modelo lógico** (`worker_id`, `workspace_id`, `use_case_id`) para
ambos orígenes. Se reutiliza el modelo `Worker` para los dos. `Worker.tenant`
("maisa"/"noxus") lo fija quien construya el `Worker` — `MaisaClient`/
`NoxusClient.get_updated_workers` (ambos aún sin implementar) deben devolverlo
ya seteado, no hay forma de derivarlo después. `Worker.agent_name`/
`agent_description`/`agent_owner` (opcionales) son el nombre/descripción/owner
reales del Agent, recuperados de Maisa/Noxus al sincronizar (ver paso 3 más
abajo) — `agent_owner` es el owner del **Agent**, distinto del owner del
**Use Case** (`UseCaseLabel.owner`, ver Flujo 1 más arriba).

**Pasos:**

1. Obtención de datos actualizados en D-1:
   - `1A` `MaisaClient.get_updated_workers(day)` — GET REST API a Maisa: workers y
     metadata.
   - `1B` `NoxusClient.get_updated_workers(day)` — GET REST API a Noxus: workspaces
     y metadata de agents (mismo modelo `Worker`, ver nota arriba).
2. `2AB` El microservicio procesa la información combinada de ambos orígenes.
3. Para cada worker, ingesta en Auron/OpenPages (`3A-5A` para origen Maisa,
   `3B-5B` para origen Noxus — mismo procedimiento, ejecutado por separado por
   origen). **`AuronClient.create_agent`/`update_agent`/`dissociate` ya
   implementados** (ver "Ya resueltos e implementados" en "Pendiente de
   acordar"); `get_agent_by_worker_id` **sigue en placeholder**
   (`NotImplementedError`) por el mecanismo de búsqueda por campo (punto
   6). Mecanismo confirmado por dos colecciones Postman reales ("IBM Open
   Pages" y "TOM-Catalogación") más un ejemplo real del equipo de
   Auron/IBM para la reasignación:
   - **`worker_id` ≠ `agent_id`**: OpenPages identifica el Agent por su propio
     `resource_id`, distinto del `worker_id` de Maisa/Noxus. Por eso el Agent
     debe llevar una **tag/campo personalizado `worker_id`** con el valor de
     Maisa/Noxus, y localizarlo requiere buscar por ese campo
     (`AuronClient.get_agent_by_worker_id`), no un GET directo por ID. El
     dict que devuelve debe incluir tanto `"id"` como `"primaryParentId"`
     (el caso de uso al que está vinculado hoy), para la comparación del
     punto siguiente.
   - **Confirmado (equipo Auron/IBM): el caso de uso vinculado
     (`primaryParentId`) NO se puede cambiar en un `PUT` ni sobrescribiendo
     la asociación.** Solo los campos ("fields") del Agent son
     actualizables así. Por eso `WorkerSyncService._ingest_worker`
     distingue tres casos, no dos:
     - Si el Agent no existe → `AuronClient.create_agent(worker_id,
       use_case_id, tenant, name, description, use_case_owner,
       agent_owner, provider_version_id)`.
     - Si existe y su `primaryParentId` **coincide** con el `use_case_id`
       actual → directamente `AuronClient.update_agent(agent_id, tenant,
       name, description, use_case_owner, agent_owner,
       provider_version_id)` (sin `use_case_id`: este método nunca toca el
       enlace).
     - Si existe pero su `primaryParentId` **difiere** (el caso de uso del
       worker cambió) → **confirmado vía ejemplo real (equipo Auron/IBM):
       se borra solo la asociación vieja y se crea la nueva**, sin tocar
       el resto del Agent: `DELETE /grc/api/contents/{agent_id}/
       associations?parents={use_case_id_viejo}` (`AuronClient.dissociate`)
       seguido de `POST /grc/api/contents/{agent_id}/associations` con
       `[{"id": use_case_id_nuevo, "associationDefinitionId": "966",
       "type": "PARENT"}]` (`AuronClient.associate`, ya implementado) —
       después, `update_agent` igual que en el caso anterior, para
       sincronizar también el resto de campos.
   - `tenant`/`name`/`description`/`agent_owner`/`provider_version_id`
     salen de `worker.tenant`/`worker.agent_name`/`worker.agent_description`/
     `worker.agent_owner`/`worker.provider_version_id`; `use_case_owner` lo
     busca `WorkerSyncService` en la tabla intermedia
     (`UseCaseLabelRepository.get_by_resource_id`), ver más abajo.
   - **Confirmado: `workspace_id` no es un dato del Agent.** El `workspace_id`
     del `Worker` vive en el propio caso de uso (solo para Noxus — Maisa no
     tiene `workspace_id` asociado), y la creación/actualización del caso de
     uso es manual y fuera de alcance del microservicio (ver paso 1 más
     arriba). Por eso `create_agent`/`update_agent` no lo reciben ni lo
     escriben — solo se sigue usando en la notificación `7A` (ver abajo), que
     es independiente del alta/actualización del Agent.
   - El enlace Agent→Use Case **en la creación** es el campo
     **`primaryParentId`** del propio payload de creación del Agent,
     confirmado via ejemplo real: `POST {auron_base_url}/grc/api/contents`
     con `"primaryParentId": "<use_case_resource_id>"` **en vez de**
     `parentFolderId`. `AuronClient.create_content` ya implementa la
     llamada genérica (confirmada y testeada). **Matiz confirmado
     después:** para *reasignar* ese enlace en un Agent ya existente, sí
     se usa `associate`/`dissociate` (`associationDefinitionId "966"`,
     `type "PARENT"`, ver punto anterior) — `primaryParentId` solo aplica
     en la creación inicial.
   - Si `use_case_id` no está presente → se resuelve/crea un caso de uso
     **genérico "Pendiente de regularizar"** (ver más abajo — **el diseño
     "por `(tenant, consumerId)`" que se había dado por confirmado se ha
     revertido a indefinido**, sigue pendiente decidir a nivel funcional
     cómo se hace, ver punto 7 de "Pendiente de acordar") **y además** se
     dispara una notificación (`7A`, confirmado que se implementa además
     del fallback genérico, no en su lugar) a los admins del workspace
     correspondiente para que lo regularicen.
   - **Caso distinto, confirmado: "Personal Productivity"** (`"personal
     productivity - <user_id>"` en Auron) — **no** es parte de la lógica
     de fallback anterior. Es un caso de uso real que el propio usuario
     elige y asigna a sus workers **desde la herramienta de Maisa** (no es
     un "cajón de sastre" impuesto por el microservicio ante la ausencia
     de dato, sino una elección explícita del usuario) — así que cuando
     aplica, `worker.use_case_id` **sí viene informado**, apuntando a este
     caso de uso. El matiz: si ese caso de uso personal todavía no existe
     en OpenPages para ese usuario en concreto, `sinc-amn` tendría que
     crearlo sobre la marcha, igual que con "Pendiente de regularizar"
     pero con un disparador distinto (no "`use_case_id` ausente", sino
     "`use_case_id` resuelve a un Personal Productivity inexistente
     todavía"). **Confirmado explícitamente sin implementar** — faltan
     los mismos datos que en el punto 7 de "Pendiente de acordar" (de
     dónde sale el `user_id` y el resto de campos del payload de
     creación).
   - **Confirmado — payload real completo de `create_agent`** (colección
     "TOM-Catalogación", `typeDefinitionId: "156"`, `name`/`description`
     **solo** como claves de nivel superior, sin duplicar en `fields.field`).
     `name` lleva el prefijo `[Agent Maisa]`/`[Agent Noxus]` (según
     `tenant`) delante del `agent_name` real; `description` es
     `agent_description` tal cual — ambos **confirmados que se recuperan de
     Maisa/Noxus al sincronizar** (`Worker.agent_name`/`agent_description`),
     no se generan en el microservicio.
     5 campos personalizados: `worker_id` (field `"3658"`,
     "Santander-Fields-Agent:PlatformAgentID" — **ya resuelto**, era el
     bloqueante duro), `"3261"` ("Santander Fields:Owner" = `use_case_owner`,
     owner del **Use Case**, no del Agent — **ya resuelto**: se persiste en
     la tabla intermedia de cada tenant durante Flujo 1, `WorkerSyncService`
     lo lee de ahí sin GET adicional, para Maisa y Noxus por igual),
     `"3293"` ("Creator of the AI Agent" = `agent_owner`, **ya resuelto**:
     owner del propio Agent, recuperado de Maisa/Noxus, distinto del owner
     del Use Case), `"3290"` ("Version id of the provider" =
     `worker.provider_version_id`, **ya resuelto**: dato de Maisa/Noxus,
     `Worker` ya lo trae) y `"3405"` ("Identifier of the cloud account...
     Development", **ya resuelto**: no es un dato de Maisa/Noxus, es
     `settings.aws_account_id` — la cuenta AWS donde corre el propio
     microservicio, inyectada por el pipeline de despliegue).
   - **El caso de uso genérico ya no sería un ID fijo simple — pero el
     diseño exacto está otra vez sin confirmar a nivel funcional** (se
     había dado por bueno "uno distinto por `(tenant, consumerId)`", con
     `consumerId` = `worker.workspace_id` o similar, pero esa hipótesis
     partía de confundir esta lógica con la de "Personal Productivity" —
     ver más arriba. Sigue sin decidir **si** hace falta granularidad por
     consumidor, o si un registro por `(tenant, entidad)` como se pensaba
     originalmente es suficiente). Lo que sí sigue siendo válido,
     independientemente de cómo se resuelva la granularidad (confirmado
     por ejemplos reales de OpenPages, no depende de esta duda):
     - Mecanismo de tres pasos antes de crear el Agent: **(a)** consultar
       por nombre si ya existe (`Query AI Use Case w/ name...`); **(b)**
       si no existe, crearlo (`typeDefinitionId: "94"`, `primaryParentId`
       = `settings.auron_generic_use_case_parent_id` — **confirmado que es
       específico de entorno**, `"10135"` es el valor real de PRE (válido
       para pruebas), falta el de PRO; y un payload de campos: País,
       Owner, AI Solution Origin, Purpose, AI Type, Primary users); **(c)**
       asociarlo a la AI solution del tenant (`associate`,
       `associationDefinitionId: "64"`, `type: "CHILD"`, ya implementado
       genéricamente — **confirmado que Maisa y Noxus usan target_id
       DISTINTOS**: `settings.auron_maisa_ai_solution_id` (`"11342"`) y
       `settings.auron_noxus_ai_solution_id` (`"15327"`)).
     - Reemplazaría `settings.generic_use_case_id` (hoy un único string
       fijo) por esta resolución dinámica. **Sin implementar todavía** —
       bloqueado tanto por la duda de diseño como por los datos concretos
       que faltan (ver punto 7 de "Pendiente de acordar").
4. `6AB` **Confirmado e implementado.** El resultado de la ingesta (Use
   Case/Agent) se registra vía `MonitoringStore.record`, que loguea un
   JSON estructurado (`{"event": "worker_sync_result", "worker_id",
   "agent_id", "use_case_id", "status", "timestamp"}`) por el logger
   estándar — no hay tabla dedicada ni cliente de CloudWatch en el
   microservicio, se apoya en que stdout del pod ya se recoge en EKS (ver
   `core/logging.py`). Mismo criterio que en "Ventana de fechas" más
   arriba: la auditoría de éxitos vive en CloudWatch, no en Postgres.
5. `7A` Email a los admins del workspace cuando el worker no tenía `use_case_id` y
   se le asignó el genérico, para que lo regularicen manualmente. Confirmado que se
   implementa (no queda descartado ni solo como TODO).
6. **Tracking de fallos: confirmado e implementado** — además del batch
   normal de D-1, se reintentan los workers pendientes de
   `worker_sync_failures` (`WorkerSyncFailureRepository.get_pending()`),
   ver detalle completo (incluida la diferencia de diseño respecto a
   Flujo 1) en "Ventana de fechas" más arriba.

**Endpoint expuesto:** `POST /flows/workers/sync`

---

## Despliegue en EKS — multi-entidad

Confirmado: **un Deployment + CronJobs independiente por entidad** (no un servicio
único compartido). Cada entidad tiene su propio conjunto de credenciales de
Auron/Maisa/Noxus y su propio `generic_use_case_id`.

Los manifiestos de Kubernetes/EKS **no se generan en este repositorio**: el
despliegue real lo gestiona el pipeline de CI/CD de Santander sobre sus instancias
de EKS. Lo relevante para ese pipeline es que necesitará, por entidad: variables de
entorno con prefijo `SINC_AMN_` (ver `config.py`), y cuatro triggers periódicos
contra la app — tres horarios (`POST /flows/use-cases/sync`,
`POST /flows/maisa-labels/sync` y `POST /flows/noxus-labels/sync`, estos dos
últimos siempre después del primero para minimizar el retraso hasta que el
caso de uso aparece en Maisa/Noxus) y uno diario a `POST /flows/workers/sync`.

---

## Estructura del proyecto

```
sinc_amn/
├── ARCHITECTURE.md
├── pyproject.toml
├── grc/sinc_amn/
│   ├── main.py                        # entrypoint FastAPI
│   ├── config.py                      # Settings (pydantic BaseSettings)
│   ├── api/routes/
│   │   ├── use_cases.py               # POST /flows/use-cases/sync (Flujo 1, Funcionalidad 1)
│   │   ├── maisa_labels.py            # POST /flows/maisa-labels/sync (Funcionalidad *)
│   │   ├── noxus_labels.py            # POST /flows/noxus-labels/sync (Funcionalidad * - Noxus)
│   │   └── workers.py                 # POST /flows/workers/sync  (Flujo 2)
│   ├── clients/
│   │   ├── auron_client.py            # AuronClient (OpenPages, GET/PUT real implementado)
│   │   ├── maisa_client.py            # MaisaClient (workers + create/update_label placeholder)
│   │   └── noxus_client.py            # NoxusClient (workers + create/update_label placeholder)
│   ├── repositories/
│   │   ├── use_case_label_repository.py  # tabla intermedia OpenPages<->Maisa (Postgres)
│   │   ├── noxus_use_case_label_repository.py  # tabla intermedia OpenPages<->Noxus (Postgres)
│   │   ├── use_case_sync_failure_repository.py  # tracking de fallos Flujo 1 (Postgres)
│   │   └── worker_sync_failure_repository.py  # tracking de fallos Flujo 2 (Postgres, snapshot de Worker)
│   ├── db/
│   │   └── pool.py                    # pool asyncpg (lifecycle en main.py)
│   ├── services/
│   │   ├── use_case_sync_service.py   # orquesta Flujo 1 (dispatch por tenant)
│   │   ├── maisa_label_sync_service.py  # orquesta Funcionalidad * (tabla intermedia -> Maisa)
│   │   ├── noxus_label_sync_service.py  # orquesta Funcionalidad * - Noxus (tabla intermedia -> Noxus)
│   │   └── worker_sync_service.py     # orquesta Flujo 2
│   ├── models/
│   │   ├── use_case.py
│   │   ├── use_case_label.py          # esquema de la tabla intermedia (Maisa)
│   │   ├── noxus_use_case_label.py    # esquema de la tabla intermedia (Noxus)
│   │   └── worker.py
│   └── core/
│       ├── checkpoint.py              # placeholder sin usar, ver "Ventana de fechas" (Flujo 1)
│       ├── monitoring.py              # registro de IDs/estado -> log JSON a CloudWatch (Flujo 2, paso 6AB)
│       ├── notifications.py           # email a admins (Flujo 2, paso 7A)
│       └── logging.py
├── db/migrations/
│   ├── 0001_create_maisa_use_case_labels.sql
│   ├── 0002_add_maisa_label_id_and_synced_status.sql
│   ├── 0003_add_entity_to_maisa_use_case_labels.sql
│   ├── 0004_create_use_case_sync_failures.sql
│   ├── 0005_add_owner_to_maisa_use_case_labels.sql
│   ├── 0006_create_noxus_use_case_labels.sql
│   └── 0007_create_worker_sync_failures.sql
└── tests/
```

(Los manifiestos de despliegue en EKS los gestiona el CI/CD de Santander, no este
repositorio — ver sección "Despliegue en EKS" más arriba.)

## Pendiente de acordar (bloqueantes antes de implementar)

### Bloqueantes abiertos

1. **Contrato REST real de Noxus** (`create_label`/`update_label` en
   `clients/noxus_client.py`) — auth, URL, payload exacto. El diseño
   interno ya está resuelto (tabla intermedia, igual que Maisa, ver
   sección "4b. Destino Noxus" más arriba); lo que falta es solo el
   contrato de envío real. Incluye, cuando llegue ese contrato (mismo
   origen, no son preguntas aparte): las "restricciones de diseño"
   equivalentes a las que el PPT documenta para Maisa (índice único,
   límites de `name`, cómo mantiene Noxus su propio `workerCount`, etc.) y
   si Noxus tiene un concepto de "organizationId" equivalente al de Maisa
   (`settings.noxus_organization_id`, hoy sin valor).
2. **`MaisaClient.update_label`**: `create_label` ya está confirmado e
   implementado (ver "Ya resueltos e implementados" más abajo); falta solo
   la actualización — el ejemplo real visto solo cubre creación, sin
   confirmar método HTTP/URL de actualización (hipótesis sin confirmar:
   mismo patrón de URL con `PUT`/`PATCH`). Tampoco confirmado si el body
   de creación admite más campos aparte de `name` (el ejemplo solo creaba
   labels de prueba tipo entorno/departamento, no casos de uso reales).
3. **Mecanismo de envío de email (7A)**: ¿SES, SMTP corporativo, servicio
   interno?
4. **Camino alternativo sin API de Maisa** (descarga diaria + carga
   separada por entidad/entorno, mencionado en el PPT como fallback) — sin
   decidir si hace falta, no implementado.
5. **Write-back del `maisa_label_id` hacia OpenPages** — pospuesto
   explícitamente, sin fecha para retomarlo (`AuronClient.update_use_case`
   ya está listo para cuando se necesite).
6. **`get_agent_by_worker_id`**: pendiente el endpoint real de búsqueda de
   un Agent por su campo personalizado `worker_id` (probablemente el mismo
   mecanismo de consulta masiva que `get_use_cases`, filtrando por field id
   `"3658"`) — ningún ejemplo real visto hasta ahora es de búsqueda, solo
   de creación.
7. **Diseño funcional del caso de uso genérico "Pendiente de
   regularizar"**: sin confirmar si necesita granularidad por
   consumidor/usuario (un registro por `(tenant, consumerId)`) o basta uno
   por `(tenant, entidad)` — la hipótesis anterior de que era por
   consumidor partía de confundirlo con "Personal Productivity" (punto 8),
   se ha revertido (ver paso 3 del Flujo 2 más arriba). Lo que sí sigue
   siendo válido con independencia de esa duda (confirmado por ejemplos
   reales): el mecanismo de tres pasos (consultar por nombre → crear si no
   existe → `associate` a la AI solution del tenant), `typeDefinitionId:
   "94"`, `primaryParentId` (`settings.auron_generic_use_case_parent_id`,
   específico de entorno, falta el valor de PRO) y el target de `associate`
   (`settings.auron_maisa_ai_solution_id`/`auron_noxus_ai_solution_id`,
   confirmado que son distintos). Falta además: de dónde sale el valor real
   de los campos del payload de creación (País, Owner, AI Solution Origin,
   Purpose, AI Type, Primary users) — el ejemplo usa valores fijos
   (`Country: ESP`, `Purpose: Other`, `Primary users: Other`) sin confirmar
   si son literales para todo caso o deberían variar.
8. **Caso de uso "Personal Productivity"** (`"personal productivity -
   <user_id>"` en Auron, ver paso 3 del Flujo 2 más arriba) — confirmado el
   concepto (el propio usuario lo elige desde Maisa para sus workers, así
   que `worker.use_case_id` ya viene informado apuntando a él; el
   microservicio solo entra en juego si ese caso personal **todavía no
   existe en OpenPages**), pero la creación-si-no-existe se deja
   **explícitamente sin implementar**: faltan los mismos datos que en el
   punto 7 (de dónde sale el `user_id` y el resto del payload) y no hay
   ningún ejemplo real todavía de este caso concreto.

### Ya resueltos e implementados (referencia rápida)

- **Monitorización (Flujo 2, paso 6AB)**: `MonitoringStore.record` loguea
  un JSON (`worker_id`, `agent_id`, `use_case_id`, `status`, `timestamp`)
  por el logger estándar → CloudWatch, no una tabla en Postgres.
- **Estrategia de fallo parcial**: aislamiento por item en los cuatro
  servicios de orquestación, más reintento selectivo en Flujo 1
  (`use_case_sync_failures`, por Resource ID) y Flujo 2
  (`worker_sync_failures`, por snapshot del `Worker`) — ver "Ventana de
  fechas" más arriba para el detalle.
- **Endpoints genéricos de OpenPages**: creación (`AuronClient
  .create_content`) y asociación (`AuronClient.associate`), field id de
  `worker_id` (`"3658"`) y `typeDefinitionId` del Agent (`"156"`).
- **`create_agent` completo**: campos "3290"
  (`worker.provider_version_id`) y "3405" (`settings.aws_account_id`)
  resueltos; manejo de `None` implementado (`name`/`agent_owner`/
  `provider_version_id` obligatorios → `ValueError`, aislado como
  cualquier otro fallo; `description` opcional → se omite del payload).
- **Tabla intermedia de Noxus** (`noxus_use_case_labels`): mismo diseño
  que Maisa, con `workspace_id` (backfill desde Flujo 2,
  `set_workspace_id_if_missing`) y `noxus_label_id` como diferencias.
- **`MaisaClient.create_label`**: `POST /organizations/{organization_id}/
  labels`, `organization_id` en la URL, auth `Bearer`, body `{"name":
  ...}`, respuesta con `id` (`maisa_label_id`) — ver "Funcionalidad \*"
  más arriba para el detalle completo del ejemplo real.
- **`update_agent` completo**: confirmado que el caso de uso vinculado
  (`primaryParentId`) NO se puede cambiar en un `PUT` — solo actualiza los
  campos ("fields") del Agent, sin `use_case_id` como parámetro. Vía
  `AuronClient.update_content` (PUT genérico, mismo endpoint que
  `create_content` usa para el POST).
- **Reasignación del caso de uso vinculado a un Agent (`AuronClient
  .dissociate` + `associate`)**: confirmado vía ejemplo real del equipo
  Auron/IBM — cuando el caso de uso de un worker cambia,
  `WorkerSyncService` borra solo la asociación vieja (`DELETE
  /grc/api/contents/{agent_id}/associations?parents={use_case_id_viejo}`)
  y crea la nueva (`associate`, `associationDefinitionId "966"`, `type
  "PARENT"`) — no hace falta borrar/recrear el Agent entero (una hipótesis
  anterior, descartada).
