from fastapi import APIRouter, Response
from pymongo.errors import PyMongoError

from sinc_amn.clients.maisa_client import MaisaClient

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/maisa-db")
async def maisa_db_health(response: Response) -> dict:
    """Diagnostico de la conexion a la BBDD de Maisa (DocumentDB).

    200 con las colecciones si conecta; 503 con el tipo de error si no
    (timeout de red/SG, TLS, autenticacion...).
    """
    try:
        result = await MaisaClient().check_connection()
    except PyMongoError as exc:
        response.status_code = 503
        return {"status": "error", "error": type(exc).__name__, "detail": str(exc)}
    return {"status": "ok", **result}
