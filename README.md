# QuantumPath

QuantumPath is a fun game using quantum errors to make going around the quantum processor exciting. Also made interesting by the peculiar layout of qbit on the processor.
Send the kitten on a mission from Qbit to adjacent Qbit. They shoud all be zero, but... are they? If an error strikes, that can be the end of your journey!

## Requirements

- Docker Desktop (with `docker compose`)
- A local `.env` file in the project root

## Run

```bash
docker compose up --build
```

By default the app is exposed on `http://localhost:8070` (mapped to container port `8000`). I assume you have something else on port 8000.

## Health Check

Open:

- `http://localhost:8070/api/health`
