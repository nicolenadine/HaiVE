# Haive — Agent Model

## Purpose

This document defines the agent roles in the haive system: what they do, what they receive, what they produce, and how they are structured. It also defines the system prompt template that all agents follow and the principles governing agent design.

---

## Agent Design Principles

**Narrow over broad.** A specialized agent with a focused system prompt produces more predictable output than a general-purpose agent that handles many task types. Routing ambiguity is resolved at definition time, not at call time.

**Non-overlapping skills.** Two agents should not be plausible routes for the same task. If the orchestrator could reasonably assign a task to either agent A or agent B, the agents are not well-defined. The fix is sharper descriptions and skills lists, not smarter routing logic.

**No model references.** Agents do not specify which model runs them. Model selection is driven entirely by task complexity at call time. The same agent definition runs on Ollama for a low-complexity task and Claude Sonnet for a high-complexity one.

**Constraints are as important as capabilities.** Every system prompt should be explicit about what the agent does NOT do. A code editor that also rewrites tests or updates documentation is doing the wrong job. Clear constraints prevent scope creep within a single task execution.

**Stateless.** Agents receive everything they need in their initial context. They do not retain memory between tasks, request clarification mid-task, or communicate with other agents directly. If the context is insufficient, the output fails validation and the retry loop adds more context.

---

## Agent Definition Schema

Every agent in the registry follows this structure:

```yaml
roles:
  agent_name:
    description: One sentence. What this agent does and when the orchestrator should route to it.
    skills:
      - skill_1
      - skill_2
    system_prompt: prompts/agent_name.md
    prompt_version: "1.0.0"
    max_tokens: 4096
    output_schema: schemas/agent_name_result.json
    retry_limit: 2
```

| Field | Purpose |
|---|---|
| `description` | Read by the orchestrator to make routing decisions. Should be unambiguous enough that no other agent has an overlapping description. |
| `skills` | Structured list. Read by the orchestrator. Enables future deterministic pre-filtering. Should not overlap significantly with other agents' skill lists. |
| `system_prompt` | Path to the current prompt file. Never read by the orchestrator. Full content is injected into each task executor's context by the Context Assembler. |
| `prompt_version` | Semver string. Bumped manually when the prompt changes. Recorded in the state file and OTel span attributes for every task, enabling debugging and eval comparisons across prompt versions. |
| `max_tokens` | Maximum output tokens. Set per agent based on expected output size. |
| `output_schema` | Path to the JSON schema (and corresponding Pydantic model) for this agent's structured output. Validated by the Output Validator after every call. |
| `retry_limit` | Maximum retries before escalating to the next model tier. Overrides the tier default for this specific agent. |

---

## Prompt Storage

Current and archived prompts are stored separately. The `prompts/` directory contains only the active version of each prompt. When a prompt is updated, the previous version is copied to `prompts/archive/{agent_name}/` before the current file is changed.

```
prompts/
  scaffold_agent.md           ← always the current version
  code_editor.md
  refactoring_agent.md
  api_integration_agent.md
  database_agent.md
  test_generator.md
  code_reviewer.md
  security_reviewer.md
  documentation_writer.md
  archive/
    refactoring_agent/
      v1.0.0.md
      v1.1.0.md
    code_editor/
      v1.0.0.md
```

This means `prompts/refactoring_agent.md` is always current. Older versions are retrievable by version number from the archive. The `prompt_version` in the registry entry is the authoritative version label — it must be bumped in the registry whenever the prompt file changes.

The `prompt_version` is recorded in:
- The state file, alongside each task result
- The OTel task span (`agent.prompt_version` attribute)

This makes it possible to answer: "did this agent behave differently before and after the prompt change?" by filtering Phoenix traces by `agent.prompt_version`.

---

## System Prompt Template

Every agent system prompt follows the same five-section structure. Consistency makes agents easier to write, audit, and compare.

```markdown
# Role

[One paragraph. What this agent is and what it is responsible for.
Written in second person: "You are a..."]

# What You Receive

[Describe the inputs this agent will find in its context:
- Task description and acceptance criteria
- Relevant code snippets or file contents (if applicable)
- Outputs from dependent tasks (if applicable)
- Reviewer feedback from prior attempts (if this is a retry)]

# Constraints

[Explicit list of what this agent must NOT do.
This section is as important as the capabilities section.
Examples: do not modify files outside the task scope,
do not write tests, do not make architectural decisions.]

# Output Format

[Exact description of the required structured output.
Reference the output schema. Be explicit about every field.]

# Quality Bar

[What good output looks like for this role. Criteria the agent
should self-evaluate against before producing its final output.]
```

---

## Initial Agent Roster

### Code Agents

#### `scaffold_agent`
**Description:** Creates new files, modules, and project structure from a specification. Use when the task requires creating something that does not yet exist.

**Skills:** new file creation, module skeleton, class/function stubs, project structure, boilerplate

**Does NOT:** modify existing files, write tests, make implementation decisions beyond what the spec requires.

> **Orchestrator rule:** When a task requires both creating a new file and modifying an existing one to wire it in, these must be separate tasks with explicit dependencies: `scaffold_agent` first, then `implementation_agent` to fill in the logic, then `code_editor` if an existing file also needs updating.

**Typical task complexity:** low–medium

---

#### `code_editor`
**Description:** Modifies existing code to implement a requirement, fix a bug, or add functionality. Use when the task targets code that already exists.

**Skills:** feature implementation, bug fixes, adding to existing modules, updating interfaces

**Does NOT:** create new files (use scaffold_agent), refactor for style (use refactoring_agent), write tests, touch files not listed in the task context.

**Typical task complexity:** medium–high

---

#### `implementation_agent`
**Description:** Implements stub or skeleton files created by the scaffold agent. Use when the file structure and interfaces already exist but the logic bodies are empty or unimplemented.

**Skills:** stub implementation, filling function and method bodies, implementing to a defined interface, test-driven implementation, satisfying acceptance criteria from existing signatures and docstrings

**Does NOT:** create new files or change stub signatures — the interface is the contract and must not be altered, modify already-working code (use code_editor), write tests.

**Typical task complexity:** medium–high

> **Workflow note:** This agent sits between `scaffold_agent` and `code_editor` in the natural task sequence. `scaffold_agent` creates the structure; `implementation_agent` fills it in; `code_editor` handles subsequent modifications to working code. The orchestrator should always create an `implementation_agent` task that depends on the `scaffold_agent` task that produced its stubs.

---

#### `refactoring_agent`
**Description:** Improves the structure, readability, or maintainability of existing code without changing its observable behavior. Use when the task is explicitly about code quality, not feature work.

**Skills:** extract function/class, rename for clarity, reduce duplication, simplify conditionals, improve module organization

**Does NOT:** add features, fix bugs (unless they are trivial and directly in the refactoring path), change public interfaces without instruction, touch files not listed in the task context.

**Scope constraint:** The system prompt includes an explicit hard constraint: only modify files listed in the task context. The Review Agent checks for out-of-scope file changes and rejects outputs that touch unlisted files, regardless of whether the changes are improvements.

**Typical task complexity:** medium

---

#### `api_integration_agent`
**Description:** Writes code that integrates with external APIs — HTTP clients, authentication flows, request/response handling, and network error handling. Use when the task is primarily about connecting to a third-party service.

**Skills:** HTTP client setup, authentication (OAuth, API keys, tokens), request/response mapping, retry and timeout handling, API error handling, rate limiting

**Does NOT:** design the API contract itself, write the business logic that consumes the integration, write tests.

**Typical task complexity:** medium–high

---

#### `database_agent`
**Description:** Writes database-related code — queries, migrations, ORM models, and data access layer logic. Use when the task is primarily about data persistence or retrieval.

**Skills:** SQL queries, ORM model definitions, schema migrations, data access objects, transaction handling, query optimization

**Does NOT:** write application logic that uses the data layer, write tests, make schema design decisions beyond the task spec.

**Typical task complexity:** medium–high (migrations always treated as high due to risk).

> **Orchestrator rule:** Any task involving a database migration must always be followed by a `security_reviewer` task as a hard dependency — not left to the orchestrator's judgment. The security reviewer checks for irreversible operations, missing down migrations, data loss risk, and unsafe column changes.

---

### Quality Agents

#### `test_generator`
**Description:** Writes tests for existing code. Use after implementation tasks to add test coverage.

**Skills:** unit tests, integration tests, test fixtures and factories, edge case coverage, parameterized tests, mocking external dependencies

**Does NOT:** write implementation code, change the code under test, make assertions about code it cannot see.

**Typical task complexity:** low–medium

---

#### `code_reviewer`
**Description:** Reviews existing code for correctness, logic errors, style, performance, and adherence to project guidelines. Use to validate implementation before merging.

**Skills:** logic correctness, edge case identification, style and readability, performance concerns, guideline compliance, naming and structure

**Does NOT:** review for security vulnerabilities (use security_reviewer), write or suggest replacement code, approve or reject — it produces findings for the human or orchestrator to act on.

**Typical task complexity:** medium

---

#### `security_reviewer`
**Description:** Reviews code specifically for security vulnerabilities. Use for any task with complexity=high due to security sensitivity, or explicitly requested for security-critical paths.

**Skills:** injection vulnerabilities (SQL, command, XSS), authentication and authorization flaws, secrets and credential handling, dependency vulnerabilities, insecure defaults, input validation gaps, OWASP Top 10

**Does NOT:** review for general code quality or style (use code_reviewer), write remediation code.

**Typical task complexity:** always treated as high — never routed to a low-tier model.

---

### Documentation Agent

#### `documentation_writer`
**Description:** Writes or updates technical documentation, docstrings, READMEs, and inline comments. Use when the task is specifically about documentation, not implementation.

**Skills:** docstrings, module-level documentation, README files, API reference docs, usage examples, inline clarification comments

**Does NOT:** write implementation code, make decisions about what the code should do, infer behavior from code that is not provided.

**Typical task complexity:** low

---

## The Review Agent (Special Case)

The Review Agent is not part of the sub-agent roster. It is a fixed component of the Task Executor loop — every task's output passes through it before a verdict is written to the state file. It is not routed to by the orchestrator.

Unlike sub-agents, the Review Agent:
- Receives the sub-agent's output alongside the original task description and acceptance criteria
- Checks against the task's `acceptance_criteria` and the project's guidelines file (`guidelines.md`)
- Produces two outputs: a full verdict (for the Task Executor's retry loop) and a summary verdict (for the orchestrator)
- Does not write code, suggest implementations, or expand scope

Its output schema:

```json
{
  "passed": true,
  "reason": "All acceptance criteria met. Tests cover the happy path and the two specified edge cases.",
  "suggestions": []
}
```

```json
{
  "passed": false,
  "reason": "Missing input validation on the email field.",
  "suggestions": [
    "Add validation that email matches RFC 5322 format before writing to the database.",
    "Return a 422 status with a descriptive error message on invalid input."
  ]
}
```

The `suggestions` list becomes the feedback injected into the next retry attempt's context.

---

## Roster Summary (for orchestrator context)

This is the compact summary derived from the registry and loaded into the orchestrator's context at startup:

```
scaffold_agent: Creates new files and project structure from a specification. Skills: new file creation, module skeleton, class/function stubs, project structure, boilerplate.
implementation_agent: Implements stub or skeleton files — fills in logic bodies for already-defined interfaces. Skills: stub implementation, implementing to a defined interface, test-driven implementation.
code_editor: Modifies existing working code to implement requirements or fix bugs. Skills: feature implementation, bug fixes, adding to existing modules, updating interfaces.
refactoring_agent: Improves code structure without changing behavior. Skills: extract function/class, rename for clarity, reduce duplication, simplify conditionals.
api_integration_agent: Writes code that integrates with external APIs. Skills: HTTP clients, authentication, request/response mapping, retry and timeout handling, rate limiting.
database_agent: Writes database queries, migrations, and data access layer code. Skills: SQL, ORM models, migrations, transactions, query optimization.
test_generator: Writes tests for existing code. Skills: unit tests, integration tests, test fixtures, edge cases, mocking.
code_reviewer: Reviews code for correctness, style, and guideline compliance. Skills: logic correctness, edge cases, readability, performance, naming.
security_reviewer: Reviews code for security vulnerabilities. Skills: injection, auth flaws, secrets handling, input validation, OWASP Top 10.
documentation_writer: Writes technical documentation and docstrings. Skills: docstrings, READMEs, API reference, usage examples.
```

---

## Adding a New Agent

To add an agent to the roster:

1. Add an entry to `agents.yaml` with `description`, `skills`, `system_prompt`, `output_schema`, `max_tokens`, and `retry_limit`.
2. Write the system prompt file following the five-section template above.
3. Define the output Pydantic model and register it with the Output Validator.
4. Verify the new agent's `description` and `skills` do not significantly overlap with any existing agent.
5. Update the orchestrator's compact summary (regenerated automatically at startup from the registry).

---

## Decisions Made

1. **`code_editor` vs. `scaffold_agent` boundary:** When a task requires both creating a new file and modifying an existing one, the orchestrator must split these into two tasks with an explicit dependency. `scaffold_agent` runs first; `code_editor` depends on it.

2. **`database_agent` migration risk:** Any migration task is always followed by a `security_reviewer` task as a hard system rule — not dependent on orchestrator judgment or acceptance criteria quality. Defined as an orchestrator rule in the `database_agent` entry above.

3. **`refactoring_agent` scope creep:** Constrained by file scope, not line count. The system prompt enforces a hard constraint to only touch files listed in the task context. The Review Agent rejects any output that modifies unlisted files.

4. **Agent versioning:** Prompt versions tracked via `prompt_version` (semver) in the registry. Current prompts live in `prompts/`; older versions archived in `prompts/archive/{agent_name}/`. Version recorded in the state file and OTel span attributes for debugging and eval comparisons.
