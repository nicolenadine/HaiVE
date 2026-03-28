# Multi-Agent Engineering Platform<br>Engineering Design Overview

## System Goal

A **self-hosted, multi-agent AI engineering platform** capable of:

- planning software systems
- writing and modifying code
- reviewing and testing implementations
- iterating on designs and workflows

All powered by **locally hosted** LLMs and related tools, with a modular architecture that evolves over time.

---

## Design Philosophy

### Core Principles

- **Model-agnostic agents**
  - capability-based routing
  - "agents" concept is separated from "models" concept
- **Context is the core system primitive**
  - skill files, RAG, and MCP servers for specialization
- **Security-first execution**
  - sandboxed execution environments
- **Composable + replaceable infrastructure**
  - microservices
  - minimize vendor lock-in
- **Separation of concerns across layers**
  - layers operate independently, communicate via API
- **Stable interfaces with version increments**
  - minimize disruptions to down-stream use cases or between services

---

## System Versions

### v0 (MVP)

> **Integration milestone**

- All layers exist and communicate
  - Some are stubs
- Single agent, minimal orchestration
- Full end-to-end pipeline works
- Architecturally correct (no rewrites later)

---

### v1

> **Usable engineering system**

- Reliable multi-agent workflows
- Strong context engineering
- Real tool usage via MCP
- Production-grade retrieval + reranking

**TODO:** Break up steps between v0 to v1 to include sub-steps

**TODO:** Deliverables per step

---

## High-Level Architecture

### Install
- get dependencies
- create lookup table of models that we support on this system

### Update
- update available models & lookup table

### System Components

### Client & Server models
**TODO:** What gets stored on local machine (client) vs cloud machine (server)? Similarly, what compute is happening localy vs remote?


#### Primary engine
- Users (SSH / CLI / API)  
- Model Gateway   
- Agent & Tool Orchestrator  
- Tool layer (MCP, Agent-Aware Context Engine)  
- Retrieval + Reranking  
- Model Serving  
- Execution Sandbox  

#### Supporting Infrastructure
- Vector Database
- Embedding Service
- Project Workspace
- Execution environment
- Logging + Telemetry

---

## Stack Overview

| Layer                | Description                                                                                   | v0 (MVP)                                          | v1                                               |
|----------------------|-----------------------------------------------------------------------------------------------|---------------------------------------------------|---------------------------------------------------|
| **User Interface**   | How users interact with the system                                                            | CLI (Python, argparse)                            | Python CLI + REST API (multi-user, SSH, user settings)                  |
| **Model Gateway**    | API frontend for model access and routing                                                     | FastAPI, single vLLM model                        | Routing layer (fallback, telemetry, multi-model)   |
| **Agent Orchestrator** | Manages agent workflows, logic, and orchestration                                           | LangGraph (2 agents, linear)                      | LangGraph graph (multi-agent, retries, memory)     |
| **Tool / MCP Layer** | Facilitates tool integration and multi-capability provider (MCP) communication                | Local FS + stubbed tools                          | MCP servers (filesystem, git, APIs, external tools)|
| **Context Engine**   | Handles how relevant context is gathered, compressed, and assembled for tasks                 | retrieve → concat → truncate                      | hierarchical retrieval, compression, clustering, AST-aware, role-aware |
| **Memory Retrieval** | Retrieves relevant task memory using vector search                                            | Simple chunking & filtering                       | file-aware + metadata-aware chunking, advanced querying and filtering logic |
| **Reranking**        | Improves ranking of retrieved results or contexts                                             | stubbed / optional                                | Qwen reranker (batched, always-on)                 |
| **Embedding Service**| Generates and manages vector representations for data                                         | simple CPU embeddings                             | batched, cached, optional GPU                      |
| **Model Serving**    | Hosts and manages inference for models                                                        | vLLM (primary) + Ollama fallback                  | vLLM multi-model + scheduling + Ollama fallback    |
| **Execution**        | Isolates and executes tasks and agents in containers/infrastructure                           | Docker Compose                                    | Docker + Kubernetes + Terraform                    |
| **Memory Storage**   | Underlying database/storage for persistent memory                                             | single Qdrant collection                          | structured memory (code, docs, history)            |
| **Project Workspace**| File/projects organization with workspace isolation                                           | `/srv/ai-lab/projects`                            | metadata + isolation (git worktrees)               |
| **Observability**    | Telemetry: collecting logs, metrics, traces, and operational visibility                       | logs                                              | tracing + metrics (LGTM, W&B)                      |
| **Config System**    | How system, user, and runtime configurations are managed                                      | static YAML                                       | dynamic hierarchical config                        |
| **Prompting**        | Supporting framework for prompt construction and reuse                                        | minimal LangChain helpers                         | structured prompts + reusable templates            |

---

## 🔌 Core Components

---

### 1. Model Gateway

**Purpose:** Unified API for all models

**Key Idea:** Agents NEVER talk to models directly

#### Responsibilities

- normalize APIs (OpenAI-compatible)
- route by capability
- manage fallback
- log usage

#### API
POST /v1/chat/completions
```json
{
  "capability": "coding",
  "messages": [...],
  "temperature": 0.2
}
Backends
Primary: vLLM


Secondary: Ollama (fallback, fast iteration)



2. Model Serving
vLLM = primary inference engine


Ollama = fallback + experimentation


Routing Example
small task → Ollama
large context / batch → vLLM

3. Agent Orchestrator
Framework: LangGraph
Responsibilities
workflow graphs


agent loops


tool execution


retry handling


v0 Agents
Planner


Coder


v1 Agents
Planner


Backend Engineer


Frontend Engineer


Reviewer


Tester


DevOps



4. Tool / MCP Layer
Purpose: External capabilities via standardized interface
v0
local filesystem


stubbed tools


v1
MCP servers:


filesystem


git


shell (sandboxed)


APIs


documentation



5. Context Engine (Critical Component)
Purpose: Construct optimal prompt context
Inputs
query


agent role


model


context budget


API
POST /augment

v0 Strategy
retrieve N chunks
→ concatenate
→ truncate

v1 Strategy
retrieve large set
→ rerank
→ cluster
→ compress
→ assemble by priority
→ fit to budget

Responsibilities
retrieval orchestration


context budgeting


prompt assembly


role-aware shaping



6. Retrieval + Memory
Database: Qdrant
Stored Data
code


documentation


agent logs


design notes



v0
fixed chunking


single collection



v1
file-aware chunking


metadata-aware filtering


multiple collections



7. Reranking
v0
optional / disabled


v1
Qwen reranker (batched GPU)


top 50 → rerank → top 10

8. Embedding Service
v0
CPU embedding model (inline)


v1
dedicated service


batching + caching



9. Execution Sandbox
Purpose: Safe code execution
Implementation
Docker containers


Flow
agent writes code
→ container runs it
→ results returned

v1 Improvements
per-task containers


resource limits


network isolation



10. Project Workspace
/srv/ai-lab/
    agents/
    services/
    projects/
    config/
    logs/
Multi-user via:
group: ai

🔄 Data Flow
Example: “build REST API”
1. user submits task
2. planner creates plan
3. agent requests context
4. retrieval + reranking
5. context assembled
6. model generates code
7. files written
8. sandbox executes tests

📏 Context Budgeting
models:
  coding_7b:
    max_tokens: 4096
    target_tokens: 3000
Agents use:
capability → model mapping

🔁 Retrieval Pipeline
query
↓
embedding search
↓
top K chunks
↓
rerank (v1)
↓
context builder
↓
prompt

⚙️ MVP Scope (v0)
Goal
Validate full system integration

Simplifications
simple chunking


no compression


minimal agents


limited tools



Services
model gateway


vLLM backend


Qdrant


context engine


agent orchestrator


sandbox runner



Example Task
create Python CLI app

🚀 V1 Upgrades
Adds
real MCP tools


advanced context engine


multi-agent workflows


structured memory


observability



🔐 Security
Risks
arbitrary code execution


resource exhaustion


Mitigation
Docker sandbox


no direct host execution


quotas + limits



🧩 Implementation Order
Step 1 — Infrastructure
Docker


Qdrant


vLLM (+ optional Ollama)



Step 2 — Model Gateway
OpenAI-compatible API


route to vLLM



Step 3 — Context Engine (v0)
retrieval


concat


truncate



Step 4 — Agent Orchestrator
planner + coder



Step 5 — Sandbox
Docker execution



Step 6 — End-to-End Test
generate small project



🔮 Future Extensions
multimodal models


UI generation agents


workflow optimization agents


CI/CD integration



🧠 Key Insight
LLMs are interchangeable
Context + orchestration are not
This system is designed so that:
models can change


workflows improve


agents evolve

