"""Codebase exploration using Claude Code headless mode.

This replaces custom exploration logic with Claude Code's built-in
exploration capabilities, making it language-agnostic and maintainable.
"""

import asyncio
import json
from typing import TypedDict
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from poag_sf.logging import stderr


class ExplorationState(TypedDict):
    """State for codebase exploration workflow.

    This state gets saved to checkpoint, so subsequent invocations
    can skip exploration and go straight to task execution.

    Two-phase initialization:
    Phase 1: Self-exploration + analyze dependencies (what I need from them)
    Phase 2: Provider analysis (what I provide to dependents)
    """
    # Input
    subflake_name: str
    subflake_path: str
    language: str | None
    dependencies: list[str]  # Names of flakes this one depends on
    dependents: list[str]    # Names of flakes that depend on this one

    # Claude Code session management
    claude_session_id: str | None

    # Contract status
    contracts_current: bool  # Whether .poag/index.json is up to date

    # Phase 1: Self-exploration results
    self_summary: str | None  # What this flake does, how it's organized

    # For tracking progress
    phase1_complete: bool
    phase2_complete: bool


async def check_contracts_node(state: ExplorationState) -> dict:
    """Check if contracts are current or need regeneration.

    This checks .poag/index.json and compares against current git commit.
    """
    from poag_sf.contracts import ContractManager

    stderr.print(f"[dim]      🔍 Checking contract status...[/dim]")

    subflake_path = Path(state["subflake_path"])
    contract_mgr = ContractManager(subflake_path)

    contracts_current = contract_mgr.are_contracts_current()

    if contracts_current:
        stderr.print(f"[dim]      ✓ Contracts are current, skipping exploration[/dim]")
        return {
            "contracts_current": True,
            "phase1_complete": True,
            "phase2_complete": True,
        }
    else:
        stderr.print(f"[dim]      Contracts need generation[/dim]")
        return {
            "contracts_current": False,
            "phase1_complete": False,
            "phase2_complete": False,
        }


async def phase1_explore_node(state: ExplorationState) -> dict:
    """Phase 1: Self-exploration + dependency analysis.

    Uses Claude Code to:
    1. Explore the codebase (README, flake.nix, source files)
    2. For each dependency: analyze how it's used and what we need from it
    3. Write contracts to .poag/contracts/inputs/{dep}.md
    """
    from poag_sf.contracts import ContractManager

    stderr.print(f"[dim]      📚 Phase 1: Self-exploration + dependency analysis...[/dim]")

    subflake_path = Path(state["subflake_path"])
    subflake_name = state["subflake_name"]
    dependencies = state.get("dependencies", [])

    contract_mgr = ContractManager(subflake_path)

    # Build dependency context for the prompt
    dep_context = ""
    if dependencies:
        dep_context = f"\n\nThis flake depends on: {', '.join(dependencies)}"

    # Craft exploration prompt
    prompt = f"""You are exploring the {subflake_name} codebase to understand its role and dependencies.

**Phase 1 Tasks:**

1. **Self-exploration:**
   - Read README.md and flake.nix
   - Explore the codebase structure
   - Understand what this project does, how it's organized, and how to test it

2. **Dependency analysis:**{dep_context}
   - For EACH dependency, analyze how it's used in this codebase
   - Find code examples showing how the dependency is referenced
   - Identify requirements/expectations this flake has of each dependency

**Output format:**

# Self Summary
[2-3 sentences: what this project does, how it's organized, how to test it]

{chr(10).join(f'''
# Dependency: {dep}
## How we use it
[Description with code snippets showing usage]

## What we need from them
[Specific requirements/expectations]
''' for dep in dependencies) if dependencies else ''}

Keep it concise and actionable."""

    # Run Claude Code in headless mode
    try:
        process = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            "--output-format", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(subflake_path)
        )

        stdout, stderr_output = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr_output.decode() if stderr_output else "Unknown error"
            stderr.print(f"[red]      ✗ Phase 1 exploration failed: {error_msg}[/red]")
            return {
                "self_summary": f"Exploration failed: {error_msg}",
                "claude_session_id": None,
                "phase1_complete": False
            }

        # Parse JSON response
        result = json.loads(stdout.decode())
        session_id = result["session_id"]
        exploration_output = result["result"]

        stderr.print(f"[dim]      ✓ Phase 1 complete (session: {session_id[:8]}...)[/dim]")

        # Extract self summary (everything before first "# Dependency:" or all of it)
        parts = exploration_output.split("# Dependency:", 1)
        self_summary = parts[0].replace("# Self Summary", "").strip()

        # Write input contracts for each dependency
        input_contracts_written = []
        for dep in dependencies:
            # Find the section for this dependency
            dep_marker = f"# Dependency: {dep}"
            if dep_marker in exploration_output:
                start_idx = exploration_output.index(dep_marker)
                # Find next dependency or end of string
                next_dep_idx = len(exploration_output)
                for other_dep in dependencies:
                    if other_dep != dep:
                        other_marker = f"# Dependency: {other_dep}"
                        if other_marker in exploration_output[start_idx + len(dep_marker):]:
                            candidate_idx = exploration_output.index(other_marker, start_idx + len(dep_marker))
                            next_dep_idx = min(next_dep_idx, candidate_idx)

                dep_content = exploration_output[start_idx:next_dep_idx].strip()
                contract_mgr.write_input_contract(dep, dep_content)
                input_contracts_written.append(dep)

        # Update index with Phase 1 results (Phase 2 outputs will be added later)
        contract_mgr.update_index_after_generation(
            input_contracts=input_contracts_written,
            output_contracts=[]  # Phase 2 not done yet
        )

        return {
            "claude_session_id": session_id,
            "self_summary": self_summary,
            "phase1_complete": True
        }

    except FileNotFoundError:
        stderr.print("[red]      ✗ Claude Code not found - is it installed?[/red]")
        return {
            "self_summary": "Claude Code not found",
            "claude_session_id": None,
            "phase1_complete": False
        }
    except json.JSONDecodeError as e:
        stderr.print(f"[red]      ✗ Failed to parse response: {e}[/red]")
        return {
            "self_summary": f"Parse error: {e}",
            "claude_session_id": None,
            "phase1_complete": False
        }
    except Exception as e:
        stderr.print(f"[red]      ✗ Unexpected error: {e}[/red]")
        return {
            "self_summary": f"Error: {e}",
            "claude_session_id": None,
            "phase1_complete": False
        }


def build_exploration_graph(checkpoint_path: str) -> StateGraph:
    """Build the codebase exploration graph.

    Multi-phase initialization:
    1. Check if contracts are current (compare git commit)
    2. If current: skip to end
    3. If stale: Run Phase 1 (self-exploration + dependency analysis)
    4. Phase 2 happens at root level (coordinating between agents)

    Args:
        checkpoint_path: Path to SQLite checkpoint database

    Returns:
        Compiled StateGraph ready to invoke
    """
    # Create graph
    graph = StateGraph(ExplorationState)

    # Add nodes
    graph.add_node("check_contracts", check_contracts_node)
    graph.add_node("phase1_explore", phase1_explore_node)

    # Conditional flow based on contract status
    def should_skip_exploration(state: ExplorationState) -> str:
        """Route based on whether contracts are current."""
        if state.get("contracts_current", False):
            return END
        else:
            return "phase1_explore"

    # Graph structure
    graph.add_edge(START, "check_contracts")
    graph.add_conditional_edges(
        "check_contracts",
        should_skip_exploration,
        {END: END, "phase1_explore": "phase1_explore"}
    )
    graph.add_edge("phase1_explore", END)

    return graph
