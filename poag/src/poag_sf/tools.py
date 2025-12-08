"""Custom tools for inter-agent communication."""

from pathlib import Path
from typing import Dict
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from poag_sf.metadata import SubflakeInfo
from poag_sf.agents import invoke_subflake_agent
from poag_sf.logging import stderr


class DependencyRequestInput(BaseModel):
    """Input schema for dependency request tool."""

    requirement: str = Field(description="The requirement or task to request from the dependency team")


def create_dependency_tools(
    agent_name: str,
    dependencies: list[str],
    subflakes: Dict[str, SubflakeInfo],
    project_root: Path,
):
    """Create tools for invoking dependency agents.

    Args:
        agent_name: Name of the current agent
        dependencies: List of dependency subflake names
        subflakes: All subflake info
        project_root: Project root path

    Returns:
        List of LangChain tools for invoking dependencies
    """
    tools = []

    def make_dependency_tool(dep_name: str, dep_info: SubflakeInfo):
        """Factory to create a dependency tool with proper closure."""

        async def request_from_dependency(requirement: str) -> str:
            """Request support from an upstream dependency team."""
            # Show inter-agent communication
            truncated_req = requirement[:256] + "..." if len(requirement) > 256 else requirement
            stderr.print(f"[dim]  ↳ {agent_name} → {dep_name}: {truncated_req}[/dim]")

            plan = await invoke_subflake_agent(
                dep_name, dep_info, requirement, project_root, subflakes
            )

            truncated_plan = plan[:256] + "..." if len(plan) > 256 else plan
            stderr.print(f"[dim]  ↲ {dep_name} → {agent_name}: {truncated_plan}[/dim]")

            return f"Plan from {dep_name}:\n\n{plan}"

        tool_name = f"request_from_{dep_name.replace('-', '_')}"
        tool_description = (
            f"Request support from the {dep_name} team. "
            f"Use this when you need the {dep_name} subflake to implement a feature "
            f"or fix a bug that your {agent_name} flake depends on."
        )

        return StructuredTool(
            name=tool_name,
            description=tool_description,
            func=request_from_dependency,
            coroutine=request_from_dependency,
            args_schema=DependencyRequestInput,
        )

    for dep_name in dependencies:
        if dep_name not in subflakes:
            continue

        dep_info = subflakes[dep_name]
        tool_instance = make_dependency_tool(dep_name, dep_info)
        tools.append(tool_instance)

    return tools
