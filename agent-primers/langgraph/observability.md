# Observability and Human-in-the-Loop Patterns with Langfuse for LangGraph Multi-Agent Systems

Langfuse is an **open-source LLM observability platform** that provides comprehensive tracing, token/cost tracking, evaluation, and debugging capabilities—making it an excellent alternative to LangSmith for teams who prefer self-hosted solutions or want to avoid vendor lock-in. This report covers the complete toolkit for integrating Langfuse with LangGraph: from self-hosted deployment to implementing sophisticated hierarchical tracing patterns for production multi-agent systems.

## Langfuse is open source and can be self-hosted using Docker

Unlike LangSmith (which requires a paid Enterprise License for self-hosting), Langfuse is **fully open source under the MIT license** and can be deployed on your own infrastructure using Docker. This makes it ideal for teams with data privacy requirements or those who want complete control over their observability stack.

**Self-hosting architecture** consists of two main containers plus supporting services:

```bash
# Core containers
langfuse/langfuse:3        # Web UI and API (port 3000)
langfuse/langfuse-worker:3 # Background worker for event processing

# Required infrastructure
PostgreSQL 12+             # State storage
Redis                      # Caching and queuing
ClickHouse                 # Analytics (v3+)
S3-compatible storage      # Trace event upload (v3+)
```

**Docker Compose deployment** is the fastest way to get started for testing and low-scale deployments:

```bash
# Clone the Langfuse repository
git clone https://github.com/langfuse/langfuse.git
cd langfuse

# Start all services
docker compose up

# Access the UI at http://localhost:3000
```

For production deployments, Langfuse recommends **Kubernetes with Helm** for high-availability and horizontal scaling. The queued ingestion architecture (traces → S3 → Redis queue → ClickHouse) ensures high spikes in request load don't cause timeouts.

**Environment configuration** requires these core variables:

```bash
# Required for web container
DATABASE_URL=postgresql://...
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=mysecret
SALT=mysalt
ENCRYPTION_KEY=$(openssl rand -hex 32)

# Required for v3 architecture
CLICKHOUSE_URL=http://clickhouse:8123
REDIS_HOST=localhost
LANGFUSE_S3_EVENT_UPLOAD_BUCKET=my-bucket
```

Langfuse supports headless initialization via `LANGFUSE_INIT_*` environment variables, enabling infrastructure-as-code and automated deployment pipelines without manual UI setup.

## The CallbackHandler integrates Langfuse tracing with LangGraph

Langfuse integrates with LangGraph through **LangChain's callback system**. The `CallbackHandler` from `langfuse.langchain` automatically captures traces of your LangGraph executions, including LLM calls, tool invocations, and state transitions.

**Basic integration pattern**:

```python
from langfuse.langchain import CallbackHandler
from langgraph.graph import StateGraph
from langchain_openai import ChatOpenAI

# Initialize the Langfuse callback handler
langfuse_handler = CallbackHandler()

# Build your LangGraph
graph_builder = StateGraph(State)
llm = ChatOpenAI(model="gpt-4o")

def chatbot(state: State):
    return {"messages": [llm.invoke(state["messages"])]}

graph_builder.add_node("chatbot", chatbot)
graph_builder.set_entry_point("chatbot")
graph_builder.set_finish_point("chatbot")
graph = graph_builder.compile()

# Pass the handler in the config
for chunk in graph.stream(
    {"messages": [HumanMessage(content="Hello!")]},
    config={"callbacks": [langfuse_handler]}
):
    print(chunk)
```

**Combining with the Langfuse SDK** gives you more control over trace attributes:

```python
from langfuse import observe, get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

@observe()  # Automatically creates a trace
def process_user_query(user_input: str):
    langfuse = get_client()
    
    # Propagate attributes to all child observations
    with propagate_attributes(
        session_id="session-1234",
        user_id="user-5678",
        tags=["production", "chatbot"]
    ):
        # Handler inherits the current trace context
        langfuse_handler = CallbackHandler()
        
        result = graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config={"callbacks": [langfuse_handler]}
        )
    
    return result
```

## Hierarchical traces capture nested agent execution paths

Langfuse's data model is designed around **traces, observations, and sessions**—perfectly suited for multi-agent hierarchies where parent agents delegate to child agents.

**Core concepts**:

| Entity | Purpose | Example |
|--------|---------|---------|
| **Trace** | Top-level execution context | Single user request |
| **Observation** | Unit of work within a trace | LLM call, tool invocation, span |
| **Session** | Groups related traces | Multi-turn conversation thread |

**Observation types** form a hierarchical tree:

- **SPAN**: Generic execution unit (function call, retrieval step)
- **GENERATION**: LLM API call with model, usage, and cost details
- **EVENT**: Discrete point-in-time action (log, error)

The `parent_observation_id` field creates the tree structure, which Langfuse visualizes in the UI:

```
Agent Execution
├─ LLM Call: Classify intent [0.4s]
│  └─ Led to retrieval decision
├─ Retrieval: Search database [0.6s]
│  └─ Used 3 documents as context
└─ LLM Call: Generate response [1.2s]
   └─ Input included retrieval results
```

**Streaming from subgraphs** in LangGraph requires `subgraphs=True`:

```python
for namespace, chunk in graph.stream(
    {"input": "hello"},
    stream_mode="updates",
    subgraphs=True  # Critical for hierarchical streaming
):
    # namespace = () for parent
    # namespace = ('child_node:task_id',) for subgraph
    print(f"Path: {namespace}, Data: {chunk}")
```

## Correlating traces across multi-agent hierarchies with shared trace IDs

For multi-agent systems where one LangGraph agent uses other agents, you need to ensure all observations land in a **single unified trace**. Langfuse provides several mechanisms for this.

**Predefined trace IDs** let you correlate traces from external systems:

```python
from langfuse import get_client, Langfuse
from langfuse.langchain import CallbackHandler

langfuse = get_client()

# Generate deterministic trace ID from external system
external_request_id = "request_12345"
predefined_trace_id = Langfuse.create_trace_id(seed=external_request_id)

# All agents will use this trace ID
langfuse_handler = CallbackHandler()

# Wrap in a trace context
with langfuse.start_as_current_observation(
    as_type="span",
    name="multi-agent-orchestration",
    trace_context={"trace_id": predefined_trace_id}
):
    # Parent agent
    parent_result = parent_graph.invoke(
        {"query": "complex task"},
        config={"callbacks": [langfuse_handler]}
    )
```

**The `run_id` approach** for LangChain/LangGraph:

```python
from uuid import uuid4
from langfuse.callback import CallbackHandler

# Shared run_id becomes the trace_id
run_id = uuid4()
langfuse_handler = CallbackHandler()

# All invocations with this run_id are grouped
graph.invoke(
    {"input": input_data},
    config={
        "callbacks": [langfuse_handler],
        "run_id": run_id
    }
)
```

**Attribute propagation** ensures consistent metadata across all observations:

```python
from langfuse import propagate_attributes

with propagate_attributes(
    user_id="user_123",
    session_id="session_abc",
    metadata={"agent_hierarchy": "supervisor->research->writer"},
    tags=["multi-agent", "production"]
):
    # All nested observations automatically inherit these attributes
    result = orchestrator_graph.invoke(query, config=config)
```

## Sessions group multi-turn conversations across traces

For chatbots and conversational agents, **sessions** group related traces together and provide a session replay view in the Langfuse UI.

```python
from langfuse import observe, propagate_attributes

@observe()
def handle_chat_turn(user_message: str, session_id: str):
    with propagate_attributes(session_id=session_id):
        langfuse_handler = CallbackHandler()
        
        result = graph.invoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"callbacks": [langfuse_handler]}
        )
    return result

# Each turn creates a separate trace, but all are grouped by session
handle_chat_turn("What's your return policy?", session_id="chat-123")
handle_chat_turn("Can I return opened items?", session_id="chat-123")
handle_chat_turn("How do I start a return?", session_id="chat-123")
```

The session detail view aggregates metrics across all traces and shows the complete conversation flow.

## Token usage and cost tracking happens automatically

Langfuse automatically tracks **token usage and costs** for major LLM providers. For supported models (OpenAI, Anthropic, etc.), costs are inferred from the model name.

**Automatic tracking** via the callback handler:

```python
# Token usage is captured automatically from LLM responses
result = graph.invoke(input_data, config={"callbacks": [langfuse_handler]})

# In Langfuse UI, you'll see:
# - Input tokens: 1,203
# - Output tokens: 1,516  
# - Total cost: $0.0234
# - Latency: 2.4s
```

**Manual token tracking** for custom LLM calls:

```python
from langfuse import get_client

langfuse = get_client()

with langfuse.start_as_current_observation(
    as_type="generation",
    name="anthropic-completion",
    model="claude-3-opus-20240229",
    input=[{"role": "user", "content": "Hello, Claude"}]
) as generation:
    response = anthropic_client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello, Claude"}]
    )
    
    generation.update(
        output=response.content[0].text,
        usage_details={
            "input": response.usage.input_tokens,
            "output": response.usage.output_tokens,
            "cache_read_input_tokens": response.usage.cache_read_input_tokens
        }
    )
```

**The Daily Metrics API** enables downstream billing and analytics:

```bash
GET /api/public/metrics/daily?traceName=my-agent&userId=john&limit=30
```

Returns aggregated usage and cost broken down by input/output tokens, filterable by application type, user, or tags.

## The @observe decorator instruments Python functions

The `@observe()` decorator provides the simplest way to instrument your LangGraph applications, automatically capturing function inputs, outputs, execution time, and errors.

**Basic usage**:

```python
from langfuse import observe, get_client

@observe()
def my_data_processing_function(data, parameter):
    # Processing logic
    return {"processed_data": data, "status": "ok"}

@observe(name="llm-call", as_type="generation")
async def my_async_llm_call(prompt_text):
    # Async LLM call
    return "LLM response"

# Input/output and timings are automatically captured
result = my_data_processing_function(input_data, param)

# Flush in short-lived applications
langfuse = get_client()
langfuse.flush()
```

**Nested functions create hierarchical traces**:

```python
@observe()
def orchestrator(query: str):
    # This becomes the root trace
    intent = classify_intent(query)
    
    if intent == "search":
        return search_agent(query)
    else:
        return chat_agent(query)

@observe()
def classify_intent(query: str):
    # This becomes a child span
    return llm.invoke(f"Classify: {query}")

@observe()
def search_agent(query: str):
    # This also becomes a child span
    results = retriever.invoke(query)
    return llm.invoke(f"Summarize: {results}")
```

**Updating observations with additional context**:

```python
from langfuse import observe, get_client

@observe(as_type="generation")
def llm_with_context(prompt: str):
    langfuse = get_client()
    
    # Update the current observation
    langfuse.update_current_generation(
        name="Contextual LLM Call",
        model="gpt-4o",
        metadata={"temperature": 0.7}
    )
    
    # Update the trace itself
    langfuse.update_current_trace(
        name="Agent Run",
        session_id="session-123",
        user_id="user-456",
        tags=["production"]
    )
    
    return llm.invoke(prompt)
```

## Context managers provide fine-grained control

For more control than decorators, use **context managers** which automatically handle span start/end and context propagation:

```python
from langfuse import get_client

langfuse = get_client()

# Create a span using a context manager
with langfuse.start_as_current_observation(
    as_type="span", 
    name="process-request"
) as span:
    # Your processing logic
    span.update(output="Processing complete")
    
    # Create a nested generation for an LLM call
    with langfuse.start_as_current_observation(
        as_type="generation",
        name="llm-response",
        model="gpt-4o"
    ) as generation:
        result = llm.invoke(prompt)
        generation.update(output=result)

# All spans are automatically closed when exiting context blocks
langfuse.flush()
```

## Human-in-the-loop uses LangGraph's interrupt() with Langfuse tracing

While Langfuse doesn't provide its own interrupt mechanism, it **traces LangGraph's built-in `interrupt()` function**, giving you full visibility into human-in-the-loop workflows.

**Basic interrupt with tracing**:

```python
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver
from langfuse.langchain import CallbackHandler

langfuse_handler = CallbackHandler()

def human_feedback_node(state):
    """Node that pauses for human input"""
    feedback = interrupt("Please provide feedback:")
    # Execution resumes here with human's response
    return {"user_feedback": feedback}

# Compile with checkpointer
memory = InMemorySaver()
graph = builder.compile(checkpointer=memory)

config = {
    "configurable": {"thread_id": "1"},
    "callbacks": [langfuse_handler]
}

# Run until interrupt - Langfuse captures the trace up to this point
result = graph.invoke({"input": "hello"}, config)
# result["__interrupt__"] contains the interrupt value

# Resume with human input - Langfuse continues the same trace
result = graph.invoke(Command(resume="approved!"), config)
```

**Approval workflow pattern**:

```python
from typing import Literal

def approval_node(state) -> Command[Literal["proceed", "cancel"]]:
    is_approved = interrupt({
        "question": "Approve this action?",
        "details": state["action_details"]
    })
    return Command(goto="proceed" if is_approved else "cancel")
```

In Langfuse, you'll see the complete trace including:
- The state at the time of interrupt
- The human's response
- The subsequent execution path

## State modification and checkpoint forking enable rollback

LangGraph's `update_state()` and checkpoint history work seamlessly with Langfuse tracing. Each state modification creates observations you can analyze.

**Modifying state mid-execution**:

```python
from langfuse.langchain import CallbackHandler

langfuse_handler = CallbackHandler()
config = {
    "configurable": {"thread_id": "1"},
    "callbacks": [langfuse_handler]
}

# Get current state
snapshot = graph.get_state(config)
print(snapshot.values)  # Current state
print(snapshot.next)    # Next node to execute

# Update state (e.g., inject human feedback)
graph.update_state(
    config,
    values={"messages": [AIMessage(content="Modified response")]},
    as_node="human"
)

# Continue from modified state - Langfuse traces this too
result = graph.invoke(None, config)
```

**Time-travel debugging with checkpoint forking**:

```python
# Get full state history
states = list(graph.get_state_history(config))

# Find checkpoint before the problematic step
selected_state = states[1]  # Second most recent

# Fork with modified input
new_config = graph.update_state(
    selected_state.config,
    values={"topic": "corrected input"}
)

# Resume from fork point - creates new execution branch
# Langfuse will show this as a new trace
result = graph.invoke(None, {
    **new_config,
    "callbacks": [langfuse_handler]
})
```

**Rollback and retry with guidance**:

```python
def rollback_and_retry(graph, config, guidance: str):
    states = list(graph.get_state_history(config))
    previous_state = states[1]  # Before problematic step
    
    # Add guidance to messages
    guidance_message = HumanMessage(content=f"GUIDANCE: {guidance}")
    current_messages = previous_state.values.get("messages", [])
    
    new_config = graph.update_state(
        previous_state.config,
        {"messages": current_messages + [guidance_message]}
    )
    
    return graph.invoke(None, {
        **new_config,
        "callbacks": [CallbackHandler()]
    })
```

## Scores enable custom evaluation metrics

Langfuse's scoring system allows you to attach **evaluation metrics** to traces and observations. Scores can be numeric, categorical, or boolean.

**Scoring from within traced code**:

```python
from langfuse import observe, get_client

@observe()
def process_with_scoring(query: str):
    langfuse = get_client()
    
    result = llm.invoke(query)
    
    # Score the current observation
    langfuse.score_current_span(
        name="response_quality",
        value=0.85,
        data_type="NUMERIC",
        comment="High relevance to query"
    )
    
    # Score the entire trace
    langfuse.score_current_trace(
        name="user_satisfaction",
        value="positive",
        data_type="CATEGORICAL"
    )
    
    return result
```

**External scoring via API** (for async evaluation pipelines):

```python
from langfuse import get_client

langfuse = get_client()

langfuse.create_score(
    name="fact_check_accuracy",
    value=0.95,
    trace_id="abcdef1234567890abcdef1234567890",
    observation_id="1234567890abcdef",  # Optional
    data_type="NUMERIC",
    comment="Source verified for 95% of claims."
)
```

**LLM-as-a-Judge evaluators** can be configured in the Langfuse UI to automatically score traces:

1. Navigate to Evaluators page → "+ Set up Evaluator"
2. Configure the judge LLM connection (OpenAI, Anthropic, etc.)
3. Define the evaluation prompt with variables from your traces
4. Set scoring format (numeric, categorical, boolean)
5. The evaluator runs automatically on matching traces

Each evaluator execution creates its own trace, giving you visibility into the evaluation process itself.

## Custom callback handlers expose Prometheus metrics

For production observability, create custom callback handlers that export metrics to **Prometheus, Datadog, or other monitoring systems**:

```python
from prometheus_client import Counter, Histogram, start_http_server
from langchain_core.callbacks import BaseCallbackHandler
import time

REQUEST_LATENCY = Histogram('langgraph_latency_seconds', 'Request latency')
TOTAL_TOKENS = Counter('langgraph_tokens_total', 'Tokens processed',
                       ['model_name', 'token_type'])
ERRORS = Counter('langgraph_errors_total', 'Total errors', ['error_type'])

class PrometheusHandler(BaseCallbackHandler):
    def __init__(self):
        self.start_time = None
    
    def on_chain_start(self, serialized, inputs, **kwargs):
        self.start_time = time.time()
    
    def on_chain_end(self, outputs, **kwargs):
        REQUEST_LATENCY.observe(time.time() - self.start_time)
    
    def on_llm_end(self, response, **kwargs):
        usage = response.llm_output.get('token_usage', {})
        model = response.llm_output.get('model_name', 'unknown')
        TOTAL_TOKENS.labels(model_name=model, token_type='prompt').inc(
            usage.get('prompt_tokens', 0))
        TOTAL_TOKENS.labels(model_name=model, token_type='completion').inc(
            usage.get('completion_tokens', 0))
    
    def on_llm_error(self, error, **kwargs):
        ERRORS.labels(error_type=type(error).__name__).inc()

# Start Prometheus metrics server
start_http_server(8000)  # Expose /metrics endpoint

# Use both handlers together
config = {
    "callbacks": [
        CallbackHandler(),      # Langfuse tracing
        PrometheusHandler()     # Prometheus metrics
    ]
}
```

**Token budget enforcement**:

```python
class TokenBudgetHandler(BaseCallbackHandler):
    def __init__(self, max_tokens: int = 50000, alert_threshold: float = 0.8):
        self.max_tokens = max_tokens
        self.alert_threshold = alert_threshold
        self.total_tokens = 0
    
    def on_llm_end(self, response, **kwargs):
        usage = response.llm_output.get('token_usage', {})
        self.total_tokens += usage.get('total_tokens', 0)
        
        usage_ratio = self.total_tokens / self.max_tokens
        if usage_ratio >= 1.0:
            raise TokenBudgetExceededError(
                f"Budget exceeded: {self.total_tokens}/{self.max_tokens}")
        elif usage_ratio >= self.alert_threshold:
            self._send_alert(usage_ratio)
```

## Loop detection and recursion limits prevent runaway agents

Production deployments need mechanisms to detect stuck agents. Combine LangGraph's built-in limits with Langfuse tracing for visibility:

```python
from langgraph.errors import GraphRecursionError
from langfuse.langchain import CallbackHandler

langfuse_handler = CallbackHandler()

# Set recursion limit (default is 25)
config = {
    "recursion_limit": 50,
    "callbacks": [langfuse_handler]
}

try:
    result = graph.invoke(inputs, config)
except GraphRecursionError:
    # Langfuse will have captured all iterations up to this point
    logging.error("Agent stuck in loop - check Langfuse trace for details")
    return get_graceful_failure_response()
```

**Custom loop detection state**:

```python
def should_continue(state) -> str:
    recent_actions = state["action_history"][-5:]
    
    # Check for repetition (same action 5 times)
    if len(set(recent_actions)) == 1:
        return "loop_detected_handler"
    
    # Check for oscillation (A->B->A->B pattern)
    if len(recent_actions) >= 4:
        if (recent_actions[-1] == recent_actions[-3] and
            recent_actions[-2] == recent_actions[-4]):
            return "oscillation_handler"
    
    return "continue"
```

## Five streaming modes provide granular control over updates

LangGraph's streaming modes work with Langfuse tracing. Each mode captures different levels of detail:

| Mode | Langfuse Captures | Use Case |
|------|-------------------|----------|
| `values` | Full state after each step | Complete state snapshots |
| `updates` | State deltas only | Incremental change tracking |
| `messages` | LLM tokens + metadata | Token-by-token streaming |
| `custom` | User-defined progress | Progress indicators |
| `debug` | Maximum execution info | Detailed debugging |

**Token-by-token streaming with tracing**:

```python
from langfuse.langchain import CallbackHandler

langfuse_handler = CallbackHandler()

async for msg, metadata in graph.astream(
    {"topic": "cats"},
    stream_mode="messages",
    config={"callbacks": [langfuse_handler]}
):
    if metadata["langgraph_node"] == "write_poem":
        print(msg.content, end="")  # Stream only from specific node
```

**Custom progress streaming**:

```python
from langgraph.config import get_stream_writer

def long_running_tool(query: str):
    writer = get_stream_writer()
    writer({"status": "starting", "progress": 0})
    # ... processing ...
    writer({"status": "progress", "progress": 50})
    # ... more processing ...
    writer({"status": "complete", "progress": 100})
    return "result"

# Consume with stream_mode="custom"
for chunk in graph.stream(
    input_data,
    stream_mode=["updates", "custom"],
    config={"callbacks": [langfuse_handler]}
):
    print(chunk)
```

## OpenTelemetry integration enables unified tracing

Langfuse's Python SDK v3 is built on **OpenTelemetry**, enabling integration with third-party instrumented libraries and cross-service distributed tracing.

**Third-party library compatibility**:

```python
from langfuse import Langfuse

# Third-party OTEL-instrumented libraries integrate automatically
langfuse = Langfuse()

# Spans from HTTP clients, databases, etc. are captured
# and nested within your Langfuse traces
```

**Filtering instrumentation scopes**:

```python
from langfuse import Langfuse

# Filter out database spans to reduce noise
langfuse = Langfuse(
    blocked_instrumentation_scopes=["sqlalchemy", "psycopg"]
)
```

**Sampling for high-volume applications**:

```python
from langfuse import Langfuse

# Sample approximately 20% of traces
langfuse_sampled = Langfuse(sample_rate=0.2)
```

## Conclusion

Building observable, controllable multi-agent systems with LangGraph and Langfuse requires combining several key capabilities:

**For self-hosted deployments**: Use Docker Compose for development and testing, Kubernetes with Helm for production. The v3 architecture with ClickHouse and S3 provides horizontal scaling and high-throughput ingestion.

**For tracing**: Use the `CallbackHandler` for automatic LangGraph tracing, combine with `@observe()` decorators for custom function instrumentation, and leverage `propagate_attributes()` for consistent metadata across hierarchical agent systems.

**For human intervention**: LangGraph's `interrupt()` function is fully traced by Langfuse. Use `update_state()` for direct state modification and checkpoint history for time-travel debugging when agents need rollback.

**For evaluation**: Implement custom scores via the SDK or API, set up LLM-as-a-Judge evaluators in the UI for automated quality assessment, and use the Metrics API for downstream analytics and billing.

**For production reliability**: Combine Langfuse tracing with custom Prometheus callback handlers, enforce token budgets with alert thresholds, add loop detection in conditional edges, and use sessions to group multi-turn conversations.

The key architectural insight is that **Langfuse complements LangGraph's checkpointing**—while LangGraph manages execution state and enables interrupts/rollback, Langfuse provides the observability layer to understand what happened, why it happened, and how to improve it. For teams requiring self-hosted solutions, Langfuse's open-source model and Docker-based deployment make it an excellent choice for production multi-agent systems.
