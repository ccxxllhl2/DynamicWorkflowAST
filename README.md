# AgentIR

> A framework-agnostic Agent Workflow Intermediate Representation (IR) and Compiler System.

English | [中文](./README_cn.md)

Converts natural language descriptions of agent workflows into runnable **Google ADK 2.0 Dynamic Workflow** Python code.

```
NL Requirement → Planner(LLM) → AgentIR Schema(.json) → Validator → ADK Compiler → Run
     .txt                         .json                     ↓              .py
                                                       artifacts/ir/   artifacts/outputs/
```

---

## Features

- **NL-driven**: Describe workflows in natural language, LLM auto-generates AgentIR Schema
- **Framework-agnostic**: IR layer has zero runtime dependencies, extensible to multiple compiler targets
- **Deterministic compilation**: Same IR → same output, Validator uses no LLM
- **6 node types**: agent, sequence, parallel, condition, loop, tool
- **Custom tools**: Write Python functions to register as workflow tool nodes
- **Multi-provider LLM**: DeepSeek, OpenAI, Ollama, Groq, Together, custom endpoints
- **FastAPI server**: Ready-to-use REST API + Swagger docs
- **Full pipeline persistence**: Requirements, IR, generated code, and run logs all persisted

---

## Installation

### Requirements

- Python 3.12+

### Install

```bash
# Clone the repo
git clone <repo-url>
cd DynamicWorkflowAST

# Core dependencies only (IR + Validator + Planner + Compiler)
pip install -e .

# With LLM support
pip install -e ".[llm]"

# With server support
pip install -e ".[server]"

# Full installation
pip install -e ".[all]"

# Development mode (tests, linting, type checking)
pip install -e ".[dev]"
```

### Dependency Groups

| Group | Dependencies | Purpose |
|-------|-------------|---------|
| `[llm]` | `openai>=1.0` | LLM client for calling provider APIs |
| `[server]` | `fastapi`, `uvicorn`, `python-dotenv` | FastAPI server |
| `[dev]` | `pytest`, `pytest-cov`, `mypy`, `ruff` | Testing & code quality |
| `[all]` | All of the above | Everything |

---

## LLM Provider Configuration

AgentIR configures the LLM via environment variables or a `.env` file. Create a `.env` file in the project root:

### DeepSeek (recommended, primary test provider)

```env
AGENTIR_LLM_PROVIDER=deepseek
AGENTIR_LLM_MODEL=deepseek-chat
DEEPSEEK_API_KEY=sk-your-key-here
```

### OpenAI

```env
AGENTIR_LLM_PROVIDER=openai
AGENTIR_LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-your-key-here
```

### Ollama (local models)

```env
AGENTIR_LLM_PROVIDER=ollama
AGENTIR_LLM_MODEL=llama3
# No API key needed; Ollama must be running locally
```

### Anthropic / Groq / Together / Custom

```env
# Anthropic
AGENTIR_LLM_PROVIDER=anthropic
AGENTIR_LLM_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-your-key-here

# Custom OpenAI-compatible endpoint
AGENTIR_LLM_PROVIDER=custom
AGENTIR_LLM_MODEL=your-model
AGENTIR_LLM_API_KEY=your-key
AGENTIR_LLM_BASE_URL=https://your-endpoint/v1
```

### Full Environment Variable Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENTIR_LLM_PROVIDER` | LLM provider name | `openai` |
| `AGENTIR_LLM_MODEL` | Model name | Provider default |
| `AGENTIR_LLM_API_KEY` | API key (generic) | — |
| `AGENTIR_LLM_BASE_URL` | Custom base URL | — |
| `AGENTIR_LLM_TEMPERATURE` | Sampling temperature | `0.7` |
| `AGENTIR_LLM_MAX_TOKENS` | Max output tokens | `4096` |
| `AGENTIR_HOST` | Server bind address | `0.0.0.0` |
| `AGENTIR_PORT` | Server port | `8000` |
| `AGENTIR_ARTIFACTS_DIR` | Artifact storage directory | `./artifacts` |
| `AGENTIR_TOOLS_DIR` | Tools directory | `./tools` |

Provider-specific API key variables also work: `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `TOGETHER_API_KEY`.

---

## Custom Tool Nodes

AgentIR lets you write Python functions as custom tools in workflows. The AST-based scanner auto-discovers tools and injects them into both the Planner and Compiler.

### Convention

Create a `.py` file in the `tools/` directory containing an `async def execute(...)` function:

1. **Function signature**: Must be `async def execute` — parameter names and type annotations are auto-extracted
2. **Docstring**: First line is used as the tool description, injected into the Planner's system prompt
3. **Return type**: Recommend returning `str`

### Basic Examples

```python
# tools/web_search.py
async def execute(query: str) -> str:
    """Search the web for information."""
    # ... call search API
    return f"Search results for: {query}"
```

```python
# tools/calculator.py
async def execute(expression: str) -> str:
    """Perform mathematical calculations."""
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"
```

### Multi-parameter Tools

```python
# tools/translator.py
async def execute(text: str, target_language: str) -> str:
    """Translate text to the target language."""
    # ... call translation API
    return f"Translated to {target_language}: {translate(text, target_language)}"
```

### Verify Tool Registration

```bash
# Scan and list all discovered tools
agentir tools scan

# Custom tools directory
agentir tools scan --dir ./my_tools
```

### How Tools Integrate Into the Pipeline

1. **Planner phase**: Tool list is injected into the LLM system prompt; the LLM generates `{"type": "tool", "tool": "web_search"}` nodes
2. **Validator phase**: `TOOL_NOT_FOUND` check ensures referenced tools exist in the registry
3. **Compiler phase**: Generates a `@node`-decorated tool wrapper function that auto-imports and calls your `execute()`

### Optional: YAML Metadata Overlay

To manually enrich tool descriptions or override parameters, create a `registry.yaml` under `tools/`:

```yaml
tools:
  - name: web_search
    path: tools/web_search.py
    function: execute
    description: Search the web for real-time information and news.
```

The YAML `description` overrides the docstring extracted by the AST scanner.

---

## Quick Start

### 1. Start the Server

```bash
# Default configuration
agentir-server

# Custom port
agentir-server --port 9000

# Hot-reload mode
agentir-server --reload
```

After starting, visit:
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/v1/health

### 2. Generate a Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflows/generate \
  -H "Content-Type: application/json" \
  -d '{"requirement": "Search for the latest AI news, then have a researcher analyze it"}'
```

The response includes the workflow ID, AgentIR Schema, and generated ADK Python code.

### 3. List Generated Workflows

```bash
curl http://localhost:8000/api/v1/workflows
```

### 4. Run a Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflows/{id}/run \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 30}'
```

---

## Python API Usage

```python
from agentir.llm import LLMConfig, create_llm_callable
from agentir.planner import Planner

# 1. Configure LLM
config = LLMConfig.deepseek(api_key="sk-xxx", model="deepseek-chat")

# 2. Configure agent behavior (optional; affects LlmAgent params in generated code)
config.set_agent("researcher", instruction="You are a research specialist.")
config.set_agent("analyst", instruction="You are a data analyst.")

# Batch config
config.set_agents_batch(
    ["researcher", "reviewer", "writer"],
    instruction_template="You are the {agent_name} agent.",
)

# 3. Create Planner
planner = Planner(config)

# 4. Generate workflow from natural language
result = planner.plan("Search first, then analyze, finally produce a report")
print(result.workflow.root)  # AgentIR Schema

# 5. Compile to ADK code
from agentir.compiler.adk import ADKCompiler
compiler = ADKCompiler()
code = compiler.compile(result.workflow)
print(code.source_code)  # Runnable Python code
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check + LLM status + tool count |
| `POST` | `/api/v1/workflows/generate` | NL → AgentIR → Validate → Compile → Save |
| `GET` | `/api/v1/workflows` | List all generated workflows |
| `POST` | `/api/v1/workflows/{id}/run` | Execute workflow in subprocess |
| `GET` | `/api/v1/tools` | List discovered user tools |
| `GET` | `/docs` | Swagger UI |

---

## AgentIR Schema Node Types

| Node | `type` | Key Fields |
|------|--------|------------|
| Agent | `"agent"` | `agent: str` |
| Sequence | `"sequence"` | `steps: list[WorkflowNode]` |
| Parallel | `"parallel"` | `branches: list[WorkflowNode]` |
| Condition | `"condition"` | `expression`, `true_branch`, `false_branch` |
| Loop | `"loop"` | `max_iterations: int`, `body: WorkflowNode` |
| Tool | `"tool"` | `tool: str` |

Example AgentIR JSON (also available in `examples/`):

```json
{
  "name": "research_pipeline",
  "version": "0.1.0",
  "description": "A simple research -> review -> write pipeline",
  "root": {
    "type": "sequence",
    "steps": [
      {"type": "agent", "agent": "researcher"},
      {
        "type": "condition",
        "expression": "output.needs_review",
        "true_branch": {
          "type": "loop",
          "max_iterations": 3,
          "body": {"type": "agent", "agent": "reviewer"}
        },
        "false_branch": {"type": "agent", "agent": "writer"}
      },
      {"type": "agent", "agent": "publisher"}
    ]
  }
}
```

---

## Project Structure

```
agentir/
├── ir/                    # Layer 1: Intermediate Representation
│   ├── nodes.py           #   6 node types (Pydantic v2)
│   ├── models.py          #   WorkflowDefinition
│   └── schema.py          #   Serialization (dict/json/file)
├── validator/             # Layer 2: Validator (deterministic, no LLM)
├── llm/                   # LLM client abstraction
├── planner/               # NL → AgentIR Planner (LLM-driven)
├── tools/                 # Custom tool module (AST scanner + registry)
├── compiler/              # Layer 3: Compiler
│   ├── base.py            #   BaseCompiler (ABC)
│   └── adk/compiler.py    #   ADKCompiler → @node dynamic workflow code
├── artifacts/             # Artifact persistence & runner
├── server/                # FastAPI server
tools/                     # User tool scripts
examples/                  # AgentIR Schema examples
tests/                     # 253 unit tests
```

---

## Testing

```bash
# Run all tests
pytest

# Run a specific module
pytest tests/test_planner.py

# With coverage
pytest --cov=agentir
```

Current test coverage: **253 tests, 100% pass**.

---

## Design Principles

| Principle | Status |
|-----------|--------|
| Deterministic | ✅ Same IR → same output |
| Runtime Agnostic | ✅ No ADK concepts in IR |
| Extensible | ✅ `BaseCompiler` ABC, pluggable runtimes |
| Strong typing | ✅ Pydantic v2 |
| No LLM in IR/Validator/Compiler | ✅ Only Planner uses LLM |
| Multi-provider LLM | ✅ DeepSeek / OpenAI / Ollama / Groq / Together / Custom |
| IR as first-class artifact | ✅ Persisted to `artifacts/ir/` |

---

## License

MIT
