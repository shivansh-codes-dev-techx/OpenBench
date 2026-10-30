from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine
from app.routers import auth
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

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
    allow_methods=[
        "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
    ],
    allow_headers=[
        "Authorization",
        "Content-Type"
    ],
)
app.include_router(auth.router)

@app.get("/")
def root():
    return {
        "success": True,
        "message": "Welcome to OpenBench API",
        "version": "1.0.0",
    }


@app.get("/health")
def health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "success": True,
            "status": "healthy",
            "database": "connected",
        }

    except Exception:
        return {
            "success": False,
            "status": "unhealthy",
            "database": "disconnected",
        }