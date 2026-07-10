# Structural limits for agent.md files.
# Adjust these before running `haive index` if the defaults are too tight
# or too loose for the target repo's directory sizes.

# Maximum total line count (including blank lines and headers) per agent.md.
AGENT_MD_MAX_LINES = 200

# Minimum and maximum character lengths for a ## Files entry description
# (the text after the em-dash separator).
AGENT_MD_MIN_DESCRIPTION_LEN = 5
AGENT_MD_MAX_DESCRIPTION_LEN = 150

# A non-entry, non-header, non-blank line with this many words or more is
# treated as a prose paragraph and flagged as a violation.
AGENT_MD_PROSE_WORD_THRESHOLD = 10

# Generation settings used by FileIndexService.
# Max LLM attempts per directory before raising AgentMdGenerationError.
AGENT_MD_MAX_GENERATION_RETRIES = 3
# max_tokens passed to the LLM for each agent.md generation call.
# 200 lines * ~10 tokens/line gives ~2 000 tokens; raised to 4096 for real
# headroom rather than the tightest value that happened to work — see the
# task_executor.py/review_agent.py editor and reviewer budget comments for
# the concrete incident (a too-tight budget forcing a premature, invalid
# response) that prompted revisiting every budget/round constant like this.
AGENT_MD_GENERATION_MAX_TOKENS = 4096

# Code Discovery Agent guardrails.
# Maximum total tool invocations per discover() call before the agent is forced to emit results.
CODE_DISCOVERY_MAX_TOOL_CALLS = 30
# max_tokens for each call_single() in the discovery loop (covers JSON output).
CODE_DISCOVERY_MAX_TOKENS = 8192

# Repo map for the Orchestrator (FileIndexService.read_repo_map).
# Token budget for the concatenated agent.md tree handed to the orchestrator —
# a small slice of its overall context budget, since this is a summary map,
# not source code.
ORCHESTRATOR_REPO_MAP_TOKEN_BUDGET = 8_000

# File extensions treated as source files when walking the repo.
# Directories that contain no file matching this set are skipped.
SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Python
        ".py",
        # JavaScript / TypeScript
        ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs",
        # Go
        ".go",
        # Java / Kotlin / Scala
        ".java", ".kt", ".scala",
        # Ruby
        ".rb",
        # Rust
        ".rs",
        # C / C++
        ".c", ".cpp", ".cc", ".h", ".hpp",
        # C#
        ".cs",
        # Swift
        ".swift",
        # Shell
        ".sh", ".bash", ".zsh",
        # Config / data formats
        ".yaml", ".yml", ".toml",
        # Docs
        ".md",
        # SQL
        ".sql",
        # Web
        ".html", ".css", ".scss", ".less",
    }
)
