import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import init_db
from routers import searches, preferences

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Shopping Agent API", lifespan=lifespan)
app.include_router(searches.router, prefix="/api/v1")
app.include_router(preferences.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
