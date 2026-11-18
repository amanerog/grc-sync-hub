"""Business Entity (BE) de OpenPages a partir de la `entity` del agente en
Maisa (`worker_manager.entity`).

Decide a que caso de uso generico (`To be regularized - Maisa - {BE}`) va un
worker sin label de caso de uso valido (ver
`WorkerSyncService._resolve_use_case`). Tabla de equivalencias dada por
Auron; algunas BE pueden venir con dos entities distintas en Maisa (p.ej.
"Consumer" y "Germany"). HQ/HQNEW van todos a "HQ - Others" (sin
sub-enrutar). Una entity que no esta en la tabla, o vacia, no tiene BE: el
caller usa `settings.auron_other_business_entity`.

Los agentes de las entities de `SKIPPED_ENTITIES` no se sincronizan (ver
`MaisaClient.get_updated_workers`).
"""

import unicodedata

HQ_OTHERS = "HQ - Others"

# Claves normalizadas (ver _normalize).
MAISA_ENTITY_TO_BE = {
    "CIB": "CIB",
    "SDS": "Other",
    "CONSUMER": "Consumer",
    "GERMANY": "Consumer",
    "SCF_GLOBAL": "Consumer",
    "OPENBANK": "Openbank",
    "GLOBAL_CARDS": "Global Cards",
    "HQ": HQ_OTHERS,
    "HQNEW": HQ_OTHERS,
    "R&C": "R&C",
    "ARGENTINA": "Santander AR",
    "BRAZIL": "Santander BR",
    "CHILE": "Santander CL",
    "COLOMBIA": "Santander COL",
    "SPAIN": "Santander ES",
    "MEXICO": "Santander MX",
    "SANTANDER PAYMENTS SOLUTIONS": "Santander Payments Solutions",
    "GETNET": "Santander Payments Solutions",
    "PERU": "Santander PE",
    "PORTUGAL": "Santander PT",
    "UK": "Santander UK",
    "USA": "Santander US",
    "URUGUAY": "Santander UY",
    "WM&I": "WM&I",
}

# Claves normalizadas. Decidido por Auron: no van a OpenPages.
SKIPPED_ENTITIES = {"PLATFORM"}


def _normalize(value: str | None) -> str:
    """Mayusculas, sin acentos ni espacios de mas."""
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(text.split()).upper()


def business_entity_for(entity: str | None) -> str | None:
    """Nombre de la BE de OpenPages para la entity de Maisa, o None si no
    esta en la tabla."""
    return MAISA_ENTITY_TO_BE.get(_normalize(entity))


def is_skipped_entity(entity: str | None) -> bool:
    """True si los agentes de esa entity no se sincronizan."""
    return _normalize(entity) in SKIPPED_ENTITIES
