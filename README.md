# OpenBench

OpenBench is a campus resource-sharing application with a FastAPI backend and
a React/Vite frontend. Students can discover resources and request bookings;
owners can publish resources and approve or reject booking requests. The
backend also supports eligibility checks and image-based condition inspections.

## Repository layout

- `app/`: FastAPI application, SQLAlchemy models, schemas, services, and routes.
- `alembic/`: versioned database migrations.
- `cv_engine/`: image inspection and comparison.
- `frontend/`: React/Vite application.
- `tests/`: backend tests.
- `docs/DEPLOYMENT.md`: Render/PostgreSQL and frontend deployment notes.

## Backend development

Run commands from the repository root. Create and activate a virtual
environment, then install pinned dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and replace the `SECRET_KEY` placeholder with a
random secret of at least 32 characters. Do not commit `.env`. The settings are:

- `SECRET_KEY`: JWT signing secret (required).
- `ALGORITHM`: JWT algorithm; defaults to `HS256`.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: token lifetime; defaults to `60`.
- `DATABASE_URL`: SQLAlchemy URL; defaults to local SQLite.
- `CORS_ORIGINS`: comma-separated allowed origins; example values are local
  development origins.

Initialize a new local database with the versioned migration:

```powershell
python -m alembic upgrade head
```

Start the API:

```powershell
python -m uvicorn app.main:app --reload
```

The local API is available at `http://127.0.0.1:8000`.

## Frontend development

Run commands from `frontend/`. Install the exact lockfile dependencies and
start the development server:

```powershell
npm ci
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
npm run dev
```

`VITE_API_BASE_URL` is consumed at build time and must point to the deployed API
for a production frontend build.

## API probes

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- `GET /health`: process liveness endpoint; it does not check the database.
- `GET /ready`: database readiness endpoint; requires connectivity and the
  application schema, returning HTTP 503 when not ready.

## Verification

From the repository root:

```powershell
python -m compileall -q app cv_engine scripts tests
python -m pip check
python -m pytest -q
git diff --check
```

From `frontend/`:

```powershell
npm ci
npm run lint
npm run build
```

See [production deployment](./docs/DEPLOYMENT.md) for Render, PostgreSQL,
migrations, and frontend deployment configuration.
