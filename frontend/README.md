# OpenBench Frontend

The frontend is a React application built with Vite. Project-wide setup,
environment configuration, API documentation, database notes, and production
prerequisites are documented in the repository-root `README.md`.

From this directory, install the locked dependencies and start the development
server with:

```text
npm ci
npm run dev
```

The frontend reads `VITE_API_BASE_URL` at build time. Set it to the address of
the running OpenBench backend when the default local address is not suitable.

Available verification commands are:

```text
npm run lint
npm run build
```

The backend's local `create_all` initialization command is not a database
migration strategy and is not a production deployment process.
