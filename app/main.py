import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.core.config import settings
from app.database import engine
from app.routers import auth, resources, eligibility, bookings

logger = logging.getLogger(__name__)

REQUIRED_TABLES = frozenset(
    {
        "users",
        "resources",
        "bookings",
        "eligibility_requirements",
        "user_qualifications",
        "condition_reports",
        "incidents",
        "waitlist",
        "activity_logs",
        "resource_images",
        "condition_report_images",
        "resource_baseline_images",
        "booking_baseline_snapshots",
        "booking_baseline_snapshot_images",
    }
)

app = FastAPI(
    title="OpenBench API",
    description="Trusted Campus Resource Sharing Platform",
    version="1.0.0",
)

allowed_origins = [
    origin.strip()
    for origin in settings.CORS_ORIGINS.split(",")
    if origin.strip()
]

if "*" in allowed_origins:
    raise ValueError("Wildcard CORS origins are not allowed")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(resources.router)
app.include_router(eligibility.router)
app.include_router(bookings.router)


@app.get("/")
def root():
    return {
        "success": True,
        "message": "Welcome to OpenBench API",
        "version": "1.0.0",
    }


@app.get("/health")
def health_check():
    return {
        "success": True,
        "status": "healthy",
    }


@app.get("/ready")
def readiness_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            table_names = set(inspect(connection).get_table_names())

        missing_tables = REQUIRED_TABLES - table_names

        if missing_tables:
            logger.error(
                "Readiness check failed. Missing tables: %s",
                sorted(missing_tables),
            )
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "status": "not_ready",
                    "database": "connected",
                },
            )

        return {
            "success": True,
            "status": "ready",
            "database": "connected",
        }

    except Exception:
        logger.exception("Readiness database check failed")
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "status": "not_ready",
                "database": "disconnected",
            },
        )