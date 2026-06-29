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
