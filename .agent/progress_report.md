# AgentIR — Project Progress Report

> **Date**: 2026-06-16  
> **Version**: v0.2.0  
> **Status**: Phase 2 Complete ✅ — Full NL → AgentIR → ADK Dynamic Workflow Pipeline

---

## 1. Overview

AgentIR is a framework-agnostic Agent Workflow Intermediate Representation (IR) and Compiler System. It converts natural language descriptions of agent workflows into runnable ADK 2.0 Dynamic Workflow Python code.

Phase 2 delivers the complete pipeline:

```
NL Requirement → Planner (LLM) → AgentIR Schema (.json) → Validator → ADK Compiler → Run
     .txt                          .json                       ↓               .py     (subprocess)
                                                          artifacts/ir/    artifacts/outputs/
```

All layers (IR Schema, Validator, Planner, Tools, ADK Compiler, Server, Artifacts) are implemented and tested.

---

## 2. Deliverables Status

| # | Deliverable | Status | Notes |
|---|------------|--------|-------|
| 1 | AgentIR Schema (IR) | ✅ Done | 6 node types (agent, sequence, parallel, condition, loop, **tool**) |
| 2 | AgentIR Validator | ✅ Done | Agent/tool existence, empty containers, depth, expressions |
| 3 | LLM Module | ✅ Done | Provider abstraction (DeepSeek, OpenAI, Ollama, custom) |
| 4 | NL Planner | ✅ Done | LLM-driven NL→AgentIR with auto-validation & retry |
| 5 | Dynamic ADK Compiler | ✅ Done | `@node` + `ctx.run_node()` pattern per ADK docs |
| 6 | Tools Module | ✅ Done | AST scanner, registry, ToolNode, `tools scan` CLI |
| 7 | FastAPI Server | ✅ Done | 6 endpoints: health, generate, list, run, tools, OpenAPI |
| 8 | Artifact Store | ✅ Done | Persists requirements, IR schemas, scripts, logs, index |
| 9 | Workflow Runner | ✅ Done | Subprocess execution with structured logging |
| 10 | Unit Test Coverage | ✅ Done | 253 tests, 100% pass |
| 11 | Real API E2E Tests | ✅ Done | DeepSeek API verified end-to-end |

---

## 3. Project Structure

```
agentir/
├── __init__.py
├── ir/                              # Layer 1: Intermediate Representation
│   ├── nodes.py                     # 6 node types (agent, sequence, parallel,
│   │                                #   condition, loop, tool)
│   ├── models.py                    # WorkflowDefinition
│   └── schema.py                    # Serialization (dict/json/file)
│
├── validator/                       # Layer 2: Validator
│   ├── rules.py                     # Validation rules + walker
│   └── validator.py                 # ValidationReport + public API
│
├── llm/                             # LLM Client Layer
│   ├── client.py                    # create_llm_callable() for OpenAI-compatible APIs
│   └── config.py                    # LLMConfig, AgentConfig (model/instruction/tools/temp)
│
├── planner/                         # NL → AgentIR Planner
│   └── planner.py                   # Planner with LLM-driven plan + retry loop
│
├── tools/                           # User Tools Module
│   ├── scanner.py                   # AST-based tool scanner
│   └── registry.py                  # Tool discovery, YAML overlay, prompt context
│
├── compiler/                        # Layer 3: Compiler
│   ├── base.py                      # BaseCompiler (ABC) + CompilationResult
│   └── adk/
│       └── compiler.py              # ADKCompiler: tree→@node dynamic workflow code
│
├── artifacts/                       # Artifact Storage & Runner
│   ├── store.py                     # WorkflowArtifactStore (requirements/ir/outputs/logs)
│   └── runner.py                    # WorkflowRunner (subprocess + log)
│
├── server/                          # FastAPI Server
│   ├── config.py                    # ServerConfig (env → LLM + paths)
│   ├── main.py                      # create_app() factory
│   ├── models.py                    # Request/Response Pydantic models
│   ├── routes.py                    # 6 API endpoints
│   └── cli.py                       # CLI: agentir-server, agentir tools scan

tools/                               # User-written tool scripts (examples)
├── web_search.py
└── calculator.py

tests/
├── test_nodes.py                    # 30 tests
├── test_models.py                   # 10 tests
├── test_schema.py                   # 13 tests
├── test_validator.py                # 21 tests
├── test_compiler.py                 # 34 tests
├── test_llm.py                      # 48 tests
├── test_planner.py                  # 25 tests
├── test_server.py                   # 50 tests
└── test_tools.py                    # 22 tests
                                     # ────
                                     # 253 tests total
```

---

## 4. Architecture Layers

### 4.1 Layer 1 — AgentIR Schema (IR Core)

6 supported node types (Pydantic v2 discriminated union):

| Node | `type` | Key Fields |
|------|--------|------------|
| **AgentNode** | `"agent"` | `agent: str` |
| **SequenceNode** | `"sequence"` | `steps: list[WorkflowNode]` |
| **ParallelNode** | `"parallel"` | `branches: list[WorkflowNode]` |
| **ConditionNode** | `"condition"` | `expression: str`, `true_branch`, `false_branch` |
| **LoopNode** | `"loop"` | `max_iterations: int`, `body: WorkflowNode` |
| **ToolNode** | `"tool"` | `tool: str` (references user tool registry) |

Example AgentIR JSON:

```json
{
  "name": "search_then_analyze",
  "version": "0.1.0",
  "description": "Search then analyze",
  "root": {
    "type": "sequence",
    "steps": [
      {"type": "tool", "tool": "web_search"},
      {"type": "agent", "agent": "analyst"}
    ]
  }
}
```

### 4.2 Layer 2 — Validator

Deterministic, no LLM. Validation rules:
- `AGENT_NOT_FOUND` / `TOOL_NOT_FOUND` — referenced entity not in registry
- `EMPTY_SEQUENCE` / `EMPTY_PARALLEL` — empty container nodes
- `EMPTY_EXPRESSION` — ConditionNode with blank expression
- `MAX_DEPTH_EXCEEDED` — nesting depth > limit (default: 20)
- `SCHEMA_ERROR` — Pydantic schema validation failure

### 4.3 LLM Module

Provider abstraction supporting DeepSeek, OpenAI, Ollama, Groq, Together, and custom endpoints. Configuration via `.env` file or environment variables.

```python
from agentir.llm.config import LLMConfig

# DeepSeek
config = LLMConfig.deepseek(api_key="sk-xxx", model="deepseek-chat")
# OpenAI
config = LLMConfig.openai(api_key="sk-xxx")
```

Agent configuration injection: per-agent model, instruction, tools, temperature.

### 4.4 Planner (NL → AgentIR)

LLM-driven planning with built-in validation retry loop:
1. Send NL description + AgentIR schema to LLM
2. Parse JSON from response
3. Validate against AgentIR schema
4. On failure: feed errors back to LLM, retry (up to `max_retries`)
5. On success: return validated `WorkflowDefinition`

Tool-aware: when tools are available, they are injected into the system prompt so the LLM can reference them as `{"type": "tool", "tool": "<name>"}` nodes.

### 4.5 Tools Module

Users write Python tools by convention:

```python
# tools/web_search.py
async def execute(query: str) -> str:
    """Search the web for information."""
    # ... implementation
    return results
```

- **Scanner**: AST-based, extracts function signature + docstring
- **Registry**: `ToolRegistry.from_directory("./tools")` auto-discovers tools
- **CLI**: `agentir tools scan` lists discovered tools
- **YAML overlay**: Optional `tools/registry.yaml` for manual metadata enrichment
- **Planner integration**: Tool list injected into LLM system prompt
- **Validator integration**: `TOOL_NOT_FOUND` check against registry

### 4.6 Dynamic ADK Compiler

Target: **Google ADK 2.0 Dynamic Workflows** (`@node` + `ctx.run_node()`).

Follows the official ADK pattern from https://adk.dev/graphs/dynamic/:

| IR Node | Generated Code |
|---------|---------------|
| AgentNode | `_result = await ctx.run_node(agent_name, _result)` |
| SequenceNode | Sequential `ctx.run_node()` chain |
| ParallelNode | `asyncio.gather()` + separate `@node` branch functions |
| ConditionNode | `if/else` with condition evaluation |
| LoopNode | `while` loop with counter |
| ToolNode | `tool_{name}` `@node` wrapper → `import tool → await execute()` |

Output structure:

```python
# Generated by AgentIR ADK Compiler v0.2.0
from google.adk import Context, Workflow
from google.adk.agents import LlmAgent
from google.adk.workflow import node

# Agent definitions (LlmAgent)
researcher = LlmAgent(name="researcher", model="gemini-2.0-flash", ...)

# Tool wrappers (@node functions)
from web_search import execute as _exec_web_search
@node
async def tool_web_search(ctx: Context, _result=None):
    return await _exec_web_search(str(_result))

# Main orchestrator
@node(rerun_on_resume=True)
async def main_workflow(ctx: Context):
    _result = None
    _result = await ctx.run_node(tool_web_search, _result)
    _result = await ctx.run_node(researcher, _result)
    return _result

# Workflow definition
workflow = Workflow(
    name="search_and_analyze",
    edges=[("START", main_workflow)],
)
```

### 4.7 Artifact Store

Three core artifacts persisted per workflow:

```
artifacts/
├── requirements/{id}.txt     # NL requirement text
├── ir/{id}.json              # AgentIR Schema (Intermediate Representation)
├── outputs/{id}.py           # ADK 2.0 Python source code
├── logs/{id}_{ts}.log        # Execution logs
└── index.json                # Workflow registry
```

- `WorkflowArtifactStore` — file-based store with atomic index updates
- `WorkflowRunner` — subprocess execution with stdout/stderr capture + structured logging

### 4.8 Server (FastAPI)

6 API endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check + LLM config status + tool count |
| `POST` | `/api/v1/workflows/generate` | NL → AgentIR → Validate → Compile → Save |
| `GET` | `/api/v1/workflows` | List all generated workflows (paginated) |
| `POST` | `/api/v1/workflows/{id}/run` | Execute workflow in subprocess + log |
| `GET` | `/api/v1/tools` | List discovered user tools |
| `GET` | `/docs` | Swagger UI |

Pipeline: `NL → Planner(LLM) → AgentIR → Validator → ADK Compiler → Save`

### 4.9 CLI

```bash
agentir-server                    # Start server
agentir-server --port 9000        # Custom port
agentir-server --reload           # Hot-reload mode
agentir tools scan                # Scan & list tools
agentir tools scan --dir ./tools  # Custom tools directory
```

---

## 5. API Quick Reference

### Generate

```bash
curl -X POST http://localhost:8000/api/v1/workflows/generate \
  -H "Content-Type: application/json" \
  -d '{"requirement": "先搜索最新AI进展，再让研究员分析"}'
```

### List & Run

```bash
curl http://localhost:8000/api/v1/workflows                    # List all
curl -X POST http://localhost:8000/api/v1/workflows/{id}/run \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 30}'                                  # Execute
```

---

## 6. Test Results

```
tests/test_nodes.py      ..........                               30 passed
tests/test_models.py     ..........                               10 passed
tests/test_schema.py     .............                            13 passed
tests/test_validator.py  .....................                    21 passed
tests/test_compiler.py   ..................................       34 passed
tests/test_llm.py        ........................................ 48 passed
tests/test_planner.py    .........................                25 passed
tests/test_server.py     .......................................... 50 passed
tests/test_tools.py      .......................                  22 passed
────────────────────────────────────────────────────────────────────────────
                         TOTAL: 253 passed
```

---

## 7. Design Principles

| Principle | Status |
|-----------|--------|
| Deterministic | ✅ Same IR → same output |
| Runtime Agnostic | ✅ No ADK concepts in IR |
| Extensible | ✅ `BaseCompiler` ABC, pluggable runtimes |
| Strong typing | ✅ Pydantic v2 |
| No LLM in IR/Validator/Compiler | ✅ Only Planner uses LLM |
| Framework independence | ✅ Multi-provider LLM abstraction |
| IR as first-class artifact | ✅ Persisted to `artifacts/ir/` |

---

## 8. What's NOT Implemented (Future)

- SubWorkflow / reusable workflow references
- Cycle detection in validator
- Additional compiler targets (LangGraph, CrewAI, AutoGen)
- Visual workflow designer / editor
- Human-in-the-loop (HITL) nodes
- Workflow versioning / diff
- Authentication / API keys for the server
- Production deployment (Docker, health probes, etc.)

---

## 9. Technical Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.12+ |
| Schema | Pydantic v2 |
| LLM Provider | DeepSeek (primary), OpenAI, Ollama, Groq, custom |
| Web Framework | FastAPI + Uvicorn |
| Testing | pytest (253 tests) |
| Linting | ruff |
| Target Runtime | Google ADK 2.0 Dynamic Workflows |
| Env Management | python-dotenv |
