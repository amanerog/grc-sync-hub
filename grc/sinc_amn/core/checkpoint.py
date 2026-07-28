from datetime import datetime


class CheckpointStore:
    """Persistencia del ultimo checkpoint exitoso del Flujo 1.

    Backend pendiente de decidir (ver ARCHITECTURE.md): DynamoDB, tabla RDS o
    ConfigMap de K8s. Usar un checkpoint persistido en lugar de una ventana
    fija de "ahora - 1h" evita perder casos de uso si el job falla o se
    retrasa entre ejecuciones.
    """

    async def get_last_checkpoint(self) -> datetime:
        raise NotImplementedError

    async def set_last_checkpoint(self, value: datetime) -> None:
        raise NotImplementedError
