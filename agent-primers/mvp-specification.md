# Agent Graph MVP Specification

## Goal

Build a minimal LangGraph-based agent orchestration system where:
1. Root agent receives a feature request or bug report from the user
2. Root agent identifies the appropriate subflake agent based on the Nix dependency DAG
3. Subflake agent analyzes requirements in isolated context with read-only subflake-specific tools
4. Subflake agent collaborates with dependency agents when needed
5. Subflake agents produce a development plan (not implementation) that bubbles up to the root
6. Root agent consolidates the plan with appropriate detail for the developer

## Core Architecture

```
┌─────────────────┐
│   User Input    │
│  "Fix bug in    │
│   hello-py"     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      Root Agent                      │
│  - Parse Nix flake metadata          │
│  - Route task to appropriate agent   │
│  - Consolidate plans from subflakes  │
└────────┬──────────────┬──────────────┘
         │              │
    ┌────▼────┐    ┌───▼────┐
    │hello-py │    │hello-rs│
    │ Agent   │    │ Agent  │
    │         │    │        │
    │ Tools:  │    │ Tools: │
    │ - Read  │    │ - Read files
    │ - Grep  │    │ - Grep code
    │ - LSP   │    │ - rust-analyzer (read-only)
    │         │    │        │
    │ Output: │    │ Output:│
    │ Plan    │    │ Plan   │
    └─────────┘    └────────┘
```

## What's In Scope for MVP

### 1. Dynamic Graph Construction from Nix Metadata

**Input**: `nix flake metadata --json` output from project root

**Output**: A mapping of subflake names to their paths and dependencies

```python
# MVP Implementation
def parse_flake_dependencies() -> dict[str, SubflakeInfo]:
    """Parse Nix flake metadata to build agent routing table."""
    result = subprocess.run(
        ["nix", "flake", "metadata", "--json"],
        capture_output=True,
        text=True,
        cwd="/Users/matt/src/hello-subflakes"
    )
    metadata = json.loads(result.stdout)

    # Extract locks to find subflake relationships
    locks = metadata["locks"]["nodes"]

    subflakes = {}
    for name, info in locks.items():
        if "parent" in info:  # This is a relative path subflake
            subflakes[name] = SubflakeInfo(
                name=name,
                path=resolve_path_from_parent(info["parent"]),
                language=detect_language(path),
                dependencies=extract_dependencies(info)
            )

    return subflakes
```

**Acceptance Criteria**:
- ✅ Parse current hello-subflakes structure
- ✅ Identify hello-rs, hello-py, hello-wasm, hello-web
- ✅ Extract dependency relationships (hello-py → hello-rs, etc.)

### 2. Root Agent with Task Routing

**State Schema**:
```python
class RootState(TypedDict):
    user_request: str
    target_subflake: str | None
    task_type: Literal["bug_fix", "feature", "test"]
    subflake_plans: dict[str, str]  # Map of subflake -> plan
    consolidated_plan: str | None
```

**Node: Task Router**
```python
def route_task(state: RootState) -> Command[Literal["hello-rs", "hello-py", "hello-wasm", "consolidate"]]:
    """Analyze user request and determine which subflake agent should handle it."""

    # Simple keyword-based routing for MVP
    request_lower = state["user_request"].lower()

    if "hello-rs" in request_lower or "rust" in request_lower:
        target = "hello-rs"
    elif "hello-py" in request_lower or "python" in request_lower:
        target = "hello-py"
    elif "hello-wasm" in request_lower or "wasm" in request_lower:
        target = "hello-wasm"
    else:
        # Default: ask user to clarify
        return Command(
            goto="consolidate",
            update={"consolidated_plan": "ERROR: Could not determine target subflake"}
        )

    return Command(
        goto=target,
        update={"target_subflake": target}
    )
```

**Acceptance Criteria**:
- ✅ Parse user request for subflake mentions
- ✅ Route to appropriate subflake agent node
- ✅ Handle ambiguous requests gracefully

### 3. Subflake Agents with Isolated Context

**State Schema (per subflake)**:
```python
class SubflakeState(TypedDict):
    task_description: str           # Compressed from parent
    cwd: str                        # Subflake directory
    analysis_log: List[str]         # What the agent analyzed
    dependency_requests: List[str]  # Requests for upstream subflakes
    development_plan: str           # The plan to return
```

**Node: Subflake Agent (Example: hello-py)**
```python
async def hello_py_agent(state: RootState) -> RootState:
    """Analyze task in hello-py subflake and produce a development plan."""

    # Transform: Extract only what this agent needs
    subflake_input = SubflakeState(
        task_description=state["user_request"],
        cwd="/Users/matt/src/hello-subflakes/hello-py",
        analysis_log=[],
        dependency_requests=[],
        development_plan=""
    )

    # Create agent with read-only subflake-specific tools
    tools = await get_subflake_tools("hello-py")
    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_modifier=f"""You are a product owner and test consultant for the hello-py subflake.
Your working directory is {subflake_input['cwd']}.
Available tools: Read files, Grep, LSP navigation (pyright), run pytest to see current status.
Task: {subflake_input['task_description']}

Your job is to:
1. Understand the requirements and analyze existing code
2. Determine if you need support from upstream dependencies (hello-rs)
3. Produce a development plan that includes:
   - Which files need changes and why
   - What tests should pass when complete (with test locations)
   - Any requests for upstream teams

DO NOT implement changes. Only produce a plan for the developer to follow."""
    )

    # Agent executes in isolation
    result = agent.invoke(subflake_input)

    # Transform: Return only compressed output to parent
    return {
        "subflake_plans": {state["target_subflake"]: result["development_plan"]}
    }
```

**Tool Set per Subflake**:

**hello-rs** (Rust):
- `read_file` - Read source files (read-only)
- `grep` - Search code patterns
- `cargo_test` - Run tests to check current status
- `cargo_check` - Fast compile check to verify understanding
- `find_rust_symbol` - Navigate code via rust-analyzer (read-only)

**hello-py** (Python):
- `read_file` - Read source files (read-only)
- `grep` - Search code patterns
- `pytest` - Run tests to check current status
- `maturin_develop` - Build to verify understanding (no persistent changes)
- `find_python_symbol` - Navigate code via pyright (read-only)

**Acceptance Criteria**:
- ✅ Each subflake agent has its own read-only tool set
- ✅ Agent CWD is set to subflake directory
- ✅ Agent cannot access files outside its subflake
- ✅ Agent returns development plan (not full conversation history)
- ✅ No code changes are persisted by agents

### 4. Plan Consolidation

**Node: Consolidate Plans**
```python
def consolidate_plans(state: RootState) -> RootState:
    """Root agent consolidates plans from all subflakes into a coherent development plan."""

    subflake = state["target_subflake"]
    plan = state["subflake_plans"].get(subflake, "No plan generated")

    # The root agent reviews the plan and may:
    # 1. Strip unnecessary detail for plans from dependencies
    # 2. Ensure the plan is actionable for the developer
    # 3. Highlight which tests should pass when complete
    # 4. Note any cross-cutting concerns

    consolidated = f"""Development Plan for {state['user_request']}

Primary Work in: {subflake}

{plan}

Next Steps:
1. Review the plan above
2. Follow test-driven development: run suggested tests first (they should fail)
3. Implement changes as described
4. Verify tests pass
5. Run `nix flake check` from project root
"""

    return {
        "consolidated_plan": consolidated
    }
```

**Acceptance Criteria**:
- ✅ Parent consolidates plans from subflakes
- ✅ Parent removes unnecessary detail about upstream dependencies
- ✅ Parent provides clear next steps for the developer
- ✅ Plan emphasizes test locations and expected outcomes

### 5. Complete Workflow

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

def build_agent_graph():
    """Build the complete agent orchestration graph."""

    builder = StateGraph(RootState)

    # Add nodes
    builder.add_node("route_task", route_task)
    builder.add_node("hello-rs", hello_rs_agent)
    builder.add_node("hello-py", hello_py_agent)
    builder.add_node("hello-wasm", hello_wasm_agent)
    builder.add_node("consolidate", consolidate_plans)

    # Add edges
    builder.add_edge(START, "route_task")

    # Router sends to subflake agents
    builder.add_conditional_edges(
        "route_task",
        lambda state: state.get("target_subflake", "consolidate"),
        {
            "hello-rs": "hello-rs",
            "hello-py": "hello-py",
            "hello-wasm": "hello-wasm",
            "consolidate": "consolidate"
        }
    )

    # Subflakes report back to parent for plan consolidation
    builder.add_edge("hello-rs", "consolidate")
    builder.add_edge("hello-py", "consolidate")
    builder.add_edge("hello-wasm", "consolidate")

    # Consolidation produces final plan
    builder.add_edge("consolidate", END)

    # Compile with checkpointer for state persistence
    return builder.compile(checkpointer=MemorySaver())
```

## What's Out of Scope for MVP

These features are important but not needed for the core workflow:

❌ **Time-travel / Optimistic Amnesia**: Parent rewinding child conversation after blocker resolution
❌ **Beads Integration**: Issue tracker for agent communication
❌ **Multi-level Hierarchy**: Nested supervisors (just root + subflakes for now)
❌ **Langfuse Observability**: Tracing and monitoring
❌ **MCP Server-of-Servers**: Agents exposing themselves as MCP endpoints
❌ **Checkpoint Forking**: Creating conversation branches
❌ **Store for World State**: Separation of code changes from conversation state
❌ **Multiple Tool Tiers**: Just basic tools, no Serena/LSP integration yet
❌ **Dynamic Flake Updates**: Handling changes to flake.nix during execution
❌ **Human-in-the-Loop**: Interrupts for approvals

## MVP Success Criteria

The MVP is successful when:

1. **User Request → Task Routing**:
   - User says "Fix the Python FFI bindings in hello-py"
   - Root agent identifies target as `hello-py` subflake

2. **Isolated Analysis**:
   - hello-py agent receives compressed task description
   - Agent has read-only tools scoped to hello-py directory only
   - Agent cannot see files in hello-rs, hello-wasm, or root (except via dependency requests)

3. **Plan Generation**:
   - Agent analyzes existing code and tests
   - Agent determines if upstream changes needed (e.g., hello-rs)
   - Agent produces plan: "Fix type hint in src/lib.rs. Tests to verify: pytest tests/test_hello.py::test_ffi_binding"
   - No code changes are made by the agent

4. **Plan Consolidation**:
   - Root agent receives plan from hello-py agent
   - Root agent consolidates and formats for developer
   - Root agent outputs: "Development plan ready. Primary work: hello-py. See plan for details."

## File Structure for MVP

```
hello-subflakes/
├── agent-graph/              # NEW SUBFLAKE
│   ├── flake.nix            # Python environment with LangGraph
│   ├── pyproject.toml       # Dependencies: langgraph, langchain-anthropic
│   ├── uv.lock
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py          # Entry point: orchestrate()
│   │   ├── graph.py         # build_agent_graph()
│   │   ├── routing.py       # route_task()
│   │   ├── agents.py        # hello_rs_agent(), hello_py_agent(), etc.
│   │   ├── verification.py  # verify_completion()
│   │   └── tools.py         # Tool factories per subflake
│   └── tests/
│       └── test_routing.py  # Unit tests for task routing
├── hello-rs/
├── hello-py/
├── hello-wasm/
└── hello-web/
```

## Implementation Order

### Phase 1: Basic Infrastructure (Day 1)
1. Create `agent-graph` subflake with LangGraph dependencies
2. Implement `parse_flake_dependencies()` function
3. Write tests to verify parsing of current structure

### Phase 2: Root Agent (Day 2)
4. Implement `RootState` schema
5. Implement `route_task()` with keyword-based routing
6. Write tests for routing logic

### Phase 3: Single Subflake Agent (Day 3-4)
7. Implement `hello-py` agent with basic tools (read_file, write_file, pytest)
8. Test isolated execution in hello-py directory
9. Verify agent cannot access files outside hello-py

### Phase 4: Parent Verification (Day 5)
10. Implement `verify_completion()` with root-level test execution
11. Wire up complete graph: root → hello-py → verify → end
12. End-to-end test of full workflow

### Phase 5: Additional Subflakes (Day 6-7)
13. Implement `hello-rs` agent with Rust tools
14. Implement `hello-wasm` agent with WASM tools
15. Test routing to all three subflake agents

## Example Usage

```bash
# Start the agent orchestrator
cd agent-graph
nix develop

# Run the MVP
python -m agent_graph.main plan "Fix the Python bindings in hello-py"

# Expected output:
# 🔍 Analyzing request...
# 📍 Routing to: hello-py
# 🔧 hello-py agent analyzing...
# ✅ hello-py plan complete
# 📋 Consolidating plans...
#
# Development Plan for "Fix the Python bindings in hello-py"
#
# Primary Work in: hello-py
#
# Analysis:
# - Current FFI bindings in src/lib.rs use incorrect type annotations
# - Python expects str, but we're passing bytes
#
# Files to modify:
# - hello-py/src/lib.rs (line 42: change PyBytes to PyString)
#
# Tests to run (should fail initially):
# - pytest tests/test_hello.py::test_ffi_string_handling -v
#
# After changes:
# - Run: nix build ./hello-py#checks.aarch64-darwin.pytest
# - Should see: 2 passed
#
# Next Steps:
# 1. Run suggested test to confirm it fails
# 2. Make the change described above
# 3. Verify test passes
# 4. Run `nix flake check` from project root
```

## Testing Strategy

**Unit Tests**:
- `test_parse_flake_dependencies()` - Nix metadata parsing
- `test_route_task()` - Task routing logic
- `test_subflake_tool_isolation()` - Verify tools are read-only and scoped correctly

**Integration Tests**:
- `test_end_to_end_hello_py_plan()` - Complete workflow produces actionable plan for hello-py
- `test_end_to_end_hello_rs_plan()` - Complete workflow produces actionable plan for hello-rs
- `test_plan_includes_test_locations()` - Verify plans specify which tests to run
- `test_no_code_changes_persisted()` - Verify agents don't modify files

**Manual Testing**:
- Give ambiguous requests (no subflake mentioned) → verify graceful handling
- Request changes in multiple subflakes → verify routing picks the right one
- Request feature requiring upstream support → verify dependency requests in plan
- Verify plans are actionable but not overly prescriptive

## Next Steps After MVP

Once the MVP works, we can add:

1. **Serena Integration**: Enhanced semantic code navigation via MCP for better analysis
2. **Beads Integration**: Use issue tracker for structured agent communication about blockers
3. **Dependency Collaboration**: Automated requests from downstream to upstream agents
4. **Langfuse Observability**: Trace agent execution for debugging plan quality
5. **Multi-level Hierarchy**: Nested supervisors for complex projects
6. **Human-in-the-Loop**: Interrupt for approvals or clarifications during planning
7. **Plan Quality Metrics**: Track whether generated plans lead to successful implementations

But the MVP demonstrates the core concept: **dependency DAG-driven agent orchestration with isolated context producing actionable development plans for a developer with poor memory**.
