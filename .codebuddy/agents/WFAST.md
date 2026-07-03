---
name: WFAST
description: 
tools: list_dir, search_file, search_content, read_file, read_lints, replace_in_file, write_to_file, execute_command, mcp_get_tool_description, mcp_call_tool, delete_file, connect_cloud_service, preview_url, web_fetch, use_skill, web_search, automation_update, task
agentMode: manual
enabled: true
enabledAutoRun: true
model: inherit
---
# AGENT.md — AgentIR System Prompt v3

> **适用于**: AI Coding Agent（CodeBuddy / Claude / Cursor 等）
> **更新日期**: 2026-06-29
> **项目阶段**: Phase 2 完成 → Phase 3 启动

---

## 项目名称

**AgentIR** — Dynamic Workflow 与传统工作流的衔接桥梁

---

## 核心愿景

AgentIR 旨在解决一个根本矛盾：

> **传统工作流**（BPMN 式拖拽）能构建复杂逻辑，但门槛极高，需要专业知识。
> **Dynamic Workflow**（AI 直接根据自然语言编写工作流脚本）门槛为零，但无法处理复杂逻辑，缺乏可测试性、可视化、和明确的节点定义。

AgentIR 是这两者之间的**桥梁**：

```
                     Natural Language
                          │
                          ▼
┌──────────────────────────────────────────────────┐
│                                                  │
│   Planner (LLM)  ──→  AgentIR (.json)            │
│                              │                   │
│                     ┌────────┼────────┐          │
│                     ▼        ▼        ▼          │
│               Security    Visual    Multi-       │
│               Audit       Editor    Compiler     │
│               (审核)    (ReactFlow) (ADK/Graph/  │
│                                    CrewAI...)    │
│                         │                   │    │
│                         ▼                   ▼    │
│                  User can edit        Runnable   │
│                  AgentIR visually     Scripts    │
│                     │                            │
│                     ▼                            │
│               Changes update                     │
│               workflow scripts                   │
│                                                  │
└──────────────────────────────────────────────────┘
```

**核心原则**：AgentIR 是唯一的真实来源（Single Source of Truth）。无论是 NL 生成、UI 编辑、还是编译为各种框架脚本，一切围绕 AgentIR 为中心。

---

## 当前阶段：Phase 3 — 交互式 AgentIR 编辑器 + 双向同步

### Phase 2 已完成（遗产）

- ✅ AgentIR Schema（6 节点类型：agent, sequence, parallel, condition, loop, tool）
- ✅ Validator（确定性校验）
- ✅ Planner（NL → AgentIR，LLM 驱动）
- ✅ ADK 2.0 Dynamic Workflow Compiler
- ✅ 自定义工具系统（AST 扫描 + 注册表）
- ✅ FastAPI Server（6 端点）
- ✅ 产物持久化（requirements/IR/outputs/logs）
- ✅ Runner（子进程执行 + 结构化日志）
- ✅ 基础 React UI（ReactFlow 只读可视化）
- ✅ Agent Registry（预定义 Agent 扫描）
- ✅ 253 个测试，100% 通过

### Phase 3 目标

**核心交付**：让用户可以在 ReactFlow UI 中直接编辑 AgentIR，并将修改同步回工作流脚本。

具体任务：

1. **AgentIR 可编辑 UI**
   - ReactFlow 节点拖拽（移动、连线调整）
   - 右键菜单 / 工具栏：添加节点（agent, tool, condition, loop）
   - 属性面板：编辑节点属性（agent 名称、expression、max_iterations）
   - 节点删除（带确认）
   - Undo/Redo 支持

2. **IR ↔ 脚本双向同步**
   - 新增 API 端点：`PUT /api/v1/workflows/{id}/ir` — 接受修改后的 AgentIR JSON，重新校验 + 编译
   - 前端修改 → 保存 → 后端重新编译 → 更新 artifacts/outputs/ 中的脚本
   - 前端显示编译结果（成功/失败，错误信息）
   - 支持"仅更新 IR，稍后编译"的草稿模式

3. **IR Diff 视图**
   - 修改前后 AgentIR JSON 的 diff 展示
   - 确认修改前预览变更

4. **更好的布局算法**
   - 当前 ir-to-graph.ts 布局算法较简单，序列化竖向堆叠
   - 需要支持：Dagre / ELK 自动布局、手动调整后保持位置

---

## 技术栈

| 层面 | 选型 |
|------|------|
| 后端语言 | Python 3.12+ |
| 包管理 | uv |
| Schema | Pydantic v2 |
| LLM 调用 | openai SDK（多厂商兼容） |
| Web 框架 | FastAPI + Uvicorn |
| 前端 | React 18 + TypeScript + Vite |
| 可视化 | @xyflow/react (ReactFlow) |
| 自动布局 | dagre / @xyflow/dagre |
| 测试 | pytest（253 测试） |
| 代码质量 | ruff + mypy（strict） |
| 当前编译器目标 | Google ADK 2.0 Dynamic Workflow |

---

## 核心架构（三层不变）

```
Layer 1: AgentIR Schema
    ↓
Layer 2: Validator（确定性，无 LLM）
    ↓
Layer 3: Compiler（框架特定，可插拔）
```

---

## AgentIR 节点类型（当前 6 种）

| 节点 | `type` | 关键字段 |
|------|--------|---------|
| AgentNode | `"agent"` | `agent: str` |
| SequenceNode | `"sequence"` | `steps: list[WorkflowNode]` |
| ParallelNode | `"parallel"` | `branches: list[WorkflowNode]` |
| ConditionNode | `"condition"` | `expression: str`, `true_branch`, `false_branch` |
| LoopNode | `"loop"` | `max_iterations: int`, `body: WorkflowNode` |
| ToolNode | `"tool"` | `tool: str` |

未来计划节点：
- SubWorkflowNode（`"subworkflow"`）— 引用其他工作流
- HITLNode（`"human_in_the_loop"`）— 人机协作审批节点
- InputNode / OutputNode — 显式输入输出定义

---

## API 端点（当前 + Phase 3 新增）

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `GET` | `/api/v1/health` | 健康检查 | ✅ |
| `POST` | `/api/v1/workflows/generate` | NL → AgentIR → 编译 → 保存 | ✅ |
| `GET` | `/api/v1/workflows` | 列表 | ✅ |
| `GET` | `/api/v1/workflows/{id}` | 详情 + AgentIR JSON | ✅ |
| `POST` | `/api/v1/workflows/{id}/run` | 执行工作流 | ✅ |
| `GET` | `/api/v1/workflows/{id}/runs` | 运行历史 | ✅ |
| `GET` | `/api/v1/tools` | 工具列表 | ✅ |
| `GET` | `/api/v1/agents` | Agent 列表 | ✅ |
| `PUT` | `/api/v1/workflows/{id}/ir` | **更新 AgentIR → 重编译** | ❌ Phase 3 |
| `POST` | `/api/v1/workflows/{id}/ir/validate` | **仅校验 AgentIR（不编译）** | ❌ Phase 3 |
| `GET` | `/api/v1/workflows/{id}/ir/diff` | **IR diff（修改前后对比）** | ❌ Phase 3 |

---

## 项目目录结构

```text
agentir/
├── __init__.py
├── ir/
│   ├── nodes.py          # 6 种节点类型 (Pydantic v2)
│   ├── models.py         # WorkflowDefinition
│   └── schema.py         # 序列化
├── validator/
│   ├── rules.py          # 校验规则 + walker
│   └── validator.py      # ValidationReport
├── llm/
│   ├── client.py         # create_llm_callable()
│   └── config.py         # LLMConfig, AgentConfig
├── planner/
│   └── planner.py        # NL → AgentIR (LLM 驱动)
├── tools/
│   ├── scanner.py        # AST 工具扫描器
│   └── registry.py       # ToolRegistry
├── agents/
│   ├── scanner.py        # AST Agent 扫描器
│   └── registry.py       # AgentRegistry
├── compiler/
│   ├── base.py           # BaseCompiler (ABC)
│   └── adk/
│       └── compiler.py   # ADKCompiler
├── artifacts/
│   ├── store.py          # WorkflowArtifactStore
│   ├── runner.py         # WorkflowRunner
│   └── run_store.py      # RunHistoryStore
├── server/
│   ├── config.py
│   ├── main.py
│   ├── models.py
│   ├── routes.py         # 当前 8 端点
│   └── cli.py

ui/
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── WorkflowGraph.tsx   # ReactFlow 可视化
│   │   ├── GeneratePanel.tsx   # NL 生成面板
│   │   └── RunPanel.tsx        # 运行面板
│   ├── api/
│   │   └── client.ts           # API 客户端
│   ├── types/
│   │   └── index.ts            # TypeScript 类型定义
│   └── utils/
│       └── ir-to-graph.ts      # AgentIR → ReactFlow 转换

tests/                           # 253 个测试
tools/                           # 用户工具脚本
agents/                          # 预定义 Agent 脚本
artifacts/                       # 持久化产物
examples/                        # AgentIR JSON 示例
```

---

## 设计原则

| 原则 | 说明 |
|------|------|
| **确定性** | 相同 IR → 相同输出。Validator 和 Compiler 不含 LLM |
| **运行时无关** | AgentIR 不含任何框架特定概念 |
| **可扩展** | `BaseCompiler` ABC，新编译器可插拔 |
| **强类型** | Pydantic v2 + TypeScript strict |
| **LLM 隔离** | 仅 Planner 使用 LLM |
| **IR 为第一公民** | 所有操作以 AgentIR 为中心 |
| **双向同步** | UI 修改 → IR 更新 → 脚本重新编译 |

---

## 编码规范

- 强类型，禁止 `Any`（除非绝对必要）
- 优先组合，而非继承
- Pydantic v2 用于所有数据模型
- 100% 确定性编译，无随机性
- 后端不包含框架锁定代码
- 前端不假设特定的后端框架
- 所有新增功能必须有对应的测试

---

## 长远目标

AgentIR 的定位是 **"Agent 工作流领域的 Terraform HCL"** — 一个通用的、框架无关的工作流中间表示标准。

最终实现：
- Dynamic Workflow（AI 写）和传统工作流（人工拖拽）共享同一套 AgentIR
- AgentIR 可以在 UI 中被人类审查、修改、批准
- AgentIR 可以编译到任何主流 Agent 框架
- AgentIR 可以作为工作流的"源代码"进行版本控制
