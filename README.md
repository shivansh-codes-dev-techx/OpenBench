# OpenBench

OpenBench is a campus resource-sharing application. The repository contains a
FastAPI backend, a SQLAlchemy data model, and a React/Vite frontend. Students
can discover resources and request bookings. Resource owners can publish
resources and approve or reject booking requests.

## Repository Layout

- `app/`: FastAPI application, SQLAlchemy models, schemas, services, and routes.
- `tests/`: backend tests.
- `frontend/`: React/Vite application.
- `.env.example`: backend environment variable template.
- `requirements.txt`: pinned Python dependencies.

## Backend Development

Run backend commands from the repository root.

### Prerequisites

- Python installed and available as `python`.
- A shell capable of creating and activating a Python virtual environment.

### Create the Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Unix-like shells:

```sh
python -m venv .venv
source .venv/bin/activate
```

Install the pinned dependencies:

```text
python -m pip install -r requirements.txt
```

### Configure Environment Variables

Copy `.env.example` to `.env` and replace the placeholder `SECRET_KEY` with a
unique secret for the environment. Do not commit `.env`.

The current backend settings are:

- `SECRET_KEY`: required signing secret for access tokens.
- `ALGORITHM`: JWT signing algorithm; defaults to `HS256`.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: token lifetime; defaults to `60`.
- `CORS_ORIGINS`: comma-separated allowed frontend origins. The example values
  are for local development.

### Initialize the Local Database

The development database is the repository-root SQLite file
`openbench.db`. On a fresh local checkout, initialize its initial schema with:

```text
python -m app.init_db
```

This command uses SQLAlchemy `create_all` to create missing tables. It does not
drop existing tables and is intended only for local development. It is not a
database migration system, is not run automatically by the API, and must not
be treated as a production schema-management process. A migration system must
be selected and implemented before production deployment.

### Start the Backend

Start the local development server with:

```text
python -m uvicorn app.main:app --reload
```

The default local API address is `http://127.0.0.1:8000`.

## Frontend Development

Run frontend commands from `frontend/`.

The frontend requires Node.js and npm.

Install the locked Node.js dependencies:

```text
npm ci
```

The frontend reads `VITE_API_BASE_URL` at build time. Set it to the backend
address when it differs from the default local value:

Windows PowerShell:

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
```

Unix-like shells:

```sh
export VITE_API_BASE_URL=http://127.0.0.1:8000
```

Start the Vite development server:

```text
npm run dev
```

## API Documentation and Probes

With the backend running, FastAPI exposes:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

`GET /health` is a liveness-style database check. It returns HTTP 200 with
`status: healthy` when a database query succeeds. If the query fails, it still
returns HTTP 200 with `status: unhealthy` and does not expose database details.

`GET /ready` is a readiness check. It returns HTTP 200 only when the database
is reachable and all required application tables exist. Database connection
failures or missing required tables return HTTP 503 with a generic error.

## Verification Commands

Run backend tests from the repository root:

```text
python -m pytest -v
```

Run frontend checks from `frontend/`:

```text
npm run lint
npm run build
```

## Development and Production

The commands above are development commands. The backend command uses
`--reload`, and the local database is a relative SQLite file. The frontend
development server is also not a production hosting service.

Before production deployment, the deployment plan must provide all of the
following without assuming a particular hosting provider:

- A unique production `SECRET_KEY` and environment-specific token settings.
- Exact production frontend origins in `CORS_ORIGINS`.
- Durable database storage suitable for the deployment topology.
- A selected and implemented database migration system. `create_all` is not a
  replacement for migrations.
- A production `VITE_API_BASE_URL` value supplied when the frontend is built.
- A backend process command without `--reload` and health/readiness probes.
- A method to serve the built frontend assets.

No production hosting provider, deployment URL, infrastructure, credentials,
or migration tool is defined by this repository.
