from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.config import settings


def _is_generic_use_case(name: str | None) -> bool:
    """Si el caso de uso es uno de los genericos de Business Entity de
    Maisa (`settings.auron_maisa_generic_use_case_name`), por su nombre."""
    prefix = settings.auron_maisa_generic_use_case_name.split("{business_entity}")[0]
    return bool(name) and name.startswith(prefix)


class CheckpointService:
    """Consultas de solo lectura para los checkpoints del pipeline de CI/CD
    de los agentes de Maisa (CP1: el Agent esta en OpenPages y cuelga de un
    caso de uso; CP2/CP3: estado del caso de uso). Todo en vivo contra
    Maisa/OpenPages, sin pasar por la tabla intermedia.
    """

    def __init__(self, auron: AuronClient, maisa: MaisaClient) -> None:
        self._auron = auron
        self._maisa = maisa

    async def get_agent(self, version_id: str) -> dict | None:
        """Estado en OpenPages del agente de una version de Maisa, o None si
        la version no existe en Maisa.

        `agent_id` None: el Agent aun no existe (Flujo 2 no ha corrido o el
        agente no cumple sus filtros). `use_case_id` None: el Agent existe
        pero no cuelga de un caso de uso del Engagement de Maisa.
        """
        worker_manager_id = await self._maisa.get_worker_manager_id(version_id)
        if worker_manager_id is None:
            return None

        result = {
            "worker_id": version_id,
            "worker_manager_id": worker_manager_id,
            "agent_id": None,
            "use_case_id": None,
            "use_case_name": None,
            "use_case_status": None,
            "is_generic_use_case": False,
        }

        agent = await self._auron.get_agent_by_worker_id(worker_manager_id, "maisa")
        if agent is None:
            result["agent_id"] = await self._auron.get_agent_id_by_worker_id(
                worker_manager_id
            )
            return result

        result["agent_id"] = agent["id"]
        result["use_case_id"] = agent["primaryParentId"]
        use_case = await self._auron.get_use_case_status(agent["primaryParentId"])
        if use_case:
            result["use_case_name"] = use_case["name"]
            result["use_case_status"] = use_case["status"]
            result["is_generic_use_case"] = _is_generic_use_case(use_case["name"])
        return result

    async def get_use_case(self, use_case_id: str) -> dict | None:
        """Nombre, Status y Owner de un caso de uso, o None si no existe."""
        return await self._auron.get_use_case_status(use_case_id)
