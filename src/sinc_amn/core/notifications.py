class AdminNotifier:
    """Notificacion a admins de workspace (Flujo 2, paso 7A).

    Se dispara cuando un worker no tenia use_case_id y se le asigno el caso de
    uso generico "Pendiente de regularizar", para que el admin del workspace
    lo regularice manualmente. Mecanismo de envio (SES/SMTP/servicio interno)
    pendiente de decidir (ver ARCHITECTURE.md).
    """

    async def notify_pending_regularization(
        self, workspace_id: str, worker_id: str
    ) -> None:
        raise NotImplementedError
