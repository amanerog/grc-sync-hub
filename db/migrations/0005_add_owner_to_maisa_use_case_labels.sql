-- owner: [Register].[Santander Fields:Owner] en Auron. Se persiste aqui
-- (y no solo en memoria como UseCase.owner) porque Flujo 2 lo necesita al
-- crear/actualizar el Agent (field "3261" - Owner del Use Case, distinto
-- del owner del propio Agent) y asi evita un GET adicional a OpenPages por
-- cada worker: lo lee de esta tabla, ya poblada por Flujo 1.
ALTER TABLE maisa_use_case_labels
    ADD COLUMN owner TEXT;
