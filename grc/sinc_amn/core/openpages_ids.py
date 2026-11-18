"""Ids de fields y asociaciones de OpenPages que usa Flujo 2.

Son los mismos campos en todas las instancias, pero con ids distintos: la
instancia se elige con `settings.auron_openpages_environment`. Los valores de
los enums se envian por nombre, que no cambia entre instancias.

Los de PRO a None aun no se conocen: `openpages_id` falla con un error claro
en vez de escribir en un field equivocado. Se sacan comparando por nombre con
PRE (scripts/map_openpages_ids.py).
"""

from sinc_amn.config import settings

OPENPAGES_IDS: dict[str, dict[str, str | None]] = {
    "PRE": {
        # Agent
        "platform_agent_id": "3658",  # Santander-Fields-Agent:PlatformAgentID
        "use_case_owner": "3261",  # Santander Fields:Owner
        "agent_creator": "3293",  # Creator of the AI Agent
        "provider_version_id": "3290",  # Version id of the provider
        "technical_owner": "179",  # MRG-AIFacts-AIComponent:Technical Owner
        "autonomy_level": "172",  # MRG-AIFacts-AIComponent:AI Component Level
        "agent_role": "3333",  # watsonx-AIComponent:Agent Role
        "solution_origin": "3966",  # Santander-Fields-Agent:AI Solution Origin
        "agent_platform": "3332",  # watsonx-AIComponent:Agent Platform
        "build_origin": "3334",  # watsonx-AIComponent:Build origin
        "technical_status": "3288",  # Santander-Fields-Agent:Status
        # Caso de uso
        "initiative": "3601",
        "api_id": "3408",
        "cloud_account": "3405",
        # Asociacion Agent -> caso de uso (PARENT)
        "agent_use_case_association": "966",
    },
    "PRO": {
        "platform_agent_id": "3524",
        "use_case_owner": None,
        "agent_creator": "3285",
        "provider_version_id": "3281",
        "technical_owner": None,
        "autonomy_level": None,
        "agent_role": None,
        "solution_origin": None,
        "agent_platform": "3186",
        "build_origin": "3188",
        "technical_status": "3287",
        "initiative": None,
        "api_id": None,
        "cloud_account": None,
        "agent_use_case_association": None,
    },
}


def openpages_id(key: str) -> str:
    """Id de `key` en la instancia de OpenPages configurada."""
    environment = settings.auron_openpages_environment
    value = OPENPAGES_IDS[environment][key]
    if value is None:
        raise LookupError(f"falta el id de {key!r} en OpenPages {environment}")
    return value
