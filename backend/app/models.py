"""Pydantic request/response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IBMContext(BaseModel):
    """Credentials passed per request; never persisted."""

    api_key: str = Field(..., description="IBM Quantum Platform API key")
    instance_crn: str | None = Field(
        default=None,
        description="Optional instance CRN (recommended)",
    )


class BackendsRequest(IBMContext):
    pass


class BackendInfo(BaseModel):
    name: str
    num_qubits: int | None = None
    operational: bool | None = None
    pending_jobs: int | None = None
    status_msg: str | None = None


class BackendsResponse(BaseModel):
    backends: list[BackendInfo]


class CalibrationRequest(IBMContext):
    backend_name: str
    use_heron2_official_layout: bool = Field(
        default=False,
        description=(
            "When the backend is IBM Heron revision 2 with 156 qubits, replace lattice positions "
            "with vendored IBM Fez reference coordinates (16-wide heavy-hex brick)."
        ),
    )


class QubitCalibration(BaseModel):
    index: int
    prob_meas1_prep0: float | None = None
    readout_error: float | None = None
    t1_us: float | None = None
    t2_us: float | None = None
    operational: bool | None = None


class CouplerCalibration(BaseModel):
    q0: int
    q1: int
    gate_error: float | None = None
    gate_name: str | None = None


class CalibrationResponse(BaseModel):
    backend_name: str
    last_update_iso: str | None = None
    qubits: list[QubitCalibration]
    couplers: list[CouplerCalibration]
    coupling_edges: list[tuple[int, int]]
    median_readout_error: float | None = None
    median_two_qubit_error: float | None = None
    qubit_grid: list[tuple[float, float]] | None = Field(
        default=None,
        description="Heavy-hex lattice (x,y) per qubit: Qiskit gate_map preset when available, else IBM backend.configuration().coords.",
    )
    nx_layout: list[tuple[float, float]] | None = Field(
        default=None,
        description="Symmetric uniform-distance embedding (x,y) per qubit from NetworkX Kamada-Kawai (fallback).",
    )
    processor_family: str | None = Field(
        default=None,
        description="IBM configuration.processor_type.family when exposed by the backend.",
    )
    processor_revision: str | None = Field(
        default=None,
        description="IBM configuration.processor_type.revision when exposed (stringified).",
    )
    heron2_official_layout_available: bool = Field(
        default=False,
        description="True when vendored Fez coords apply (Heron rev 2, 156 qubits).",
    )
    use_heron2_official_layout_applied: bool = Field(
        default=False,
        description="True when this response used the vendored Heron2/Fez lattice for qubit_grid.",
    )


DemoStrategy = Literal["deterministic", "perfect", "noisy"]


class RunPathRequest(IBMContext):
    backend_name: str
    path: list[int] = Field(..., min_length=1, description="Physical qubit indices in visit order")
    starting_lives: int = Field(default=3, ge=1, le=100)
    demo_mode: bool = Field(
        default=False,
        description="If true, return synthetic bits (no IBM job). For local UI only.",
    )
    demo_strategy: DemoStrategy = Field(
        default="deterministic",
        description=(
            "When demo_mode: deterministic = hash-derived bits; perfect = all zeros (always succeed); "
            "noisy = independent classical draws using per-qubit calibration (prep→meas error)."
        ),
    )


class RunPathResponse(BaseModel):
    backend_name: str
    path: list[int]
    bitstring: str | None = Field(
        default=None,
        description="Single-shot outcome, MSB..LSB matching virtual qubit order (path order)",
    )
    measured_bits: list[int] | None = None
    lives_remaining: int
    lives_lost: int
    reached_index: int
    reached_qubit: int | None = None
    success: bool
    job_id: str | None = None
    demo_mode: bool = False
    demo_strategy: DemoStrategy | None = Field(
        default=None,
        description="Which synthetic strategy ran (only when demo_mode).",
    )
    error: str | None = None
    raw_details: dict[str, Any] | None = None
