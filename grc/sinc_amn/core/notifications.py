import logging

logger = logging.getLogger(__name__)


class AdminNotifier:
    """Notificacion a admins de workspace (Flujo 2, paso 7A).

    Se dispara cuando un worker no tenia caso de uso valido y su Agent se
    colgo del caso de uso generico, para que lo regularicen manualmente.
    Mecanismo de envio (SES/SMTP/servicio interno) y destinatarios pendientes
    de decidir (ver ARCHITECTURE.md): mientras tanto solo deja un aviso en el
    log, para no convertir en fallo un Agent que ya se ha creado bien.
    """

    async def notify_pending_regularization(
        self, workspace_id: str, worker_id: str
    ) -> None:
        logger.warning(
            "notificacion pendiente de implementar: worker %s (workspace %s) "
            "en el caso de uso generico",
            worker_id,
            workspace_id,
        )
