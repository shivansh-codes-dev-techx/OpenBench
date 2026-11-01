# Production deployment

## Deployment scope

The backend is a FastAPI service; `frontend/` contains the React/Vite
application. This repository does not include Vercel project configuration or
deployment credentials, so the actual Vercel deployment is not performed here.

The backend was tested with Python 3.14.5. `.python-version` pins that runtime
for Render.

## Required environment variables

Configure these on Render; never commit production values:

| Variable | Required value |
| --- | --- |
| `SECRET_KEY` | A newly generated random string of at least 32 characters. |
| `DATABASE_URL` | Render PostgreSQL internal connection URL. The app normalizes `postgres://` and `postgresql://` URLs to the psycopg 3 driver. |
| `CORS_ORIGINS` | Comma-separated, exact production frontend origins (scheme and host, no paths). Wildcard origins are rejected. |

Generate a key in a trusted terminal with:

```shell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env.example` contains placeholders and local SQLite settings only. For local
development, copy it to `.env` and replace the key before starting the API.

## Render Web Service

Create a Python Web Service from this repository and set:

- **Build command:** `python -m pip install -r requirements.txt`
- **Start command:** `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Attach a Render PostgreSQL database and set `DATABASE_URL` to its internal
  URL.
- Set `SECRET_KEY` and `CORS_ORIGINS` in the service environment. Add the exact
  Vercel production origin to `CORS_ORIGINS` once the Vercel hostname is known.
- Configure `/health` as the liveness check and `/ready` as the readiness check.
  `/health` is process liveness and does not query the database. `/ready` checks
  database connectivity and all required application tables and returns HTTP
  503 when either check fails.

## Database initialization and migrations

The application does not create tables at startup. For a fresh PostgreSQL
database, run the versioned schema migration once before starting the service:

```shell
python -m alembic upgrade head
```

Run this using the same `DATABASE_URL` and `SECRET_KEY` as the service, from the
Render Shell or a trusted operator environment with database network access.
Alembic records applied revisions, and repeating `upgrade head` is safe.

The initial migration creates the complete current schema, including the
resource baseline and immutable booking snapshot tables. No SQLite-to-PostgreSQL
data migration is required. Do not run the SQLite-only
`scripts/migrate_baseline_snapshots.py` against PostgreSQL. Downgrading the
initial migration to `base` drops the application tables and their data; do not
run it against production as a routine rollback.

Public registration creates student accounts only. After applying migrations,
trusted operators can provision owner and initial admin accounts interactively
using the configured database environment:

```shell
python -m scripts.provision_account OWNER
python -m scripts.provision_account ADMIN
```

The password is entered through a hidden prompt, not a command-line argument.

SQLite remains the local fallback. On a new local database, use the same
`python -m alembic upgrade head` command. The existing SQLite baseline upgrade
and rollback scripts are for an already-initialized legacy SQLite database
only; see [the SQLite procedure](./BASELINE_SQLITE_MIGRATION.md).

## Vercel frontend

Configure the Vercel project to use `frontend/` as its root directory. The
frontend's `package.json` defines `npm run build`; Vite's default output
directory is `dist`. Set this build-time environment variable for production:

| Variable | Required value |
| --- | --- |
| `VITE_API_BASE_URL` | The deployed Render API base URL, with scheme and host and no trailing slash (for example, `https://your-service.onrender.com`). |

Add the deployed Vercel origin to the backend's `CORS_ORIGINS`. The frontend
defaults to `http://127.0.0.1:8000` only when `VITE_API_BASE_URL` is unset;
ensure it is set for production builds.

## Deployment order

1. Create the Render PostgreSQL database and Web Service.
2. Configure `SECRET_KEY`, `DATABASE_URL`, and `CORS_ORIGINS`.
3. Run `python -m alembic upgrade head` against the fresh database.
4. Provision the initial administrator with
   `python -m scripts.provision_account ADMIN`.
5. Start the backend and verify `/health` and `/ready`.
6. Deploy the frontend on Vercel with `VITE_API_BASE_URL` set to the Render API,
   then add its production origin to backend CORS.

## Common failures

- **Settings validation fails:** set `SECRET_KEY` to a non-placeholder value
  with at least 32 characters.
- **Database driver or connection error:** install from the repository's
  `requirements.txt`, use the Render internal URL, and ensure the service can
  reach the database.
- **Readiness returns 503:** inspect Render database availability and the
  service's `DATABASE_URL`; the response intentionally does not expose
  connection details.
- **Browser CORS error:** set the exact frontend origin in `CORS_ORIGINS`
  (including `https://`), without a path or wildcard, then restart the service.
- **Migration reports existing tables:** this initial revision targets a fresh
  database. Stop and inspect the target rather than dropping or overwriting
  existing data.
