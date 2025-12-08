# LangGraph hierarchical multi-agent systems with isolated context

**LangGraph provides robust primitives for building hierarchical agent systems where each agent maintains completely isolated state.** The framework supports independent state schemas for subgraphs, checkpoint namespaces for hierarchical persistence, and explicit state transformation at agent boundaries—exactly what's needed for a Nix subflake-like dependency DAG of domain experts. Your use case of communicating via compressed feature requests and bug reports (rather than raw context) maps directly to LangGraph's state transformation patterns.

This report covers the complete architectural approach: from basic graph construction to advanced patterns for context isolation, supervisor hierarchies, time travel, and memory management.

---

## LangGraph fundamentals for multi-agent systems

LangGraph models agent workflows as **graphs** with three core components: **state** (a shared TypedDict data structure), **nodes** (functions that receive and update state), and **edges** (routing logic between nodes). Every node reads from state and returns partial updates that get merged via reducer functions.

### State schemas using TypedDict

State schemas define the data contract between all nodes in a graph:

```python
from typing import TypedDict, Annotated, List
from langgraph.graph import StateGraph, START, END
import operator

class AgentState(TypedDict):
    input: str
    messages: List[str]
    all_actions: Annotated[List[str], operator.add]  # Reducer appends
```

The `Annotated` syntax with a reducer function (like `operator.add`) controls how updates merge. Without a reducer, values simply overwrite. LangGraph provides a built-in `MessagesState` for chat-based workflows with intelligent message handling.

### Basic graph construction

```python
workflow = StateGraph(AgentState)
workflow.add_node("research", research_node)
workflow.add_node("analyze", analyze_node)
workflow.add_edge(START, "research")
workflow.add_edge("research", "analyze")
workflow.add_edge("analyze", END)

graph = workflow.compile()
result = graph.invoke({"input": "query", "messages": []})
```

### The Command API enables simultaneous routing and state updates

The **Command** type is essential for multi-agent handoffs—it lets nodes update state AND specify the next node in a single return:

```python
from langgraph.types import Command
from typing import Literal

def research_node(state: AgentState) -> Command[Literal["analyzer", END]]:
    result = do_research(state)
    goto = "analyzer" if needs_analysis(result) else END
    
    return Command(
        update={"messages": result["messages"]},  # State update
        goto=goto                                   # Next node
    )
```

For subgraphs communicating with parent graphs, use `Command.PARENT`:

```python
def child_node(state):
    return Command(
        goto="parent_node_name",
        update={"result": "completed"},
        graph=Command.PARENT  # Navigate to parent graph context
    )
```

---

## State isolation between parent and child subgraphs

**Child graphs can have completely independent state schemas from parents**—this is the key to preventing context pollution. LangGraph offers two subgraph integration patterns.

### Pattern 1: Shared state keys (compiled subgraph as node)

When parent and child share at least one state key, add the compiled subgraph directly:

```python
class SharedState(TypedDict):
    foo: str  # Shared with parent
    bar: str  # Private to subgraph

subgraph = subgraph_builder.compile()
builder = StateGraph(SharedState)
builder.add_node("child", subgraph)  # Add compiled graph directly
```

The parent automatically receives updates to shared keys; private keys remain invisible.

### Pattern 2: Different schemas (function wrapper with transformation)

**For your Nix subflake DAG use case, this is the critical pattern.** When schemas differ completely, invoke the subgraph inside a wrapper function that transforms state:

```python
class ParentState(TypedDict):
    task_queue: List[str]
    results: List[str]

class ChildAgentState(TypedDict):
    feature_request: str     # Input from parent
    bug_report: str          # Output to parent
    internal_context: List[str]  # Private working memory

def call_child_agent(state: ParentState) -> ParentState:
    # Transform: extract only what child needs
    child_input = {"feature_request": state["task_queue"][0]}
    
    # Child runs with isolated context
    child_result = child_graph.invoke(child_input)
    
    # Transform: return only compressed output
    return {"results": [child_result["bug_report"]]}

builder.add_node("child_agent", call_child_agent)  # Function, not compiled graph
```

This pattern ensures the child's `internal_context` never pollutes the parent's state—only the structured `bug_report` passes through.

### Checkpoint namespaces create hierarchical isolation

LangGraph uses `checkpoint_ns` to organize checkpoints hierarchically:

- Root graph: `checkpoint_ns = ""`
- Child: `checkpoint_ns = "child_agent"`  
- Grandchild: `checkpoint_ns = "child_agent|grandchild_agent"`

The pipe-separated path mirrors your Nix subflake DAG structure. Subgraphs share the parent's `thread_id` but maintain separate checkpoint histories under their namespace.

```python
# Parent gets the checkpointer—it propagates automatically
checkpointer = MemorySaver()
parent_graph = builder.compile(checkpointer=checkpointer)

# Subgraphs compile WITHOUT explicit checkpointer
child_graph = child_builder.compile()

# For subgraph-specific persistence (v0.2.64+):
child_graph = child_builder.compile(checkpointer=True)
```

---

## Hierarchical supervisor architecture

The supervisor pattern creates a coordination layer that routes tasks to specialized child agents.

### Using create_supervisor() for quick setup

```python
from langgraph_supervisor import create_supervisor
from langgraph.prebuilt import create_react_agent

# Specialized domain agents
nix_agent = create_react_agent(model, tools=[nix_tools], name="nix_expert")
rust_agent = create_react_agent(model, tools=[rust_tools], name="rust_expert")

# Supervisor coordinates them
workflow = create_supervisor(
    [nix_agent, rust_agent],
    model=model,
    prompt="Route tasks to the appropriate domain expert.",
    output_mode="last_message"  # Only pass final output, not full history
)
```

### Building hierarchical supervisors (supervisors managing supervisors)

For your DAG structure, nest supervisors to match your dependency tree:

```python
# Level 1: Domain team supervisors
nix_team = create_supervisor(
    [flake_agent, derivation_agent],
    model=model,
    supervisor_name="nix_supervisor"
).compile(name="nix_team")

rust_team = create_supervisor(
    [cargo_agent, async_agent],
    model=model,
    supervisor_name="rust_supervisor"
).compile(name="rust_team")

# Level 2: Top-level supervisor
root_supervisor = create_supervisor(
    [nix_team, rust_team],
    model=model,
    supervisor_name="root"
).compile()
```

### Dynamic graph construction for DAG-like structures

When your agent topology matches a Nix flake's inputs, construct graphs programmatically:

```python
def build_agent_dag(flake_inputs: dict) -> StateGraph:
    graph = StateGraph(AgentState)
    
    # Create nodes from flake inputs
    for name, config in flake_inputs.items():
        agent = create_domain_agent(name, config)
        graph.add_node(name, agent)
    
    # Wire edges based on dependencies
    for name, config in flake_inputs.items():
        for dep in config.get("inputs", []):
            graph.add_edge(dep, name)  # Dependency must complete first
    
    return graph.compile()
```

### State passing between supervisor and child agents

Use the Command API for controlled handoffs:

```python
def supervisor_node(state: State) -> Command[Literal["nix_expert", "rust_expert", END]]:
    decision = route_to_expert(state["messages"][-1])
    
    # Pass only relevant context, not full history
    return Command(
        goto=decision,
        update={"task_context": extract_relevant_context(state)}
    )
```

---

## Checkpointing and time travel capabilities

LangGraph saves a checkpoint after every node execution (each "super-step"), enabling conversation rewinding and forking.

### Browsing checkpoint history with get_state_history()

```python
config = {"configurable": {"thread_id": "session_1"}}

for snapshot in graph.get_state_history(config):
    print(f"Step {snapshot.metadata['step']}: {snapshot.values}")
    print(f"Next nodes: {snapshot.next}")
    print(f"Checkpoint ID: {snapshot.config['configurable']['checkpoint_id']}")
```

Each `StateSnapshot` contains:
- `values`: State at that checkpoint
- `next`: Tuple of next nodes to execute
- `config`: Including `thread_id`, `checkpoint_ns`, `checkpoint_id`
- `metadata`: Source (`input`/`loop`/`update`/`fork`), step number, parent info

### Forking from arbitrary checkpoints

This is powerful for your use case—rewind a child agent while preserving external changes:

```python
# Get historical state
history = list(graph.get_state_history(config))
checkpoint_before_bug = history[3]  # Select desired point

# Fork with modified state (creates new branch, doesn't affect original)
branch_config = graph.update_state(
    checkpoint_before_bug.config,
    values={"feature_request": "Updated requirements after code commit"},
    as_node="__start__"
)

# Continue from fork—original history preserved
result = graph.invoke(None, branch_config)
```

### Checkpoint metadata for marking significant points

```python
# Add custom metadata when updating state
config = {
    "metadata": {
        "milestone": "v1.0_feature_complete",
        "external_commit": "abc123",
        "significance": "major_decision_point"
    },
    "configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}
}

graph.update_state(config, values={"approved": True})

# Later, filter by metadata
for snapshot in graph.get_state_history(config, filter={"source": "update"}):
    if snapshot.metadata.get("milestone"):
        print(f"Found milestone: {snapshot.metadata['milestone']}")
```

### Checkpoints in nested subgraphs

Subgraph checkpoints use namespaced paths:

```python
{
    "configurable": {
        "thread_id": "main_session",
        "checkpoint_ns": "nix_team|flake_agent",  # Hierarchical path
        "checkpoint_id": "1ef7c6ba-5c71-6f90-8001-04f60f3c8173"
    }
}
```

Access subgraph state during interrupts:

```python
parent_state = graph.get_state(config, subgraphs=True)
for task in parent_state.tasks:
    if task.state:  # Available during interrupts
        subgraph_state = graph.get_state(task.state.config)
```

---

## Context compression and summary passing between agents

**This directly addresses your requirement to communicate via feature requests and bug reports without context pollution.**

### The core pattern: State transformation at boundaries

```python
class ParentState(TypedDict):
    messages: List[BaseMessage]
    agent_summaries: dict[str, str]

class ChildAgentState(TypedDict):
    feature_request: str          # Compressed input
    internal_messages: List[str]  # Private working memory
    bug_report: str               # Compressed output

def call_child_with_compression(state: ParentState) -> ParentState:
    # Compress: Extract only relevant feature request
    feature_request = summarize_for_child(state["messages"])
    
    # Child works with isolated context
    child_input = {"feature_request": feature_request}
    child_result = child_graph.invoke(child_input)
    
    # Compress: Only return structured bug report
    return {
        "agent_summaries": {
            "child_agent": child_result["bug_report"]
        },
        "messages": [AIMessage(content=f"Child completed: {child_result['bug_report'][:100]}...")]
    }
```

### Using LangMem's SummarizationNode for automatic compression

```python
from langmem.short_term import SummarizationNode

summarization_node = SummarizationNode(
    model=summarization_model,
    max_tokens=256,                    # Final output limit
    max_tokens_before_summary=256,     # When to trigger
    max_summary_tokens=128,            # Summary budget
    output_messages_key="summarized_messages"
)

# Add to graph before agent nodes
workflow.add_node("compress", summarization_node)
workflow.add_edge("compress", "agent")
```

### Token tracking to detect context constraints

```python
from langchain_core.messages.utils import trim_messages, count_tokens_approximately

def check_context_limit(state: AgentState) -> str:
    token_count = count_tokens_approximately(state["messages"])
    
    if token_count > 3500:
        return "summarize"
    elif token_count > 4000:
        return "truncate"
    return "continue"

builder.add_conditional_edges(
    "agent",
    check_context_limit,
    {"summarize": "summarization_node", "truncate": "trim_node", "continue": "next"}
)
```

### Implementing feature request/bug report communication

For your specific use case, define structured handoff types:

```python
from pydantic import BaseModel

class FeatureRequest(BaseModel):
    domain: str
    description: str
    priority: int
    context_summary: str  # Compressed, not full history

class BugReport(BaseModel):
    domain: str
    issue: str
    resolution: str
    affected_dependencies: List[str]

class DomainAgentState(TypedDict):
    incoming_requests: List[FeatureRequest]
    internal_context: List[BaseMessage]  # Private
    outgoing_reports: List[BugReport]

def domain_agent_wrapper(state: ParentState) -> ParentState:
    # Create structured request from parent context
    request = FeatureRequest(
        domain="nix",
        description=extract_task(state),
        priority=1,
        context_summary=summarize_relevant_context(state)
    )
    
    # Agent works in isolation
    result = nix_agent.invoke({"incoming_requests": [request]})
    
    # Return structured report only
    return {
        "reports": result["outgoing_reports"],
        "messages": [format_report_as_message(result["outgoing_reports"][-1])]
    }
```

---

## Memory management patterns for hierarchical isolation

### When to use threads vs. namespaces vs. subgraphs

| Strategy | Use Case | Isolation Level |
|----------|----------|-----------------|
| **Separate threads** | Completely independent sessions | Full isolation (different `thread_id`) |
| **Checkpoint namespaces** | Same workflow, different hierarchy levels | Agent-level (automatic in subgraphs) |
| **Subgraphs with different schemas** | Agents needing private working memory | Complete state isolation |
| **Private state keys** | Partial isolation within shared graph | Key-level (e.g., `alice_messages`) |

### Preventing context pollution: Private message histories

```python
class SwarmState(TypedDict):
    messages: List[BaseMessage]  # Shared coordination channel
    
class AliceState(TypedDict):
    alice_messages: List[BaseMessage]  # Private to Alice
    alice_scratchpad: str

def call_alice(state: SwarmState) -> SwarmState:
    # Alice gets her own message history
    alice_input = {"alice_messages": [extract_task(state["messages"])]}
    result = alice_graph.invoke(alice_input)
    
    # Only final output returns to shared state
    return {"messages": [result["alice_messages"][-1]]}
```

### Running summaries for long-lived agents

```python
from langmem.short_term import summarize_messages, RunningSummary

class AgentState(TypedDict):
    messages: List[BaseMessage]
    running_summary: RunningSummary | None

def agent_with_summary(state):
    result = summarize_messages(
        state["messages"],
        running_summary=state.get("running_summary"),
        model=summarization_model,
        max_tokens=256,
        max_tokens_before_summary=200,
    )
    
    response = llm.invoke(result.messages)
    
    return {
        "messages": [response],
        "running_summary": result.running_summary
    }
```

---

## Putting it together: Architecture for your Nix subflake DAG

Here's how these patterns combine for your specific use case:

```python
from typing import TypedDict, List
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

# Root coordinator state
class RootState(TypedDict):
    pending_requests: List[FeatureRequest]
    completed_reports: List[BugReport]
    coordination_log: List[str]

# Each domain agent has isolated state
class DomainAgentState(TypedDict):
    feature_request: FeatureRequest      # Input
    internal_context: List[BaseMessage]  # Private working memory
    bug_report: BugReport                # Output

def create_domain_agent(domain: str, dependencies: List[str]):
    """Create an agent node with isolated state for a domain."""
    
    def agent_wrapper(state: RootState) -> RootState:
        # Find request for this domain
        request = next(r for r in state["pending_requests"] if r.domain == domain)
        
        # Agent works in complete isolation
        agent_input = {"feature_request": request}
        result = domain_graphs[domain].invoke(agent_input)
        
        # Return only structured bug report
        return {
            "completed_reports": [result["bug_report"]],
            "coordination_log": [f"{domain} completed: {result['bug_report'].resolution[:50]}"]
        }
    
    return agent_wrapper

# Build graph matching flake structure
def build_flake_dag(flake_config: dict):
    builder = StateGraph(RootState)
    
    # Add supervisor
    builder.add_node("coordinator", coordinator_node)
    builder.add_edge(START, "coordinator")
    
    # Add domain agents from flake inputs
    for domain, config in flake_config["inputs"].items():
        agent = create_domain_agent(domain, config.get("inputs", []))
        builder.add_node(domain, agent)
    
    # Wire based on dependencies (respecting DAG order)
    builder.add_conditional_edges("coordinator", route_to_domain)
    
    for domain in flake_config["inputs"]:
        builder.add_edge(domain, "coordinator")
    
    return builder.compile(checkpointer=MemorySaver())
```

---

## Conclusion

LangGraph's architecture aligns well with your Nix subflake DAG use case. **State isolation through independent schemas** ensures each domain agent maintains private context. **State transformation at boundaries** implements your feature request/bug report communication pattern naturally. **Checkpoint namespaces** provide hierarchical persistence that mirrors your dependency structure.

The key architectural decisions for your implementation:

1. **Use function wrappers** (not compiled subgraphs as nodes) to enforce complete state isolation between domains
2. **Define structured types** (FeatureRequest, BugReport) for inter-agent communication instead of passing raw messages
3. **Implement summarization** at agent boundaries using LangMem's SummarizationNode or custom compression
4. **Leverage checkpoint namespaces** to maintain separate histories per domain while sharing thread_id
5. **Use get_state_history()** with checkpoint metadata to rewind specific agents while preserving external state

The framework provides the primitives; the architectural pattern of isolated agents communicating through compressed, structured messages is something you implement through state transformation functions at subgraph boundaries.
