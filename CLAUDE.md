# CLAUDE.md

## Working Principles

- Work on one objective at a time.
- Prioritize correctness, maintainability, and small focused changes
- Before editing, understand the surrounding code and identify the smallest safe change that solves the task
- Prefer simple, readable solutions over clever abstractions.
- Preserve existing behavior unless the task explicitly requires changing it.
- Do not perform unrelated refactors or formatting changes.

## File Safety

- Do not create, edit, rename, delete, or reorganize files outside the current task.
- Do not modify files you did not create unless they are clearly required for the task.
- Ask before changing sensitive files such as `.env`, secrets, credentials, migrations, CI/CD config, deployment config, or package/dependency files.
- Do not overwrite user work.
- Do not remove comments, tests, or documentation unless they are clearly obsolete or incorrect.


## Design Guidelines

- Follow SOLID principles where practical.
- Each class, function, and module should have a single clear responsibility.
- Prefer composition over inheritance.
- Avoid god classes, hidden side effects, and unnecessary mutable state.
- Make dependencies explicit through parameters, constructors, or interfaces.
- Avoid premature abstraction. Create abstractions only when they reduce duplication or clarify intent.
- Keep business logic, data access, UI, validation, and infrastructure concerns separated.

## Naming and Structure

- Use clear, descriptive names that explain intent.
- Avoid vague names like `data`, `result`, `manager`, `handler`, `stuff`, or `temp` unless the scope is very small.
- Boolean names should read naturally, such as `is_valid`, `has_access`, `should_retry`, or `can_submit`.
- Functions should usually be named with verbs.
- Classes should represent clear domain concepts.
- Follow the naming and organization patterns already present in the project.

## Function and Class Design

- Functions should do one thing well.
- Keep functions small and easy to reason about.
- Prefer pure functions when practical.
- Avoid large parameter lists and boolean flags that make one function behave like multiple functions.
- Keep constructors simple; avoid I/O, network calls, or expensive work inside constructors.
- Avoid creating a class when a simple function would be clearer.

## Testing

- Add or update tests for meaningful behavior changes.
- Prefer behavior-focused tests over implementation-detail tests.
- Cover common paths, edge cases, and failure cases when practical.
- Do not delete or weaken tests to make code pass.
- Keep tests deterministic and avoid unnecessary reliance on network calls, time, randomness, or global state.

## Error Handling

- Do not silently swallow exceptions.
- Use specific errors and useful messages with enough context to debug.
- Validate inputs at system boundaries.
- Fail fast when continuing would produce unsafe or incorrect behavior.
- Do not expose secrets in logs, errors, tests, or documentation.

## Dependencies and Configuration

- Do not add new dependencies unless clearly necessary.
- Prefer the standard library and existing project dependencies.
- Do not update unrelated dependencies.
- Keep configuration separate from code.


## Git and PR Discipline

- Keep changes scoped to the requested objective.
- Do not rewrite history, rebase, squash, or force-push unless explicitly asked.
- Do not mix formatting-only changes with functional changes.
- Summarize what changed, why it changed, and how it was tested.
- Call out assumptions, risks, and anything not verified.

## Communication

When making changes, summarize:

- What changed
- Why it changed
- Files touched
- Tests or checks run
- Any assumptions, risks, or unverified work

If a larger issue is discovered, mention it separately instead of fixing it silently.

## Default Workflow

1. Understand the existing structure before editing.
2. Identify the smallest safe change.
3. Make the focused change.
4. Run relevant tests, linting, or type checks when available.
5. Report changed files, verification performed, and any caveats.