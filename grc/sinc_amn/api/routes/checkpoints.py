import logging

import httpx
from fastapi import APIRouter, HTTPException
from pymongo.errors import PyMongoError

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.services.checkpoint_service import CheckpointService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checkpoints", tags=["checkpoints"])


def _service() -> CheckpointService:
    return CheckpointService(auron=AuronClient(), maisa=MaisaClient())


@router.get("/agents/{worker_id}")
async def get_agent_checkpoint(worker_id: str) -> dict:
    """CP1: el Agent de una version de Maisa (`worker_id` = id de la
    version, el `lastVersionId`) y el caso de uso del que cuelga.

    404 si la version no existe en Maisa; 502 si falla Maisa u OpenPages.
    """
    try:
        result = await _service().get_agent(worker_id)
    except (httpx.HTTPError, PyMongoError) as exc:
        logger.exception("checkpoints: fallo consultando el agente %s", worker_id)
        raise HTTPException(status_code=502, detail=type(exc).__name__) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="version de Maisa no encontrada")
    return result


@router.get("/use-cases/{use_case_id}")
async def get_use_case_checkpoint(use_case_id: str) -> dict:
    """CP2/CP3: nombre, Status y Owner de un caso de uso de OpenPages.

    404 si no existe; 502 si falla OpenPages.
    """
    try:
        result = await _service().get_use_case(use_case_id)
    except httpx.HTTPError as exc:
        logger.exception("checkpoints: fallo consultando el caso de uso %s", use_case_id)
        raise HTTPException(status_code=502, detail=type(exc).__name__) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="caso de uso no encontrado")
    return result
