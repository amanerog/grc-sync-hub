import asyncpg

from sinc_amn.config import settings

_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    global _pool
    # min_size=0: no abre conexiones al crear el pool (por defecto asyncpg
    # abre min_size=10 de forma eager y create_pool() no vuelve hasta
    # conseguirlas). Con 0, el arranque del servicio no depende de que la
    # BBDD ya este disponible; el fallo se ve al primer uso real (acquire()
    # en UseCaseLabelRepository), no en el startup del pod.
    _pool = await asyncpg.create_pool(dsn=settings.intermediate_db_dsn, min_size=0)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("El pool de la tabla intermedia no esta inicializado")
    return _pool
