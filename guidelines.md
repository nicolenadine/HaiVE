# Project Coding Guidelines

These guidelines apply to all code produced or modified by haive agents.
Review agents must evaluate submissions against these standards.

---

## Correctness

- Code must satisfy the task's acceptance criteria exactly — no partial implementations.
- Handle error cases explicitly; do not swallow exceptions silently.
- Validate inputs at system boundaries (user input, external API responses).
- Fail fast when continuing would produce unsafe or incorrect behavior.
- Do not expose secrets, tokens, or credentials in logs, errors, or output.

## Design

- Follow SOLID principles where practical.
- Each class and function should have one clear responsibility.
- Prefer composition over inheritance.
- Avoid hidden side effects and unnecessary mutable state.
- Make dependencies explicit through parameters, constructors, or interfaces.
- Avoid premature abstraction — create abstractions only when they reduce real duplication.

## Naming and Structure

- Use clear, descriptive names that explain intent.
- Avoid vague names: `data`, `result`, `manager`, `handler`, `stuff`, `temp`.
- Boolean names should read naturally: `is_valid`, `has_access`, `should_retry`.
- Functions should be named with verbs. Classes should represent domain concepts.
- Follow naming and organization patterns already present in the codebase.

## Functions and Classes

- Functions should do one thing well and be easy to reason about.
- Prefer pure functions when practical.
- Avoid large parameter lists and boolean flags that make one function behave like multiple.
- Keep constructors simple; no I/O, network calls, or expensive work inside them.
- Avoid creating a class when a simple function would be clearer.

## Comments

- Default to writing no comments.
- Only add a comment when the WHY is non-obvious: a hidden constraint, a subtle invariant,
  a workaround for a specific bug, behavior that would surprise a reader.
- Never write comments that describe WHAT the code does — well-named identifiers do that.

## Error Handling

- Use specific error types with useful messages that include enough context to debug.
- Do not catch broad exceptions unless explicitly re-raising or wrapping them.
- Do not use fallbacks or defaults that silently hide failures.

## Testing

- Tests should be behavior-focused, not implementation-detail-focused.
- Cover common paths, edge cases, and failure cases.
- Keep tests deterministic — avoid unnecessary reliance on time, randomness, or global state.
- Do not delete or weaken existing tests to make new code pass.

## Dependencies

- Do not add new dependencies unless clearly necessary.
- Prefer the standard library and existing project dependencies.
- Do not update unrelated dependencies.

## Security

- Never generate SQL, shell commands, or HTML from user input without proper escaping.
- Do not log sensitive data (tokens, passwords, PII).
- Do not hardcode credentials or secrets.
- Prefer parameterized queries and safe serialization over string concatenation.
