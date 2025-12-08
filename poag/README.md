# POAG: Product Owner Agent Graph for Subflakes

A LangGraph-based multi-agent system that generates development plans for Nix subflake projects. Each subflake (including the root) gets its own "product owner" agent that analyzes requirements and produces actionable development plans—not implementations.

## Architecture

```
┌─────────────┐
│ User Request│
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│  Analyze & Route    (NetworkX dependency graph) │
│  - Discovers all subflakes + root flake         │
│  - Determines relevant agents for request       │
└──────┬──────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│  Phase 1: Initialize Agents (sequential)        │
│  - Self-exploration of codebase                 │
│  - Generate input contracts (what they need)    │
└──────┬──────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│  Phase 2: Generate Provider Contracts           │
│  - Find all dependents (using graph)            │
│  - Read dependent's input contracts             │
│  - Generate output contracts (what they provide)│
└──────┬──────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│  Invoke Relevant Agents                         │
│  - root agent (user acceptance tests, UAT)      │
│  - hello-py agent (with Serena + dep tools)     │
│  - hello-rs agent (with Serena + dep tools)     │
│  - hello-wasm agent (with Serena + dep tools)   │
│  - hello-web agent (with Serena + dep tools)    │
│                                                  │
│  Each agent:                                     │
│  - Can invoke upstream dependencies             │
│  - Returns development plan                     │
└──────┬──────────────────────────────────────────┘
       │
       ▼
┌─────────────────┐
│ Consolidate     │  ← Combines plans from all agents
└──────┬──────────┘
       │
       ▼
   Final Plan (JSON to stdout)
```

## Features

- **Graph-based dependency analysis**: Uses NetworkX to build a directed graph of flake dependencies (including root flake!)
- **Root flake as first-class agent**: The root flake has its own agent representing user acceptance tests and integration requirements
- **Contract-based discovery**: Agents discover their context on-demand using `poag` tools
  - `poag ls --neighbors`: See direct dependencies and dependents
  - `poag describe <flake>`: Get README, flake.nix, neighbors, and contracts
  - No keyword matching - agents make architectural decisions based on contracts
- **Two-phase contract system**:
  - Phase 1: Agents explore and generate input contracts (what they need from dependencies)
  - Phase 2: Providers generate output contracts (what they provide to dependents)
- **Persistent agent memory**: Agents initialize once per project, exploring the codebase thoroughly, then reuse that knowledge
- **Sequential initialization**: Avoids rate limiting by initializing agents one at a time
- **Serena integration**: Each agent uses Serena (MCP server) in planning mode for read-only code analysis
- **Inter-agent communication**: Agents can request support from their upstream dependencies using contract context
- **Test-focused planning**: Plans emphasize which tests should pass when work is complete
- **CLI interface**: Pipe requests in, get plans out as JSON

## Setup

```bash
cd poag
nix develop

# Install dependencies
uv sync

# Set your Anthropic API key
export ANTHROPIC_API_KEY=your_key_here
# Or put it in ~/.anthropic-api-key
```

## Usage

### Generate Development Plans

```bash
# Basic usage
poag plan "Fix the Python FFI bindings in hello-py"

# Pipe from stdin
echo "Add error handling to hello-rs" | poag plan

# Specify project root
poag plan --root /path/to/project "Add tests for hello-wasm"
```

### List Subflakes

```bash
# List all subflakes in current project with initialization status
poag ls

# Example output:
# ┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
# ┃ Name                     ┃ Path       ┃ Language ┃ Dependencies        ┃
# ┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
# │ hello-subflakes (root)   │ .          │ python   │ hello-py, hello-web │
# │ hello-py                 │ hello-py   │ rust     │ hello-rs            │
# │ hello-rs                 │ hello-rs   │ rust     │ none                │
# │ hello-wasm               │ hello-wasm │ wasm     │ hello-rs            │
# │ hello-web                │ hello-web  │ web      │ hello-wasm          │
# └──────────────────────────┴────────────┴──────────┴─────────────────────┘
#
# Initialized: hello-py, hello-rs, hello-wasm, hello-web
# Not initialized: root
```

### Manage Agent State

```bash
# Clear all agent initialization state (force re-initialization on next run)
poag clear

# Clear specific agent
poag clear --agent hello-rs

# Useful when:
# - You want agents to re-explore the codebase
# - Testing different initialization strategies
# - Agent seems to have outdated understanding
```

### Output

- **stderr**: Progress updates, agent activity
- **stdout**: Final development plan (suitable for piping or saving)

Example:

```bash
$ echo "Fix type annotations in hello-py" | poag plan > plan.md

# stderr shows:
# 🔍 Analyzing request...
# 📊 Parsing flake dependencies...
# 🏗️  Building agent graph...
# 🚀 Starting agent orchestration...
# 🔧 hello-py agent analyzing...
# ✅ hello-py plan complete
# 📋 Consolidating plans...

# stdout (saved to plan.md):
# Development Plan for: Fix type annotations in hello-py
#
# Primary Work in: hello-py
#
# [Detailed plan from agent...]
```

## How It Works

1. **Metadata Parsing & Graph Construction**:
   - Reads `nix flake metadata --json` for each subflake and root
   - Builds NetworkX DiGraph representing dependency relationships
   - Nodes: (flake_name, input/output_name) tuples
   - Edges: (provider_output) → (consumer_input)

2. **Task Routing**:
   - LLM analyzes request with contract context
   - Determines which subflakes are directly responsible
   - Creates specific instructions for each relevant agent

3. **Phase 1: Initialization (Sequential)**:
   - Agents explore their codebase using Serena
   - Generate input contracts describing dependencies needed
   - Stored in `.poag/contracts/inputs/`
   - Reused on subsequent runs (persistent memory)

4. **Phase 2: Provider Contracts**:
   - Use graph to find all dependents (including root!)
   - Read each dependent's input contract
   - Generate corresponding output contracts
   - Stored in `.poag/contracts/outputs/`

5. **Planning**:
   - Agent analyzes code with full contract context
   - Determines if work is internal or requires upstream changes
   - Produces development plan (no implementation)

6. **Consolidation**:
   - Combines plans from all agents
   - Outputs JSON to stdout with next steps

## Agent Roles

Each agent acts as a "product owner" for its subflake:

- **Analyze**: Understand requirements using Serena's code navigation
- **Decide**: Determine if work belongs in this flake or upstream
- **Collaborate**: Request support from dependency agents if needed
- **Plan**: Specify files to change, tests to run, and acceptance criteria

**Special Role: Root Agent**
- Represents user acceptance tests and integration requirements
- Contains nuanced user-level requirements not visible in implementation-focused subflakes
- Other agents generate provider contracts for root just like any other dependent
- Root's contracts shape how subflakes understand user needs

## Dependencies

- **LangGraph**: Agent orchestration framework
- **NetworkX**: Graph library for dependency analysis and traversal
- **Serena**: MCP server for semantic code analysis (launched via uvx)
- **langchain-mcp-adapters**: Connects Serena to LangGraph agents
- **Anthropic**: Claude as the LLM backbone
- **Rich**: Terminal UI for progress display
- **Typer**: CLI framework

## Development

```bash
# Run tests
pytest

# Check structure
ls -la src/poag_sf/
```

## Files

- `main.py`: CLI entry point (typer-based) - `plan`, `ls`, `clear` commands
- `metadata.py`: Nix flake parsing logic, includes root flake
- `graph_builder.py`: NetworkX dependency graph construction and queries
- `graph.py`: LangGraph orchestration with Phase 1 & Phase 2
- `agents.py`: Subflake agent creation with Serena integration
- `tools.py`: Inter-agent communication tools
- `contracts.py`: Contract management (read/write input/output contracts)
- `checkpoints.py`: Persistent agent state management
- `config.py`: XDG directory configuration
- `logging.py`: Structured logging setup

### New Commands for Agent Discovery

```bash
# From within a subflake directory, see your neighbors
cd hello-py
poag ls --neighbors

# Output shows current flake and its direct dependencies + dependents:
# ┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
# ┃ Name                     ┃ Path       ┃ Language ┃ Dependencies        ┃
# ┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
# │ hello-py ← current       │ hello-py   │ rust     │ hello-rs            │
# │ hello-rs                 │ hello-rs   │ rust     │ none                │
# │ hello-subflakes (root)   │ .          │ python   │ hello-py, hello-web │
# └──────────────────────────┴────────────┴──────────┴─────────────────────┘

# Get detailed information about a specific flake
poag describe hello-rs

# Output (JSON to stdout):
# {
#   "name": "hello-rs",
#   "path": "hello-rs",
#   "language": "rust",
#   "description": "Core Rust library for greetings",
#   "readme": "...",
#   "flake_nix": "...",
#   "neighbors": {
#     "hello-py": {
#       "description": "Python FFI bindings",
#       "language": "rust",
#       "relationship": ["dependent"]
#     }
#   },
#   "contracts": {
#     "outputs": {
#       "hello-py": "# Provider Contract: What hello-rs provides..."
#     }
#   }
# }
```

These commands enable agents to discover their context on-demand rather than relying on keyword matching.

## Limitations

- LLM-based routing (not embedding-based semantic similarity yet)
- SQLite-based checkpointing (works for single-user local dev; PostgreSQL recommended for production)
- Assumes Serena is available via `uvx`
- Requires poag in subflake devShells for agent discovery tools

## Future Enhancements

- **Semantic routing using embeddings**: Move beyond keyword matching to semantic understanding
- **Parallel agent execution**: For independent subflakes with no dependency relationships
- **Beads integration**: Structured issue tracking for agent communication about blockers
- **Graph visualization**: Export dependency graph to Mermaid/Graphviz for documentation
- **Multi-output tracking**: Handle multiple outputs per flake in the graph
- **Root agent initialization**: Initialize root agent like other agents to generate contracts
- **Plan quality metrics**: Track whether generated plans lead to successful implementations
- **Human-in-the-loop approvals**: Interrupt for approvals or clarifications during planning
- **Contract validation**: Verify that provider contracts actually satisfy dependent's input contracts

---

For more details on the architecture, see `../agent-primers/mvp-specification.md`.
