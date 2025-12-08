
When humans do this sort of thing, they need a sort of "same page" to look at.  Often that's a github issue, or jira, or whatever.  I've recently learnd about "beads" which seems to provide some of that: https://github.com/steveyegge/beads

I'm not sure if the "issues" it creates are actually uploaded to github or if they could be stored locally somehow and then referenced by the agents.  I'm worried that agents will get into a back and forth where they're drifting away from the original intent, so it might be helpful for them to say things to each other like "please see issue 1234" rather than ping ponging back and forth while the substance of the issue gets lost.

------

Beads: A Perfect Fit for Your "Shared Page" Problem
Beads is a lightweight memory system for coding agents, using a graph-based issue tracker. Four kinds of dependencies work to chain your issues together like beads, making them easy for agents to follow for long distances, and reliably perform complex task streams in the right order. github
Key Properties That Match Your Needs
1. Completely Local, Git-Versioned (Not GitHub Issues)
Issues are backed by git, but through a clever design it manages to act like a managed, centrally hosted SQL database shared by all of the agents working on a project (repo), even across machines. github
The issues live in .beads/issues.jsonl — a JSONL file committed to your repo. No external service required. This is perfect for your Nix subflake structure: each subflake could have its own .beads/ directory, or you could have a single shared one at the root.
2. Hash-Based IDs Designed for Multi-Agent Workflows
Hash-based IDs eliminate merge conflicts and collision issues. Previous versions used sequential IDs (bd-1, bd-2, bd-3...) which caused frequent collisions when multiple agents or branches created issues concurrently. Version 0.20.1 switches to hash-based IDs (bd-a1b2, bd-f14c, bd-3e7a...) that are collision-resistant and merge-friendly. github
This directly solves the problem of multiple subflake agents creating issues simultaneously.
3. Dependency Tracking That Mirrors Your DAG
Four dependency types: blocks (hard blocker - issue cannot start until blocker is resolved), related (soft relationship - issues are connected but not blocking), parent-child (hierarchical relationship), discovered-from (issue discovered during work on another issue). github
The discovered-from type is particularly useful for your pattern — when hello-fancy discovers a bug in hello-py, it creates an issue with --type discovered-from, and that relationship is tracked.
4. The "Same Page" Reference Pattern You Want
Agents can always ground themselves by referencing the issue:
bash# Agent says "please see bd-a1b2" and any other agent can run:
bd show bd-a1b2 --json

# Returns full context: description, status, dependencies, audit trail
This prevents the ping-pong drift — instead of re-explaining the problem each round, agents reference the canonical issue.
5. JSON Output for LangGraph Integration
Agent-friendly: --json flags for programmatic integration github
Every command supports --json, making it trivial to wrap as LangGraph tools:
python@tool
def create_bug_report(title: str, description: str, blocks: list[str] = None) -> dict:
    """Create a bug report in the local issue tracker."""
    cmd = ["bd", "create", title, "-d", description, "-t", "bug", "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=subflake_path)
    issue = json.loads(result.stdout)
    
    if blocks:
        for blocker_id in blocks:
            subprocess.run(["bd", "dep", "add", issue["id"], blocker_id, "--type", "blocks"])
    
    return issue

@tool  
def get_issue_context(issue_id: str) -> dict:
    """Get the full context of an issue for grounding a conversation."""
    result = subprocess.run(["bd", "show", issue_id, "--json"], capture_output=True, text=True)
    return json.loads(result.stdout)

@tool
def find_ready_work() -> list[dict]:
    """Find issues with no blockers that are ready to work on."""
    result = subprocess.run(["bd", "ready", "--json"], capture_output=True, text=True)
    return json.loads(result.stdout)

Agent Mail for Real-Time Coordination
For the actual back-and-forth conversation between agents, there's a complementary project:
A mail-like coordination layer for coding agents, exposed as an HTTP-only FastMCP server. It gives agents memorable identities, an inbox/outbox, searchable message history, and voluntary file reservation "leases" to avoid stepping on each other. Think of it as asynchronous email + directory + change-intent signaling for your agents, backed by Git (for human-auditable artifacts) and SQLite (for indexing and queries). GitHub
Optional Agent Mail - Real-time multi-agent coordination (<100ms vs 2-5s git sync, 98.5% reduction in git traffic) github
The combination would be:

Beads = the "issue tracker" (shared state, canonical problem definition)
Agent Mail = the "conversation channel" (real-time messages referencing issues)


Proposed Integration Pattern
Here's how I'd structure the agent-to-agent communication using Beads as the "same page":
pythonfrom pydantic import BaseModel
from typing import Literal

class IssueReference(BaseModel):
    """All inter-agent messages reference a beads issue"""
    issue_id: str  # e.g., "bd-a1b2"
    action: Literal["created", "updated", "needs_verification", "verified", "rejected"]
    summary: str  # Brief context, but full details are in the issue

class DependencyRequest(BaseModel):
    """Request sent from dependent to dependency"""
    issue_id: str
    request_type: Literal["bug_report", "feature_request", "support_request"]
    requester_agent: str  # e.g., "hello-fancy"
    # The actual content is in the beads issue, not here
    
class VerificationRequest(BaseModel):
    """Sent when fix is ready for testing"""
    issue_id: str
    resolver_agent: str
    test_instructions: str
    commit_hash: str  # What to test

class VerificationResponse(BaseModel):
    """Sent after requester tests the fix"""
    issue_id: str
    result: Literal["pass", "fail"]
    notes: str
```

### The Workflow
```
1. hello-fancy discovers a bug in hello-py's output
   └─> bd create "String concatenation fails for unicode" -t bug -p 1 --json
   └─> Sends DependencyRequest(issue_id="bd-a1b2", ...) to hello-py agent

2. hello-py agent receives request
   └─> bd show bd-a1b2 --json  # Gets full context from the "same page"
   └─> Works on fix (possibly delegating to hello-rs)
   └─> bd update bd-a1b2 --status in_progress
   
3. hello-py completes fix
   └─> bd update bd-a1b2 --status awaiting_verification
   └─> Sends VerificationRequest(issue_id="bd-a1b2", commit_hash="abc123")

4. hello-fancy tests the fix
   └─> bd show bd-a1b2 --json  # Checks the canonical issue state
   └─> Runs tests in its context
   └─> Sends VerificationResponse(issue_id="bd-a1b2", result="pass")

5. hello-py closes the issue
   └─> bd close bd-a1b2 --reason "Verified by hello-fancy"
The key insight: the message payloads are thin (just issue IDs and actions), while the issue itself is the source of truth. This prevents drift because any agent can always bd show <issue-id> to re-ground themselves.

Audit Trail Prevents Lost Context
Beads even improves work auditability. The issue tracker has a sophisticated audit trail, which agents can use to reconstruct complex operations that may have spanned multiple sessions. github
If agents do drift, the audit trail shows what happened:
bashbd show bd-a1b2 --json | jq '.audit_trail'
# Shows: created by hello-fancy, updated by hello-py, status changes, etc.

Integration with Your LangGraph Architecture
Here's how Beads tools would fit into your domain agent factory:
pythondef build_beads_tools(subflake_path: str, agent_name: str) -> list:
    """Build beads tools scoped to a subflake."""
    
    @tool
    def create_issue(
        title: str, 
        description: str, 
        issue_type: Literal["bug", "feature", "task"] = "task",
        priority: int = 2,
        discovered_from: str | None = None
    ) -> dict:
        """Create a new issue in the local tracker."""
        cmd = ["bd", "create", title, "-d", description, "-t", issue_type, 
               "-p", str(priority), "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=subflake_path)
        issue = json.loads(result.stdout)
        
        if discovered_from:
            subprocess.run(
                ["bd", "dep", "add", issue["id"], discovered_from, "--type", "discovered-from"],
                cwd=subflake_path
            )
        return issue
    
    @tool
    def get_issue(issue_id: str) -> dict:
        """Get full issue details - use this to ground yourself on what's being discussed."""
        result = subprocess.run(
            ["bd", "show", issue_id, "--json"], 
            capture_output=True, text=True, cwd=subflake_path
        )
        return json.loads(result.stdout)
    
    @tool
    def update_issue_status(
        issue_id: str, 
        status: Literal["open", "in_progress", "awaiting_verification", "closed"]
    ) -> dict:
        """Update issue status."""
        cmd = ["bd", "update", issue_id, "--status", status, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=subflake_path)
        return json.loads(result.stdout)
    
    @tool
    def get_incoming_requests() -> list[dict]:
        """Get issues assigned to this agent that are ready to work on."""
        result = subprocess.run(
            ["bd", "ready", "--assignee", agent_name, "--json"],
            capture_output=True, text=True, cwd=subflake_path
        )
        return json.loads(result.stdout)
    
    @tool
    def get_dependency_tree(issue_id: str) -> str:
        """Visualize the dependency tree for an issue."""
        result = subprocess.run(
            ["bd", "dep", "tree", issue_id],
            capture_output=True, text=True, cwd=subflake_path
        )
        return result.stdout
    
    return [create_issue, get_issue, update_issue_status, get_incoming_requests, get_dependency_tree]

One Beads DB or Multiple?
You have two options:
Option A: Single .beads/ at repo root

All agents share one issue database
Issues use labels or assignee to route to correct subflake agent
Simpler, but all agents see all issues

Option B: .beads/ per subflake

Each subflake has isolated issue tracking
Cross-subflake issues require explicit "external reference" linking
More isolation, matches your context isolation goals

I'd lean toward Option A with labels like subflake:hello-rs, subflake:hello-py — this lets the root supervisor see all issues while individual agents filter by their domain.

Summary
Beads is an excellent fit because:

Local-first — No GitHub/Jira dependency, just .beads/ in your repo
Multi-agent native — Hash IDs designed for concurrent agent workflows
Dependency-aware — Four relationship types map to your DAG structure
JSON API — Easy to wrap as LangGraph tools
Prevents drift — The issue becomes the "same page" agents reference by ID
Audit trail — Full history if you need to debug agent behavior

The pattern is: thin messages (issue IDs + actions) + fat shared state (beads issues). Agents never re-explain the problem in messages — they say "see bd-a1b2" and the other agent queries the canonical issue.
