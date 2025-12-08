The Coding Agent Tooling Landscape
There are essentially three tiers of coding capabilities you can wire into LangGraph agents:
Tier 1: Basic File Operations (Minimum Viable)
Simple Python tools for:

Read file — Path(path).read_text()
Write file — atomic writes with backup
Run bash — subprocess.run() with timeout
Git operations — commit, diff, status

This is what most tutorials show, and it works for simple cases but breaks down quickly on real codebases.
Tier 2: Semantic Code Operations (What Serena Provides)
Serena provides IDE-like tools to your LLM/coding agent. With it, the agent no longer needs to read entire files, perform grep-like searches or basic string replacements. Instead, it can use code-centric tools like find_symbol, find_referencing_symbols and insert_after_symbol. github
This is the key insight: semantic operations are dramatically more token-efficient. Instead of dumping 500 lines of code into context, the agent asks "where is the UserService.validateUser method defined?" and gets back a precise location.
Serena's semantic code analysis capabilities build on language servers using the widely implemented language server protocol (LSP). Equipped with these capabilities, Serena discovers and edits code just like a seasoned developer making use of an IDE's capabilities would. github
For your Nix subflake use case, this is perfect because Serena supports over 30 programming languages, including Nix, Rust, and Python github — exactly the stack you're working with.
Tier 3: Repository-Aware Context Management (What Aider Does)
Aider doesn't try to read your entire codebase. Instead, it creates what they call a "repository map" — essentially a structured index of your code. This gives the AI structural awareness without burning tokens on implementation details. The Omega Developer
When you ask to "add JWT authentication," it knows which files are relevant before diving into specifics. Aider uses a hierarchical approach to context management. The Omega Developer

Integrating MCP Tools with LangGraph Agents
The langchain-mcp-adapters package is the bridge you need. Here's how it works:
pythonfrom langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

# Configure MCP servers per subflake
async def create_subflake_agent(subflake_name: str, cwd: str):
    client = MultiServerMCPClient({
        "serena": {
            "command": "uvx",
            "args": [
                "--from", "git+https://github.com/oraios/serena",
                "serena", "start-mcp-server",
                "--workspace", cwd
            ],
            "transport": "stdio",
        }
    })
    
    tools = await client.get_tools()
    
    return create_react_agent(
        model="anthropic:claude-sonnet-4-20250514",
        tools=tools,
        prompt=f"You are an expert in the {subflake_name} subflake. Your CWD is {cwd}."
    )
The library allows you to connect to multiple MCP servers and load tools from them. GitHub This means each subflake agent can have its own Serena instance configured for that specific directory.

Architecture for Your Nix Subflake Agents
Here's how I'd structure the tooling per agent type:
Leaf Agents (hello-rs, hello-py, hello-wasm)
Each gets:

Serena MCP server — configured with --workspace pointing to the subflake directory, with the appropriate language server (rust-analyzer, pyright, etc.)
Domain-specific bash tools — wrapped to run inside nix develop:

python   @tool
   def run_in_devshell(command: str) -> str:
       """Run a command in the Nix devshell for this subflake."""
       result = subprocess.run(
           ["nix", "develop", "--command", "bash", "-c", command],
           cwd=self.subflake_path,
           capture_output=True, text=True, timeout=120
       )
       return result.stdout + result.stderr

Git tools — but scoped to the subflake's files

Supervisor Agents (root, hello-fancy)
These get:

Nix metadata tools — parse nix flake metadata --json
Test orchestration tools — run pytest at the root level
Delegation tools — invoke child agents via the patterns from part 1


The Key Insight: Tool Isolation = Context Isolation
Your original insight is correct: Terminal-based tools make the agent's actions explicit and auditable IKANGAI — but more importantly for your case, different toolsets create different cognitive scopes.
When the hello-rs agent only has access to:

find_symbol (Rust symbols only, via rust-analyzer)
cargo_test
cargo_build

...it literally cannot get distracted by Python code. The toolset enforces the isolation you want.
Compare to Composio's approach using specialized agents with distinct toolsets, each focused on specific tasks: CodeAnalyzer Agent analyzes codebases; Editor Agent manages navigation and file modifications. This specialization improves performance by allowing each agent to focus on a well-defined task. LangChain

Concrete Implementation Path
python# agent_factory.py
from dataclasses import dataclass
from typing import List
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

@dataclass
class SubflakeConfig:
    name: str
    path: str
    language: str  # "rust", "python", "nix", etc.
    dependencies: List[str]

async def create_domain_agent(config: SubflakeConfig):
    """Create an agent with tools scoped to a specific subflake."""
    
    # Serena provides semantic code tools via LSP
    mcp_client = MultiServerMCPClient({
        "serena": {
            "command": "uvx",
            "args": [
                "--from", "git+https://github.com/oraios/serena",
                "serena", "start-mcp-server",
                "--workspace", config.path
            ],
            "transport": "stdio",
        }
    })
    
    mcp_tools = await mcp_client.get_tools()
    
    # Add domain-specific tools
    domain_tools = build_domain_tools(config)
    
    return create_react_agent(
        model="anthropic:claude-sonnet-4-20250514",
        tools=mcp_tools + domain_tools,
        prompt=build_domain_prompt(config)
    )

def build_domain_tools(config: SubflakeConfig) -> list:
    """Build tools appropriate for this subflake's language."""
    
    @tool
    def run_tests() -> str:
        """Run the test suite for this subflake."""
        return run_in_nix_develop(config.path, get_test_command(config.language))
    
    @tool  
    def build() -> str:
        """Build this subflake."""
        return run_in_nix_develop(config.path, get_build_command(config.language))
    
    # Language-specific tools
    if config.language == "rust":
        @tool
        def cargo_check() -> str:
            """Run cargo check for fast feedback."""
            return run_in_nix_develop(config.path, "cargo check")
        return [run_tests, build, cargo_check]
    
    elif config.language == "python":
        @tool
        def pytest_verbose(test_path: str = "") -> str:
            """Run pytest with verbose output."""
            cmd = f"pytest -v {test_path}" if test_path else "pytest -v"
            return run_in_nix_develop(config.path, cmd)
        return [run_tests, build, pytest_verbose]
    
    return [run_tests, build]

Feature Request / Bug Report Protocol
When a parent agent needs to delegate to a child, it should communicate via structured messages, not raw context:
pythonfrom pydantic import BaseModel

class FeatureRequest(BaseModel):
    domain: str
    description: str
    acceptance_criteria: List[str]
    context_summary: str  # 100 words max, compressed from parent's context

class BugReport(BaseModel):
    domain: str
    symptom: str
    reproduction_steps: List[str]
    relevant_test: str | None

class TaskResult(BaseModel):
    status: Literal["completed", "blocked", "needs_clarification"]
    summary: str  # What was done, in 50 words
    files_changed: List[str]
    tests_passing: bool
    follow_up_needed: str | None
This structured protocol prevents the parent from leaking its full context into the child's window.
