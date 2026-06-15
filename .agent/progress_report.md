# AgentIR — Project Progress Report

> **Date**: 2026-06-15  
> **Version**: v0.1.0  
> **Status**: Phase 1 Core Pipeline Complete ✅

---

## 1. Overview

AgentIR is a framework-agnostic Agent Workflow Intermediate Representation (IR) and Compiler System — the "Terraform of Agent Workflows".

Phase 1 delivers the core pipeline:

```
JSON → Pydantic → Validator → ADK Compiler → Executable Python Code
```

All three layers (IR Schema, Validator, ADK Compiler) are implemented and tested.

---

## 2. Deliverables Status

| # | Deliverable | Status | Notes |
|---|------------|--------|-------|
| 1 | AgentIR Schema | ✅ Done | 5 node types, Pydantic v2, discriminated union |
| 2 | AgentIR Validator | ✅ Done | Agent existence, empty containers, depth limit, expression check |
| 3 | ADK Workflow Compiler | ✅ Done | Targets ADK 2.0 Workflow Runtime |
| 4 | Unit Test Coverage | ✅ Done | 99 tests, 100% pass |
| 5 | Example Workflows | ✅ Done | 3 examples (research, translation, quality loop) |
| 6 | Architecture Documentation | ✅ Done | This document + design in `system_agent.md` |

---

## 3. Implemented Architecture

### 3.1 Project Structure

```
agentir/
├── __init__.py
├── ir/                              # Layer 1: Intermediate Representation
│   ├── __init__.py
│   ├── nodes.py                     # AgentNode, SequenceNode, ParallelNode,
│   │                                #   ConditionNode, LoopNode + WorkflowNode union
│   ├── models.py                    # WorkflowDefinition (root model)
│   └── schema.py                    # Serialization utilities (dict/json/file)
│
├── validator/                       # Layer 2: Validator
│   ├── __init__.py
│   ├── rules.py                     # AgentRegistry, ValidationError, built-in rules
│   └── validator.py                 # validate_workflow/dict/json + ValidationReport
│
├── compiler/                        # Layer 3: Compiler
│   ├── __init__.py
│   ├── base.py                      # BaseCompiler (ABC) + CompilationResult
│   └── adk/
│       ├── __init__.py
│       └── compiler.py              # ADKCompiler: tree→graph flattening + code gen
│
examples/
├── research_pipeline.json           # Research → (Review loop | Write) → Publish
├── parallel_translation.json        # Extract → [Translate ×3] → Merge
└── quality_check_loop.json          # Generate → (Check + Improve loop)

tests/
├── test_nodes.py                    # 30 tests
├── test_models.py                   # 10 tests
├── test_schema.py                   # 13 tests
├── test_validator.py                # 21 tests
└── test_compiler.py                 # 25 tests
```

### 3.2 Layer 1 — AgentIR Schema (v0.1)

5 supported node types, implemented as Pydantic v2 discriminated union:

| Node | `type` literal | Key Fields |
|------|---------------|------------|
| **AgentNode** | `"agent"` | `agent: str` |
| **SequenceNode** | `"sequence"` | `steps: list[WorkflowNode]` |
| **ParallelNode** | `"parallel"` | `branches: list[WorkflowNode]` |
| **ConditionNode** | `"condition"` | `expression: str`, `true_branch`, `false_branch` |
| **LoopNode** | `"loop"` | `max_iterations: int (>0)`, `body: WorkflowNode` |

Features:
- Recursive nesting (any node can nest any node)
- Discriminated union via `Annotated[..., Field(discriminator="type")]`
- Full JSON Schema generation via `generate_json_schema()`
- File I/O: `workflow_from_file()`, `workflow_to_file()`

### 3.3 Layer 2 — Validator

Deterministic, no LLM involved.

Validation rules:
- `AGENT_NOT_FOUND` — referenced agent not in registry
- `EMPTY_SEQUENCE` — SequenceNode with zero steps
- `EMPTY_PARALLEL` — ParallelNode with zero branches
- `EMPTY_EXPRESSION` — ConditionNode with blank expression
- `MAX_DEPTH_EXCEEDED` — nesting depth exceeds limit (default: 20)
- `SCHEMA_ERROR` — Pydantic schema validation failure

Public API:
```python
from agentir.validator import (
    validate_workflow,        # WorkflowDefinition → ValidationReport
    validate_workflow_dict,   # dict → ValidationReport (includes schema check)
    validate_workflow_json,   # JSON string → ValidationReport
    AgentRegistry,            # Set of available agent names
    ValidationReport,         # { is_valid, errors, warnings, summary() }
)
```

### 3.4 Layer 3 — ADK Compiler

Target: **Google ADK 2.0 Workflow Runtime** (NOT the deprecated 1.x SequentialAgent/ParallelAgent/LoopAgent API).

Compilation strategy:
1. Walk the tree IR, flatten into a graph (`FlatGraph`)
2. Assign unique IDs to agent occurrences
3. Decompose compound nodes:
   - **Sequence** → linear edges
   - **Parallel** → `fork` (fan-out) + `join` (fan-in) helper nodes
   - **Condition** → `condition` helper node with `{"true": ..., "false": ...}` routing
   - **Loop** → `loop_counter` helper + `body_entry` join + cycle edges
4. Generate clean Python source code using `LlmAgent` + `Workflow` + `@node` helpers

Output: Valid, compilable Python source code that creates an ADK `Workflow` object.

---

## 4. Test Results

```
tests/test_nodes.py      ..........                               30 passed
tests/test_models.py     ..........                               10 passed
tests/test_schema.py     .............                            13 passed
tests/test_validator.py  .....................                    21 passed
tests/test_compiler.py   .........................                25 passed
--------------------------------------------------------------------
                         TOTAL: 99 passed in 0.39s
```

---

## 5. Example: End-to-End Pipeline

```python
from agentir.ir.schema import workflow_from_file
from agentir.validator import validate_workflow, AgentRegistry
from agentir.compiler.adk import ADKCompiler

# 1. JSON → Pydantic
wf = workflow_from_file("examples/research_pipeline.json")

# 2. Validate
registry = AgentRegistry.from_list(["researcher", "reviewer", "writer", "publisher"])
report = validate_workflow(wf, agent_registry=registry)
assert report.is_valid

# 3. Compile to ADK 2.0
result = ADKCompiler().compile(wf)
assert result.success
compile(result.source_code, "<generated>", "exec")  # Valid Python ✅
```

All 3 example workflows pass the complete pipeline:
- ✅ `research_pipeline.json` — 4 agents, condition + loop
- ✅ `parallel_translation.json` — 5 agents, parallel branches
- ✅ `quality_check_loop.json` — 4 agents, nested loop + condition

---

## 6. Design Principles Compliance

| Principle | Status |
|-----------|--------|
| Deterministic | ✅ Same IR → same output always |
| Runtime Agnostic | ✅ No ADK concepts in IR |
| Extensible | ✅ `BaseCompiler` ABC, pluggable runtimes |
| Strong typing | ✅ Pydantic v2 + mypy-ready |
| No LLM involvement | ✅ Validator and Compiler are pure code |
| Framework independence | ✅ ADK is optional; compiler generates code |
| No code generation hacks | ✅ Object-based graph building, then serialization |

---

## 7. What's NOT Implemented (Future Phases)

- SubWorkflow node
- Natural Language → AgentIR parser
- LLM-driven workflow planning
- Visual workflow designer
- Additional compiler targets (LangGraph, CrewAI, AutoGen, Dify, etc.)
- Runtime execution environment
- Cycle detection in validator
- Agent configuration injection (model, instruction, tools)

---

## 8. Next Steps

Suggested priorities:

1. **Agent configuration injection** — Allow passing model/instruction/tools per agent to the compiler
2. **Cycle detection** — Add graph cycle detection to validator
3. **SubWorkflow node** — Complete the 6th node type
4. **LangGraph compiler** — Second runtime target
5. **Runtime test harness** — Actually execute compiled workflows against real ADK/LangGraph
6. **CLI tool** — `agentir compile input.json --target adk --output workflow.py`

---

## 9. Technical Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.12+ |
| Package Manager | uv (pip fallback available) |
| Schema | Pydantic v2 |
| Testing | pytest (99 tests) |
| Code Quality | ruff |
| Type Checking | mypy (strict mode planned) |
| Documentation | mkdocs (planned) |
| Target Runtime | Google ADK 2.0 Workflow Runtime |
