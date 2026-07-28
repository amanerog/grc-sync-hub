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
2. `AuronClient.get_use_cases(since, tenants=["maisa", "noxus"])` — GET a OpenPages
   filtrando casos de uso creados/actualizados desde el último checkpoint
   ("since the last successful call"). El filtro real, según el propio contrato de
   OpenPages, es por `Engagement.Name LIKE 'Maisa%' OR 'Noxus%'` sobre el `Register`
   asociado (join `Register`→`Engagement` por `PARENT`). Auth: API key. Protocolo:
   HTTPS. Formatos: JSON/JSON.
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
  `name_lower` (clave de igualdad/unicidad que exige Maisa), `organization_id`
  (entidad/entorno — viene de `settings.maisa_organization_id`, no de OpenPages,
  porque el microservicio ya se despliega por entidad), `worker_count` (**lo
  mantiene Maisa** vía asignación/desasignación de workers; la ingesta desde
  OpenPages nunca lo toca salvo al crear el registro, que arranca en 0),
  `status` (`new`/`modified`/`synced`/`deprecated` — `synced` lo añadimos para
  la coordinación con "Funcionalidad \*", ver abajo) y el bloque de auditoría
  (`created_at`/`updated_at`/`deleted_at`/`is_deleted`).
- Un **humano**, desde el front de Maisa, asigna manualmente el caso de uso a cada
  worker una vez la colección llega a Maisa. Esa asignación **no la hace el
  microservicio**.
- El front de Maisa **sí filtra los casos de uso mostrados por país/entidad**
  (confirmado) — responsabilidad del front de Maisa, no del microservicio.
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
- **Pendiente aún:** endpoint real de la **consulta masiva** (listar Resource
  ID/Name filtrando por Engagement Maisa/Noxus — la que sí usa el batch
  horario) no tiene todavía un ejemplo de código real como el resto de
  llamadas; sigue con placeholder y TODOs en `clients/auron_client.py`. Ídem
  para el mecanismo exacto del filtro incremental "since".

### "Funcionalidad \*" — tabla intermedia → Maisa (DocumentDB)

**Implementado** (ver diapositivas 5-6 del PPT, "SubTask"). Endpoint:
`POST /flows/maisa-labels/sync`, mismo cadencia horaria que "Funcionalidad 1".

- La BBDD real de Maisa es **AWS DocumentDB** (compatible Mongo), colección
  `labels`, backend en Go (`labels.go`/`label.go` según el PPT).
- Contrato REST de Maisa **aún no confirmado** (a diferencia de OpenPages, para
  esto no tenemos ejemplos de código reales todavía) — `MaisaClient.create_label`
  / `update_label` son placeholders con `NotImplementedError`, mismo patrón que
  la consulta masiva de OpenPages.
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

### 4b. Destino Noxus — push automático

- `NoxusClient.push_use_case(use_case)` — Noxus expone **su propia API de ingesta**;
  el microservicio empuja el caso de uso directamente y **Noxus asocia el caso de
  uso automáticamente**, sin label table intermedia ni paso manual de asignación.

### Checkpoint

- Se persiste el último checkpoint exitoso (`CheckpointStore`) en vez de usar una
  ventana fija "ahora - 1h", para no perder casos de uso si el CronJob falla o se
  retrasa. Backend de persistencia pendiente de decidir (DynamoDB/RDS/ConfigMap).
- Pendiente de definir estrategia de fallo parcial: si Maisa u Noxus falla para un
  caso de uso concreto, ¿el checkpoint no avanza más allá de ese punto, o se
  necesita tracking de estado por destino para reintentar solo lo pendiente?

**Endpoint expuesto:** `POST /flows/use-cases/sync`

---

## Flujo 2 — Maisa/Noxus → Auron (sincronización de workers)

**Frecuencia:** diaria, procesa datos de "D-1".

**Modelo de datos:** el diagrama distingue terminológicamente "workers" (Maisa) de
"workspaces y agents metadata" (Noxus), pero **confirmado que es solo diferencia de
nombre — mismo modelo lógico** (`worker_id`, `workspace_id`, `use_case_id`) para
ambos orígenes. Se reutiliza el modelo `Worker` para los dos.

**Pasos:**

1. Obtención de datos actualizados en D-1:
   - `1A` `MaisaClient.get_updated_workers(day)` — GET REST API a Maisa: workers y
     metadata.
   - `1B` `NoxusClient.get_updated_workers(day)` — GET REST API a Noxus: workspaces
     y metadata de agents (mismo modelo `Worker`, ver nota arriba).
2. `2AB` El microservicio procesa la información combinada de ambos orígenes.
3. Para cada worker, ingesta en Auron/OpenPages (`3A-5A` para origen Maisa,
   `3B-5B` para origen Noxus — mismo procedimiento, ejecutado por separado por
   origen). **Implementado en `WorkerSyncService`/`AuronClient`, en placeholder**
   (contrato real de OpenPages para Agents aún no confirmado, mismo tratamiento
   que la consulta masiva de Flujo 1):
   - **`worker_id` ≠ `agent_id`**: OpenPages identifica el Agent por su propio
     `resource_id`, distinto del `worker_id` de Maisa/Noxus. Por eso el Agent
     debe llevar una **tag/campo personalizado `worker_id`** con el valor de
     Maisa/Noxus, y localizarlo requiere buscar por ese campo
     (`AuronClient.get_agent_by_worker_id`), no un GET directo por ID.
   - Si existe → `AuronClient.update_agent(agent_id, workspace_id, use_case_id)`.
     Si no existe → `AuronClient.create_agent(worker_id, workspace_id, use_case_id)`.
   - **Confirmado:** el enlace al caso de uso es un **campo dentro del propio
     payload** de creación/actualización del Agent (no una llamada de
     asociación aparte) — por eso `create_agent`/`update_agent` reciben
     `use_case_id` directamente y no existe un método `link_use_case` separado.
   - Si `use_case_id` no está presente → se usa el genérico
     **"Pendiente de regularizar"** (`settings.generic_use_case_id`) **y además**
     se dispara una notificación (`7A`, confirmado que se implementa además del
     fallback genérico, no en su lugar) a los admins del workspace
     correspondiente para que lo regularicen.
   - **Pendiente de confirmar con Auron:** endpoint de creación (POST) de un
     Agent (los ejemplos reales que tenemos son GET/PUT sobre un recurso ya
     existente), y los `field id` de los campos personalizados `worker_id`
     (`settings.auron_agent_worker_id_field_id`) y enlace a caso de uso
     (`settings.auron_agent_use_case_field_id`).
4. `6AB` Se envían los IDs devueltos por las llamadas de creación (Use Case/Agent)
   a una **BBDD de monitorización**, vía `MonitoringStore`, para poder auditar el
   proceso. **Payload exacto: pendiente de cerrar** (el propio PPT lo marca como no
   cerrado) — de mínimos: `worker_id`, `agent_id`, `use_case_id`, estado (éxito/error)
   y timestamp.
5. `7A` Email a los admins del workspace cuando el worker no tenía `use_case_id` y
   se le asignó el genérico, para que lo regularicen manualmente. Confirmado que se
   implementa (no queda descartado ni solo como TODO).

**Endpoint expuesto:** `POST /flows/workers/sync`

---

## Despliegue en EKS — multi-entidad

Confirmado: **un Deployment + CronJobs independiente por entidad** (no un servicio
único compartido). Cada entidad tiene su propio conjunto de credenciales de
Auron/Maisa/Noxus y su propio `generic_use_case_id`.

Los manifiestos de Kubernetes/EKS **no se generan en este repositorio**: el
despliegue real lo gestiona el pipeline de CI/CD de Santander sobre sus instancias
de EKS. Lo relevante para ese pipeline es que necesitará, por entidad: variables de
entorno con prefijo `SINC_AMN_` (ver `config.py`), y tres triggers periódicos
contra la app — dos horarios (`POST /flows/use-cases/sync` y
`POST /flows/maisa-labels/sync`, este segundo siempre después del primero para
minimizar el retraso hasta que el caso de uso aparece en Maisa) y uno diario a
`POST /flows/workers/sync`.

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
│   │   └── workers.py                 # POST /flows/workers/sync  (Flujo 2)
│   ├── clients/
│   │   ├── auron_client.py            # AuronClient (OpenPages, GET/PUT real implementado)
│   │   ├── maisa_client.py            # MaisaClient (workers + create/update_label placeholder)
│   │   └── noxus_client.py            # NoxusClient (push automático + workers)
│   ├── repositories/
│   │   └── use_case_label_repository.py  # tabla intermedia OpenPages<->Maisa (Postgres)
│   ├── db/
│   │   └── pool.py                    # pool asyncpg (lifecycle en main.py)
│   ├── services/
│   │   ├── use_case_sync_service.py   # orquesta Flujo 1 (dispatch por tenant)
│   │   ├── maisa_label_sync_service.py  # orquesta Funcionalidad * (tabla intermedia -> Maisa)
│   │   └── worker_sync_service.py     # orquesta Flujo 2
│   ├── models/
│   │   ├── use_case.py
│   │   ├── use_case_label.py          # esquema de la tabla intermedia
│   │   └── worker.py
│   └── core/
│       ├── checkpoint.py              # persistencia del último checkpoint (Flujo 1)
│       ├── monitoring.py              # registro de IDs/estado (Flujo 2, paso 6AB)
│       ├── notifications.py           # email a admins (Flujo 2, paso 7A)
│       └── logging.py
├── db/migrations/
│   ├── 0001_create_maisa_use_case_labels.sql
│   └── 0002_add_maisa_label_id_and_synced_status.sql
└── tests/
```

(Los manifiestos de despliegue en EKS los gestiona el CI/CD de Santander, no este
repositorio — ver sección "Despliegue en EKS" más arriba.)

## Pendiente de acordar (bloqueantes antes de implementar)

1. URL/path real del endpoint de OpenPages y nombres reales de los campos JSON
   de respuesta (`clients/auron_client.py` usa placeholders razonables).
2. Mecanismo exacto del filtro incremental "since" contra OpenPages (query
   param vs. cláusula WHERE adicional).
3. Payload exacto de la BBDD de monitorización (paso 6AB).
4. Contrato de la API de ingesta de Noxus (paso 4b) — auth, forma del payload.
5. Backend de persistencia del checkpoint del Flujo 1 (DynamoDB/RDS/ConfigMap).
6. Backend de persistencia de `MonitoringStore` (¿misma BBDD que el checkpoint?).
7. Mecanismo de envío de email (7A): ¿SES, SMTP corporativo, servicio interno?
8. Estrategia de fallo parcial en Flujo 1 (Maisa ok / Noxus falla, o viceversa).
9. ID del caso de uso genérico "Pendiente de regularizar" en Auron, **por entidad**.
10. Contrato REST real de Maisa (`create_label`/`update_label` en
    `clients/maisa_client.py`) — auth, URL, payload exacto de la colección
    `labels` en su DocumentDB.
11. Si finalmente hace falta el camino alternativo sin API de Maisa (descarga
    diaria + carga separada por entidad/entorno, mencionado en el PPT como
    fallback) — no implementado.
12. Si/cuándo se retoma el write-back del `maisa_label_id` hacia OpenPages
    (pospuesto explícitamente; `AuronClient.update_use_case` ya está listo).
13. Endpoint real de creación (POST) de un Agent en OpenPages — solo tenemos
    ejemplos de GET/PUT sobre un recurso ya existente.
14. Field id de los campos personalizados del Agent en OpenPages: tag
    `worker_id` y enlace a `use_case_id` (`auron_agent_worker_id_field_id` /
    `auron_agent_use_case_field_id` en `config.py`, ambos sin valor real aún).
15. Endpoint/mecanismo para `AuronClient.get_agent_by_worker_id` (buscar un
    Agent por su tag `worker_id` — probablemente el mismo tipo de consulta
    masiva que el punto 1, pero sin confirmar).
