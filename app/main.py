"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import init_db
from app.routers import certificates, jobs

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: make sure the output folder and database tables exist.

    Note: the test-suite uses TestClient *without* a `with` block, so this
    hook does not run in tests and the real database is never touched.
    """
    settings.generated_files_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="Bulk Certificate Generator API",
    description=(
        "Submit one request with many recipients, track the generation job, "
        "and download each generated PDF certificate."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(jobs.router)
app.include_router(certificates.router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}