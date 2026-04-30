# Docker

## Python dependencies and pip

Install **only inside the image**. Do not run `pip install` on your machine for this project.

- Dependencies are declared in [backend/requirements.txt](../backend/requirements.txt).
- During `docker build`, the Dockerfile runs `python -m pip install` to populate the runtime image.

## Run

```bash
docker compose up --build
```

The API listens on port 8000. Open `http://localhost:8000` for the UI (when static assets are present) or `http://localhost:8000/api/health` to verify the server.

## Tests (optional)

If a test image is added, it should run `python -m pip install` inside that image as well—never assume a host virtualenv.
