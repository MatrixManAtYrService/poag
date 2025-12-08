"""LangGraph-based agent orchestration graph construction."""

import asyncio
import json
import os
import operator
from pathlib import Path
from typing import Annotated, Dict, TypedDict, List
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_anthropic import ChatAnthropic
from rich.console import Console
import networkx as nx

from poag_sf.metadata import SubflakeInfo
from poag_sf.agents import invoke_subflake_agent, initialize_subflake_agent
from poag_sf.config import Home
from poag_sf.graph_builder import find_all_dependents

stderr = Console(stderr=True)


class RootState(TypedDict):
    """State for the root coordination agent."""

    user_request: str
    relevant_subflakes: List[str]  # Which subflakes to query
    subflake_instructions: dict[str, str]  # Specific instructions for each subflake
    subflakes_queried: Annotated[List[str], operator.add]  # Reduced by concatenation
    subflake_plans: Annotated[dict[str, str], operator.or_]  # Reduced by dict merge
    consolidated_plan: str | None


def build_agent_graph(
    subflakes: Dict[str, SubflakeInfo],
    dependency_graph: nx.DiGraph,
    project_root: Path,
    home: Home
):
    """Build the complete agent orchestration graph.

    Args:
        subflakes: Map of subflake name to SubflakeInfo
        dependency_graph: NetworkX DiGraph of flake dependencies
        project_root: Path to project root directory
        home: Home directory for config and logs

    Returns:
        Compiled LangGraph
    """
    builder = StateGraph(RootState)

    # Add analysis node
    def analyze_request(state: RootState) -> RootState:
        """Analyze the request and determine which subflakes are relevant."""
        return _analyze_request(state, subflakes, project_root)

    # Add initialization node (async to properly await initialization)
    async def initialize_agents(state: RootState) -> RootState:
        """Phase 1: Initialize all relevant agents sequentially to avoid rate limiting.

        This runs self-exploration and generates input contracts (what each agent needs).
        """
        relevant = state.get("relevant_subflakes", [])
        if not relevant:
            return state

        stderr.print(f"[cyan]🔄 Phase 1: Initializing {len(relevant)} agent(s) sequentially...[/cyan]")

        for agent_name in relevant:
            if agent_name not in subflakes:
                continue

            info = subflakes[agent_name]
            # Initialize one at a time (await, not asyncio.run)
            await initialize_subflake_agent(agent_name, info, project_root, subflakes, home)

        stderr.print("[green]✅ Phase 1 complete for all agents[/green]")
        return state

    # Add Phase 2 coordination node
    async def phase2_contracts(state: RootState) -> RootState:
        """Phase 2: Generate output contracts by sharing input contracts between agents.

        For each agent, read input contracts from its dependents and generate
        corresponding output contracts describing what it provides.
        """
        from poag_sf.contracts import ContractManager

        relevant = state.get("relevant_subflakes", [])
        if not relevant:
            return state

        stderr.print(f"[cyan]🔄 Phase 2: Generating provider contracts...[/cyan]")

        # For each agent, find its dependents and generate output contracts
        for agent_name in relevant:
            if agent_name not in subflakes:
                continue

            info = subflakes[agent_name]
            subflake_path = project_root / info.path
            contract_mgr = ContractManager(subflake_path)

            # Find dependents using the graph (includes root flake!)
            dependents = sorted(find_all_dependents(dependency_graph, agent_name))

            if not dependents:
                stderr.print(f"[dim]    {agent_name}: no dependents, skipping Phase 2[/dim]")
                continue

            stderr.print(f"[dim]    {agent_name}: generating contracts for {len(dependents)} dependent(s): {', '.join(dependents)}[/dim]")

            # For each dependent, read their input contract about us
            output_contracts_written = []
            for dependent_name in dependents:
                dependent_info = subflakes.get(dependent_name)
                if not dependent_info:
                    continue

                dependent_path = project_root / dependent_info.path
                dependent_contract_mgr = ContractManager(dependent_path)

                # Read what they need from us
                their_needs = dependent_contract_mgr.read_input_contract(agent_name)
                if not their_needs:
                    stderr.print(f"[yellow]      ⚠ {dependent_name} has no input contract for {agent_name}[/yellow]")
                    continue

                # Use Claude Code to analyze our codebase and create a response
                prompt = f"""You are the maintainer of the {agent_name} project.

A downstream consumer ({dependent_name}) has documented what they need from your project:

{their_needs}

**Your task:** Analyze your codebase to understand how you meet these requirements and create a provider contract.

**Output format:**

# Provider Contract: What {agent_name} provides to {dependent_name}

## Current Implementation
[Describe how your code currently satisfies their requirements, with file references and code snippets]

## API Stability
[What parts of the API are stable vs subject to change]

## Breaking Change Protocol
[How you'll communicate breaking changes to dependents]

## Testing
[What tests ensure this contract is maintained]

Keep it concise and actionable."""

                try:
                    # Run Claude Code in the provider's directory
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
                        stderr.print(f"[red]      ✗ Failed to generate contract for {dependent_name}: {error_msg}[/red]")
                        continue

                    result = json.loads(stdout.decode())
                    provider_contract = result["result"]

                    # Write the output contract
                    contract_mgr.write_output_contract(dependent_name, provider_contract)
                    output_contracts_written.append(dependent_name)

                except Exception as e:
                    stderr.print(f"[red]      ✗ Error generating contract for {dependent_name}: {e}[/red]")
                    continue

            # Update index with Phase 2 results
            if output_contracts_written:
                # Re-read existing index to preserve input contracts
                index = contract_mgr.load_index()
                if index:
                    input_contracts = [f.replace(".md", "") for f in index.contracts.get("inputs", [])]
                else:
                    input_contracts = []

                contract_mgr.update_index_after_generation(
                    input_contracts=input_contracts,
                    output_contracts=output_contracts_written
                )

        stderr.print("[green]✅ Phase 2 complete - all contracts generated[/green]")
        return state

    builder.add_node("analyze_request", analyze_request)
    builder.add_node("initialize_agents", initialize_agents)
    builder.add_node("phase2_contracts", phase2_contracts)
    builder.add_node("consolidate", lambda state: consolidate_plans(state, subflakes))

    # Create node functions for each subflake agent
    def make_agent_node(name: str, info: SubflakeInfo):
        """Create a node function for a subflake agent."""

        async def agent_node(state: RootState) -> dict:
            """Invoke the subflake agent and update state with its plan."""
            # Get the specific instruction for this agent
            instructions = state.get("subflake_instructions", {})
            agent_instruction = instructions.get(name, state["user_request"])

            # Show what request we're sending to this agent
            truncated_instruction = agent_instruction[:100] + "..." if len(agent_instruction) > 100 else agent_instruction
            stderr.print(f"[cyan]🔧 {name}[/cyan]: {truncated_instruction}")

            # Invoke the agent with specific instruction
            plan = await invoke_subflake_agent(
                name, info, agent_instruction, project_root, subflakes, home
            )

            stderr.print(f"[green]✅ {name} complete[/green]")

            # Return ONLY the updates - reducers will merge them
            return {
                "subflake_plans": {name: plan},  # Dict will be merged with operator.or_
                "subflakes_queried": [name],      # List will be concatenated with operator.add
            }

        return agent_node

    # Add subflake agent nodes
    for name, info in subflakes.items():
        node_func = make_agent_node(name, info)
        builder.add_node(name, node_func)

    # Add edges
    builder.add_edge(START, "analyze_request")
    builder.add_edge("analyze_request", "initialize_agents")
    builder.add_edge("initialize_agents", "phase2_contracts")

    # Router: fan out to relevant subflakes after contract generation
    def route_to_agents(state: RootState) -> List[str]:
        """Route to relevant subflake agents."""
        relevant = state.get("relevant_subflakes", [])
        if not relevant:
            return ["consolidate"]
        return relevant

    builder.add_conditional_edges("phase2_contracts", route_to_agents)

    # All subflake agents return to consolidate
    for name in subflakes.keys():
        builder.add_edge(name, "consolidate")

    builder.add_edge("consolidate", END)

    # Compile with checkpointer for state persistence
    return builder.compile(checkpointer=MemorySaver())


def _analyze_request(
    state: RootState, subflakes: Dict[str, SubflakeInfo], project_root: Path
) -> RootState:
    """Use contracts and LLM to analyze request and determine which subflakes are relevant.

    This reads the .poag/contracts/ directories to understand what each agent actually does
    and how they relate, enabling smarter routing decisions.
    """
    from poag_sf.contracts import ContractManager

    stderr.print("[dim]🤔 Root agent analyzing which subflakes are relevant...[/dim]")

    # Read README for context
    readme_path = project_root / "README.md"
    readme_content = ""
    if readme_path.exists():
        readme_content = readme_path.read_text()[:3000]  # First 3k chars

    # Build context about subflakes INCLUDING their contracts
    subflakes_context = []
    for name, info in subflakes.items():
        if name == "poag":  # Skip orchestration system (not a subflake to route to)
            continue

        subflake_path = project_root / info.path
        contract_mgr = ContractManager(subflake_path)

        # Check if contracts exist
        if not contract_mgr.are_contracts_current():
            # No contracts yet, use basic info
            subflakes_context.append(
                f"- {name}: {info.language} project at {info.path} (no contracts yet)"
            )
            continue

        # Read all contracts to understand this agent
        contracts = contract_mgr.get_all_contracts()

        # Build contract summary
        contract_summary = []
        if contracts["inputs"]:
            deps = ", ".join(contracts["inputs"].keys())
            contract_summary.append(f"depends on: {deps}")

        if contracts["outputs"]:
            provides = ", ".join(contracts["outputs"].keys())
            contract_summary.append(f"provides to: {provides}")

        # Get a snippet of what this agent does (from self summary if available)
        # For now, just use the contract information
        context_str = f"- {name}: {info.language} project"
        if contract_summary:
            context_str += f" ({'; '.join(contract_summary)})"

        subflakes_context.append(context_str)

    subflakes_info = "\n".join(subflakes_context)

    # Use LLM to decide with contract-aware prompt
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        stderr.print("[yellow]Warning: No ANTHROPIC_API_KEY, querying all subflakes[/yellow]")
        return {
            **state,
            "relevant_subflakes": [name for name in subflakes.keys() if name != "poag"],
            "subflakes_queried": [],
        }

    model = ChatAnthropic(model="claude-sonnet-4-20250514", api_key=api_key, temperature=0)

    prompt = f"""You are the root coordinator for a multi-subflake Nix project.

Available subflakes:
{subflakes_info}

Project README (excerpt):
{readme_content}

User request: {state['user_request']}

Your task:
1. Analyze which subflakes are **directly responsible** for this request based on their contracts and capabilities
2. For EACH relevant subflake, create specific instructions tailored to that subflake's role

ROUTING STRATEGY - Contract-Based Discovery:
1. Look at the contracts to understand what each subflake provides and needs
2. Match the user's request to the capabilities described in contracts
3. Route to the subflake(s) most directly responsible - they can use `poag describe` to learn about neighbors
4. Agents have access to `poag ls --neighbors` and `poag describe <flake>` for discovering context
5. Only route to multiple agents if the request genuinely affects multiple independent components
6. The root flake represents user acceptance tests and integration requirements

Available Tools for Agents:
- `poag ls --neighbors`: Shows current flake and its direct neighbors (dependencies + dependents)
- `poag describe <flake-name>`: Returns JSON with flake's README, flake.nix, neighbors, and contracts

For each relevant subflake, craft instructions that:
- Reference their specific role from contracts (if available)
- Reference what they depend on (if relevant)
- Are actionable for that specific component
- Encourage them to use `poag describe` to understand neighbors if needed

Example:
- User request: "change the greeting to say goodbye"
  Analysis: Contract shows hello-rs provides greeting function, hello-py wraps it, root consumes it
  Output: {{"hello-py": "Change your greeting output to say 'goodbye' instead of 'hello'. Use 'poag describe hello-rs' to understand your dependency and 'poag describe root' to understand how the root flake uses you. Determine whether this requires upstream changes or can be handled in your FFI layer."}}

- User request: "make all greetings say goodbye"
  Analysis: Multiple flakes provide greeting functionality via different tech stacks
  Output: {{
    "hello-py": "Update the Python greeting to say 'goodbye' instead of 'hello'. Use 'poag ls --neighbors' to see your dependencies.",
    "hello-wasm": "Update the WebAssembly greeting to say 'goodbye' instead of 'hello'.",
    "hello-web": "Ensure the web interface displays 'goodbye' greetings from hello-wasm."
  }}

Return ONLY a JSON object mapping subflake names to their specific instructions.
Respond with just the JSON object, nothing else."""

    response = model.invoke(prompt)
    content = response.content.strip()

    # Parse JSON - expecting object now, not array
    try:
        # Handle markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        subflake_instructions = json.loads(content)
        relevant = list(subflake_instructions.keys())
        stderr.print(f"[dim]Relevant subflakes: {', '.join(relevant)}[/dim]")

        for name, instruction in subflake_instructions.items():
            stderr.print(f"[dim]  → {name}: {instruction[:80]}{'...' if len(instruction) > 80 else ''}[/dim]")

    except json.JSONDecodeError as e:
        stderr.print(f"[yellow]Warning: Could not parse LLM response: {e}[/yellow]")
        # Fallback: route to all and use original request
        relevant = [name for name in subflakes.keys() if name != "poag"]
        subflake_instructions = {name: state['user_request'] for name in relevant}

    return {
        **state,
        "relevant_subflakes": relevant,
        "subflake_instructions": subflake_instructions,
        "subflakes_queried": [],
    }


def consolidate_plans(state: RootState, subflakes: Dict[str, SubflakeInfo]) -> RootState:
    """Root agent consolidates plans from all queried subflakes.

    Output as JSON for easy parsing and navigation.
    """
    stderr.print("[dim]📋 Consolidating plans from all agents...[/dim]")

    plans = state.get("subflake_plans", {})

    if not plans:
        error_output = {
            "error": "No plans generated",
            "queried_subflakes": state.get('relevant_subflakes', [])
        }
        return {
            **state,
            "consolidated_plan": json.dumps(error_output, indent=2),
        }

    # Create structured JSON output
    output = {
        "user_request": state['user_request'],
        "plans": plans,  # This is already a dict of {subflake_name: plan}
        "subflakes_analyzed": list(plans.keys()),
        "next_steps": [
            "Review the plans for each affected subflake",
            "Follow test-driven development: run suggested tests first (they should fail)",
            "Implement changes as described in each subflake",
            "Verify tests pass in each subflake",
            "Run `nix flake check` from project root to verify integration"
        ]
    }

    consolidated = json.dumps(output, indent=2)

    return {
        **state,
        "consolidated_plan": consolidated,
    }
