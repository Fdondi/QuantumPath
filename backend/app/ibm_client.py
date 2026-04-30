"""IBM Quantum Platform helpers (calibration, topology, single sampler run)."""

from __future__ import annotations

import hashlib
import random
import statistics
from dataclasses import dataclass
from typing import Any

from qiskit import QuantumCircuit, ClassicalRegister, QuantumRegister
from qiskit.transpiler import CouplingMap
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

from backend.app.ibm_qubit_layout import (
    coords_from_backend_configuration,
    grid_positions_for_topology,
    load_heron2_fez_official_qubit_grid,
)
from backend.app.nx_layout import symmetric_layout_coordinates
from backend.app.models import (
    BackendInfo,
    CalibrationResponse,
    CouplerCalibration,
    QubitCalibration,
)


def make_service(api_key: str, instance_crn: str | None) -> QiskitRuntimeService:
    kwargs: dict[str, Any] = {"channel": "ibm_quantum_platform", "token": api_key}
    if instance_crn:
        kwargs["instance"] = instance_crn
    return QiskitRuntimeService(**kwargs)


def list_backends(api_key: str, instance_crn: str | None) -> list[BackendInfo]:
    service = make_service(api_key, instance_crn)
    out: list[BackendInfo] = []
    for b in service.backends():
        try:
            cfg = b.configuration()
            nq = cfg.n_qubits
        except Exception:
            nq = None
        try:
            st = b.status()
            op = st.operational
            pj = st.pending_jobs
            msg = st.status_msg
        except Exception:
            op, pj, msg = None, None, None
        out.append(
            BackendInfo(
                name=b.name,
                num_qubits=nq,
                operational=op,
                pending_jobs=pj,
                status_msg=msg,
            )
        )
    return sorted(out, key=lambda x: x.name)


def _prop_val(props: Any, qubit: int, name: str) -> float | None:
    try:
        qp = props.qubit_property(qubit, name=name)
        if qp is None:
            return None
        v = qp[0]
        return float(v) if v is not None else None
    except Exception:
        return None


def _median_nonempty(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _processor_type_fields(backend: object) -> tuple[str | None, str | None]:
    """Return ``(family, revision)`` string pair from ``configuration().processor_type`` when present."""
    try:
        cfg = backend.configuration()
        raw = getattr(cfg, "processor_type", None)
        if raw is None and hasattr(cfg, "to_dict"):
            raw = cfg.to_dict().get("processor_type")
        if raw is None:
            return None, None
        if isinstance(raw, dict):
            fam = raw.get("family")
            rev = raw.get("revision")
        else:
            fam = getattr(raw, "family", None)
            rev = getattr(raw, "revision", None)
        fam_s = str(fam) if fam is not None else None
        rev_s = str(rev) if rev is not None else None
        return fam_s, rev_s
    except Exception:
        return None, None


def fetch_calibration(
    api_key: str,
    instance_crn: str | None,
    backend_name: str,
    *,
    use_heron2_official_layout: bool = False,
) -> CalibrationResponse:
    service = make_service(api_key, instance_crn)
    backend = service.backend(backend_name)
    props = backend.properties()
    last_update_iso = None
    if props and getattr(props, "last_update_date", None):
        try:
            last_update_iso = props.last_update_date.isoformat()
        except Exception:
            last_update_iso = str(props.last_update_date)

    n_qubits = backend.configuration().n_qubits
    qubits: list[QubitCalibration] = []
    p10_list: list[float] = []
    readout_list: list[float] = []

    faulty: set[int] = set()
    try:
        faulty = set(props.faulty_qubits()) if props else set()
    except Exception:
        faulty = set()

    for i in range(n_qubits):
        p10 = _prop_val(props, i, "prob_meas1_prep0") if props else None
        ro = _prop_val(props, i, "readout_error") if props else None
        t1 = _prop_val(props, i, "T1") if props else None
        t2 = _prop_val(props, i, "T2") if props else None
        if t1 is not None:
            t1 *= 1e6
        if t2 is not None:
            t2 *= 1e6
        if p10 is not None:
            p10_list.append(p10)
        if ro is not None:
            readout_list.append(ro)
        op = i not in faulty if faulty else None
        qubits.append(
            QubitCalibration(
                index=i,
                prob_meas1_prep0=p10,
                readout_error=ro,
                t1_us=t1,
                t2_us=t2,
                operational=op,
            )
        )

    coupling_edges: list[tuple[int, int]] = []
    couplers: list[CouplerCalibration] = []
    cz_errors: list[float] = []
    raw_cm = backend.configuration().coupling_map
    if raw_cm is not None:
        try:
            if hasattr(raw_cm, "get_edges"):
                edge_iter = raw_cm.get_edges()
            else:
                edge_iter = CouplingMap(raw_cm).get_edges()
            for edge in edge_iter:
                coupling_edges.append((int(edge[0]), int(edge[1])))
        except Exception:
            for pair in raw_cm:
                coupling_edges.append((int(pair[0]), int(pair[1])))

    target = getattr(backend, "target", None)
    for q0, q1 in coupling_edges:
        ge = None
        gname = None
        if target is not None:
            for g in ("cz", "ecr", "cx"):
                try:
                    inst = target[g].get((q0, q1)) or target[g].get((q1, q0))
                except Exception:
                    inst = None
                if inst is not None:
                    gname = g
                    ge = getattr(inst, "error", None)
                    if ge is not None:
                        cz_errors.append(float(ge))
                    break
        couplers.append(CouplerCalibration(q0=q0, q1=q1, gate_error=ge, gate_name=gname))

    proc_family, proc_revision = _processor_type_fields(backend)
    official_heron2 = load_heron2_fez_official_qubit_grid()
    heron2_match = (
        proc_family == "Heron"
        and proc_revision == "2"
        and n_qubits == 156
    )
    heron2_official_layout_available = bool(official_heron2 and heron2_match)

    qubit_grid = grid_positions_for_topology(backend_name, n_qubits)
    if qubit_grid is None:
        qubit_grid = coords_from_backend_configuration(backend)
    nx_pos = None if qubit_grid is not None else symmetric_layout_coordinates(n_qubits, coupling_edges)

    use_heron2_official_layout_applied = False
    if use_heron2_official_layout and heron2_official_layout_available and official_heron2 is not None:
        qubit_grid = official_heron2
        nx_pos = None
        use_heron2_official_layout_applied = True

    return CalibrationResponse(
        backend_name=backend_name,
        last_update_iso=last_update_iso,
        qubits=qubits,
        couplers=couplers,
        coupling_edges=coupling_edges,
        median_readout_error=_median_nonempty(readout_list),
        median_two_qubit_error=_median_nonempty(cz_errors),
        qubit_grid=qubit_grid,
        nx_layout=nx_pos,
        processor_family=proc_family,
        processor_revision=proc_revision,
        heron2_official_layout_available=heron2_official_layout_available,
        use_heron2_official_layout_applied=use_heron2_official_layout_applied,
    )


def validate_path(path: list[int], edges: set[tuple[int, int]]) -> str | None:
    if len(path) != len(set(path)):
        return "Path contains duplicate qubits"
    for a, b in zip(path[:-1], path[1:]):
        if (a, b) not in edges and (b, a) not in edges:
            return f"No coupler between {a} and {b}"
    return None


def demo_bitstring_deterministic(path: list[int]) -> str:
    """Deterministic fake bits from path hash (legacy demo)."""
    h = hashlib.sha256(("demo|" + ",".join(map(str, path))).encode()).digest()
    return "".join(str((h[i // 8] >> (i % 8)) & 1) for i in range(len(path)))


def demo_bitstring_perfect(path: list[int]) -> str:
    """All zeros — replay scoring always succeeds if starting_lives >= 1."""
    return "0" * len(path)


def _meas1_prep0_prob(cal: CalibrationResponse, qubit: int) -> float:
    """Classical proxy for measuring |0⟩ on hardware: P(bit==1)."""
    p = None
    if 0 <= qubit < len(cal.qubits):
        qc = cal.qubits[qubit]
        p = qc.prob_meas1_prep0
        if p is None:
            p = qc.readout_error
    if p is None:
        p = cal.median_readout_error
    if p is None:
        p = 0.05
    return max(0.0, min(1.0, float(p)))


def demo_bitstring_noisy(
    path: list[int],
    cal: CalibrationResponse,
    rng: random.Random | None = None,
) -> tuple[str, list[float]]:
    """Independent classical Bernoulli draws per path step using calibration."""
    rng = rng or random.Random()
    probs = [_meas1_prep0_prob(cal, q) for q in path]
    bits = [1 if rng.random() < pr else 0 for pr in probs]
    return "".join(map(str, bits)), probs


def run_path_hardware(
    api_key: str,
    instance_crn: str | None,
    backend_name: str,
    path: list[int],
) -> tuple[str, str | None]:
    """Submit one SamplerV2 job with shots=1; return (bitstring, job_id)."""
    service = make_service(api_key, instance_crn)
    backend = service.backend(backend_name)
    n = len(path)
    qr = QuantumRegister(n, "q")
    cr = ClassicalRegister(n, "meas")
    qc = QuantumCircuit(qr, cr, name="path_measure")
    qc.measure(qr, cr)

    pm = generate_preset_pass_manager(
        optimization_level=1,
        backend=backend,
        initial_layout=list(path),
    )
    isa = pm.run(qc)

    sampler = Sampler(mode=backend)
    job = sampler.run([isa], shots=1)
    _jid = getattr(job, "job_id", None)
    job_id = _jid() if callable(_jid) else _jid
    result = job.result()
    pub = result[0]
    bitstrings = pub.data.meas.get_bitstrings()
    if not bitstrings:
        raise RuntimeError("Sampler returned no bitstrings")
    return bitstrings[0], job_id


@dataclass
class ScoreReplay:
    measured_bits: list[int]
    lives_remaining: int
    lives_lost: int
    reached_index: int
    reached_qubit: int | None
    success: bool


def replay_path_score(bitstring: str, path: list[int], starting_lives: int) -> ScoreReplay:
    """bitstring: first char is MSB = path[0], last char is LSB = path[-1] for standard bitstring order."""
    if len(bitstring) != len(path):
        raise ValueError("Bitstring length does not match path length")
    bits = [int(ch) for ch in bitstring]
    lives = starting_lives
    lost = 0
    reached_idx = -1
    reached_q = None
    for i, b in enumerate(bits):
        if b == 1:
            lost += 1
            lives -= 1
        reached_idx = i
        reached_q = path[i]
        if lives <= 0:
            return ScoreReplay(
                measured_bits=bits,
                lives_remaining=0,
                lives_lost=lost,
                reached_index=reached_idx,
                reached_qubit=reached_q,
                success=False,
            )
    return ScoreReplay(
        measured_bits=bits,
        lives_remaining=lives,
        lives_lost=lost,
        reached_index=reached_idx,
        reached_qubit=reached_q,
        success=True,
    )
