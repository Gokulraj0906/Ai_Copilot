"""Lightweight admin endpoint to view log anomalies without SSH access.
Not authenticated beyond the existing X-API-Key — for production,
restrict this to an admin-only key or remove entirely."""

from fastapi import APIRouter, Query
from pathlib import Path
from datetime import datetime

from app.service.log_analysis import parse_log_file, filter_since, analyze

router = APIRouter(prefix="/admin", tags=["admin"])

LOG_PATH = Path("app.log")


@router.get("/log-analysis")
async def log_analysis(since: str | None = Query(default=None, description="YYYY-MM-DD HH:MM:SS")):
    if not LOG_PATH.exists():
        return {"error": "app.log not found"}

    records = parse_log_file(LOG_PATH)

    since_dt = None
    if since:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return {"error": "invalid 'since' format, expected YYYY-MM-DD HH:MM:SS"}
        records = filter_since(records, since_dt)

    return analyze(records)