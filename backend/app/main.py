"""FastAPI app: static frontend + IBM relay API."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app import ibm_client
from backend.app.models import (
    BackendsRequest,
    BackendsResponse,
    CalibrationRequest,
    CalibrationResponse,
    RunPathRequest,
    RunPathResponse,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_app_version() -> str:
    """Semver from docs/VERSION at repo root (see AGENT.md)."""
    override = os.environ.get("APP_VERSION_FILE", "").strip()
    path = Path(override).expanduser() if override else _repo_root() / "docs" / "VERSION"
    if not path.is_file():
        raise RuntimeError(
            f"Version file not found: {path}. "
            "Add docs/VERSION or set APP_VERSION_FILE to a readable path."
        )
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Version file is empty: {path}")
    return text


_APP_VERSION = read_app_version()
app = FastAPI(title="Quantum Error Dungeon", version=_APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_INDEX = _STATIC_DIR / "index.html"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/version")
def api_version():
    return {"version": _APP_VERSION}


@app.post("/api/backends", response_model=BackendsResponse)
def post_backends(body: BackendsRequest):
    try:
        backends = ibm_client.list_backends(body.api_key, body.instance_crn)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return BackendsResponse(backends=backends)


@app.post("/api/calibration", response_model=CalibrationResponse)
def post_calibration(body: CalibrationRequest):
    try:
        return ibm_client.fetch_calibration(
            body.api_key,
            body.instance_crn,
            body.backend_name,
            use_heron2_official_layout=body.use_heron2_official_layout,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/run-path", response_model=RunPathResponse)
def post_run_path(body: RunPathRequest):
    cal = ibm_client.fetch_calibration(body.api_key, body.instance_crn, body.backend_name)
    edges: set[tuple[int, int]] = set()
    for a, b in cal.coupling_edges:
        edges.add((a, b))
        edges.add((b, a))
    err = ibm_client.validate_path(body.path, edges)
    if err:
        raise HTTPException(status_code=400, detail=err)

    if body.demo_mode:
        strat = body.demo_strategy
        probs_used: list[float] | None = None
        if strat == "perfect":
            bs = ibm_client.demo_bitstring_perfect(body.path)
            note = "Synthetic all-zero outcome (ideal success preview)."
        elif strat == "noisy":
            bs, probs_used = ibm_client.demo_bitstring_noisy(body.path, cal)
            note = (
                "Synthetic bits from classical draws vs calibration "
                "P(meas 1 | prep 0) per physical qubit on the path."
            )
        else:
            bs = ibm_client.demo_bitstring_deterministic(body.path)
            note = "Synthetic bits from SHA-256(path); deterministic, not hardware."

        replay = ibm_client.replay_path_score(bs, body.path, body.starting_lives)
        raw: dict = {"demo_strategy": strat, "note": note}
        if probs_used is not None:
            raw["per_step_p_bit_is_1"] = probs_used
        return RunPathResponse(
            backend_name=body.backend_name,
            path=body.path,
            bitstring=bs,
            measured_bits=replay.measured_bits,
            lives_remaining=replay.lives_remaining,
            lives_lost=replay.lives_lost,
            reached_index=replay.reached_index,
            reached_qubit=replay.reached_qubit,
            success=replay.success,
            job_id=None,
            demo_mode=True,
            demo_strategy=strat,
            raw_details=raw,
        )

    try:
        bs, job_id = ibm_client.run_path_hardware(
            body.api_key, body.instance_crn, body.backend_name, body.path
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    replay = ibm_client.replay_path_score(bs, body.path, body.starting_lives)
    return RunPathResponse(
        backend_name=body.backend_name,
        path=body.path,
        bitstring=bs,
        measured_bits=replay.measured_bits,
        lives_remaining=replay.lives_remaining,
        lives_lost=replay.lives_lost,
        reached_index=replay.reached_index,
        reached_qubit=replay.reached_qubit,
        success=replay.success,
        job_id=job_id,
        demo_mode=False,
        demo_strategy=None,
    )


def _mount_static():
    assets_dir = _STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="assets",
        )


_mount_static()


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Serve React SPA for non-API routes."""
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="Not found")
    if _INDEX.is_file():
        return FileResponse(_INDEX)
    raise HTTPException(
        status_code=503,
        detail="Frontend not built; static/index.html missing",
    )
