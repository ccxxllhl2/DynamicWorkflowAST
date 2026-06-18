# AgentIR

> 一个框架无关的 Agent 工作流中间表示（IR）和编译器系统。

[English](./README.md) | 中文

将自然语言描述的 Agent 工作流转换为可运行的 **Google ADK 2.0 Dynamic Workflow** Python 代码。

```
NL 需求 → Planner(LLM) → AgentIR Schema(.json) → Validator → ADK Compiler → 运行
  .txt                       .json                     ↓              .py
                                                    artifacts/ir/   artifacts/outputs/
```

---

## 特性

- **自然语言驱动**：用中文或英文描述工作流，LLM 自动生成 AgentIR Schema
- **框架无关**：IR 层不含任何运行时依赖，可扩展至多种编译器目标
- **确定性编译**：同样的 IR 生成同样的代码，Validator 不含 LLM
- **6 种节点类型**：agent、sequence、parallel、condition、loop、tool
- **自定义工具**：编写 Python 函数即可注册为工作流工具节点
- **多 LLM 提供商**：DeepSeek、OpenAI、Ollama、Groq、Together、自定义端点
- **FastAPI 服务**：开箱即用的 REST API + Swagger 文档
- **全流程持久化**：需求、IR、生成代码、运行日志均持久化存储

---

## 安装

### 环境要求

- Python 3.12+

### 基础安装

```bash
# 克隆项目
git clone <repo-url>
cd DynamicWorkflowAST

# 仅安装核心依赖（IR + Validator + Planner + Compiler）
pip install -e .

# 安装 LLM 支持
pip install -e ".[llm]"

# 安装服务端
pip install -e ".[server]"

# 完整安装
pip install -e ".[all]"

# 开发模式（包含测试、lint、类型检查）
pip install -e ".[dev]"
```

### 各依赖组说明

| 组 | 包含依赖 | 用途 |
|---|---------|------|
| `[llm]` | `openai>=1.0` | LLM 客户端，调用各厂商 API |
| `[server]` | `fastapi`, `uvicorn`, `python-dotenv` | FastAPI 服务端 |
| `[dev]` | `pytest`, `pytest-cov`, `mypy`, `ruff` | 测试与代码检查 |
| `[all]` | 以上全部 | 完整功能 |

---

## 配置 LLM 提供商

AgentIR 通过环境变量或 `.env` 文件配置 LLM。在项目根目录创建 `.env` 文件：

### DeepSeek（推荐，主要测试提供商）

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

### Ollama（本地模型）

```env
AGENTIR_LLM_PROVIDER=ollama
AGENTIR_LLM_MODEL=llama3
# 无需 API Key，Ollama 需在本机运行
```

### Anthropic / Groq / Together / 自定义端点

```env
# Anthropic
AGENTIR_LLM_PROVIDER=anthropic
AGENTIR_LLM_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-your-key-here

# 自定义 OpenAI 兼容端点
AGENTIR_LLM_PROVIDER=custom
AGENTIR_LLM_MODEL=your-model
AGENTIR_LLM_API_KEY=your-key
AGENTIR_LLM_BASE_URL=https://your-endpoint/v1
```

### 完整环境变量参考

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AGENTIR_LLM_PROVIDER` | LLM 提供商 | `openai` |
| `AGENTIR_LLM_MODEL` | 模型名称 | 各提供商默认值 |
| `AGENTIR_LLM_API_KEY` | API Key（通用） | - |
| `AGENTIR_LLM_BASE_URL` | 自定义 API 地址 | - |
| `AGENTIR_LLM_TEMPERATURE` | 生成温度 | `0.7` |
| `AGENTIR_LLM_MAX_TOKENS` | 最大输出 token | `4096` |
| `AGENTIR_HOST` | 服务监听地址 | `0.0.0.0` |
| `AGENTIR_PORT` | 服务端口 | `8000` |
| `AGENTIR_ARTIFACTS_DIR` | 产物存储目录 | `./artifacts` |
| `AGENTIR_TOOLS_DIR` | 工具目录 | `./tools` |

提供商专属 API Key 变量也有同样效果：`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GROQ_API_KEY`、`TOGETHER_API_KEY`。

---

## 自定义工具节点

AgentIR 支持用户编写 Python 函数作为工作流中的自定义工具。扫描器通过 AST 自动发现工具，注入到 Planner 和 Compiler 中。

### 约定

在 `tools/` 目录下创建 `.py` 文件，文件中包含一个 `async def execute(...)` 函数：

1. **函数签名**：必须是 `async def execute`，参数名和类型注解会被自动提取
2. **文档字符串**：第一行作为工具描述，注入到 Planner 的 system prompt 中
3. **返回值**：建议返回 `str` 类型

### 基础示例

```python
# tools/web_search.py
async def execute(query: str) -> str:
    """Search the web for information."""
    # ... 调用搜索 API
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

### 带多个参数的工具

```python
# tools/translator.py
async def execute(text: str, target_language: str) -> str:
    """Translate text to the target language."""
    # ... 调用翻译 API
    return f"Translated to {target_language}: {translate(text, target_language)}"
```

### 验证工具注册状态

```bash
# 扫描并列出所有发现的工具
agentir tools scan

# 指定自定义工具目录
agentir tools scan --dir ./my_tools
```

### 工具如何融入工作流

1. **Planner 阶段**：工具列表注入 LLM system prompt，LLM 会生成 `{"type": "tool", "tool": "web_search"}` 节点
2. **Validator 阶段**：检查 `TOOL_NOT_FOUND`，确保引用的工具在注册表中
3. **Compiler 阶段**：生成 `@node` 装饰的工具包装函数，自动导入并调用你的 `execute()`

### 可选：YAML 元数据覆盖

如需手动补充工具描述或覆盖参数，可在 `tools/` 下创建 `registry.yaml`：

```yaml
tools:
  - name: web_search
    path: tools/web_search.py
    function: execute
    description: Search the web for real-time information and news.
```

YAML 中的 `description` 会覆盖 AST 扫描获取的文档字符串。

---

## 快速开始

### 1. 启动服务

```bash
# 使用默认配置
agentir-server

# 指定端口
agentir-server --port 9000

# 开发热重载
agentir-server --reload
```

服务启动后访问：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/v1/health

### 2. 生成工作流

```bash
curl -X POST http://localhost:8000/api/v1/workflows/generate \
  -H "Content-Type: application/json" \
  -d '{"requirement": "先搜索最新AI进展，再让研究员分析"}'
```

返回结果包含工作流 ID、AgentIR Schema 和生成的 ADK Python 代码。

### 3. 查看已生成的工作流

```bash
curl http://localhost:8000/api/v1/workflows
```

### 4. 运行工作流

```bash
curl -X POST http://localhost:8000/api/v1/workflows/{id}/run \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 30}'
```

---

## Python API 使用

```python
from agentir.llm import LLMConfig, create_llm_callable
from agentir.planner import Planner

# 1. 配置 LLM
config = LLMConfig.deepseek(api_key="sk-xxx", model="deepseek-chat")

# 2. 配置 Agent 行为（可选，影响生成代码中 LlmAgent 的参数）
config.set_agent("researcher", instruction="You are a research specialist.")
config.set_agent("analyst", instruction="You are a data analyst.")

# 批量配置
config.set_agents_batch(
    ["researcher", "reviewer", "writer"],
    instruction_template="You are the {agent_name} agent.",
)

# 3. 创建 Planner
planner = Planner(config)

# 4. 从自然语言生成工作流
result = planner.plan("先搜索资料，再让研究员分析，最后输出报告")
print(result.workflow.root)  # AgentIR Schema

# 5. 编译为 ADK 代码
from agentir.compiler.adk import ADKCompiler
compiler = ADKCompiler()
code = compiler.compile(result.workflow)
print(code.source_code)  # 生成的可运行 Python 代码
```

---

## API 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/health` | 健康检查 + LLM 状态 + 工具数 |
| `POST` | `/api/v1/workflows/generate` | NL → AgentIR → 校验 → 编译 → 保存 |
| `GET` | `/api/v1/workflows` | 列出所有已生成的工作流 |
| `POST` | `/api/v1/workflows/{id}/run` | 在子进程中执行工作流 |
| `GET` | `/api/v1/tools` | 列出已发现的用户工具 |
| `GET` | `/docs` | Swagger UI |

---

## AgentIR Schema 节点类型

| 节点 | `type` | 关键字段 |
|------|--------|---------|
| Agent | `"agent"` | `agent: str` |
| Sequence | `"sequence"` | `steps: list[WorkflowNode]` |
| Parallel | `"parallel"` | `branches: list[WorkflowNode]` |
| Condition | `"condition"` | `expression`, `true_branch`, `false_branch` |
| Loop | `"loop"` | `max_iterations: int`, `body: WorkflowNode` |
| Tool | `"tool"` | `tool: str` |

示例 AgentIR JSON（可直接在 `examples/` 中找到）：

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

## 项目结构

```
agentir/
├── ir/                    # Layer 1: 中间表示
│   ├── nodes.py           #   6 种节点类型 (Pydantic v2)
│   ├── models.py          #   WorkflowDefinition
│   └── schema.py          #   序列化 (dict/json/file)
├── validator/             # Layer 2: 校验器（确定性，无 LLM）
├── llm/                   # LLM 客户端抽象
├── planner/               # NL → AgentIR Planner（LLM 驱动）
├── tools/                 # 自定义工具模块（AST 扫描 + 注册表）
├── compiler/              # Layer 3: 编译器
│   ├── base.py            #   BaseCompiler (ABC)
│   └── adk/compiler.py    #   ADKCompiler → @node 动态工作流代码
├── artifacts/             # 产物持久化 & 运行器
├── server/                # FastAPI 服务
tools/                     # 用户工具脚本
examples/                  # AgentIR Schema 示例
tests/                     # 253 个单元测试
```

---

## 测试

```bash
# 运行全部测试
pytest

# 运行特定模块
pytest tests/test_planner.py

# 带覆盖率
pytest --cov=agentir
```

当前测试覆盖率：**253 tests，100% pass**。

---

## 设计原则

| 原则 | 状态 |
|------|------|
| 确定性编译 | ✅ 相同 IR → 相同输出 |
| 运行时无关 | ✅ IR 层无 ADK 概念 |
| 可扩展 | ✅ `BaseCompiler` ABC，可插拔运行时 |
| 强类型 | ✅ Pydantic v2 |
| LLM 隔离 | ✅ 仅 Planner 使用 LLM |
| 多厂商 LLM | ✅ DeepSeek / OpenAI / Ollama / Groq / Together / 自定义 |
| IR 为第一公民 | ✅ 持久化到 `artifacts/ir/` |

---

## License

MIT
