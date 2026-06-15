import logging
from contextlib import asynccontextmanager
import sys
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.cache import init_redis, close_redis, check_redis
from app.db.database import check_db, engine
from app.routes import copilot, workflows


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),           
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("copilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(title="AI Workflow Copilot", lifespan=lifespan)

app.include_router(copilot.router)
app.include_router(workflows.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "Something went wrong. Please retry."},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    db_ok = await check_db()
    redis_ok = await check_redis()
    if not (db_ok and redis_ok):
        return JSONResponse(status_code=503, content={"db": db_ok, "redis": redis_ok})
    return {"db": db_ok, "redis": redis_ok}