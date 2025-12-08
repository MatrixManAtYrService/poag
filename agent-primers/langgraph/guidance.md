Based on my research, here are the most relevant projects and research you should be aware of. They fall into a few distinct categories:

Most Similar to Your Approach: Codebase Partitioning for Agent Boundaries
agentic-cursorrules
GitHub: github.com/s-smits/agentic-cursorrules GitHub
This is the closest match to your philosophy. It partitions large codebases into domain-specific contexts for multi-agent workflows, generating isolated markdown rule files that prevent agent conflicts by giving them explicit file-tree boundaries. GitHub
The core insight is identical to yours: "Traditional workflows drown agents in context they don't need. Agentic-cursorrules solves this by keeping each agent inside a clearly defined slice of the tree. Conversations stay focused, diffs stay local, and coordination overhead drops because your agents aren't trying to understand the entire universe at once." GitHub
Key lessons you can borrow:

They generate per-domain markdown files (like @agent_backend_api.md) that define operational boundaries GitHub
Each agent file contains a visual tree of only the files that matter to that domain, along with instructions to "only reference and modify files within this structure" DeepWiki
They use YAML config to define boundaries: tree_focus: ["backend/api", "frontend/dashboard", "shared/utils"]

Difference from your approach: They're doing static file-tree partitioning, while you're using the Nix dependency DAG to derive boundaries. Your approach is more principled because the boundaries have semantic meaning (actual dependencies), not just directory structure.

Academic Research: MASAI (Modular Architecture for Software-engineering AI)
Paper: arxiv.org/abs/2406.11638
GitHub: github.com/masai-dev-agent/masai
MASAI proposes a Modular Architecture for Software-engineering AI agents, where different LLM-powered sub-agents are instantiated with well-defined objectives and strategies tuned to achieve those objectives. arXiv
Key advantages they identified (which validate your approach):

Employing and tuning different problem-solving strategies across sub-agents (e.g., ReAct or CoT) arXiv
Enabling sub-agents to gather information from different sources scattered throughout a repository arXiv
Avoiding unnecessarily long trajectories which inflate costs and add extraneous context arXiv

They instantiate 5 sub-agents (Test Template Generator, Issue Reproducer, Fault Localizer, Code Generator, Solution Ranker) to collectively resolve repository-level issues. arXiv This achieved state-of-the-art on SWE-bench Lite.
Key lesson: Their sub-agents are task-specialized (by function), while yours are domain-specialized (by codebase module). Both are valid decompositions that avoid the "one agent sees everything" problem.

Context Engineering Paper
Paper: arxiv.org/abs/2508.08322 - "Context Engineering for Multi-Agent LLM Code Assistants"
Each subagent operates with an isolated context window. This means that when the orchestrator invokes (for example) the backend-architect agent to handle a task, that agent receives only the information relevant to its task (plus any persistent project context) and does not see the entire dialogue history or unrelated data. This design is intentional: it prevents cross-contamination between different phases of the workflow and keeps each agent focused. arXiv
They specifically call out systems like MASAI achieving significantly higher success on repository-level challenges (28.3% on SWE-Bench Lite) than single-agent baselines arXiv.

Danau5tin's Multi-Agent Coding System
GitHub: github.com/Danau5tin/multi-agent-coding-system (reached #13 on Stanford's Terminal Bench)
While all agents use the same underlying LLM, each operates with its own context window, specialized system message, and distinct toolset. This creates functionally different agents optimized for their specific roles. GitHub
Their novel contribution: A "Context Store" - a persistent knowledge layer that transforms isolated agent actions into coherent problem-solving. Unlike traditional multi-agent systems where agents operate in isolation, this architecture enables sophisticated knowledge accumulation and sharing. GitHub
Key pattern you might adopt:

Explicit Expectations: Every task specifies exactly what contexts should be returned, eliminating unfocused exploration GitHub
Tight Scoping: Defines clear boundaries - what to do AND what not to do, preventing scope creep GitHub


Counter-Perspective: Cognition's "Don't Build Multi-Agents"
Blog: cognition.ai/blog/dont-build-multi-agents
Cognition (Devin) actually argues against multi-agent systems:
"The fundamental issue with multi-agent systems is context management. When you split a task between multiple agents, you're essentially playing a game of telephone where critical information can get lost in transmission." Cognition
Their example: "If you assign one agent to build the background with green pipes and hitboxes, and another agent to create the bird asset, they might develop completely incompatible components." Cognition
However, they acknowledge subagents have value: "The benefit of having a subagent is that all the subagent's investigative work does not need to remain in the history of the main agent, allowing for longer traces before running out of context." Cognition
Key insight for you: "Planning is something that we do. And the context of planning emergency came up for us is actually a form of context management... it's about avoiding this game of telephone where you have to constantly recompress the information." Jxnl
Your Beads integration addresses this—the issue tracker becomes the "same page" that prevents telephone-game drift.

Tool-Level Context Isolation: Aider's Repository Map
Docs: aider.chat/docs/repomap.html
Aider uses a concise map of your whole git repository that includes the most important classes and functions along with their types and call signatures. This helps aider understand the code it's editing and how it relates to other parts of the codebase. Aider
For large repositories even just the repo map might be too large for GPT's context window. Aider solves this by sending just the most relevant portions of the repo map. It does this by analyzing the full repo map using a graph ranking algorithm, computed on a graph where each source file is a node and edges connect files which have dependencies. Aider
Key insight: Aider optimizes the repo map by selecting the most important parts of the codebase which will fit into the token budget. Aider
This is essentially doing dynamically what you're doing statically with Nix subflakes—partitioning based on the dependency graph.

Production Architecture: OpenHands (formerly OpenDevin)
Docs: docs.openhands.dev
OpenHands V1 introduces a new architecture grounded in four design principles: Optional isolation (agent runs locally by default but can switch to sandboxed environment), Stateless by default with one source of truth for state, Strict separation of concerns, and Two-layer composability. arXiv
Sub-agents operate as independent conversations that inherit the parent's model configuration and workspace context, enabling structured parallelism and isolation without any changes to the core SDK. arXiv

Key Lessons Synthesized

Your Nix approach is more principled than file-tree partitioning because the boundaries have semantic meaning (actual compile-time dependencies)
The "Context Store" pattern (from Danau5tin) complements your Beads integration—both solve the "how do agents share knowledge without polluting each other's context" problem
Cognition's criticism of multi-agents is about conflicting decisions, not isolated contexts. Your approach mitigates this because:

Subflakes have clear dependency relationships (no circular confusion)
Beads provides a canonical issue as the "same page"
The parent can rewind child conversations (your "optimistic amnesia" pattern)


Dynamic repo mapping (Aider) vs static partitioning (you): Aider does relevance-based dynamic selection per-query. Your static partitioning is less flexible but more predictable—each agent always knows exactly what it owns.
Tool isolation = context isolation is validated across multiple projects. Your Serena/LSP per-subflake approach (rust-analyzer for hello-rs, pyright for hello-py) is a clean implementation of this.
