# MEMORY

`RiskAgent-BackEnd` 的记忆模块不是一个单独的向量库服务.
它本质上是一个统一门面 + Redis 持久层 + 进程内语义索引 的混合架构.

核心目标如下.

- 给 planning 阶段提供历史上下文
- 给 execution 阶段持续记录 working memory
- 给 finalize 阶段沉淀 run summary
- 给 resume 阶段恢复 task graph 和 memory state
- 给多角色协作提供 shared memory 和 private memory

## 1. 总体架构

```text
RiskAgent-BackEnd Memory Architecture

[Workflow / Agents]
    |
    v
[MemoryStore]
    |
    +-- append / list_recent / retrieve_for_planning
    +-- save_run_context / build_resume_payload
    +-- persist_run_artifacts / persist_approval_memory
    |
    +-- RedisBackend
    |     |
    |     +-- shared memory list
    |     +-- agent private memory list
    |     +-- run context hash
    |     +-- run summary hash
    |
    +-- SemanticIndexer
          |
          +-- 对重要记忆做轻量语义索引
          +-- 供 planning 时做经验召回
```

统一门面是 `MemoryStore`.
它对上承接 workflow 和 agent.
对下同时管理 Redis 持久化和语义检索.

## 1.1 Redis 数据形态

这一层里实际有 4 种核心数据.
前 2 种更像协作记忆流.
后 2 种更像运行态快照和恢复执行基础设施.

### A. shared memory list

作用

- 保存所有角色都能看到的共享记忆流
- 典型条目包括 `plan` `working_memory` `final` `approval`
- planning 阶段会从这里取 recent hits 和 shared board

Redis key

```text
shared:memory
```

Redis type

```text
List
```

value 格式

- list 中的每一个元素都是一个 JSON string
- 每个 JSON string 都符合 `memory_entry.v1` 结构

单条 value 完整字段

```json
{
  "schema_version": "memory_entry.v1",
  "entry_id": "mem_xxx",
  "ts_ms": 1710000000000,
  "agent_id": "system_engineer",
  "scope": "shared",
  "kind": "working_memory",
  "memory_type": "episodic",
  "session_id": "sess_monitor_001",
  "run_id": "run_proactive_001",
  "source": "task_graph_execution",
  "created_by": "system_engineer",
  "agent_role": "system_engineer",
  "agent_perspective": "system_reliability",
  "task_phase": "execution",
  "confidence": 0.93,
  "trace_ref": {
    "run_id": "run_proactive_001",
    "step_id": "step_fetch_metrics",
    "command_id": "cmd_fetch_metrics_001"
  },
  "content": {
    "text": "step step_fetch_metrics kind=tool_call status=completed agent=system_engineer tool=get_service_metrics task=监控交易台敞口和系统状态",
    "task_id": "task_monitor_001",
    "payload": {
      "content": "监控交易台敞口和系统状态",
      "desk": "delta_one"
    },
    "trace_entry": {
      "step_id": "step_fetch_metrics",
      "kind": "tool_call",
      "status": "completed",
      "tool_name": "get_service_metrics",
      "target_agent": "system_engineer",
      "command_id": "cmd_fetch_metrics_001"
    },
    "node_result": {
      "output": {
        "summary": "service healthy",
        "confidence": 0.93
      }
    }
  },
  "tags": [
    "tool_call",
    "completed",
    "execution"
  ]
}
```

### B. agent private memory list

作用

- 保存某个 agent 的私有任务快照
- 主要用于角色隔离和局部状态延续
- planning 阶段会把默认角色的 private memory state 一起读回来

Redis key

```text
agent:{agent_id}:memory
```

例子

```text
agent:system_engineer:memory
agent:risk_analyst:memory
agent:critic:memory
```

Redis type

```text
List
```

value 格式

- list 中的每一个元素也是一个 JSON string
- 顶层还是 `memory_entry.v1`
- 但 `content` 会是 `build_private_task_snapshot()` 产出的私有快照结构

单条 value 完整字段

```json
{
  "schema_version": "memory_entry.v1",
  "entry_id": "mem_private_xxx",
  "ts_ms": 1710000000100,
  "agent_id": "system_engineer",
  "scope": "private",
  "kind": "private_task_state",
  "memory_type": "episodic",
  "session_id": "sess_monitor_001",
  "run_id": "run_proactive_001",
  "source": "task_graph_execution",
  "created_by": "system_engineer",
  "agent_role": "system_engineer",
  "agent_perspective": "system_reliability",
  "task_phase": "execution",
  "confidence": 0.93,
  "trace_ref": {
    "run_id": "run_proactive_001",
    "step_id": "step_fetch_metrics",
    "command_id": "cmd_fetch_metrics_001"
  },
  "content": {
    "role": "system_engineer",
    "task_goal": "监控交易台敞口和系统状态",
    "current_progress": "completed",
    "open_questions": [],
    "recent_observations": [
      "service healthy"
    ],
    "next_intended_action": "handoff_to_next_step",
    "snapshot_text": "role=system_engineer goal=监控交易台敞口和系统状态 progress=completed observation=service healthy next=handoff_to_next_step"
  },
  "tags": [
    "private_task_memory",
    "completed"
  ]
}
```

### C. run context hash

作用

- 保存某一次 run 的完整运行上下文快照
- 这是 `resume` 能成立的关键基础设施
- 主要给恢复执行 回放 审计 调试使用

Redis key

```text
context:{run_id}
```

例子

```text
context:run_proactive_001
```

Redis type

```text
Hash
```

field 格式

```text
payload
```

field 对应的 value

- 是一个 JSON string
- 顶层结构由 `save_run_context()` 写入

完整 example

```json
{
  "run_id": "run_proactive_001",
  "event_id": "task_monitor_001",
  "created_at_ms": 1710000001000,
  "data": {
    "status": "completed",
    "entry_type": "user_task",
    "run_context": {
      "run_id": "run_proactive_001",
      "entry_type": "user_task",
      "task_id": "task_monitor_001"
    },
    "task": {
      "task_id": "task_monitor_001",
      "session_id": "sess_monitor_001",
      "payload": {
        "content": "监控交易台敞口和系统状态"
      }
    },
    "source_event": {},
    "route_decision": {},
    "intent": {
      "primary_intent_type": "check_system"
    },
    "task_graph": {
      "schema_version": "task_graph.v1",
      "nodes": [],
      "edges": []
    },
    "task_graph_execution": {
      "status": "completed",
      "blocked_step_id": null,
      "failed_step_id": null,
      "trace": []
    },
    "receipts": [],
    "approval_trace": [],
    "memory_hits": [],
    "planning_memory": {
      "hit_count": 2,
      "texts": [
        "[episodic/plan] previous plan"
      ]
    },
    "shared_memory_board": [],
    "private_memory_state": {
      "system_engineer": [],
      "risk_analyst": [],
      "critic": [],
      "orchestrator": []
    },
    "run_summary": {
      "text": "desk exposure and service metrics checked",
      "key_points": [
        "exposure within limit",
        "service healthy"
      ],
      "receipt_command_ids": [],
      "task_id": "task_monitor_001",
      "session_id": "sess_monitor_001"
    },
    "final_output": {
      "summary": "desk exposure and service metrics checked"
    }
  }
}
```

### D. run summary hash

作用

- 保存某次 run 的轻量总结
- 用于快速展示和 resume 时补充 run summary
- 它比 `run context hash` 小很多 更像摘要页

Redis key

```text
summary:{run_id}
```

例子

```text
summary:run_proactive_001
```

Redis type

```text
Hash
```

field 格式

```text
payload
updated_at
```

field 对应的 value

- `payload` 是 JSON string
- `updated_at` 是 Unix 时间戳整数

完整 example

```json
{
  "payload": "{\"text\":\"desk exposure and service metrics checked\",\"key_points\":[\"exposure within limit\",\"service healthy\"],\"receipt_command_ids\":[],\"task_id\":\"task_monitor_001\",\"session_id\":\"sess_monitor_001\"}",
  "updated_at": 1710000001
}
```

如果按应用层解析 `payload` 之后 它的结构是

```json
{
  "text": "desk exposure and service metrics checked",
  "key_points": [
    "exposure within limit",
    "service healthy"
  ],
  "receipt_command_ids": [],
  "task_id": "task_monitor_001",
  "session_id": "sess_monitor_001"
}
```

## 2. 记忆分层

### 2.1 短期共享记忆

- 所有 agent 都可见
- 主要存 plan step working_memory approval memory
- 底层是 Redis List
- 典型 key 类似 `shared:memory`

### 2.2 短期私有记忆

- 只给单个 agent 自己看
- 主要存每个角色的 task state snapshot
- 底层也是 Redis List
- 典型 key 类似 `agent:{agent_id}:memory`

### 2.3 长期经验记忆（Skill 系统）

- 运行结束后沉淀 summary，所有学习产物（procedural/semantic）统一由 Skill 系统管理
- Skill 系统通过 SkillInjector 在 planning 阶段注入 few-shot，替代原 lesson/semantic_case 检索
- 当前实现是进程内 `SemanticIndexer`，Skill 系统有独立的索引器

### 2.4 TTL 分级策略

系统通过 `TTLPolicyEngine` 将记忆按 `kind` 自动分配到四个 TTL 层级，实现从工作记忆到长期经验的自动演进：

| TTL 层级 | TTL | 包含的 kind | 说明 |
|----------|-----|------------|------|
| `EPHEMERAL` | 24h | `working_memory`, `plan`, `step`, `command`, `receipt`, `approval`, `message`, `private_task_state`, `working` | 运行中的工作态记忆,任务结束后自然过期 |
| `SHORT_TERM` | 7d | `final`, `analysis`, `task`, `intent_disambiguation` | 任务级别的产物,保留一周供复盘和对照 |
| `LONG_TERM` | **永久** | `few_shot`, `knowledge`, `fact`, `example` | 经验类型，永不过期，会触发 MySQL 落盘 |
| `PERMANENT` | **永久** | `skill`, `policy`, `config`, `procedure`, `playbook` | Skill 和系统配置,永不过期,会触发 MySQL 落盘 |

**分类优先级**（5 级决策链）：
1. entry 中显式指定的 `ttl_tier` 字段
2. `custom_overrides` 自定义覆盖
3. `KIND_TO_TTL_TIER` 默认映射表
4. 根据 `memory_type` 兜底推断（procedural→LONG_TERM, semantic→LONG_TERM, episodic→SHORT_TERM）
5. 最终兜底 → EPHEMERAL

**演进机制**：
- **时间驱动**：EPHEMERAL → SHORT_TERM 由时间自然驱动
- **质量驱动**：学习产物统一由 Skill 系统管理，Skill 的 confidence 策略控制升级
- **永久保护**：LONG_TERM 和 PERMANENT 永不过期,且触发 MySQL 落盘

### 2.5 MySQL 持久化

系统通过 `PersistenceBackend` 将 LONG_TERM 和 PERMANENT 层级的记忆异步落盘到 MySQL，解决 Redis 重启丢失关键经验的问题。

**存储模型**：使用 `memory_store` 表（`INSERT ON DUPLICATE KEY UPDATE` 语义），核心字段：`entry_id`, `ts_ms`, `agent_id`, `scope`, `kind`, `memory_type`, `content`(JSON), `confidence`, `trace_ref`(JSON), `tags`(JSON), `session_id`, `run_id`, `ttl_tier`。

**落盘触发时机**：
- `MemoryStore.append()` 写入时，若 `TTLPolicyEngine.should_persist()` 返回 True，则通过 `asyncio.ensure_future()` fire-and-forget 异步落盘
- `flush_to_persistence()` 定期批量同步，遍历 shared:memory 和各 agent 私有记忆，将 LONG_TERM/PERMANENT 条目批量落盘

**故障恢复**：`restore_from_persistence()` 从 MySQL 批量加载记忆 → 逐条写回 Redis → 重建 SemanticIndexer 索引

**关键设计**：
- Fire-and-forget：落盘不阻塞主执行链路
- Upsert 语义：`INSERT ON DUPLICATE KEY UPDATE` 保证幂等
- 同步引擎异步包装：SQLAlchemy 同步 Engine 通过 `asyncio.to_thread` 包装为异步
- JSON 透明序列化：`content`/`trace_ref`/`tags` 自动序列化/反序列化

## 3. 主调用链

### 3.1 planning 链

workflow 启动后先拿 `MemoryStore`.
然后统一读取 shared board private memory recent memory 和 semantic hits.
这些内容会被合并成 planning memory.
最后交给 orchestrator 产出 plan.
产出后的 plan 会再次写回 shared memory.

主链大致如下.

```text
proactive_workflow
  -> memory_store.retrieve_for_planning()
  -> orchestrator 使用 memory summary 生成 plan
  -> persist_plan_memory()
```

### 3.2 execution 链

`TaskGraphExecutor` 每执行完一个 node 就会回调一次记忆写入.
共享 working memory 一定会写.
如果启用了 private memory 还会给对应 agent 写 private task state.

主链大致如下.

```text
TaskGraphExecutor.execute()
  -> on_node_completed
  -> memory_store.record_working_memory()
```

### 3.3 finalize 链

执行完成后系统会生成 final output.
critic 会做 final review.
然后把 run summary 沉淀下来（学习产物统一由 Skill 系统管理）.

主链大致如下.

```text
proactive_workflow
  -> memory_store.persist_run_artifacts()
```

### 3.4 approval 链

执行过程里产生的 approval record 不只是 trace.
它们在 run 结束后会被转成 approval memory 写入 shared memory.
这样后续回放和审计就可以直接从记忆层读取.

### 3.5 resume 链

如果某次 workflow 需要 resume.
系统会先按 `run_id` 读回 run context.
然后恢复 task graph 和 execution state.
再把 memory state shared board private state 和 run summary 合回 planning memory.
最后从 blocked step 继续执行.

## 4. 关键文件

统一门面

- `src/riskagent_backend/memory/memory_store.py`

写入编排

- `src/riskagent_backend/memory/memory_operations.py`

Redis 后端

- `src/riskagent_backend/memory/redis_backend.py`

TTL 分级策略

- `src/riskagent_backend/memory/ttl_policy.py`

MySQL 持久化

- `src/riskagent_backend/memory/persistence_backend.py`

语义索引

- `src/riskagent_backend/memory/semantic_indexer.py`

记忆 schema

- `src/riskagent_backend/contracts/memory_entry.py`

workflow 接入点

- `src/riskagent_backend/orchestration/proactive_workflow.py`

plan 和 result 落记忆

- `src/riskagent_backend/orchestration/workflow_memory.py`

resume 接入

- `src/riskagent_backend/orchestration/workflow_resume.py`

## 5. 设计重点

### 5.1 shared memory 是主链核心

shared memory 是整个系统的主协作面.
private memory 只是辅助角色隔离和局部状态保存.

### 5.2 记忆层和 workflow 强绑定

这里的记忆模块不是单纯的 CRUD 存储.
它直接服务 planning execution finalize resume 四条主链.

### 5.3 resume 能成立是因为上下文和记忆一起存

如果只存 task graph 不存 memory state.
恢复执行时就会丢掉之前的上下文.
当前实现把 run context 和 memory state 一起保存.
所以 resume 不是重新跑一遍.
而是真正从中断位置继续.

### 5.4 长期经验后端当前不是 Chroma

仓库里虽然有 Chroma.
但它属于 knowledge 子系统.
记忆主链当前真正使用的是 Redis + 进程内 `SemanticIndexer`.

## 6. 一句话总结

这个项目的记忆模块本质上是.

`以 MemoryStore 为统一入口, 用 Redis 保存短期和运行态记忆, 用轻量语义索引保存可复用经验, 并把 planning execution finalize resume 四条主链全部接到同一套记忆读写协议上.`
