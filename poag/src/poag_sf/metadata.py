"""Parse Nix flake metadata to discover subflake structure."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import networkx as nx

from poag_sf.graph_builder import build_dependency_graph, get_direct_dependencies


@dataclass
class SubflakeInfo:
    """Information about a subflake."""

    name: str
    path: Path  # Relative to project root
    dependencies: List[str]  # Names of other subflakes this depends on
    language: str  # "rust", "python", "wasm", "web", etc.
    description: str | None  # Human-readable description from flake metadata


def parse_flake_dependencies(project_root: Path) -> Dict[str, SubflakeInfo]:
    """Parse Nix flake metadata to build agent routing table.

    Args:
        project_root: Path to the project root containing flake.nix

    Returns:
        Dict mapping subflake name to SubflakeInfo (includes root flake)
    """
    # Get metadata from root
    root_metadata = _get_flake_metadata(project_root)

    # Known subflake directories (those with agents)
    # We'll detect these by checking if they have flake.nix files
    potential_subflakes = ["hello-rs", "hello-py", "hello-wasm", "hello-web"]

    subflakes = {}

    for name in potential_subflakes:
        subflake_path = project_root / name
        if not (subflake_path / "flake.nix").exists():
            continue

        # Get metadata for this subflake
        metadata = _get_flake_metadata(subflake_path)

        # Extract dependencies from the locks
        dependencies = _extract_dependencies(metadata, potential_subflakes)

        # Detect language
        language = _detect_language(subflake_path)

        # Extract description from metadata
        description = metadata.get("description")

        subflakes[name] = SubflakeInfo(
            name=name,
            path=subflake_path.relative_to(project_root),
            dependencies=dependencies,
            language=language,
            description=description,
        )

    # Add the root flake itself as a first-class participant
    # Use the project directory name as the root flake name
    root_name = project_root.name
    root_dependencies = _extract_dependencies(root_metadata, potential_subflakes)
    root_language = _detect_language(project_root)
    root_description = root_metadata.get("description")

    subflakes["root"] = SubflakeInfo(
        name=root_name,
        path=Path("."),  # Root is at the project root
        dependencies=root_dependencies,
        language=root_language,
        description=root_description,
    )

    return subflakes


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


def _extract_dependencies(metadata: dict, known_subflakes: List[str]) -> List[str]:
    """Extract subflake dependencies from metadata.

    Args:
        metadata: The flake metadata dict
        known_subflakes: List of subflake names we're tracking

    Returns:
        List of dependency names (filtered to only known subflakes)
    """
    locks = metadata.get("locks", {}).get("nodes", {})
    root_node = locks.get("root", {})
    inputs = root_node.get("inputs", {})

    # Filter to only known subflakes
    dependencies = []
    for input_name in inputs.keys():
        if input_name in known_subflakes:
            dependencies.append(input_name)

    return dependencies


def _detect_language(path: Path) -> str:
    """Detect the primary language of a subflake.

    Args:
        path: Path to the subflake directory

    Returns:
        Language identifier: "rust", "python", "wasm", "web", etc.
    """
    if (path / "Cargo.toml").exists():
        # Check if it's WASM or regular Rust
        if path.name == "hello-wasm":
            return "wasm"
        return "rust"

    if (path / "pyproject.toml").exists():
        return "python"

    if (path / "package.json").exists():
        return "web"

    return "unknown"


def parse_flake_structure(project_root: Path) -> Tuple[Dict[str, SubflakeInfo], nx.DiGraph]:
    """Parse Nix flake metadata and build dependency graph.

    This is the main entry point that combines subflake parsing with graph construction.

    Args:
        project_root: Path to the project root containing flake.nix

    Returns:
        Tuple of:
        - Dict mapping subflake name to SubflakeInfo
        - NetworkX DiGraph representing dependency relationships
    """
    # Parse subflakes using existing logic
    subflakes = parse_flake_dependencies(project_root)

    # Build dependency graph (includes root flake!)
    known_subflakes = list(subflakes.keys())
    graph = build_dependency_graph(project_root, known_subflakes)

    # Update SubflakeInfo.dependencies using graph queries for consistency
    for name, info in subflakes.items():
        info.dependencies = sorted(get_direct_dependencies(graph, name))

    return subflakes, graph
