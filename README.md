# AgentIR

> **Agent Workflow Intermediate Representation** — a framework-agnostic bridge between Dynamic Workflow (AI-generated) and Traditional Workflow (BPMN).

[English](./README.md) | [中文](./README_cn.md)

---

## Introduction

AgentIR solves a fundamental contradiction:

- **Traditional workflows** (BPMN drag-and-drop) can build complex logic but require deep expertise
- **Dynamic Workflows** (AI writes scripts from natural language) have zero barrier but lack visualization, testability, and clear node definitions

AgentIR bridges the gap: describe workflows in natural language → generate **AgentIR** (JSON IR) → visually review/edit → compile to multi-framework executable scripts.

```
Natural Language → Planner (LLM) → AgentIR (.json)

                                        ├── Visual Editor (ReactFlow)
                                        ├── Security Audit
                                        ├── ADK Compiler
                                        ├── LangGraph Compiler
                                        └── CrewAI Compiler
```

**Current capabilities:**
- 7 workflow node types (agent, tool, subworkflow, sequence, parallel, condition, loop)
- AI auto-generates system prompts for each Agent
- ReactFlow visual editor (property panel, undo/redo, IR diff, dagre layout)
- 3 compiler targets (Google ADK, LangGraph, CrewAI)
- 289 tests, 100% pass rate

---

## Screenshots

> 📸 *（Screenshots to be added: workflow generation, visual editor, execution results）*

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- DeepSeek API Key (or any OpenAI-compatible API)

### 1. Clone

```bash
git clone <repo-url>
cd DynamicWorkflowAST
```

### 2. Configure API Key

```bash
cp .env.example .env
```

Edit `.env` with your DeepSeek API key:
```env
AGENTIR_LLM_PROVIDER=deepseek
AGENTIR_LLM_MODEL=deepseek-chat
AGENTIR_LLM_API_KEY=sk-your-key-here
```

### 3. Create virtual environment & install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install openai fastapi uvicorn python-dotenv pytest
```

### 4. Start backend

```bash
agentir-server
# or
python -m agentir.server.cli
```

Open http://localhost:8000/docs for the API documentation.

### 5. Start frontend (optional)

```bash
cd ui
npm install
npm run dev
```

Open http://localhost:5173 for the visual editor.

### 6. Quick test

```bash
# Generate a workflow
curl -X POST http://localhost:8000/api/v1/workflows/generate \
  -H "Content-Type: application/json" \
  -d '{"requirement": "First have researcher gather data, then writer produce a report"}'

# Run all tests
pytest
```
