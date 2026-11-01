# OpenBench Frontend

React frontend for the OpenBench campus resource-sharing platform, built with Vite.

Project-wide setup, environment configuration, API documentation, database notes, and production prerequisites are documented in the repository-root README.md.

## Local development

Install dependencies using npm ci.

Copy .env.example to .env and set VITE_API_BASE_URL to your reachable OpenBench API URL. The local example uses http://127.0.0.1:8000.

Make sure the backend CORS allowlist includes your frontend origin and port.

Start the frontend using npm run dev.

## Available checks

- npm run lint — runs Oxlint.
- npm run build — creates the production build.
- npm run preview — serves the production build locally.

There is currently no frontend test script.

The frontend reads VITE_API_BASE_URL at build time. Configure it before creating a production build.

## Backend integration limits

The current backend supports resource creation and editing as JSON, but does not expose resource image upload or image retrieval routes, email verification, or password reset endpoints.

Photo selection and inspection comparison UI currently remain session-only previews and do not persist to the backend.

The backend's local create_all initialization command is not a database migration strategy or a production deployment process.
