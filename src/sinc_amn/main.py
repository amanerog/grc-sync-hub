from contextlib import asynccontextmanager

from fastapi import FastAPI

from sinc_amn.api.routes import maisa_labels, use_cases, workers
from sinc_amn.core.logging import configure_logging
from sinc_amn.db.pool import close_pool, create_pool

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    yield
    await close_pool()


app = FastAPI(title="sinc-amn", version="0.1.0", lifespan=lifespan)
app.include_router(use_cases.router)
app.include_router(maisa_labels.router)
app.include_router(workers.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
