"""Subflake agents using Claude Code headless mode."""

import os
import json
import asyncio
from pathlib import Path
from typing import TypedDict, List

from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from poag_sf.metadata import SubflakeInfo
from poag_sf.config import Home
from poag_sf.logging import stderr
from poag_sf.checkpoints import CheckpointManager
from poag_sf.exploration_graph import build_exploration_graph, ExplorationState


class SubflakeState(TypedDict):
    """State for a single subflake agent."""

    task_description: str  # Compressed from parent
    cwd: str  # Subflake directory
    analysis_log: List[str]  # What the agent analyzed
    dependency_requests: List[str]  # Requests for upstream subflakes
    development_plan: str  # The plan to return


async def initialize_subflake_agent(
    agent_name: str,
    info: SubflakeInfo,
    project_root: Path,
    all_subflakes: dict,
    home: Home | None = None,
) -> None:
    """Initialize a subflake agent by exploring its codebase.

    This creates an initial checkpoint with codebase understanding that can be
    reused across multiple task invocations.

    Args:
        agent_name: Name of the agent/subflake
        info: SubflakeInfo for this subflake
        project_root: Path to project root
        home: Home directory for logs (optional)
    """
    # Get API key from environment
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    if home is None:
        home = Home()

    checkpoint_mgr = CheckpointManager(home)

    # Check if already initialized
    if checkpoint_mgr.is_initialized(agent_name, project_root):
        stderr.print(f"[dim]    ✓ {agent_name}: already initialized[/dim]")
        return

    stderr.print(f"[yellow]    📚 {agent_name}: first run, exploring codebase...[/yellow]")

    subflake_path = project_root / info.path
    checkpoint_path = checkpoint_mgr.get_checkpoint_path(agent_name)
    thread_id = checkpoint_mgr.get_thread_id(agent_name, project_root)

    # Build exploration graph (uses Claude Code headless)
    exploration_graph_builder = build_exploration_graph(checkpoint_path)

    # Compile with checkpointer
    async with AsyncSqliteSaver.from_conn_string(checkpoint_path) as checkpointer:
        exploration_graph = exploration_graph_builder.compile(
            checkpointer=checkpointer
        )

        # Find dependents (flakes that depend on this one)
        dependents = [name for name, sf in all_subflakes.items()
                     if agent_name in (sf.dependencies or [])]

        # Run exploration with initial state
        stderr.print(f"[dim]      Starting {agent_name} exploration...[/dim]")

        initial_state: ExplorationState = {
            "subflake_name": agent_name,
            "subflake_path": str(subflake_path),
            "language": info.language,
            "dependencies": info.dependencies or [],
            "dependents": dependents,
            "claude_session_id": None,
            "contracts_current": False,
            "self_summary": None,
            "phase1_complete": False,
            "phase2_complete": False,
        }

        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        # Invoke the exploration graph
        result = await exploration_graph.ainvoke(initial_state, config)

        # Check if exploration succeeded
        if result.get("phase1_complete"):
            summary_preview = result.get('self_summary', 'No summary')[:100]
            stderr.print(f"[dim]      ✓ Phase 1 complete: {summary_preview}...[/dim]")
        elif result.get("contracts_current"):
            stderr.print(f"[dim]      ✓ Using existing contracts (up to date)[/dim]")
        else:
            stderr.print(f"[yellow]      ⚠ Exploration incomplete or failed[/yellow]")

    # Mark as initialized
    checkpoint_mgr.mark_initialized(agent_name, project_root)
    stderr.print(f"[green]    ✓ {agent_name}: initialization complete[/green]")


async def invoke_subflake_agent(
    agent_name: str,
    info: SubflakeInfo,
    task_description: str,
    project_root: Path,
    all_subflakes: dict = None,
    home: Home | None = None,
) -> str:
    """Invoke a subflake agent and return its development plan.

    Resumes the Claude Code session created during initialization to create
    a development plan for the given task.

    Args:
        agent_name: Name of the agent/subflake
        info: SubflakeInfo for this subflake
        task_description: The task to analyze
        project_root: Path to project root
        all_subflakes: Dict of all subflake infos (for dependency tools)
        home: Home directory for logs (optional)

    Returns:
        Development plan as a string
    """
    if home is None:
        home = Home()

    subflake_path = project_root / info.path
    checkpoint_mgr = CheckpointManager(home)
    checkpoint_path = checkpoint_mgr.get_checkpoint_path(info.name)
    thread_id = checkpoint_mgr.get_thread_id(info.name, project_root)

    # Retrieve the Claude Code session ID from the checkpoint
    async with AsyncSqliteSaver.from_conn_string(checkpoint_path) as checkpointer:
        # Get the most recent checkpoint for this thread
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)

        if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
            stderr.print(f"[red]No checkpoint found for {agent_name} - run initialization first[/red]")
            return "Error: Agent not initialized. Run initialization first."

        # Extract the session ID from the checkpoint state
        checkpoint_state = checkpoint_tuple.checkpoint.get("channel_values", {})
        session_id = checkpoint_state.get("claude_session_id")

        if not session_id:
            stderr.print(f"[red]No Claude Code session ID found for {agent_name}[/red]")
            return "Error: No Claude Code session found in checkpoint."

    # Build context about agent relationships from contracts
    from poag_sf.contracts import ContractManager

    contract_mgr = ContractManager(subflake_path)
    contracts = contract_mgr.get_all_contracts()

    upstream_context = ""
    if contracts["inputs"]:
        upstream_info = []
        for dep_name, contract_content in contracts["inputs"].items():
            # Include snippet from contract showing what we need
            snippet = contract_content[:200] + "..." if len(contract_content) > 200 else contract_content
            upstream_info.append(f"  - {dep_name}: You have a contract describing what you need from them")
            upstream_info.append(f"    Contract snippet: {snippet}")
        if upstream_info:
            upstream_context = "\n\nYour upstream dependencies (you can request changes from them):\n" + "\n".join(upstream_info)

    downstream_context = ""
    if contracts["outputs"]:
        downstream_info = []
        for dep_name, contract_content in contracts["outputs"].items():
            # Include snippet from contract showing what we provide
            snippet = contract_content[:200] + "..." if len(contract_content) > 200 else contract_content
            downstream_info.append(f"  - {dep_name}: You have a contract describing what you provide to them")
            downstream_info.append(f"    Contract snippet: {snippet}")
        if downstream_info:
            downstream_context = "\n\nYour downstream consumers (they depend on your outputs):\n" + "\n".join(downstream_info)

    # Create task prompt for this product owner
    task_prompt = f"""You are a product owner and test consultant for the {info.name} subflake.

Your Responsibilities:
- You own the Nix flake in {info.path}
- Description: {info.description or "no description available"}
- Your job is to analyze requirements and produce a development plan (NOT implement it){upstream_context}{downstream_context}

Discovery Tools Available:
You can use these commands to learn about your neighbors on-demand:
- `poag ls --neighbors`: Shows your current flake and its direct neighbors (dependencies + dependents)
- `poag describe <flake-name>`: Returns JSON with that flake's README, flake.nix, neighbors, and contracts

Use these tools when you need to:
- Understand what a dependency provides (use `poag describe <dependency>`)
- Understand how a dependent uses you (use `poag describe <dependent>`)
- See the full dependency context (use `poag ls --neighbors`)
- Make architectural decisions about where work belongs

Context:
- There is one developer who is skilled but has poor memory
- Your plans should specify tests that will pass when the task is complete
- Tests should be in appropriate locations (unit tests in same flake, integration tests may be elsewhere)
- Test failure messages should remind the developer what requirement they ensure

Task Analysis Process:
1. Understand the requirement using the codebase knowledge from your exploration
2. Use `poag describe` to understand your neighbors' contracts and capabilities if relevant
3. Determine if you can handle it in your flake, or if you need upstream support
4. Produce a plan that includes:
   - Which files need changes and why
   - What tests should pass (with exact test commands like pytest/cargo test)
   - Any requests for upstream teams (if applicable, with context from `poag describe`)
   - Guidance on running tests before/after implementation

Important:
- DO NOT implement changes yourself
- DO NOT propose entire implementations
- DO provide hints, relevant files, and test strategies
- Your plan should have enough detail to guide the developer's hand, but not so much that the developer doesn't have to think about what's going on.
- USE the poag tools to understand your context, don't guess about neighbors

Task: {task_description}"""

    # Resume Claude Code session with the task
    stderr.print(f"[dim]      Resuming session {session_id[:8]}... for task planning[/dim]")

    try:
        process = await asyncio.create_subprocess_exec(
            "claude", "-p", task_prompt,
            "--resume", session_id,
            "--output-format", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(subflake_path)  # Set working directory for the process
        )

        stdout, stderr_output = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr_output.decode() if stderr_output else "Unknown error"
            stderr.print(f"[red]      ✗ Claude Code task planning failed: {error_msg}[/red]")
            return f"Error: Task planning failed - {error_msg}"

        # Parse JSON response
        result = json.loads(stdout.decode())
        return result["result"]

    except FileNotFoundError:
        stderr.print("[red]      ✗ Claude Code not found - is it installed?[/red]")
        return "Error: Claude Code not found - install with: npm install -g @anthropic-ai/claude-code"
    except json.JSONDecodeError as e:
        stderr.print(f"[red]      ✗ Failed to parse Claude Code response: {e}[/red]")
        return f"Error: Failed to parse response - {e}"
    except Exception as e:
        stderr.print(f"[red]      ✗ Unexpected error: {e}[/red]")
        return f"Error: {e}"
