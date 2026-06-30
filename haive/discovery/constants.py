# Structural limits for agent.md files.
# Adjust these before running `haive index` if the defaults are too tight
# or too loose for the target repo's directory sizes.

# Maximum total line count (including blank lines and headers) per agent.md.
AGENT_MD_MAX_LINES = 200

# Maximum number of entries in the ## Key Symbols section.
AGENT_MD_MAX_SYMBOLS = 50

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
# 200 lines * ~10 tokens/line gives ~2 000 tokens; 2 048 provides headroom.
AGENT_MD_GENERATION_MAX_TOKENS = 2048

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
