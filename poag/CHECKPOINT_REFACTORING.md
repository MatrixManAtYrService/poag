# Checkpoint and Initialization Refactoring

## Problem Statement

The original implementation had several issues:

1. **Rate Limiting**: When multiple agents needed initialization, they would all start simultaneously, each spinning up a Serena MCP server instance and making API calls. With 4+ agents, this triggered rate limiting.

2. **Hidden Initialization**: The initialization phase was hidden inside the `invoke_subflake_agent` function as an inline check. This made the two-phase execution pattern unclear.

3. **No Explicit Architecture**: Initialization happened as a side effect during the first task invocation, rather than as an explicit architectural phase.

4. **Missing Import**: `AsyncSqliteSaver` was used but not imported, causing a runtime error.

## Solution Overview

The refactoring separates initialization from task execution and makes initialization sequential to avoid rate limiting.

### Key Changes

#### 1. Separated Initialization from Execution (`agents.py`)

**Before**: Single function `invoke_subflake_agent` that checked initialization state inline
**After**: Two separate functions:

- `initialize_subflake_agent(agent_name, info, project_root, home)` - Explicit initialization phase
- `invoke_subflake_agent(agent_name, info, task_description, project_root, all_subflakes, home)` - Task execution (assumes already initialized)

#### 2. Sequential Initialization in Graph (`graph.py`)

**Before**: Graph fanned out directly from `analyze_request` to all relevant agent nodes simultaneously

```python
# Old flow
START → analyze_request → [agent1, agent2, agent3, ...] → consolidate → END
```

**After**: Added explicit `initialize_agents` node that runs sequentially before fan-out

```python
# New flow
START → analyze_request → initialize_agents → [agent1, agent2, agent3, ...] → consolidate → END
```

The `initialize_agents` node:
- Runs initialization sequentially (one agent at a time)
- Checks if each agent is already initialized before running initialization
- Only initializes agents that are relevant to the current request

#### 3. Enhanced Initialization Process

The initialization phase now has a dedicated system prompt that guides the agent through:

1. Reading README or main documentation
2. Exploring directory structure
3. Identifying key source, test, and config files
4. Understanding the project's purpose
5. Learning the testing framework
6. Understanding dependency relationships

This creates a rich checkpoint that the agent can resume from for any task.

#### 4. Fixed Missing Import

Added `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver` to `agents.py`.

## Checkpoint Strategy

### Current Implementation (SQLite per-agent)

Each agent gets its own SQLite checkpoint database:
- **Location**: `~/.local/state/poag-sf/checkpoints/{agent_name}.db`
- **Thread ID**: `{project_root}:{agent_name}`
- **Isolation**: Complete state isolation between agents
- **Limitation**: Write-lock contention if multiple requests hit same agent simultaneously

### Metadata Tracking

Initialization state is tracked in `~/.local/state/poag-sf/checkpoints/metadata.json`:

```json
{
  "/Users/matt/src/hello-subflakes:hello-rs": true,
  "/Users/matt/src/hello-subflakes:hello-py": true,
  ...
}
```

This allows the system to quickly check if an agent has been initialized without loading the full checkpoint database.

### Future Consideration: PostgreSQL Migration

The research document provided shows that **PostgreSQL is recommended for production** with the following benefits:

- Shared connection pool across all agents
- Proper concurrent write access
- Horizontal scaling capability
- Thread ID-based isolation within a shared database

For now, SQLite works well with sequential initialization, but PostgreSQL should be considered when:
- Running in production
- Handling concurrent user requests
- Scaling beyond a few agents

## Two-Phase Execution

### Phase 1: Initialization (First Run)

When an agent is first encountered for a project:

1. `initialize_agents` node detects uninitialized agent
2. Calls `initialize_subflake_agent()` which:
   - Starts Serena MCP server for the subflake
   - Loads Serena tools (code navigation, file reading, etc.)
   - Creates agent with initialization-focused system prompt
   - Agent explores codebase, reads docs, understands structure
   - Checkpoint saved with rich codebase understanding
3. Marks agent as initialized in metadata

### Phase 2: Task Execution (Every Run)

When an agent executes a task:

1. Assumes agent is already initialized (enforced by graph flow)
2. `invoke_subflake_agent()`:
   - Starts Serena MCP server
   - Loads both Serena tools AND dependency communication tools
   - Creates agent with task-focused system prompt
   - Resumes from existing checkpoint (has codebase knowledge)
   - Agent analyzes task and produces development plan
   - Checkpoint updated with new conversation
3. Returns plan to coordinator

## Usage

### Normal Operation

```bash
# First run: initializes relevant agents sequentially, then executes
poag plan "Fix the FFI bindings in hello-py"

# Subsequent runs: skips initialization, goes straight to execution
poag plan "Add type hints to hello-py"
```

### Managing Initialization State

```bash
# List all subflakes and their initialization status
poag ls

# Clear specific agent (force re-initialization on next run)
poag clear --agent hello-rs

# Clear all agents for current project
poag clear
```

### Development Tips

- **Rate limiting still happening?** Use `poag clear` to clear state and verify sequential initialization is working
- **Agent seems confused?** Clear its initialization to trigger fresh codebase exploration: `poag clear --agent <name>`
- **Testing different initialization strategies?** Clear agents between tests
- **Want to see what's available?** Use `poag ls` to see all subflakes and which are initialized

## Testing

To test the refactored system:

```bash
# List available subflakes
poag ls

# Clear all state
poag clear

# Run a broad request that triggers multiple agents
poag plan "make it say goodbye instead of hello"

# You should see:
# 1. Request analysis
# 2. Sequential initialization (one agent at a time)
# 3. Parallel task execution (all agents at once)
# 4. Consolidated plan

# Check initialization status
poag ls

# Run another request - should skip initialization
poag plan "add error handling to hello-rs"
```

## Files Changed

- `src/poag_sf/agents.py`: Split initialization from execution, added missing import
- `src/poag_sf/graph.py`: Added `initialize_agents` node, changed edge flow
- `src/poag_sf/main.py`: Added `clear` and `ls` commands for state management
- `pyproject.toml`: No changes needed - all commands under single `poag` entry point

## Next Steps (Future Work)

1. **PostgreSQL Migration**: Consider migrating to PostgreSQL with connection pooling for production deployments
2. **Initialization Versioning**: Add version hashing (e.g., based on `flake.nix` or `flake.lock` hash) to auto-invalidate initialization when project structure changes
3. **Parallel Initialization with Rate Limiting**: Instead of fully sequential, batch initializations with delays to respect rate limits while improving performance
4. **Initialization Quality Metrics**: Track how well initialization prepares agents for tasks (e.g., do they need to re-explore during task execution?)
5. **Shared Initialization Context**: Consider sharing common project context across all agents to reduce redundant exploration

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      User Request                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  analyze_request      │ Determine relevant agents
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  initialize_agents    │ Sequential initialization
         │  (new node)           │ - Check if initialized
         │                       │ - Run exploration if needed
         │                       │ - Save checkpoint
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   Fan-out to agents   │ Parallel task execution
         │  (hello-rs, hello-py, │ - Resume from checkpoint
         │   hello-wasm, ...)    │ - Analyze task
         │                       │ - Produce plan
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │    consolidate        │ Combine all plans
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   Final Plan Output   │
         └───────────────────────┘
```

## Comparison: Before vs After

### Before (Parallel Initialization, Rate Limiting)

```
User request → Analyze → Fan-out to [agent1, agent2, agent3, agent4]
                              ↓          ↓          ↓          ↓
                        [init+task] [init+task] [init+task] [init+task]
                              ↓          ↓          ↓          ↓
                         (4 Serena instances start simultaneously)
                         (4 agents make API calls simultaneously)
                         **RATE LIMIT ERROR**
```

### After (Sequential Initialization, No Rate Limiting)

```
User request → Analyze → Initialize agents sequentially
                              ↓
                         init agent1 → init agent2 → init agent3 → init agent4
                         (one at a time, no rate limiting)
                              ↓
                         Fan-out to [agent1, agent2, agent3, agent4]
                              ↓          ↓          ↓          ↓
                          [task]     [task]     [task]     [task]
                         (all already initialized, can run in parallel)
```

## Summary

This refactoring makes the two-phase execution pattern explicit in the architecture, eliminates rate limiting by initializing agents sequentially, and provides better control over agent state through the new `poag-reset` utility. The checkpoint strategy now clearly separates initialization (expensive, one-time) from task execution (fast, reusable).
