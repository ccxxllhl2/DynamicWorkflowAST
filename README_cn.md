# AgentIR

> **Agent 工作流中间表示** — Dynamic Workflow（AI 生成）与传统工作流（BPMN）之间的框架无关桥梁。

[English](./README.md) | 中文

---

## 项目简介

AgentIR 解决的核心矛盾：

- **传统工作流**（BPMN 拖拽）能构建复杂逻辑，但门槛极高，需要专业知识
- **Dynamic Workflow**（AI 根据自然语言编写脚本）门槛为零，但缺乏可视化、可测试性和明确的节点定义

AgentIR 作为两者之间的**桥梁**：用户用自然语言描述工作流 → 自动生成 **AgentIR**（JSON 中间表示）→ 可视化审查/编辑 → 编译为多框架可执行脚本。

```
自然语言 → Planner (LLM) → AgentIR (.json)

                               ├── 可视化编辑器 (ReactFlow)
                               ├── 安全审核
                               ├── ADK 编译器
                               ├── LangGraph 编译器
                               └── CrewAI 编译器
```

**当前能力：**
- 7 种工作流节点（agent、tool、subworkflow、sequence、parallel、condition、loop）
- AI 自动为每个 Agent 生成系统提示词
- ReactFlow 可视化编辑器（属性面板、Undo/Redo、IR Diff、Dagre 布局）
- 3 个编译器目标（Google ADK、LangGraph、CrewAI）
- 289 个测试，100% 通过

---

## 截图实例

> 📸 *（待补充：工作流生成界面、可视化编辑器、运行结果截图）*

---

## 项目启动方法

### 环境要求

- Python 3.12+
- Node.js 18+
- DeepSeek API Key（或其他 OpenAI 兼容 API）

### 1. 克隆项目

```bash
git clone <repo-url>
cd DynamicWorkflowAST
```

### 2. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 DeepSeek API Key：
```env
AGENTIR_LLM_PROVIDER=deepseek
AGENTIR_LLM_MODEL=deepseek-chat
AGENTIR_LLM_API_KEY=sk-your-key-here
```

### 3. 创建虚拟环境 & 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install openai fastapi uvicorn python-dotenv pytest
```

### 4. 启动后端

```bash
agentir-server
# 或
python -m agentir.server.cli
```

访问 http://localhost:8000/docs 查看 API 文档。

### 5. 启动前端（可选）

```bash
cd ui
npm install
npm run dev
```

访问 http://localhost:5173 打开可视化编辑器。

### 6. 快速测试

```bash
# 生成工作流
curl -X POST http://localhost:8000/api/v1/workflows/generate \
  -H "Content-Type: application/json" \
  -d '{"requirement": "先让researcher收集数据，然后writer写报告"}'

# 运行全部测试
pytest
```
