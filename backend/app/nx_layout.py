"""Fallback graph layouts when no chip lattice coordinates are available."""

from __future__ import annotations

import math

import networkx as nx


def symmetric_layout_coordinates(
    n_qubits: int,
    coupling_edges: list[tuple[int, int]],
) -> list[tuple[float, float]] | None:
    """
    Spread nodes using Fruchterman–Reingold with strong repulsion (large ``k``).

    Avoids Kamada–Kawai's tendency to collapse the center on dense heavy-hex graphs.
    """
    if n_qubits <= 0:
        return None

    G = nx.Graph()
    G.add_nodes_from(range(n_qubits))
    for a, b in coupling_edges:
        if 0 <= a < n_qubits and 0 <= b < n_qubits and a != b:
            G.add_edge(int(a), int(b))

    if G.number_of_edges() == 0:
        return None

    try:
        n = max(n_qubits, 1)
        k = 22.0 / math.sqrt(n)
        pos = nx.spring_layout(
            G,
            k=k,
            iterations=320,
            seed=42,
            threshold=1e-5,
            scale=3.0,
        )
        return [(float(pos[i][0]), float(pos[i][1])) for i in range(n_qubits)]
    except Exception:
        return None
