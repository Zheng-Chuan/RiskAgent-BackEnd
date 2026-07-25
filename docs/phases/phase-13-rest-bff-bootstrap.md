# Phase 13: REST BFF 初始闭环

## 状态

开发中, 基础任务接口, memory 视图接口, TaskGraph 图快照接口和 SSE 事件流代码已完成, 当前进入本地 K8s 验收阶段.

## 核心目标

在不破坏 Multi-Agent 主执行内核的前提下, 为 FrontEnd 提供浏览器友好的最小 REST BFF 层, 打通 `提交任务 -> 轮询状态 -> 展示智能体 -> 展示结果` 的联调闭环.

## 为什么这是新需求

当前 BackEnd 的对外 HTTP 能力只有 `/health` `/ready` `/metrics` `/api/llm/usage`.

虽然系统内部已经具备统一工作流, `run_trace.v2`, `run_context`, `task_graph_execution`, `receipts`, `memory` 等真实状态来源, 但仍缺少以下两个关键能力:

- 缺少面向浏览器的 REST BFF 路由层
- 缺少任务执行过程中的运行时状态快照, 无法支持前端轮询

因此本阶段不是简单新增 3 个接口, 而是补一个新的后端产品能力层.

## 工作范围

### In Scope

- 新增 `POST /api/tasks`
- 新增 `GET /api/tasks/{task_id}`
- 新增 `GET /api/agents`
- 新增 `GET /api/memory`
- 新增 `GET /api/tasks/{task_id}/memory`
- 新增 `GET /api/stream`
- 新增 `GET /api/tasks/{task_id}/graph`
- 为工作流新增最小运行时任务注册表
- 为运行时任务注册表新增 TaskGraph 快照能力
- 用 `run_context` `task_graph_execution` `run_trace` 构建任务详情视图
- 用工作流单例与最近 trace 派生智能体状态视图
- 基于统一 memory store 输出浏览器友好的结构化记忆视图和脱敏结果
- 基于 SSE 向前端实时推送智能体状态, 记忆快照和 TaskGraph 快照

### Out of Scope

- 不实现完整 trace 查询 API
- 不实现前端审批恢复接口
- 不实现浏览器端的 DAG 编辑能力
- 不做长期历史任务分页列表
- 不把 MCP 暴露给浏览器

## 初始需求提炼

### 需求一: 浏览器友好任务创建接口

前端需要一个稳定的 `POST /api/tasks` 接口, 请求体只包含自然语言描述. 后端负责:

- 生成 `task_id`
- 生成 `session_id`
- 组装标准用户任务结构
- 异步触发统一工作流
- 立即返回 `pending` 状态

### 需求二: 可轮询的任务状态快照

前端需要一个 `GET /api/tasks/{task_id}` 接口, 其返回值不能直接暴露内部工作流结果, 而应聚合成浏览器友好的任务详情模型, 至少包括:

- 任务状态
- 步骤列表
- 结果摘要
- 错误信息
- 最近更新时间
- 可独立查询的 TaskGraph 节点, 边和图级状态

### 需求三: 最小智能体状态视图

当前系统没有统一持久化的 agent runtime store. 本阶段允许用派生态实现 `GET /api/agents`, 但必须明确:

- 这不是强一致状态
- 来源于工作流单例角色对象和最近 task trace
- 仅服务于前端最小展示

## 技术判断

### 单一真相源

任务详情的权威来源优先级如下:

1. 运行中的任务: 运行时任务注册表
2. 已完成任务: `MemoryStore.get_run_context(run_id)` 中保存的 `data`
3. 审计补充: `RunTraceStore.get_snapshot(run_id)`

### 为什么必须新增运行时注册表

当前代码只会在任务结束后调用 `save_run_context`. 这意味着:

- 运行中的任务没有可轮询状态
- 前端会长时间拿不到任务详情
- 轮询 MVP 无法真正成立

因此本阶段必须新增一个最小运行时状态模型, 至少覆盖:

- `task_id`
- `run_id`
- `status`
- `created_at`
- `updated_at`
- `steps`
- `result`
- `error`
- `graph_snapshot`

### 路由层边界

REST BFF 层不直接实现业务逻辑. 其职责是:

- 校验浏览器请求
- 调用工作流 facade
- 读取运行时状态和持久化状态
- 把后端内部结构映射为前端契约

## 成功标准

- `POST /api/tasks` 返回 `task_id` 和 `pending`
- `GET /api/tasks/{task_id}` 能在任务执行中返回 `pending` 或 `running`
- `GET /api/tasks/{task_id}` 在完成后返回步骤, 结果和错误信息
- `GET /api/agents` 返回最小角色状态列表
- `GET /api/memory` 返回最近结构化记忆快照和聚合摘要
- `GET /api/tasks/{task_id}/memory` 返回任务维度的记忆视图和聚合摘要
- `GET /api/tasks/{task_id}/graph` 返回任务维度的真实 TaskGraph DAG 快照
- `GET /api/stream` 能实时推送智能体状态, 记忆快照和 TaskGraph 快照
- FrontEnd 第一版 MVP 页面能完成一次真实联调
- memory 响应中不直接暴露 Redis 原始结构或明文敏感信息

## 初始接口范围

### `POST /api/tasks`

请求:

```json
{
  "description": "查询所有 desk 头寸"
}
```

响应:

```json
{
  "task_id": "run_xxx",
  "status": "pending",
  "created_at": 1784803200000
}
```

### `GET /api/tasks/{task_id}`

响应:

```json
{
  "id": "run_xxx",
  "title": "查询所有 desk 头寸",
  "description": "查询所有 desk 头寸",
  "status": "running",
  "steps": [
    {
      "id": "step_1",
      "title": "delegate system_engineer",
      "status": "completed"
    }
  ],
  "result": null,
  "error": null,
  "created_at": 1784803200000,
  "updated_at": 1784803205000
}
```

### `GET /api/agents`

响应:

```json
{
  "items": [
    {
      "id": "system_engineer",
      "name": "ProactiveSystemEngineerAgent",
      "role": "engineer",
      "status": "working",
      "currentTaskId": "run_xxx",
      "capabilities": ["analyze", "monitor", "execute"]
    }
  ],
  "updated_at": 1784803205000
}
```

### `GET /api/memory`

响应:

```json
{
  "items": [
    {
      "id": "mem_xxx",
      "taskId": "run_xxx",
      "sessionId": "session_xxx",
      "agentId": "system_engineer",
      "scope": "shared",
      "kind": "working_memory",
      "memoryType": "episodic",
      "changeType": "updated",
      "summary": "已同步最近任务状态",
      "details": ["来源 task_graph_execution"],
      "tags": ["delegate"],
      "confidence": 1.0,
      "createdAt": 1784803205000
    }
  ],
  "summary": {
    "sharedCount": 1,
    "privateCount": 0,
    "agentCount": 1
  },
  "updated_at": 1784803205000
}
```

### `GET /api/tasks/{task_id}/memory`

响应:

```json
{
  "task_id": "run_xxx",
  "session_id": "session_xxx",
  "items": [
    {
      "id": "mem_task_xxx",
      "taskId": "run_xxx",
      "sessionId": "session_xxx",
      "agentId": "risk_analyst",
      "scope": "private",
      "kind": "private_task_state",
      "memoryType": "episodic",
      "changeType": "updated",
      "summary": "正在复核风险暴露",
      "details": ["任务 run_xxx"],
      "tags": ["review"],
      "confidence": 1.0,
      "createdAt": 1784803206000
    }
  ],
  "summary": {
    "sharedCount": 0,
    "privateCount": 1,
    "agentCount": 1
  },
  "updated_at": 1784803206000
}
```

### `GET /api/stream`

响应媒体类型:

```text
text/event-stream
```

事件:

- `agent_snapshot`
- `memory_snapshot`
- `graph_snapshot`
- `heartbeat`

## 风险与取舍

- 风险 1: 运行时注册表与最终持久化状态存在短暂不一致
- 风险 2: 智能体状态是派生态, 不能承诺强一致
- 风险 3: 工作流当前是串行 await, 如果 `POST /api/tasks` 设计不当会阻塞 HTTP 请求
- 风险 4: memory 展示如果直接透传底层结构, 会带来敏感信息泄露和前端解释成本
- 风险 5: SSE 如果不做快照去重和心跳保活, 会造成前端重连抖动和无效事件洪泛

取舍:

- 优先实现异步提交和最小轮询能力
- 优先实现 SSE 实时推送, 轮询保留为兜底
- 优先保证任务详情可信, 智能体状态允许弱一致
- 优先做与 FrontEnd 契约一致的 JSON 结构, 不把内部复杂对象直接暴露出去

## 交付物

- 代码: REST BFF service 和 route handler
- 代码: 运行时任务注册表
- 代码: memory 结构化映射与脱敏输出
- 代码: TaskGraph 结构化映射与运行时快照同步
- 代码: SSE 事件流与快照去重逻辑
- 代码: `GET /api/tasks/{task_id}/graph` 与 `graph_snapshot` 已接入浏览器契约
- 文档: 本阶段规划文档
- 文档: PRD 需求补充
- 测试: REST BFF 基本契约测试, memory 接口测试与 SSE 事件流测试

## 相关文档

- [PRD](../PRD.md)
- [ARCHITECTURE](../ARCHITECTURE.md)
- [ADR-005 run_trace.v2](../decisions/ADR-005-run-trace-v2.md)
