"""Build and analyze the dependency graph from Nix flake metadata.

This module constructs a NetworkX DiGraph representing the dependency relationships
between flakes and their inputs/outputs. This enables proper dependency analysis
including finding all dependents (even the root flake) and determining initialization order.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple
import networkx as nx


# Type aliases for clarity
FlakeOutputNode = Tuple[str, str]  # (flake_name, output_name)
FlakeInputNode = Tuple[str, str]   # (flake_name, input_name)


def build_dependency_graph(project_root: Path, known_subflakes: List[str]) -> nx.DiGraph:
    """Build a directed graph of flake dependencies.

    Nodes represent flake inputs/outputs as tuples: (flake_name, input_or_output_name)
    Edges represent dependency relationships: (provider_output) → (consumer_input)

    Args:
        project_root: Path to the project root containing flake.nix
        known_subflakes: List of subflake names to include (e.g., ["hello-rs", "hello-py"])

    Returns:
        NetworkX DiGraph with nodes as (flake_name, input/output_name) tuples
    """
    G = nx.DiGraph()

    # First, add all subflake nodes and their internal dependencies
    for subflake_name in known_subflakes:
        subflake_path = project_root / subflake_name
        if not (subflake_path / "flake.nix").exists():
            continue

        _add_flake_to_graph(G, subflake_path, subflake_name, known_subflakes)

    # Then, add the root flake and its dependencies
    _add_flake_to_graph(G, project_root, "root", known_subflakes)

    return G


def _add_flake_to_graph(
    G: nx.DiGraph,
    flake_path: Path,
    flake_name: str,
    known_subflakes: List[str]
) -> None:
    """Add a flake's inputs/outputs to the graph.

    Args:
        G: The graph to modify
        flake_path: Path to the flake directory
        flake_name: Name of this flake (e.g., "hello-py" or "root")
        known_subflakes: List of known subflake names to track
    """
    # Get flake metadata
    metadata = _get_flake_metadata(flake_path)

    # Extract inputs from the locks
    locks = metadata.get("locks", {}).get("nodes", {})
    root_node = locks.get("root", {})
    inputs = root_node.get("inputs", {})

    # For each input that's a known subflake, create an edge
    for input_name, input_node_name in inputs.items():
        if input_name not in known_subflakes:
            continue

        # Create edge: (provider_flake, "default") → (consumer_flake, input_name)
        # We assume "default" output for now; could be enhanced to track specific outputs
        provider_output = (input_name, "default")
        consumer_input = (flake_name, input_name)

        G.add_edge(provider_output, consumer_input)

        # Also add nodes explicitly for clarity
        G.add_node(provider_output, type="output", flake=input_name)
        G.add_node(consumer_input, type="input", flake=flake_name)


def _get_flake_metadata(path: Path) -> dict:
    """Get flake metadata JSON for a given path."""
    result = subprocess.run(
        ["nix", "flake", "metadata", "--json"],
        capture_output=True,
        text=True,
        cwd=str(path),
        check=True,
    )
    return json.loads(result.stdout)


def find_all_dependents(graph: nx.DiGraph, flake_name: str) -> Set[str]:
    """Find all flakes that depend on the given flake (including root!).

    Args:
        graph: The dependency graph
        flake_name: Name of the flake to find dependents for

    Returns:
        Set of flake names that depend on this flake
    """
    dependents = set()

    # Find all output nodes for this flake
    flake_outputs = [n for n in graph.nodes()
                     if isinstance(n, tuple) and n[0] == flake_name]

    # For each output, find what consumes it
    for output_node in flake_outputs:
        for successor in graph.successors(output_node):
            if isinstance(successor, tuple):
                consumer_flake = successor[0]
                if consumer_flake != flake_name:
                    dependents.add(consumer_flake)

    return dependents


def get_initialization_order(graph: nx.DiGraph) -> List[str]:
    """Get the order in which flakes should be initialized (leaves first).

    Uses topological sort to ensure dependencies are initialized before dependents.

    Args:
        graph: The dependency graph

    Returns:
        List of flake names in initialization order
    """
    # Collapse to flake-level graph (remove input/output distinction)
    flake_graph = nx.DiGraph()

    for edge in graph.edges():
        src_node, dst_node = edge
        if isinstance(src_node, tuple) and isinstance(dst_node, tuple):
            src_flake, dst_flake = src_node[0], dst_node[0]
            if src_flake != dst_flake:
                flake_graph.add_edge(src_flake, dst_flake)

    # Topological sort (dependencies before dependents)
    try:
        return list(nx.topological_sort(flake_graph))
    except nx.NetworkXError:
        # Cycle detected - return all nodes in arbitrary order
        return list(flake_graph.nodes())


def find_impacted_flakes(graph: nx.DiGraph, changed_flake: str) -> Set[str]:
    """Find all flakes that might be impacted by changes to the given flake.

    This includes all transitive dependents (things that depend on this flake,
    and things that depend on those, etc.).

    Args:
        graph: The dependency graph
        changed_flake: Name of the flake that changed

    Returns:
        Set of flake names that might be impacted
    """
    impacted = set()

    # Find all output nodes for this flake
    flake_outputs = [n for n in graph.nodes()
                     if isinstance(n, tuple) and n[0] == changed_flake]

    # Find all descendants (transitive dependents)
    for output in flake_outputs:
        descendants = nx.descendants(graph, output)
        for node in descendants:
            if isinstance(node, tuple):
                impacted.add(node[0])

    return impacted


def get_direct_dependencies(graph: nx.DiGraph, flake_name: str) -> Set[str]:
    """Get the direct dependencies of a flake (things it depends on).

    Args:
        graph: The dependency graph
        flake_name: Name of the flake

    Returns:
        Set of flake names that this flake directly depends on
    """
    dependencies = set()

    # Find all input nodes for this flake
    flake_inputs = [n for n in graph.nodes()
                    if isinstance(n, tuple) and n[0] == flake_name]

    # For each input, find what provides it
    for input_node in flake_inputs:
        for predecessor in graph.predecessors(input_node):
            if isinstance(predecessor, tuple):
                provider_flake = predecessor[0]
                if provider_flake != flake_name:
                    dependencies.add(provider_flake)

    return dependencies


def export_to_mermaid(graph: nx.DiGraph) -> str:
    """Export the dependency graph to Mermaid diagram format.

    Args:
        graph: The dependency graph

    Returns:
        Mermaid diagram as a string
    """
    # Collapse to flake-level for visualization
    flake_edges = set()
    for src, dst in graph.edges():
        if isinstance(src, tuple) and isinstance(dst, tuple):
            if src[0] != dst[0]:
                flake_edges.add((src[0], dst[0]))

    lines = ["graph TD"]
    for src, dst in flake_edges:
        lines.append(f"    {src} --> {dst}")

    return "\n".join(lines)
