# import logging
# import sys
# from contextlib import asynccontextmanager

# from fastapi import FastAPI, Request
# from fastapi.responses import JSONResponse

# from app.core.cache import check_redis, close_redis, init_redis
# from app.core.encryption import is_configured as enc_configured
# from app.db.database import check_db, engine
# from app.routes import admin, copilot, workflows, webhooks
# from app.routes.auth import router as auth_router
# from app.routes.credentials import router as credentials_router

# # Logging Configuration
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     handlers=[
#         logging.FileHandler("app.log"),
#         logging.StreamHandler(sys.stdout),
#     ],
# )
# logger = logging.getLogger("copilot")

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # Encryption Check
#     if not enc_configured():
#         logger.critical(
#             "ENCRYPTION_MASTER_KEY is missing or invalid. "
#             "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\" "
#             "and add to .env"
#         )
#         # Recommended: Add sys.exit(1) here (see notes below)

#     # Redis Init
#     await init_redis()
#     logger.info("Redis connected")
    
#     yield
    
#     # Teardown
#     await close_redis()
#     await engine.dispose()
#     logger.info("Shutdown complete")

# # App Initialization
# app = FastAPI(
#     title="AI Workflow Copilot",
#     description="No-code workflow automation — multi-tenant with per-user encrypted credentials",
#     version="3.0.0",
#     lifespan=lifespan,
# )

# # Routers
# app.include_router(auth_router)
# app.include_router(credentials_router)
# app.include_router(copilot.router)
# app.include_router(workflows.router)
# app.include_router(admin.router)
# app.include_router(webhooks.router)

# # Exception Handling
# @app.exception_handler(Exception)
# async def global_exception_handler(request: Request, exc: Exception):
#     logger.exception(f"Unhandled error on {request.url.path}: {exc}")
#     return JSONResponse(
#         status_code=500,
#         content={"error": "internal_error", "detail": "Something went wrong. Please retry."},
#     )

# # Probes
# @app.get("/health")
# async def health():
#     return {"status": "ok"}

# @app.get("/ready")
# async def ready():
#     db_ok = await check_db()
#     redis_ok = await check_redis()
#     enc_ok = enc_configured()
    
#     if not (db_ok and redis_ok and enc_ok):
#         return JSONResponse(
#             status_code=503,
#             content={"db": db_ok, "redis": redis_ok, "encryption": enc_ok},
#         )
#     return {"db": db_ok, "redis": redis_ok, "encryption": enc_ok}


import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.cache import check_redis, close_redis, init_redis
from app.core.encryption import is_configured as enc_configured
from app.db.database import check_db, engine
from app.routes import admin, copilot, workflows, webhooks
from app.routes.auth import router as auth_router
from app.routes.credentials import router as credentials_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("copilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not enc_configured():
        raise RuntimeError(
            "\n\n"
            "══════════════════════════════════════════════════════════\n"
            "  STARTUP FAILED: ENCRYPTION_MASTER_KEY is missing.\n"
            "\n"
            "  Generate it once and add to your .env file:\n"
            "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "\n"
            "  Then set in .env:\n"
            "  ENCRYPTION_MASTER_KEY=<your 64-char hex string>\n"
            "══════════════════════════════════════════════════════════\n"
        )
    await init_redis()
    logger.info("Redis connected")
    yield
    await close_redis()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="AI Workflow Copilot",
    description="No-code workflow automation — multi-tenant with per-user encrypted credentials",
    version="3.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(credentials_router)
app.include_router(copilot.router)
app.include_router(workflows.router)
app.include_router(admin.router)
app.include_router(webhooks.router)


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
    enc_ok = enc_configured()
    if not (db_ok and redis_ok and enc_ok):
        return JSONResponse(
            status_code=503,
            content={"db": db_ok, "redis": redis_ok, "encryption": enc_ok},
        )
    return {"db": db_ok, "redis": redis_ok, "encryption": enc_ok}