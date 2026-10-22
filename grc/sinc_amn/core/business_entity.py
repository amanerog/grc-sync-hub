"""Business Entity (BE) de OpenPages a partir de los datos de Workday del
creador de un agente.

Decide a que caso de uso generico va un worker sin caso de uso valido (ver
`WorkerSyncService._resolve_use_case`). Logica dada por el equipo de Auron:

- position_level_2 distinto de "Global & Corporate HQ": la BE sale de la
  entidad legal (POSITION_LEVEL2_TO_BE).
- "Global & Corporate HQ" con business_unit CHQ/HQ: se sub-enruta por
  functional_group_1 (FG1_TO_BE, fallback "HQ - Others").
- "Global & Corporate HQ" con otra business_unit: BUSINESS_UNIT_TO_BE.

Sin coincidencia, o creador sin datos en Workday: "Other". En PRE no existe
la BE "Other"; eso se resuelve con `settings.auron_other_business_entity`,
no aqui.
"""

import re
import unicodedata

from sinc_amn.models.workday_member import WorkdayMember

OTHER = "Other"
HQ_OTHERS = "HQ - Others"
_GLOBAL_HQ = "GLOBAL & CORPORATE HQ"
_HQ_BUSINESS_UNITS = {"CHQ", "HQ"}

# Claves normalizadas (ver _normalize), confirmadas por Auron contra los
# valores reales del CSV de Workday.
POSITION_LEVEL2_TO_BE = {
    "SANTANDER ESPANA": "Santander ES",
    "SANTANDER MEXICO": "Santander MX",
    "DIRECCION GENERAL GFS": "Santander MX",  # Mexico en Workday
    "SANTANDER CONSUMER GROUP": "Consumer",
    "OPENBANK & OPEN DIGITAL SERVICES": "Openbank",
    "BRASIL": "Santander BR",
    "SANTANDER PERU": "Santander PE",
    "SANTANDER PORTUGAL": "Santander PT",
    "SANTANDER UK": "Santander UK",
    "PAGONXT HOLDCO": "Santander Payments Solutions",
}

FG1_TO_BE = {
    "DATA & AI": "HQ - Data & AI",
    "PEOPLE & CULTURE": "HQ - People&Culture",
    "LEGAL": "HQ - Legal",
    "RISK": "HQ - Risks",
    "IT": "HQ - T&O",
    "OPERATIONAL PROCESSES": "HQ - T&O",
    "FINANCIAL ACCOUNTING AND MGMT CTRL": "HQ - Finance Control de Gestion",
    "FINANCE": "HQ - Gestion Financiera",
    "INTERNAL AUDIT": "HQ - Auditory",
    "BRAND, MKT & COMMS": "HQ - Marketing",
}

# CIB y WM&I no se sub-enrutan por functional_group_1.
BUSINESS_UNIT_TO_BE = {
    "CIB": "CIB",
    "CRD": "Global Cards",
    "WM": "WM&I",
    "RET": "R&C",
    "DCB": "Openbank",
    "PGX": "Santander Payments Solutions",
    "SCF": "Consumer",
}

# Codigo de entidad que Workday antepone a algunos nombres
# ("SANES_8901 SANTANDER ESPAÑA", "SCONS_0000 Santander Consumer Group").
_CODE_PREFIX_RE = re.compile(r"^\w+_\w+\s+")


def _normalize(value: str | None) -> str:
    """Mayusculas, sin acentos ni codigo de entidad delante."""
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    text = _CODE_PREFIX_RE.sub("", text.strip())
    return " ".join(text.split()).upper()


def business_entity_for(member: WorkdayMember | None) -> str:
    """Nombre de la BE de OpenPages para el creador de un agente."""
    if member is None:
        return OTHER
    position_level_2 = _normalize(member.position_level_2)
    business_unit = _normalize(member.business_unit)
    if position_level_2 != _GLOBAL_HQ:
        return POSITION_LEVEL2_TO_BE.get(position_level_2, OTHER)
    if business_unit in _HQ_BUSINESS_UNITS:
        return FG1_TO_BE.get(_normalize(member.functional_group_1), HQ_OTHERS)
    return BUSINESS_UNIT_TO_BE.get(business_unit, OTHER)
