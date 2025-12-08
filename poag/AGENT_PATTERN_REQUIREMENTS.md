# Agent Pattern Problem & Requirements

## The Problem We're Encountering

### Error Details

We're getting this error when trying to invoke LangGraph's `create_react_agent`:

```
ValueError: Received multiple non-consecutive system messages.
```

This error comes from `langchain_anthropic/chat_models.py` in the `_format_messages` function.

### What's Happening

1. **We create an agent using `create_react_agent()`**:
   ```python
   agent = create_react_agent(
       model,  # ChatAnthropic
       tools,  # Serena MCP tools + our dependency tools
   )
   ```

2. **We invoke it with a user message**:
   ```python
   result = await agent.ainvoke(
       {"messages": [("user", "Explore this codebase...")]}
   )
   ```

3. **It hangs or errors with "multiple non-consecutive system messages"**

### Root Cause Analysis

The error suggests that somewhere in the message flow, system messages are being created in a way that violates Anthropic's API requirements. Specifically:

- `create_react_agent` internally manages system messages for the ReAct pattern
- When combined with checkpointing and/or multiple tool invocations, multiple system messages get added
- Anthropic requires system messages to be consolidated at the start, not scattered throughout

### What We've Tried

1. ✅ **Removed system prompts from user messages** - Still errors
2. ✅ **Removed checkpointing entirely** - Still hangs
3. ✅ **Simplified to just user messages** - Still errors
4. ✅ **Switched from `astream_events` to `ainvoke`** - Still errors

This suggests the issue is fundamental to how `create_react_agent` works with our setup, not our usage of it.

## Current Implementation (What Fails)

### Initialization Function (`agents.py`)

```python
async def initialize_subflake_agent(
    agent_name: str,
    info: SubflakeInfo,
    project_root: Path,
    home: Home | None = None,
) -> None:
    """Initialize a subflake agent by exploring its codebase.

    This creates an initial checkpoint with codebase understanding that can be
    reused across multiple task invocations.
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

    # Configure Serena MCP server parameters
    server_params = StdioServerParameters(
        command="sh",
        args=[
            "-c",
            f"uvx --from git+https://github.com/oraios/serena serena start-mcp-server --mode planning {subflake_path} 2>{stderr_log}",
        ],
        env={
            **os.environ,
            "SERENA_PROJECT_ROOT": str(subflake_path),
        },
    )

    checkpoint_path = checkpoint_mgr.get_checkpoint_path(agent_name)
    thread_id = checkpoint_mgr.get_thread_id(agent_name, project_root)

    # Initialize agent with exploration
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Load Serena tools for this subflake
            serena_tools = await load_mcp_tools(session)

            # Create LLM
            model = ChatAnthropic(
                model="claude-sonnet-4-20250514",
                api_key=anthropic_api_key,
                temperature=0.7,
            )

            # Create ReAct agent with Serena tools (no checkpointing for now to debug)
            agent = create_react_agent(
                model,
                serena_tools
            )

            # Run initialization phase
            init_message = f"""Explore this codebase thoroughly. Read documentation, examine the directory structure, understand the main source files and tests. Provide a summary of what this subflake does and how it's organized.

Focus on understanding:
- Project purpose and main functionality
- Directory structure and key files
- Testing framework and test organization
- Dependencies: {', '.join(info.dependencies) if info.dependencies else 'none'}"""

            stderr.print(f"[dim]      Starting {agent_name} initialization...[/dim]")
            init_result = await agent.ainvoke(
                {"messages": [("user", init_message)]}
            )
            # ^^^ THIS HANGS OR ERRORS

    # Mark as initialized
    checkpoint_mgr.mark_initialized(agent_name, project_root)
    stderr.print(f"[green]    ✓ {agent_name}: initialization complete[/green]")
```

### Task Execution Function (`agents.py`)

```python
async def invoke_subflake_agent(
    agent_name: str,
    info: SubflakeInfo,
    task_description: str,
    project_root: Path,
    all_subflakes: dict = None,
    home: Home | None = None,
) -> str:
    """Invoke a subflake agent and return its development plan.

    Assumes the agent has already been initialized via initialize_subflake_agent.
    """
    # Get API key from environment
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    if all_subflakes is None:
        all_subflakes = {}

    if home is None:
        home = Home()

    subflake_path = project_root / info.path

    # Configure Serena MCP server parameters
    server_params = StdioServerParameters(
        command="sh",
        args=[
            "-c",
            f"uvx --from git+https://github.com/oraios/serena serena start-mcp-server --mode planning {subflake_path} 2>{stderr_log}",
        ],
        env={
            **os.environ,
            "SERENA_PROJECT_ROOT": str(subflake_path),
        },
    )

    # Set up checkpointing for persistent state
    checkpoint_mgr = CheckpointManager(home)
    checkpoint_path = checkpoint_mgr.get_checkpoint_path(info.name)
    thread_id = checkpoint_mgr.get_thread_id(info.name, project_root)

    # Keep the session open during agent invocation
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Load Serena tools for this subflake
            serena_tools = await load_mcp_tools(session)

            # Create dependency communication tools
            from poag_sf.tools import create_dependency_tools

            dependency_tools = create_dependency_tools(
                info.name, info.dependencies, all_subflakes, project_root
            )

            # Combine all tools
            tools = serena_tools + dependency_tools

            # Create LLM
            model = ChatAnthropic(
                model="claude-sonnet-4-20250514",
                api_key=anthropic_api_key,
                temperature=0.7,
            )

            # Create ReAct agent with Serena tools (no checkpointing for now to debug)
            agent = create_react_agent(
                model,
                tools
            )

            # Task execution
            task_message = f"""Analyze this development task and create a plan:

{task_description}

Remember:
- Specify which files need changes and why
- Include exact test commands (pytest/cargo test)
- Note any upstream dependencies needed: {', '.join(info.dependencies) if info.dependencies else 'none'}
- Provide guidance on testing before/after implementation"""

            result = await agent.ainvoke(
                {"messages": [("user", task_message)]}
            )
            # ^^^ THIS ALSO HANGS OR ERRORS

            # Extract the final message as the plan
            if result and "messages" in result:
                # Get the last AI message
                for msg in reversed(result["messages"]):
                    if hasattr(msg, "content") and msg.content:
                        return msg.content

            return "No plan generated"
```

### Graph Architecture (`graph.py`)

```python
def build_agent_graph(subflakes: Dict[str, SubflakeInfo], project_root: Path, home: Home):
    """Build the complete agent orchestration graph."""
    builder = StateGraph(RootState)

    # Add analysis node
    def analyze_request(state: RootState) -> RootState:
        """Analyze the request and determine which subflakes are relevant."""
        return _analyze_request(state, subflakes, project_root)

    # Add initialization node (async to properly await initialization)
    async def initialize_agents(state: RootState) -> RootState:
        """Initialize all relevant agents sequentially to avoid rate limiting."""
        relevant = state.get("relevant_subflakes", [])
        if not relevant:
            return state

        stderr.print(f"[cyan]🔄 Initializing {len(relevant)} agent(s) sequentially...[/cyan]")

        for agent_name in relevant:
            if agent_name not in subflakes:
                continue

            info = subflakes[agent_name]
            # Initialize one at a time (await, not asyncio.run)
            await initialize_subflake_agent(agent_name, info, project_root, home)

        stderr.print("[green]✅ All agents initialized[/green]")
        return state

    builder.add_node("analyze_request", analyze_request)
    builder.add_node("initialize_agents", initialize_agents)
    builder.add_node("consolidate", lambda state: consolidate_plans(state, subflakes))

    # Create node functions for each subflake agent
    def make_agent_node(name: str, info: SubflakeInfo):
        """Create a node function for a subflake agent."""

        async def agent_node(state: RootState) -> RootState:
            """Invoke the subflake agent and update state with its plan."""
            truncated_request = state["user_request"][:200] + "..." if len(state["user_request"]) > 200 else state["user_request"]
            stderr.print(f"[cyan]🔧 {name}[/cyan]: {truncated_request}")

            # Invoke the agent (await instead of asyncio.run)
            plan = await invoke_subflake_agent(
                name, info, state["user_request"], project_root, subflakes, home
            )

            stderr.print(f"[green]✅ {name} complete[/green]")

            # Update state with the plan
            subflake_plans = state.get("subflake_plans", {})
            subflake_plans[name] = plan

            # Track that we've queried this subflake
            subflakes_queried = state.get("subflakes_queried", [])
            if name not in subflakes_queried:
                subflakes_queried.append(name)

            return {
                **state,
                "subflake_plans": subflake_plans,
                "subflakes_queried": subflakes_queried,
            }

        return agent_node

    # Add subflake agent nodes
    for name, info in subflakes.items():
        node_func = make_agent_node(name, info)
        builder.add_node(name, node_func)

    # Add edges
    builder.add_edge(START, "analyze_request")
    builder.add_edge("analyze_request", "initialize_agents")

    # Router: fan out to relevant subflakes after initialization
    def route_to_agents(state: RootState) -> List[str]:
        """Route to relevant subflake agents."""
        relevant = state.get("relevant_subflakes", [])
        if not relevant:
            return ["consolidate"]
        return relevant

    builder.add_conditional_edges("initialize_agents", route_to_agents)

    # All subflake agents return to consolidate
    for name in subflakes.keys():
        builder.add_edge(name, "consolidate")

    builder.add_edge("consolidate", END)

    # Compile with checkpointer for state persistence
    return builder.compile(checkpointer=MemorySaver())
```

### Dependency Communication Tools (`tools.py`)

```python
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
```

### Checkpoint Management (`checkpoints.py`)

```python
class CheckpointManager:
    """Manages LangGraph checkpoints for subflake agents."""

    def __init__(self, home: Home | None = None):
        if home is None:
            home = Home()
        self.home = home
        self.checkpoint_dir = home.state / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.checkpoint_dir / "metadata.json"

    def get_checkpoint_path(self, subflake_name: str) -> str:
        """Get the database path for a specific subflake's checkpointer.

        Args:
            subflake_name: Name of the subflake

        Returns:
            Path to the SQLite database as a string
        """
        db_path = self.checkpoint_dir / f"{subflake_name}.db"
        return str(db_path)

    def is_initialized(self, subflake_name: str, project_root: Path) -> bool:
        """Check if a subflake agent has been initialized.

        Args:
            subflake_name: Name of the subflake
            project_root: Project root path (for cache invalidation)

        Returns:
            True if initialized, False otherwise
        """
        metadata = self._load_metadata()
        key = f"{project_root}:{subflake_name}"
        return key in metadata

    def mark_initialized(self, subflake_name: str, project_root: Path) -> None:
        """Mark a subflake agent as initialized.

        Args:
            subflake_name: Name of the subflake
            project_root: Project root path
        """
        metadata = self._load_metadata()
        key = f"{project_root}:{subflake_name}"
        metadata[key] = True
        self._save_metadata(metadata)

    def get_thread_id(self, subflake_name: str, project_root: Path) -> str:
        """Get a consistent thread ID for a subflake agent.

        Args:
            subflake_name: Name of the subflake
            project_root: Project root path

        Returns:
            Thread ID string
        """
        return f"{project_root}:{subflake_name}"
```

## What We Need From an Agent Pattern

### Core Requirements

#### 1. **Tool Integration**
We need to give agents access to two types of tools:

**Serena MCP Tools** (read-only code navigation):
- `list_dir` - List directory contents
- `read_file` - Read file contents
- `search_code` - Search for code patterns
- `get_symbols` - Get code symbols (functions, classes)
- ~20 other Serena tools for code understanding

Example of how tools are loaded:
```python
async with ClientSession(read, write) as session:
    await session.initialize()
    serena_tools = await load_mcp_tools(session)
    # serena_tools is now a list of LangChain Tool objects
```

**Custom Dependency Communication Tools**:
```python
# Example: hello-py depends on hello-rs
# When hello-py agent calls request_from_hello_rs(),
# it internally invokes the hello-rs agent
StructuredTool(
    name="request_from_hello_rs",
    description="Request support from the hello-rs team",
    func=async_invoke_hello_rs_agent,
    coroutine=async_invoke_hello_rs_agent,
    args_schema=DependencyRequestInput
)
```

#### 2. **Checkpointing / State Persistence**
- **Two-phase execution**:
  - Phase 1: Initialization (explore codebase once, ~20-30 tool calls)
  - Phase 2: Task execution (reuse exploration knowledge, ~5-10 tool calls)
- **Cross-invocation memory**: Agent should remember previous conversations
- **Per-project, per-agent isolation**: `thread_id = f"{project_root}:{agent_name}"`
- **Storage**: SQLite for now (one DB per agent), PostgreSQL for production

What checkpointing should preserve:
```python
# After initialization
checkpoint = {
    "messages": [
        ("user", "Explore this codebase..."),
        ("assistant", "I used list_dir and found..."),
        (ToolMessage from list_dir),
        ("assistant", "I read README.md and learned..."),
        (ToolMessage from read_file),
        # ... more exploration
        ("assistant", "Summary: This is a Rust library...")
    ]
}

# On next invocation, resume with all that context
# and just add new task message
```

#### 3. **Message Control**
- **No system message conflicts**: Must work with Anthropic's constraints
- **Simple user/assistant flow**: User gives task, agent produces plan
- **Tool call handling**: Agent can call multiple tools, iterate on findings
- **Streaming optional**: Would be nice for progress updates but not required

The Anthropic API requires:
- System messages at the start only (if any)
- No system messages scattered throughout the conversation
- User/Assistant alternation (with tool messages interspersed)

#### 4. **Async Execution**
- Everything must be async (we're using `asyncio.run` from typer CLI)
- Multiple agents may invoke each other (agent A → agent B → agent C)
- Sequential initialization, then parallel task execution

Execution flow:
```
asyncio.run(
    graph.ainvoke(...)
) → initialize_agents (async, sequential)
  → agent_node_1 (async)
    → invoke_subflake_agent (async)
      → agent.ainvoke (async)
        → tool_1 (async)
        → tool_2 (async, may call another agent!)
```

### Desired Flow

```
┌─────────────────────────────────────────────────────────────┐
│ INITIALIZATION (First run, saved to checkpoint)             │
├─────────────────────────────────────────────────────────────┤
│ User: "Explore this codebase thoroughly..."                 │
│ Agent: [calls list_dir]                                     │
│ Agent: "I see src/, tests/, Cargo.toml"                     │
│ Agent: [calls read_file on Cargo.toml]                      │
│ Agent: "This is a Rust library named hello-rs"              │
│ Agent: [calls read_file on src/lib.rs]                      │
│ Agent: "The main function is hello_world()"                 │
│ Agent: [calls list_dir on tests/]                           │
│ Agent: "Tests use cargo test framework"                     │
│ Agent: "Summary: This is a Rust library for greetings..."   │
│ → Checkpoint saved with all messages                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ TASK EXECUTION (Subsequent runs, resume from checkpoint)    │
├─────────────────────────────────────────────────────────────┤
│ User: "Make this say goodbye instead of hello"              │
│ Agent: [already knows codebase from checkpoint]             │
│ Agent: [calls read_file on src/lib.rs to check current impl]│
│ Agent: "I see hello_world() returns 'Hello'"                │
│ Agent: "Development Plan: Change lib.rs line 5 from         │
│        'Hello' to 'Goodbye'. Run cargo test to verify."     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ DEPENDENCY INVOCATION (Agent calling another agent)         │
├─────────────────────────────────────────────────────────────┤
│ User (to hello-py): "Add error handling"                    │
│ hello-py agent: [analyzes code]                             │
│ hello-py agent: "I depend on hello-rs for the FFI"          │
│ hello-py agent: [calls request_from_hello_rs tool]          │
│   → Internally invokes hello-rs agent with:                 │
│      "Add Result<> return type to hello_world()"            │
│   → hello-rs agent analyzes and returns plan                │
│ hello-py agent: "Plan: First, hello-rs needs to change      │
│                  their interface (see dependency plan).      │
│                  Then update hello-py bindings..."           │
└─────────────────────────────────────────────────────────────┘
```

### Non-Requirements (Things We DON'T Need)

- ❌ **Code execution**: Agents only analyze and plan, never execute code
- ❌ **Human-in-the-loop**: No interrupts or approvals during execution
- ❌ **Multi-agent supervisors**: Simple fan-out pattern (coordinator → agents)
- ❌ **Memory windows**: Can trim old messages if needed, but prefer full history
- ❌ **Streaming output**: Nice to have but not essential

## Alternative Patterns to Research

### 1. **Raw LangChain Agent with Checkpointing**
Instead of `create_react_agent`, build our own agent loop:
- Use `ChatAnthropic.bind_tools()`
- Manually handle tool calls in a loop
- Add checkpointing ourselves

**Pros**: Full control over message flow
**Cons**: More code to maintain

### 2. **LangGraph Custom Agent Graph**
Build the agent as an explicit graph instead of using prebuilt:
- Node 1: Model call
- Node 2: Tool execution
- Node 3: Repeat or finish
- Add checkpointing at graph level

**Pros**: Explicit state management, clear message flow
**Cons**: More complex setup

### 3. **Plain LangChain LCEL with Tools**
Use LangChain Expression Language without LangGraph:
```python
agent = (
    prompt
    | model.bind_tools(tools)
    | tool_executor
    | output_parser
)
```

**Pros**: Simpler, less abstraction
**Cons**: No built-in checkpointing, would need to implement ourselves

### 4. **Custom ReAct Loop**
Implement ReAct pattern ourselves:
```python
async def react_loop(messages, tools, checkpointer):
    while True:
        # Call model
        response = await model.ainvoke(messages)

        # If no tool calls, return
        if not response.tool_calls:
            return response

        # Execute tools
        for tool_call in response.tool_calls:
            result = await execute_tool(tool_call)
            messages.append(result)

        # Save checkpoint
        await checkpointer.save(messages)
```

**Pros**: Complete control, no black box
**Cons**: Need to handle all edge cases ourselves

## Key Questions for Research

1. **Why does `create_react_agent` create multiple system messages?**
   - Is this a known issue?
   - Is there a configuration to prevent it?
   - Does it work without MCP tools?

2. **What's the recommended LangGraph pattern for tool-using agents with Anthropic?**
   - Are there examples using `ChatAnthropic` + tools + checkpointing?
   - Is there a different prebuilt agent we should use?

3. **How do other projects handle MCP tools with LangGraph?**
   - Any examples of `langchain-mcp-adapters` + `create_react_agent`?
   - Do they encounter the same system message issues?

4. **Can we use LangGraph's Agent Supervisor pattern?**
   - Our coordinator → PO agents maps to supervisor → worker pattern
   - Does the supervisor pattern avoid system message conflicts?

5. **Should we be using a different checkpoint pattern?**
   - Maybe checkpointing at the graph level instead of agent level?
   - Or using LangGraph's built-in persistence differently?

## Debug Information

### Current Dependencies
```toml
langgraph = ">=0.2.64"
langgraph-checkpoint-sqlite = ">=2.0.4"
langchain-anthropic = ">=0.3.0"
langchain-mcp-adapters = ">=0.1.0"
```

### Model Configuration
```python
model = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    api_key=anthropic_api_key,
    temperature=0.7,
)
```

### Tool Setup
```python
# Serena MCP tools loaded from session
serena_tools = await load_mcp_tools(session)
# Returns list of ~20 LangChain Tool objects

# Custom dependency tools
dependency_tools = create_dependency_tools(
    agent_name, info.dependencies, all_subflakes, project_root
)
# Returns list of StructuredTool objects

# Combined
tools = serena_tools + dependency_tools
```

## Success Criteria

We'll know we have the right pattern when:

1. ✅ Agent can call multiple MCP tools during initialization
2. ✅ Agent's exploration knowledge persists to checkpoint
3. ✅ Subsequent invocations resume from checkpoint without re-initialization
4. ✅ Agent can invoke other agents via dependency tools
5. ✅ No "multiple system messages" errors
6. ✅ No hangs during agent invocation
7. ✅ Works with async execution from typer CLI
8. ✅ Sequential initialization works (4 agents one at a time)
9. ✅ Parallel task execution works (4 agents at once, post-init)

## Current Status

**Architecture**: ✅ Complete and sound
- Sequential initialization to avoid rate limiting
- Checkpoint-based state management
- Per-agent, per-project isolation
- Async graph execution

**Blocker**: ❌ Agent invocation fails
- `create_react_agent()` either hangs or errors with "multiple system messages"
- Happens even without checkpointing enabled
- Happens even with minimal user messages
- Root cause appears to be in `create_react_agent` + Anthropic interaction
