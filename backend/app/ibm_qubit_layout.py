"""IBM-style grid coordinates for device topology (Qiskit gate_map presets, index-ordered)."""

from __future__ import annotations

import ast
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _preset_maps_by_num_qubits() -> dict[int, list[list[int]]]:
    """Parse Qiskit's visualization/gate_map.py for ``qubit_coordinates_map`` literals."""
    try:
        import qiskit.visualization.gate_map as gm

        path = Path(gm.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        out: dict[int, list[list[int]]] = {}
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name != "plot_gate_map":
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                for target in stmt.targets:
                    if not isinstance(target, ast.Subscript):
                        continue
                    if not isinstance(target.value, ast.Name) or target.value.id != "qubit_coordinates_map":
                        continue
                    sl = target.slice
                    key: int | None = None
                    if isinstance(sl, ast.Constant) and isinstance(sl.value, int):
                        key = sl.value
                    if key is None:
                        continue
                    try:
                        rendered = ast.unparse(stmt.value)
                        val = ast.literal_eval(rendered)
                    except (SyntaxError, ValueError, TypeError):
                        continue
                    if isinstance(val, list):
                        out[key] = val
            break
        return out
    except Exception:
        return {}


def ibm_configuration_coords_to_xy(pairs: list) -> list[tuple[float, float]] | None:
    """
    Map IBM Runtime ``configuration.coords`` to planar ``(x, y)``.

    For Heron/Fez, each pair is ``[col, row]`` in lattice units (first row is
    ``[1, 1]`` … ``[16, 1]``); we use ``(x, y) = (col, row)``.
    """
    out: list[tuple[float, float]] = []
    for p in pairs:
        if p is None or len(p) < 2:
            return None
        out.append((float(p[0]), float(p[1])))
    return out


@lru_cache(maxsize=1)
def load_heron2_fez_official_qubit_grid() -> list[tuple[float, float]] | None:
    """
    Vendored ``coords`` from IBM Fez (Heron revision 2, 156 qubits): same order as qubit index.

    Source: ``qiskit_ibm_runtime`` ``conf_fez.json`` (heavy-hex brick, 16 columns wide).
    """
    path = Path(__file__).resolve().parent / "data" / "heron2_fez_official_coords.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or len(raw) != 156:
            return None
        return ibm_configuration_coords_to_xy(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def coords_from_backend_configuration(backend: object) -> list[tuple[float, float]] | None:
    """
    IBM Runtime ``coords``: lattice pairs ``[col, row]`` (see Fez/Heron conf), mapped to ``(x,y)=(col,row)``.

    Qiskit's ``qubit_coordinates_map`` presets use ``[row, col]`` instead; those are handled in
    ``grid_positions_for_topology``.
    """
    try:
        cfg = backend.configuration()
        n = cfg.n_qubits
        raw = getattr(cfg, "coords", None)
        if raw is None and hasattr(cfg, "to_dict"):
            raw = cfg.to_dict().get("coords")
        if not raw or len(raw) != n:
            return None
        return ibm_configuration_coords_to_xy(list(raw))
    except Exception:
        return None


def grid_positions_for_topology(backend_name: str, n_qubits: int) -> list[tuple[float, float]] | None:
    """
    Per-qubit planar (x, y) from Qiskit ``qubit_coordinates_map``: ``x = col``, ``y = row``.

    Returns ``None`` if the backend name does not look IBM-hosted or no preset matches ``n_qubits``.
    """
    name_l = backend_name.lower()
    if "ibm" not in name_l and "fake" not in name_l:
        return None
    presets = _preset_maps_by_num_qubits()
    coords = presets.get(n_qubits)
    if not coords or len(coords) != n_qubits:
        return None
    return [(float(c[1]), float(c[0])) for c in coords]
