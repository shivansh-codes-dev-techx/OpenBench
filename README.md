# OpenBench

## Backend Setup

Create and activate a Python virtual environment, install the pinned backend
dependencies, and configure the local environment from `.env.example`.

On a fresh installation, initialize the SQLite schema before starting the API:

```text
python -m app.init_db
```

Start the backend locally with:

```text
python -m uvicorn app.main:app --reload
```

The initialization command creates the initial SQLAlchemy tables. It is not a
database migration system and is not called automatically during application
startup. Future schema changes require a separate migration process.
