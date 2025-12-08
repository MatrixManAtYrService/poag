"""CLI entry point for poag."""

import asyncio
import os
import sys
import typer
from rich.console import Console
from rich.table import Table
from pathlib import Path
from typing import Optional

from poag_sf.graph import build_agent_graph
from poag_sf.metadata import parse_flake_dependencies, parse_flake_structure
from poag_sf.config import Home
from poag_sf.logging import setup_logging, stderr
from poag_sf.checkpoints import CheckpointManager

app = typer.Typer(help="POAG - Product Owner Agent Graph for development planning")


@app.command()
def plan(
    request: Optional[str] = typer.Argument(None, help="Development request"),
    project_root: Optional[Path] = typer.Option(
        None,
        "--root",
        "-r",
        help="Path to project root (flake directory)",
    ),
):
    """Generate a development plan for a request."""

    # Set up XDG directories and logging
    home = Home()
    setup_logging(home.get_log_file(), home.get_serena_log_dir())

    # Suppress Serena's verbose logging by setting log level
    os.environ["SERENA_LOG_LEVEL"] = "WARNING"

    # Auto-detect project root
    if project_root is None:
        cwd = Path.cwd()
        # If we're in poag directory, use parent
        if cwd.name == "poag":
            project_root = cwd.parent
            stderr.print(f"[dim]Detected poag directory, using parent: {project_root}[/dim]")
        else:
            project_root = cwd

    project_root = project_root.resolve()

    # Read from stdin if no request provided
    if request is None:
        if not sys.stdin.isatty():
            request = sys.stdin.read().strip()
        else:
            stderr.print("[red]Error: No request provided[/red]")
            stderr.print("Usage: echo 'request' | poag plan")
            stderr.print("   or: poag plan 'request'")
            raise typer.Exit(1)

    if not request:
        stderr.print("[red]Error: Empty request[/red]")
        raise typer.Exit(1)

    stderr.print(f"[dim]Project root: {project_root}[/dim]")
    stderr.print("🔍 Analyzing request...")

    try:
        # Parse flake structure
        stderr.print("📊 Parsing flake dependencies...")
        subflakes, dependency_graph = parse_flake_structure(project_root)
        stderr.print(f"[dim]Found {len(subflakes)} subflakes: {', '.join(subflakes.keys())}[/dim]")

        # Build agent graph
        stderr.print("🏗️  Building agent graph...")
        graph = build_agent_graph(subflakes, dependency_graph, project_root, home)

        # Invoke graph (using async API since we have async nodes)
        stderr.print("🚀 Starting agent orchestration...")
        result = asyncio.run(
            graph.ainvoke(
                {
                    "user_request": request,
                    "relevant_subflakes": [],
                    "subflake_instructions": {},
                    "subflakes_queried": [],
                    "subflake_plans": {},
                    "consolidated_plan": None,
                },
                config={"configurable": {"thread_id": "default"}},
            )
        )

        # Output final plan to stdout
        if result.get("consolidated_plan"):
            print(result["consolidated_plan"])
        else:
            stderr.print("[red]Error: No plan generated[/red]")
            raise typer.Exit(1)

    except Exception as e:
        stderr.print(f"[red]Error: {e}[/red]")
        import traceback
        stderr.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command()
def clear(
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Clear specific agent (default: all)"),
    project_root: Optional[Path] = typer.Option(
        None,
        "--root",
        "-r",
        help="Path to project root (flake directory)",
    ),
):
    """Clear agent initialization state and contracts to force re-initialization on next run."""
    import shutil

    home = Home()
    checkpoint_mgr = CheckpointManager(home)

    # Auto-detect project root
    if project_root is None:
        cwd = Path.cwd()
        if cwd.name == "poag":
            project_root = cwd.parent
        else:
            project_root = cwd

    project_root = project_root.resolve()

    # Get list of subflakes to clear contracts for
    from poag_sf.metadata import parse_flake_dependencies
    try:
        subflakes = parse_flake_dependencies(project_root)
    except Exception as e:
        stderr.print(f"[yellow]Warning: Could not parse flakes: {e}[/yellow]")
        subflakes = {}

    if agent:
        # Clear specific agent
        key = f"{project_root}:{agent}"
        metadata = checkpoint_mgr._load_metadata()

        if key in metadata:
            del metadata[key]
            checkpoint_mgr._save_metadata(metadata)
            stderr.print(f"[green]✓ Cleared initialization state for {agent}[/green]")

            # Delete the checkpoint database
            checkpoint_path = checkpoint_mgr.get_checkpoint_path(agent)
            checkpoint_file = Path(checkpoint_path)
            if checkpoint_file.exists():
                checkpoint_file.unlink()
                stderr.print(f"[green]✓ Deleted checkpoint database[/green]")

            # Delete .poag directory for this agent
            if agent in subflakes:
                poag_dir = project_root / subflakes[agent].path / ".poag"
                if poag_dir.exists():
                    shutil.rmtree(poag_dir)
                    stderr.print(f"[green]✓ Deleted {poag_dir.relative_to(project_root)}[/green]")
        else:
            stderr.print(f"[yellow]Agent {agent} was not initialized for this project[/yellow]")
    else:
        # Clear all agents for this project
        metadata = checkpoint_mgr._load_metadata()
        prefix = f"{project_root}:"
        keys_to_delete = [k for k in metadata.keys() if k.startswith(prefix)]

        if keys_to_delete:
            agent_names = []
            for key in keys_to_delete:
                agent_name = key.split(":")[-1]
                agent_names.append(agent_name)
                del metadata[key]

                # Delete checkpoint database
                checkpoint_path = checkpoint_mgr.get_checkpoint_path(agent_name)
                checkpoint_file = Path(checkpoint_path)
                if checkpoint_file.exists():
                    checkpoint_file.unlink()

                # Delete .poag directory for this agent
                if agent_name in subflakes:
                    poag_dir = project_root / subflakes[agent_name].path / ".poag"
                    if poag_dir.exists():
                        shutil.rmtree(poag_dir)
                        stderr.print(f"[green]✓ Deleted {poag_dir.relative_to(project_root)}[/green]")

            checkpoint_mgr._save_metadata(metadata)
            stderr.print(f"[green]✓ Cleared initialization state for {len(keys_to_delete)} agent(s): {', '.join(agent_names)}[/green]")
        else:
            stderr.print(f"[yellow]No initialized agents found for this project[/yellow]")


@app.command()
def ls(
    project_root: Optional[Path] = typer.Option(
        None,
        "--root",
        "-r",
        help="Path to project root (flake directory)",
    ),
    neighbors: bool = typer.Option(
        False,
        "--neighbors",
        "-n",
        help="Show only current flake and its neighbors (dependencies + dependents)",
    ),
):
    """List subflakes found in the current repository."""
    # Auto-detect project root
    if project_root is None:
        cwd = Path.cwd()
        if cwd.name == "poag":
            project_root = cwd.parent
        else:
            project_root = cwd

    project_root = project_root.resolve()

    # Detect current flake if --neighbors is used
    current_flake = None
    if neighbors:
        cwd = Path.cwd().resolve()
        # Check if we're in a subflake directory
        if cwd == project_root:
            current_flake = "root"
        else:
            # Check if cwd is a subflake
            rel_path = cwd.relative_to(project_root) if cwd.is_relative_to(project_root) else None
            if rel_path and (cwd / "flake.nix").exists():
                current_flake = cwd.name

    try:
        # Parse flake structure with graph
        from poag_sf.graph_builder import find_all_dependents, get_direct_dependencies
        subflakes, graph = parse_flake_structure(project_root)

        if not subflakes:
            stderr.print(f"[yellow]No subflakes found in {project_root}[/yellow]")
            return

        # Filter to neighbors if requested
        if neighbors:
            if not current_flake:
                stderr.print("[red]Error: Could not detect current flake. Run from a flake directory.[/red]")
                raise typer.Exit(1)

            if current_flake not in subflakes:
                stderr.print(f"[red]Error: Current flake '{current_flake}' not found in project[/red]")
                raise typer.Exit(1)

            # Find dependencies and dependents
            dependencies = get_direct_dependencies(graph, current_flake)
            dependents = find_all_dependents(graph, current_flake)
            neighbor_names = {current_flake} | dependencies | dependents

            # Filter subflakes to just neighbors
            subflakes = {name: info for name, info in subflakes.items() if name in neighbor_names}

            stderr.print(f"[dim]Showing {current_flake} and its neighbors[/dim]\n")

        # Create a rich table
        title = f"Neighbors of {current_flake}" if neighbors else f"Subflakes in {project_root}"
        table = Table(title=title)
        table.add_column("Name", style="cyan")
        table.add_column("Path", style="dim")
        table.add_column("Language", style="green")
        table.add_column("Dependencies", style="yellow")

        # Sort by path so root (.) appears first
        for name, info in sorted(subflakes.items(), key=lambda x: str(x[1].path)):
            deps = ", ".join(info.dependencies) if info.dependencies else "[dim]none[/dim]"
            # Mark root flake with special styling - use the actual name (project dir name)
            display_name = f"{info.name} [dim](root)[/dim]" if str(info.path) == "." else info.name
            # Highlight current flake if in neighbors mode
            if neighbors and name == current_flake:
                display_name = f"[bold]{display_name} ← current[/bold]"
            table.add_row(display_name, str(info.path), info.language or "[dim]unknown[/dim]", deps)

        stderr.print(table)

        # Show initialization status
        home = Home()
        checkpoint_mgr = CheckpointManager(home)
        metadata = checkpoint_mgr._load_metadata()

        initialized = []
        not_initialized = []

        for name in sorted(subflakes.keys()):
            key = f"{project_root}:{name}"
            if key in metadata:
                initialized.append(name)
            else:
                not_initialized.append(name)

        if initialized:
            stderr.print(f"\n[green]Initialized:[/green] {', '.join(initialized)}")
        if not_initialized:
            stderr.print(f"[dim]Not initialized:[/dim] {', '.join(not_initialized)}")

    except Exception as e:
        stderr.print(f"[red]Error parsing flake metadata: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def describe(
    flake_name: str = typer.Argument(..., help="Name of the flake to describe"),
    project_root: Optional[Path] = typer.Option(
        None,
        "--root",
        "-r",
        help="Path to project root (flake directory)",
    ),
):
    """Describe a flake's structure, contracts, and neighbors (outputs JSON to stdout)."""
    import json
    from poag_sf.contracts import ContractManager
    from poag_sf.graph_builder import find_all_dependents, get_direct_dependencies

    # Auto-detect project root
    if project_root is None:
        cwd = Path.cwd()
        if cwd.name == "poag":
            project_root = cwd.parent
        else:
            project_root = cwd

    project_root = project_root.resolve()

    try:
        # Parse flake structure with graph
        subflakes, graph = parse_flake_structure(project_root)

        if flake_name not in subflakes:
            stderr.print(f"[red]Error: Flake '{flake_name}' not found in project[/red]")
            stderr.print(f"[dim]Available flakes: {', '.join(subflakes.keys())}[/dim]")
            raise typer.Exit(1)

        info = subflakes[flake_name]
        flake_path = project_root / info.path

        # Read README if it exists
        readme_content = None
        readme_path = flake_path / "README.md"
        if readme_path.exists():
            readme_content = readme_path.read_text()

        # Read flake.nix if it exists
        flake_nix_content = None
        flake_nix_path = flake_path / "flake.nix"
        if flake_nix_path.exists():
            flake_nix_content = flake_nix_path.read_text()

        # Find neighbors
        dependencies = sorted(get_direct_dependencies(graph, flake_name))
        dependents = sorted(find_all_dependents(graph, flake_name))

        # Build neighbor info (name and description only, not full details)
        neighbors_info = {}
        for neighbor_name in dependencies + dependents:
            if neighbor_name in subflakes:
                neighbor_info = subflakes[neighbor_name]
                neighbors_info[neighbor_name] = {
                    "description": neighbor_info.description,
                    "language": neighbor_info.language,
                    "relationship": []
                }
                if neighbor_name in dependencies:
                    neighbors_info[neighbor_name]["relationship"].append("dependency")
                if neighbor_name in dependents:
                    neighbors_info[neighbor_name]["relationship"].append("dependent")

        # Read contracts
        contract_mgr = ContractManager(flake_path)
        all_contracts = contract_mgr.get_all_contracts()

        # Build output JSON
        output = {
            "name": info.name,
            "path": str(info.path),
            "language": info.language,
            "description": info.description,
            "readme": readme_content,
            "flake_nix": flake_nix_content,
            "neighbors": neighbors_info,
            "contracts": {
                "inputs": {},
                "outputs": {}
            }
        }

        # Add contract content
        for dep_name, contract_content in all_contracts["inputs"].items():
            output["contracts"]["inputs"][dep_name] = contract_content

        for dep_name, contract_content in all_contracts["outputs"].items():
            output["contracts"]["outputs"][dep_name] = contract_content

        # Output JSON to stdout
        print(json.dumps(output, indent=2))

    except Exception as e:
        stderr.print(f"[red]Error: {e}[/red]")
        import traceback
        stderr.print(traceback.format_exc())
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
