---
name: WFAST
description: 
tools: list_dir, search_file, search_content, read_file, read_lints, replace_in_file, write_to_file, execute_command, mcp_get_tool_description, mcp_call_tool, delete_file, connect_cloud_service, preview_url, web_fetch, use_skill, web_search, automation_update, task
agentMode: manual
enabled: true
enabledAutoRun: true
---
# AGENT.md

## Project Name

AgentIR

A framework-agnostic Agent Workflow Intermediate Representation (IR) and 
Compiler System.

The project aims to become the "Terraform of Agent Workflows".

Instead of directly generating framework-specific code, workflows are 
represented as a normalized intermediate representation (AgentIR), 
validated, and compiled into different Agent runtimes.

The first target runtime is Google ADK Dynamic Workflow.

Future targets include:

* LangGraph
* CrewAI
* AutoGen
* Dify
* OpenAI Agents SDK
* Semantic Kernel

---

# Vision

Build a universal Agent Workflow Compiler.

```text
AgentIR
    ↓
Compiler
    ├── ADK
    ├── LangGraph
    ├── CrewAI
    ├── AutoGen
    └── Dify
```

AgentIR must remain independent from any runtime.

The IR is the source of truth.

---

# Phase 1 Scope

Implement only:

```text
AgentIR
    ↓
Validator
    ↓
ADK Compiler
```

DO NOT implement:

* Natural Language Parsing
* LLM Planning
* Workflow Generation by AI
* Visual Designer

These will be future phases.

---

# Technical Stack

Language:

* Python 3.12+

Package Manager:

* uv

Testing:

* pytest

Typing:

* mypy
* pydantic v2

Code Quality:

* ruff

Documentation:

* mkdocs

---

# Core Architecture

## Layer 1

AgentIR Schema

Defines workflow structures independent of runtime.

Example:

```json
{
  "type": "sequence",
  "steps": [
    {
      "type": "agent",
      "agent": "researcher"
    },
    {
      "type": "agent",
      "agent": "writer"
    }
  ]
}
```

---

## Layer 2

Validator

Responsibilities:

* schema validation
* agent existence validation
* workflow structure validation
* cycle detection
* parameter validation

Validation errors must be deterministic.

No LLM involvement.

---

## Layer 3

Compiler

Responsibilities:

Convert AgentIR into runtime-specific executable workflow definitions.

Initial compiler:

```text
AgentIR
    ↓
ADK Dynamic Workflow
```

Future:

```text
AgentIR
    ↓
LangGraph
```

```text
AgentIR
    ↓
CrewAI
```

Compiler output should be generated through object construction whenever 
possible.

Avoid string-based code generation when a runtime API is available.

---

# AgentIR Specification

## Workflow Nodes

### Agent Node

```json
{
  "type": "agent",
  "agent": "researcher"
}
```

---

### Sequence Node

```json
{
  "type": "sequence",
  "steps": []
}
```

---

### Parallel Node

```json
{
  "type": "parallel",
  "branches": []
}
```

---

### Condition Node

```json
{
  "type": "condition",
  "expression": "need_retry",
  "true_branch": {},
  "false_branch": {}
}
```

---

### Loop Node

```json
{
  "type": "loop",
  "max_iterations": 3,
  "body": {}
}
```

---

### SubWorkflow Node

```json
{
  "type": "subworkflow",
  "workflow": "research_pipeline"
}
```

---

# Compiler Design Principles

## Deterministic

The same AgentIR must always produce the same output.

No randomness.

No LLM calls.

---

## Reproducible

Compilation results must be reproducible across machines.

---

## Runtime Agnostic

AgentIR must not contain ADK-specific concepts.

Bad:

```json
{
  "type": "adk_node"
}
```

Good:

```json
{
  "type": "agent"
}
```

---

## Extensible

New runtimes must be pluggable.

Target architecture:

```python
class Compiler:
    def compile(ir):
        pass

class ADKCompiler(Compiler):
    pass

class LangGraphCompiler(Compiler):
    pass
```

---

# Project Structure

```text
agentir/

├── ir/
│   ├── models.py
│   ├── nodes.py
│   └── schema.py
│
├── validator/
│   ├── validator.py
│   └── rules.py
│
├── compiler/
│   ├── base.py
│   ├── adk/
│   │   ├── compiler.py
│   │   └── translator.py
│   │
│   └── langgraph/
│
├── runtime/
│
├── examples/
│
├── tests/
│
└── docs/
```

---

# Deliverables

Phase 1 Deliverables:

1. AgentIR Schema
2. AgentIR Validator
3. ADK Dynamic Workflow Compiler
4. Unit Test Coverage > 80%
5. Example Workflows
6. Architecture Documentation

---

# Coding Rules

* Strong typing everywhere
* No Any unless unavoidable
* Favor composition over inheritance
* Pydantic models for all schemas
* 100% deterministic compilation
* No hidden magic
* No runtime code generation hacks
* No framework lock-in

---

# Long-Term Goal

AgentIR should become a universal workflow representation for Agent 
systems, similar to how Terraform HCL became a universal abstraction layer 
for cloud infrastructure.

The project should prioritize correctness, determinism, extensibility, and 
framework independence over rapid feature growth.