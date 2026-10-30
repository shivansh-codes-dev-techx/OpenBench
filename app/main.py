from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine

app = FastAPI(
    title="OpenBench API",
    description="Trusted Campus Resource Sharing Platform",
    version="1.0.0",
)


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