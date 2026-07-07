# AI Agent Harness — Initial Project Brief

## Project Summary

This project is an **AI agent harness** for coordinating software development work across multiple specialized agents. The system will use a combination of **local open-source models** and **frontier models**, selecting the most appropriate model for each task based on cost, complexity, context requirements, and expected reasoning depth.

The core idea is to create a structured multi-agent development environment where a **lead agent** determines the next useful step, breaks work into focused tasks, and delegates those tasks to specialized sub-agents. These sub-agents may be responsible for implementation, testing, review, documentation, planning, refactoring, or other project-specific activities.

A major priority of this project is **efficient token usage**. The system should avoid unnecessary reasoning, unnecessary context sharing, and unnecessary use of expensive frontier models. Wherever possible, deterministic workflows, structured handoffs, concise artifacts, and targeted context retrieval should be used instead of repeatedly passing large amounts of text between agents.

## Primary Goal

Build a practical AI-assisted software development harness that can:

* Determine the next best development step or pull request.
* Break that work into clear, scoped tasks.
* Assign tasks to appropriate specialized agents.
* Coordinate code generation, review, testing, and documentation.
* Use the right model for the right job.
* Minimize token usage through structured communication and deterministic workflows.
* Maintain project-specific agent instructions, skills, and resources.
* Produce high-quality technical documentation as part of the design process.

## Intended Development Style

This project should be designed collaboratively and iteratively. The initial focus is not to immediately build the full system, but to first create the supporting planning and design documents needed to make implementation disciplined and maintainable.

The planning process should produce documents such as:

* Architecture diagrams
* System flow diagrams
* Agent interaction diagrams
* Wireframes
* Prototypes
* Database models
* Data flow models
* Agent role definitions
* Skill file specifications
* Technical specifications
* Implementation plan
* Development roadmap
* Testing strategy
* Evaluation strategy

These documents should evolve as the project becomes better understood.

## Core System Concept

The harness will be organized around a **lead agent** and multiple **specialized sub-agents**.

The lead agent is responsible for:

* Understanding the current project state.
* Identifying the next useful objective.
* Selecting the next PR-sized unit of work.
* Breaking that objective into smaller tasks.
* Determining which sub-agent should handle each task.
* Managing task handoffs.
* Reviewing outputs from sub-agents.
* Deciding whether additional work, testing, or review is needed.
* Maintaining forward progress without expanding scope unnecessarily.

Sub-agents may include roles such as:

* Code generation agent
* Test generation agent
* Code review agent
* Documentation agent
* Architecture agent
* Planning agent
* Refactoring agent
* Security review agent
* Local model agent for low-cost/simple tasks
* Frontier model agent for high-reasoning/high-risk tasks

The exact agent roles should be refined during the design process.

## Agent Files and Skills

Each agent should have its own dedicated instruction and capability files. These may include:

* Agent-specific `.md` instruction files
* Skill files defining repeatable workflows
* Task templates
* Review checklists
* Context requirements
* Model selection preferences
* Input/output schemas
* Handoff formats
* Relevant resources or artifacts

Each agent should have a clear, narrow responsibility. Agents should not all receive the entire project context by default. Instead, each agent should receive only the information required to complete its assigned task.

## Token Efficiency Priorities

Token efficiency is a first-class design concern for this project.

The system should minimize token usage through:

* Clear task boundaries
* Small PR-sized objectives
* Concise agent handoffs
* Structured outputs
* Shared artifacts instead of repeated long explanations
* Context retrieval instead of full-context broadcasting
* Deterministic workflows where reasoning is unnecessary
* Model routing based on task complexity
* Local/open-source model usage where sufficient
* Frontier model usage only when the task requires deeper reasoning, higher reliability, or broader synthesis
* Summaries and state files that preserve useful context without carrying entire conversation histories
* Avoiding repeated re-analysis of already-settled decisions

The system should explicitly distinguish between tasks that require reasoning and tasks that can be handled through deterministic scripts, templates, static analysis, tests, or rule-based workflows.

## Model Routing Philosophy

The harness should choose models intentionally.

Local or cheaper open-source models may be appropriate for:

* Simple code edits
* Formatting
* Boilerplate generation
* Small test additions
* Summarization of narrow context
* Basic classification or routing
* Checking against explicit rules
* Generating drafts from templates

Frontier models may be appropriate for:

* Architecture decisions
* Complex debugging
* Ambiguous requirements
* Cross-file reasoning
* Security-sensitive review
* Planning large changes
* Evaluating tradeoffs
* Synthesizing multiple sources of context
* High-risk implementation tasks

The design should include a model selection strategy that considers:

* Task difficulty
* Required context size
* Cost
* Latency
* Reliability requirements
* Risk of incorrect output
* Whether deterministic tooling can solve the task instead

## Communication Between Agents

Cross-agent communication should be structured, concise, and purpose-driven.

Agent handoffs should avoid vague summaries and instead include:

* Objective
* Relevant files or artifacts
* Constraints
* Inputs
* Expected output
* Acceptance criteria
* Known risks
* Open questions
* Required verification steps

Agents should not pass entire reasoning traces to each other. Instead, they should pass decisions, evidence, outputs, and unresolved questions.

## Design Principles

The project should follow good software design principles:

* Keep responsibilities clear and separated.
* Prefer small, focused modules.
* Avoid unnecessary abstraction early.
* Prefer composition over inheritance.
* Make dependencies explicit.
* Keep side effects isolated.
* Design for testability.
* Use deterministic workflows where possible.
* Keep agent roles narrow and understandable.
* Keep implementation steps small enough to review safely.
* Avoid hidden global state where possible.
* Preserve a clear audit trail of decisions, task assignments, and outputs.

## Initial Documentation Goals

Before implementation begins, create the following planning documents.

### 1. Project Overview

A concise description of the system, goals, non-goals, constraints, and guiding principles.

### 2. Architecture Overview

A high-level architecture document describing the major system components, their responsibilities, and how they interact.

### 3. Agent Model

A document defining the lead agent, sub-agent roles, responsibilities, input/output expectations, and escalation paths.

### 4. Communication Protocol

A specification for how agents exchange tasks, results, summaries, decisions, and requests for clarification.

### 5. Model Routing Strategy

A document describing when to use local models, cheaper hosted models, and frontier models.

### 6. Token Efficiency Strategy

A document describing the system’s approach to minimizing token usage through scoped context, summaries, artifacts, deterministic workflows, and model routing.

### 7. Data and State Model

A document describing what state the harness needs to persist, including tasks, PRs, agent outputs, decisions, summaries, artifacts, model usage, and execution history.

### 8. Technical Specification

A detailed specification covering implementation architecture, interfaces, data models, execution flow, configuration, storage, logging, testing, and integration points.

### 9. Build Plan

A phased implementation plan that explains what will be built in what order.

## Proposed Build Plan

### Phase 1: Planning and Requirements

Goal: Establish the project foundation before writing production code.

Deliverables:

* Project overview
* Goals and non-goals
* Core terminology
* Initial architecture sketch
* Initial agent role list
* Initial build plan
* Open questions list

### Phase 2: Architecture and System Design

Goal: Define the major system components and how they interact.

Deliverables:

* Architecture overview
* Agent orchestration flow
* Task lifecycle diagram
* Agent handoff format
* State management approach
* Model routing design
* Token efficiency design

### Phase 3: Minimal Prototype

Goal: Build the smallest working version of the harness.

Potential scope:

* Lead agent selects or receives one objective.
* Objective is broken into tasks.
* Tasks are assigned to simple sub-agent roles.
* Sub-agents produce structured outputs.
* Outputs are collected and summarized.
* Basic state is persisted.
* Model routing is initially simple and configurable.

### Phase 4: Agent Specialization

Goal: Make sub-agents more useful and clearly separated.

Potential scope:

* Code generation agent
* Test generation agent
* Review agent
* Documentation agent
* Planning agent
* Agent-specific instruction files
* Agent-specific skill files
* Standard task templates
* Standard review checklists

### Phase 5: Token Optimization

Goal: Improve cost and context efficiency.

Potential scope:

* Context budgeting
* Concise handoff schemas
* Summary artifacts
* Deterministic routing
* Local model routing
* Frontier model escalation rules
* Token usage logging
* Model usage reporting

### Phase 6: Review, Testing, and Reliability

Goal: Make the harness safer and more dependable.

Potential scope:

* Task acceptance criteria
* Automated verification hooks
* Test execution workflow
* Code review workflow
* Failure handling
* Retry policy
* Human approval gates
* Audit trail for decisions

### Phase 7: Developer Experience

Goal: Make the harness practical to use.

Potential scope:

* CLI or lightweight UI
* Project dashboard
* Task queue visualization
* Agent activity view
* PR/objective status tracking
* Configuration files
* Documentation workflow
* Example project run

## Early Open Questions

These should be answered during the design process:

* What is the minimum viable version of the harness?
* Should the lead agent autonomously choose the next PR, or should the user provide objectives?
* How much autonomy should agents have to edit files?
* What actions require human approval?
* What state needs to be persisted?
* What should the initial storage layer be?
* What local models should be supported first?
* What frontier models should be supported first?
* Should the system be CLI-first, UI-first, or API-first?
* How should task handoffs be represented?
* How should agent outputs be validated?
* How should token usage and model cost be tracked?
* What deterministic tools should be used before invoking an LLM?
* How should the system prevent agents from duplicating work?
* How should failed or low-quality agent outputs be handled?

## Non-Goals for the Initial Version

The initial version does not need to support:

* Unbounded, indefinite autonomy — `haive run` loops automatically across a capped number of waves per invocation (`max_waves_per_run`) and always stops to surface to a human when genuinely stalled or the cap is reached
* Complex multi-user collaboration
* Production-grade distributed execution
* Perfect model routing
* Advanced UI
* Full IDE integration
* Complex permissions system
* Support for every model provider
* Large-scale agent marketplaces or plugin ecosystems

These may be considered later, but the first version should prioritize a small, understandable, working harness.

## Success Criteria

The project is successful if the harness can:

* Take a focused software development objective.
* Break it into clear tasks.
* Route tasks to appropriate agents.
* Use structured handoffs between agents.
* Produce useful code, tests, reviews, or documentation.
* Avoid unnecessary context sharing.
* Use cheaper or local models for simpler tasks.
* Escalate to frontier models only when justified.
* Preserve a clear record of decisions and outputs.
* Help the user build software more reliably with less manual coordination.
