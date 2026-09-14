"""Fakes minimos de asyncpg.Pool/Connection, compartidos entre tests de
repositorios (evitan tocar una BBDD real)."""


class FakeConnection:
    def __init__(self, fetchrow_results=None, fetch_result=None):
        self.fetchrow_results = list(fetchrow_results or [])
        self.fetch_result = fetch_result or []
        self.fetchrow_calls: list[tuple] = []
        self.fetch_calls: list[tuple] = []
        self.execute_calls: list[tuple] = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self.fetchrow_results.pop(0) if self.fetchrow_results else None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.fetch_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class _AcquireContext:
    def __init__(self, conn: FakeConnection):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc_info):
        return False


class FakePool:
    def __init__(self, conn: FakeConnection):
        self.conn = conn

    def acquire(self):
        return _AcquireContext(self.conn)
