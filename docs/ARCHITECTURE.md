# RiskAgent-BackEnd Architecture

## 目录

- [1. 系统统一主流程](#section-1)
- [2. TaskGraph 执行内核详解](#section-2)
  - [2.1 执行逻辑概览](#section-2-1)
  - [2.2 关键执行步骤](#section-2-2)
  - [2.3 节点类型与执行分发](#section-2-3)
  - [2.4 审批拦截机制](#section-2-4)
  - [2.5 意外中断的上下文恢复机制](#section-2-5)
  - [2.6 执行受阻后的 TaskGraph 修改与续跑机制](#section-2-6)
  - [2.7 优缺点](#section-2-7)
  - [2.8 关键代码出处](#section-2-8)
- [3. Agent BDI 心智架构](#section-3)
  - [3.1 定位与三者关系](#section-3-1)
  - [3.2 数据结构](#section-3-2)
  - [3.3 状态流转：Perceive → Deliberate → Act](#section-3-3)
  - [3.4 意图状态机](#section-3-4)
  - [3.5 与主链的接入点](#section-3-5)
  - [3.6 关键代码出处](#section-3-6)
- [4. ReAct / CoT 推理循环](#section-4)
  - [4.1 核心概念与数据结构](#section-4-1)
  - [4.2 ReAct 循环主流程](#section-4-2)
  - [4.3 CoT 思维链的五个阶段](#section-4-3)
  - [4.4 各 Agent 的 ReAct 使用差异](#section-4-4)
  - [4.5 _generate_final_answer 的角色差异](#section-4-5)
  - [4.6 ReAct 与评估体系的关联](#section-4-6)
  - [4.7 优点](#section-4-7)
  - [4.8 缺点与风险](#section-4-8)
  - [4.9 改进建议](#section-4-9)
  - [4.10 关键代码出处](#section-4-10)

- [5. 统一记忆架构](#section-5)
  - [5.1 总体架构](#section-5-1)
  - [5.2 数据结构：memory_entry.v1](#section-5-2)
  - [5.3 短期共享记忆](#section-5-3)
  - [5.4 短期私有记忆（分角色）](#section-5-4)
  - [5.5 长期经验记忆](#section-5-5)
    - [5.5.1 TTL 分级策略](#section-5-5-1)
    - [5.5.2 MySQL 持久化](#section-5-5-2)
  - [5.6 记忆能解决什么问题](#section-5-6)
  - [5.7 缺点与风险](#section-5-7)
  - [5.8 关键代码出处](#section-5-8)
- [6. Skill 自创闭环生命周期](#section-6)
  - [6.1 总体架构](#section-6-1)
  - [6.2 数据结构：skill.v1](#section-6-2)
  - [6.3 Skill 存储位置](#section-6-3)
  - [6.4 创建：SkillProposer](#section-6-4)
  - [6.5 检索与注入：SkillInjector](#section-6-5)
  - [6.6 使用与置信度更新：SkillUsageTracker](#section-6-6)
  - [6.7 修订：SkillReviser](#section-6-7)
  - [6.8 降级与归档](#section-6-8)
  - [6.9 Skill 能解决什么问题](#section-6-9)
  - [6.10 缺点与风险](#section-6-10)
  - [6.11 关键代码出处](#section-6-11)
- [7. MCP 工具调用与治理](#section-7)
  - [7.1 协议与传输层](#section-7-1)
  - [7.2 MCP 部署位置](#section-7-2)
  - [7.3 鉴权机制](#section-7-3)
  - [7.4 工具注册与角色区分](#section-7-4)
  - [7.5 Agent 如何知道可用工具](#section-7-5)
  - [7.6 工具调用全流程](#section-7-6)
  - [7.7 五道治理关卡](#section-7-7)
  - [7.8 MCP Resources 与 Prompts](#section-7-8)
  - [7.9 关键代码出处](#section-7-9)
- [8. 5min 主动监控全流程](#section-8)
  - [8.1 启动与停止](#section-8-1)
  - [8.2 监控循环](#section-8-2)
  - [8.3 感知层：数据源采集与过滤](#section-8-3)
  - [8.4 信念更新](#section-8-4)
  - [8.5 意图形成](#section-8-5)
  - [8.6 意图执行与事件投递](#section-8-6)
  - [8.7 主链执行](#section-8-7)
  - [8.8 频率控制与预算熔断](#section-8-8)
  - [8.9 关键代码出处](#section-8-9)
- [9. REST BFF 服务层](#section-9)
  - [9.1 端点概览](#section-9-1)
  - [9.2 运行时任务注册表](#section-9-2)
  - [9.3 SSE 事件流与快照去重](#section-9-3)
  - [9.4 脱敏机制](#section-9-4)
  - [9.5 nginx 反向代理](#section-9-5)
  - [9.6 缺点与风险](#section-9-6)
- [10. LLM 成本治理](#section-10)
  - [10.1 TokenTracker](#section-10-1)
  - [10.2 cost_model.py 定价表](#section-10-2)
  - [10.3 CostCircuitBreaker 三级熔断](#section-10-3)
  - [10.4 与 ProactiveBudgetManager 集成](#section-10-4)
  - [10.5 暴露端点](#section-10-5)
  - [10.6 缺点与风险](#section-10-6)
- [11. 评估体系](#section-11)
  - [11.1 参考框架与基准](#section-11-1)
  - [11.2 评估维度与指标体系](#section-11-2)
  - [11.3 指标计算方式](#section-11-3)
  - [11.4 LLM 辅助评估](#section-11-4)
  - [11.5 质量门禁](#section-11-5)
  - [11.6 测试数据集](#section-11-6)
  - [11.7 评估报告](#section-11-7)
  - [11.8 优点](#section-11-8)
  - [11.9 缺点与风险](#section-11-9)
  - [11.10 关键代码出处](#section-11-10)
- [12. 渠道接入与调度](#section-12)
  - [12.1 多平台网关（gateway/）](#section-12-1)
  - [12.2 内置调度（scheduling/）](#section-12-2)
  - [12.3 CLI 辅助（cli/）](#section-12-3)

<a id="section-1"></a>
# 1. 系统统一主流程
```text
[输入]
    |
    +-> [user_task]
    |       | 用户显式任务
    |       v
    |   [run_proactive_workflow]
    |
    +-> [system_event]
    |       | 特殊的系统输入
    |       | normalize_event
    |       | validate_event
    |       | publish 到 MessageBus
    |       | proactive budget 判断
    |       | ModeratorAgent route decision
    |       | 转成 unified task
    |       v
    |   [run_proactive_workflow]
    |
    +-> [resume request]
            | 输入 run_id approval_decision resume_from_step_id
            | build_resume_payload
            | 读取 task_graph execution_state memory_state run_summary
            | _apply_resume_context
            v
        [run_proactive_workflow]
    
    |
    v
[ProactiveBackEndWorkflow.run]
    | 检查 memory_enabled baseline_mode benchmark_config
    | 组装 task_with_context
    | 生成统一 run_id 和 run_context
    v
[Step 1] intent
    | IntentAgent 识别 primary_intent_type
    | 输出 intent evidence permission_requirements
    | 写入 intent trace
    v
[Step 2] retrieve planning memory
    | runtime recent shared memory
    | built-in semantic experience retrieval
    | 如果是 resume 则合并 memory_state 和 run_summary
    | 形成 orchestrator context.memory
    v
[Step 3] orchestrator_plan
    | OrchestratorAgent 输出 orchestrator_output.v1
    | normalize_orchestrator_output
    | plan_steps -> task_graph
    | task_graph 包含 nodes edges schema_version = task_graph.v1
    v
[Step 4] critic_plan
    | CriticAgent 审查计划
    | 输出 issues suggested_fixes require_human_approval
    | 决定是否 replan
    v
[Step 5] task_graph execution
    | TaskGraphExecutor 按依赖调度节点
    | 支持 delegate / tool_call / finalize / ask_human / replan / stop
    |
    +-> [delegate]
    |       | engineer / analyst 执行子任务
    |       | 输出 delegate_result
    |
    +-> [tool_call]
    |       | 构造标准 command
    |       | 注入 timeout_ms retry_budget
    |       v
    |   [tool_executor.py]
    |       | 检查 tool registry
    |       | 检查 RBAC
    |       | 检查 budget
    |       | 判断是否 require approval
    |       |
    |       +-> [approval required]
    |       |       | 生成 approval_request
    |       |       | approval state = pending approved rejected expired resumed
    |       |       | 写入 approval_trace approval_memory
    |       |       | 若 pending 则 blocked 并等待 resume
    |       |
    |       +-> [handler execution]
    |               | 执行具体工具
    |               | 捕获 timeout runtime dependency validation
    |               v
    |           [receipt]
    |               | ok error approval_state
    |               | failure_classification retry_count timeout_ms
    |               | 写入 task_graph_execution.trace
    |
    +-> [working memory]
            | step 完成后 record_working_memory
            | 写入 shared episodic memory
    v
[Step 6] receipts approvals replan
    | 汇总 receipts approval_trace retry_records
    | failure or critic rejection -> replan
    | replan 后新子图重新进入 TaskGraphExecutor
    | blocked_step_id 或 failed_step_id 进入 resume 路径
    | resume 时只清失败节点和下游输出
    v
[Step 7] finalize output
    | 汇总 engineer analyst receipts approvals
    | 生成 final_output quality approval summary
    | critic 写 final
    v
[Step 8] persist and trace
    | build_run_trace_snapshot -> run_trace.v2
    | category 包括 task message version_snapshot plan step command receipt approval memory final
    | RunTraceStore 内存缓存 + 持久化到 results/run_traces
    | 运行态存储保存 run context 和 resume state
    | eval/ 目录消费 trace 做 replay evaluator gate benchmark
    | 返回统一结果
    v
[输出]
    | user_task 返回给用户
    | system_event 产出统一 run_trace 和 follow-up result
    | resume 返回继续执行后的结果
```

> **角色命名约定**：本文档以 `IntentAgent` / `OrchestratorAgent` / `CriticAgent` 等角色概念名叙述架构；代码中的实现类为 `ProactiveIntentAgent` / `ProactiveOrchestratorAgent` / `ProactiveCriticAgent` 等（[roles.py](../src/riskagent_backend/proactive_agents/roles.py)，完整映射见 4.10 节）。`ToolExecutor` 同理，指 [tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) 模块（入口函数 `execute_agent_command()`），代码中并无同名类。

<a id="section-2"></a>
# 2. TaskGraph 执行内核详解

TaskGraph 执行内核是主流程 Step 5 的核心组件，将多角色协作抽象为有向无环图（DAG），实现可并行、可重规划、可恢复、可审计的动态任务调度。

<a id="section-2-1"></a>
## 2.1 执行逻辑概览

执行内核的核心流程是一个 **while 循环**，每轮循环执行以下闭环：

```
while remaining_nodes:
    ① 找出就绪节点（依赖已满足）
    ② 评估条件边（跳过不满足条件的分支）
    ③ 并行执行所有就绪节点（asyncio.gather）
    ④ 同步状态：更新 node.status / node_outputs / receipts / trace
    ⑤ 判断是否应该停止（blocked / failed / stopped）
    → 回到 ①
```

核心代码位于 [task_graph_executor.py `execute()`](../src/riskagent_backend/orchestration/task_graph_executor.py)，单节点执行位于 [node_executors.py `execute_node()`](../src/riskagent_backend/orchestration/node_executors.py)。

<a id="section-2-2"></a>
## 2.2 关键执行步骤

#### Step 1: 初始化与恢复上下文

`execute()` 方法接收 `execution_state`（上次执行的状态快照）和 `resume_from_step_id`（恢复入口），从中恢复已完成节点、已跳过节点、节点输出、receipts、审批记录等：

```python
# task_graph_executor.py
prior_state = dict(execution_state) if isinstance(execution_state, dict) else {}
completed = self._extract_completed_steps(prior_state)     # 已完成的 step_id 集合
skipped = self._extract_skipped_steps(prior_state)         # 已跳过的 step_id 集合
node_outputs = self._extract_node_outputs(prior_state)     # 各节点输出 payload
delegate_results = self._restore_delegate_results(prior_state)  # Agent 返回值
receipts = self._extract_receipts(prior_state)             # 工具回执
approval_records = self._extract_approval_records(prior_state)  # 审批记录
execution_trace = list(prior_state.get("trace", []))       # 执行 trace
resume_history = list(prior_state.get("resume_history", []))  # 恢复历史
```

然后构建依赖图并标记恢复点下游节点为 `pending`（清除其已完成状态）：

```python
# task_graph_executor.py
if self._should_resume_node(step_id=step_id, resume_from_step_id=resume_from_step_id, dependency_map=dependency_map):
    node["status"] = "pending"         # 重置为待执行
    completed.discard(step_id)           # 从已完成集合移除
    node_outputs.pop(step_id, None)      # 清除旧输出
    node_statuses[step_id] = "pending"
```

`_should_resume_node()` 通过递归遍历 `dependency_map` 判断某节点是否是恢复点的下游（直接或间接依赖），确保**只重跑失败节点及其下游，已成功节点不重跑**。

#### Step 2: 就绪节点识别

每轮循环首先找出所有依赖已满足的节点：

```python
# task_graph_executor.py
terminal_steps = completed | skipped   # 已终态节点
ready_nodes = [
    node
    for step_id, node in remaining.items()
    if dependency_map.get(step_id, set()).issubset(terminal_steps)
]
```

依赖满足的判断标准：节点的所有父节点（通过 `parent_id` 或 `edges` 建立的依赖）都已进入终态（`completed` 或 `skipped`）。

#### Step 3: 条件边评估与分支跳过

对于每个就绪节点，调用 `_evaluate_node_readiness()` 检查入边条件。条件不满足的节点被标记为 `skipped`，不执行：

```python
# task_graph_executor.py
readiness = self._evaluate_node_readiness(
    task=task, node=node,
    incoming_edges=incoming_edges_map.get(step_id, []),
    node_outputs=node_outputs, node_statuses=node_statuses,
)
if readiness.get("status") == "skipped":
    skipped_nodes.append((node, readiness))  # 条件不满足，跳过
else:
    executable_nodes.append(node)            # 条件满足，执行
```

支持的条件类型：`always` / `on_success` / `on_failure` / `on_skipped` / `equals:path:value` / `truthy:path` / `falsy:path`。

#### Step 4: 并行执行与重试

所有就绪节点通过 `asyncio.gather` 并行执行，每个节点由 `NodeExecutor.execute_with_retry()` 处理：

```python
# task_graph_executor.py
results = await asyncio.gather(
    *(
        self._node_executor.execute_with_retry(
            task=task, node=node, node_outputs=node_outputs,
        )
        for node in executable_nodes
    )
)
```

`execute_with_retry()` 的重试逻辑（[node_executors.py](../src/riskagent_backend/orchestration/node_executors.py)）：

```python
# node_executors.py
for attempt in range(retry_budget + 1):
    result = await self.execute_once(task=task, node=node, node_outputs=node_outputs)
    if result["status"] in {"completed", "stopped"}:
        return result                              # 成功，返回
    failure_classification = result.get("failure_classification", "")
    retryable = failure_classification in {"timeout", "dependency", "runtime"}
    retry_records.append({"attempt": attempt + 1, "failure_classification": ..., "retry_scheduled": retryable and attempt < retry_budget})
    if not retryable or attempt >= retry_budget:
        return result                              # 不可重试或重试次数用完
```

**关键设计**：只有 `timeout` / `dependency` / `runtime` 三类失败才会重试，`validation`（参数错误）和 `permission`（权限不足）不重试——参数错误需要人工修复，重试无意义。

#### Step 5: 状态同步与下游触发

执行完成后，更新节点状态并触发下游：

```python
# task_graph_executor.py
for node, node_result in zip(processed_nodes, processed_results):
    step_id = str(node["step_id"])
    node["status"] = node_result["status"]     # 更新节点状态
    node_statuses[step_id] = node_result["status"]

    if node_result["status"] == "completed":
        completed.add(step_id)                    # 加入已完成集合 → 下游依赖满足
        node_outputs[step_id] = node_result["output"]
    elif node_result["status"] == "skipped":
        skipped.add(step_id)                      # 加入已跳过集合 → 下游依赖满足
    elif node_result["status"] == "blocked":
        should_stop = True                        # 审批等待，停止执行
        status = "blocked"
        blocked_step_id = step_id
    else:  # failed
        status = "failed"
        failed_step_id = step_id

    remaining.pop(step_id, None)                 # 从待执行集合移除
```

每完成一个节点还会触发回调 `_on_node_completed`，由 `proactive_workflow` 注册用于写入 working_memory 和 session 分段。

#### Step 6: 终止判断与结果输出

```python
# task_graph_executor.py
if should_stop or status == "failed":
    break                       # 遇到 blocked/failed/stop，跳出循环

# 无就绪节点且仍有剩余节点 → 图卡住（deadlock）
if not executable_nodes and not skipped_nodes:
    status = "failed"
    for node in remaining.values():
        node["status"] = "blocked"
    errors.append("task_graph_stalled")
    break
```

最终输出包含完整执行状态：

```python
return {
    "status": status,                    # completed / failed / blocked / stopped
    "task_graph": {"nodes": ..., "edges": ...},  # 最终图状态（含节点 status）
    "task_graph_execution": {
        "completed_steps": sorted(completed),
        "skipped_steps": sorted(skipped),
        "failed_step_id": failed_step_id,
        "blocked_step_id": blocked_step_id,
        "errors": errors,
        "node_outputs": node_outputs,     # 各节点输出
        "retry_records": retry_records,    # 重试记录
        "resume_history": resume_history, # 恢复历史
        "resume_ready": failed_step_id is not None,  # 是否可恢复
        "receipts": receipts,             # 工具回执
        "approval_records": approval_records,
        "trace": execution_trace,         # 执行 trace
    },
    "delegate_results": delegate_results,
    "receipts": receipts,
    "final_output": final_output,
}
```

<a id="section-2-3"></a>
## 2.3 节点类型与执行分发

`execute_node()` 根据 `node.kind` 分发到不同执行路径（[node_executors.py](../src/riskagent_backend/orchestration/node_executors.py)）：

| kind | 执行逻辑 | 输出 |
|------|---------|------|
| `delegate` | 调用 `delegate_handlers[target_agent]`（如 SystemEngineer.analyze_task） | `delegate_result` + `output_ref=target_agent` |
| `tool_call` | 构造 `AgentCommand` → `execute_agent_command()` → `Receipt` | `receipt` + `command_id` + `approval_record` |
| `finalize` | 聚合所有 `node_outputs` 的 summary/report，生成最终结论 | `final_output` + `receipt_command_ids` |
| `analyze` | 有 target_agent 则走 delegate；否则纯文本分析上游输出 | `summary` + `report` |
| `ask_human` | 有 `human_response` 则完成；否则生成 `pending` 审批，blocked | `approval_record` + `error=human_input_required` |
| `replan` | 标记需要重规划，输出 `replan=True` | `output_ref=replan` |
| `stop` | 生成停止输出，status=`stopped` | `final_output` + `stopped=True` |

<a id="section-2-4"></a>
## 2.4 审批拦截机制

在执行节点前，`execute_node()` 先调用 `_check_step_approval()` 检查节点级审批（[node_executors.py](../src/riskagent_backend/orchestration/node_executors.py)）：

```python
step_approval_result = self._check_step_approval(node=node)
if step_approval_result is not None:
    return step_approval_result  # 返回 blocked 状态，阻止执行
```

审批状态机：`pending` → `approved`（放行）/ `rejected`（blocked）/ `expired`（blocked）。只有 `approved` 和 `resumed` 状态才允许继续执行。

对于 `tool_call` 节点，审批在 `Receipt` 层处理：`execute_agent_command()` 内部通过 tool_executor.py 的五道关卡检查 RBAC 权限和审批要求。

### HITL_AUTO_APPROVE 自动审批机制（Phase 10 引入）

当环境变量 `HITL_AUTO_APPROVE=1` 显式开启时，`side_effect` 工具的审批参数会被自动注入，无需人工介入即可执行处置动作。**默认值为关闭（fail-safe）**：2026-08-11 安全加固（commit ee6ae70）将该开关改为默认关闭，需显式设置 `HITL_AUTO_APPROVE=1` 才会启用自动审批。代码位置：[node_executors.py](../src/riskagent_backend/orchestration/node_executors.py)、[hitl_policy.py](../src/riskagent_backend/orchestration/hitl_policy.py)。

**工作原理**：
- `execute_node()` 在处理 `tool_call` 节点时检查 `HITL_AUTO_APPROVE` 环境变量
- 当 `HITL_AUTO_APPROVE=1` 时，自动将 `approval_state` 设为 `approved`，跳过 `pending → approved` 的人工等待
- 主动监控场景下不使用 `ask_human` 节点人类升级，开启自动审批后可消除全链路阻塞
- 审批记录仍会写入 `approval_trace`，确保审计可追溯

**设计权衡**：
- 自动审批适用于主动监控等需要快速响应的场景，避免因人工等待导致全链路阻塞
- 默认保持人工审批（fail-safe），仅在显式设置 `HITL_AUTO_APPROVE=1` 时开启自动审批
- Phase 10 验证中，此机制替代了原计划的 `ask_human` 人类升级流程

<a id="section-2-5"></a>
## 2.5 意外中断的上下文恢复机制

#### 恢复入口

中断恢复通过 `resume_request` 进入主流程（见主流程图的 resume 路径）：

```python
# orchestration/workflow_resume.py（resume 入口解析）
execution_state = resume_request.get("execution_state")
resume_from_step_id = (
    resume_request.get("resume_from_step_id")
    or execution_state.get("failed_step_id")  # 自动取失败节点
)
```

#### 恢复过程

`TaskGraphExecutor.execute()` 接收 `execution_state` 和 `resume_from_step_id`，执行恢复：

```
恢复前状态:
  completed = {s1, s2}        ← s1、s2 已成功
  s3 failed                   ← s3 失败导致中断
  s4, s5 pending              ← s4、s5 未执行

恢复操作:
  ① 从 execution_state 恢复 completed/skipped/node_outputs/receipts
  ② _should_resume_node(s3) == True → s3 重置为 pending
  ③ _should_resume_node(s4) == True（s4 依赖 s3）→ s4 重置为 pending
  ④ _should_resume_node(s5) == True（s5 依赖 s4）→ s5 重置为 pending
  ⑤ s1、s2 不在 s3 下游 → 保持 completed，不重跑

恢复后:
  s1: completed (不重跑)       ← 幂等性保证
  s2: completed (不重跑)
  s3: pending → 重新执行
  s4: pending → 等待 s3 完成后执行
  s5: pending → 等待 s4 完成后执行
```

`_should_resume_node()` 使用递归 DFS 遍历 `dependency_map`，判断目标节点是否在恢复点的下游链路上：

```python
# task_graph_executor.py
def _should_resume_node(self, *, step_id, resume_from_step_id, dependency_map) -> bool:
    if step_id == resume_from_step_id:
        return True                                    # 是恢复点本身
    return self._depends_on(step_id=step_id, target_step_id=resume_from_step_id, dependency_map=dependency_map)

def _depends_on(self, *, step_id, target_step_id, dependency_map) -> bool:
    stack = list(dependency_map.get(step_id, set()))    # 从当前节点出发
    visited = set()
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == target_step_id:
            return True                                # 依赖链上找到恢复点
        stack.extend(dependency_map.get(current, set()))  # 继续向上遍历
    return False
```

#### 恢复记录

每次恢复都会在 `resume_history` 中插入一条记录：

```python
# task_graph_executor.py
resume_history.insert(0, {
    "resume_from_step_id": resume_from_step_id,
    "mode": "step_resume",
})
```

最终写入 `run_trace.v2`，审计时可追溯完整的恢复链路。

<a id="section-2-6"></a>
## 2.6 执行受阻后的 TaskGraph 修改与续跑机制

#### 受阻场景一：节点失败 → 自动重试 → 人工修复后恢复

节点执行失败后，`execute_with_retry()` 根据 `failure_classification` 决定是否重试：

| failure_classification | 是否自动重试 | 原因 |
|------------------------|------------|------|
| `timeout` | ✅ | 超时可能是暂时性的（网络抖动） |
| `dependency` | ✅ | 依赖不可用可能是暂时的（服务重启） |
| `runtime` | ✅ | 运行时异常有概率自恢复 |
| `validation` | ❌ | 参数错误需要人工修复参数 |
| `permission` | ❌ | 权限不足需要人工授权 |

重试次数由 `node.retry_budget` 或 `task.execution_policy.default_retry_budget` 控制（默认 0，不重试）。

当自动重试用尽后，执行返回 `status=failed`，`resume_ready=True`，等待人工干预：

```
第 1 次执行:
  s1: completed ✓
  s2: failed (validation error, retry_budget=1)
    → retry_records: [{attempt:1, classification:validation, retry_scheduled:False}]
    → resume_ready: True

人工修复后第 2 次执行（传入修复后的 task_graph + execution_state + resume_from_step_id=s2）:
  s1: completed (跳过，不重跑) ✓
  s2: pending → 重新执行 (参数已修复) → completed ✓
  s3: pending → 执行 → completed ✓
  → status: completed
```

#### 受阻场景二：审批等待 → 人工审批后恢复

节点级审批或工具级审批触发 `status=blocked`，执行暂停：

```
第 1 次执行:
  s1: completed ✓
  s2: blocked (approval_required, state=pending)
    → approval_record: {approval_id:appr_001, state:pending}
    → status: blocked, blocked_step_id: s2

人工审批后第 2 次执行（传入 approval.state=approved 的 task_graph）:
  s1: completed (跳过) ✓
  s2: _check_step_approval → state=approved → 放行 → completed ✓
  s3: pending → 执行 → completed ✓
  → status: completed
```

#### 受阻场景三：Critic 拒绝计划 → 重规划子图挂接

CriticAgent 在 plan_review 阶段拒绝 OrchestratorAgent 的计划时，触发重规划：

```python
# orchestration/workflow_planning.py（critic 拒绝触发重规划）
if should_replan(critic_result.output):
    # 1. 让 OrchestratorAgent 在 replan 上下文中重新规划
    replan_result = await self._orchestrator_agent.orchestrate(
        task=task,
        context={"phase": "replan", "critic": critic_result.output, "prior_orchestrator_plan": orchestrator_result.output},
    )
    # 3. 将新计划作为子图挂接到原 TaskGraph 后面
    active_task_graph = append_replan_subgraph(
        active_task_graph,          # 原 TaskGraph
        replan_result.output,        # 新计划
        reason=build_replan_reason(critic_result.output),
    )
```

`append_replan_subgraph()` 的挂接逻辑（[task_graph.py](../src/riskagent_backend/contracts/task_graph.py)）：

```
原 TaskGraph:                      重规划后:
  s1 → s2 → s3 (finalize)           s1 → s2 → s3 (finalize)
                                          ↓
                                     rp1 (replan 节点)
                                          ↓
                                     rp1_s1 → rp1_s2 → rp1_s3 (finalize)
```

具体步骤：
1. 在原图终端节点后插入 `replan` 节点（`step_id=rp1`），`condition=critic_rejected`
2. 新计划的节点 step_id 加前缀 `rp1_`（如 `s1` → `rp1_s1`），避免与原图冲突
3. 新节点的 `parent_id` 重定向到 `rp1`，形成新的子链
4. 新子图的入口节点通过 `always` 边连接到 `rp1`

#### 受阻场景四：运行时重规划

执行过程中也可能触发运行时重规划（`_maybe_runtime_replan`）：

```python
# orchestration/workflow_execution.py（_maybe_runtime_replan）
runtime_replan = await self._maybe_runtime_replan(
    task=task, intent_result=intent_result,
    execution_result=execution_result,
    executor=executor, ...
)
if runtime_replan is not None:
    active_task_graph = runtime_replan["task_graph"]
    execution_result = runtime_replan["execution_result"]
```

<a id="section-2-7"></a>
## 2.7 优缺点

| 维度 | 优点 | 缺点 |
|------|------|------|
| **并行性** | 无依赖的节点通过 `asyncio.gather` 自动并行执行，减少总执行时间 | 并行执行下多个 `tool_call` 可能竞争外部资源（如数据库连接池），需工具层自行控制并发 |
| **可恢复性** | `execution_state` + `resume_from_step_id` 实现精确恢复，只重跑失败节点及下游，不重跑已成功节点 | 恢复依赖调用方正确传入 `execution_state`，如果中间状态丢失（如进程崩溃且未持久化），无法恢复 |
| **可重规划** | `append_replan_subgraph` 动态挂接新计划，保留原图历史，审计可追溯 | 重规划子图的节点命名靠 `rp{index}_` 前缀避免冲突，多次重规划后 step_id 会变长，可读性下降 |
| **可审计性** | 每个节点的 status/error/retry_records/latency_ms/command_id 全部写入 `execution_trace`，最终进入 `run_trace.v2` | trace 数据量大（每个节点 15+ 字段），长任务图可能产生数百条 trace 记录 |
| **容错性** | 三类失败自动重试（timeout/dependency/runtime），两类不重试（validation/permission）避免无意义重试 | `retry_budget` 默认为 0（不重试），需要调用方显式配置；重试间隔无指数退避（backoff），可能立即再次失败 |
| **条件分支** | 支持 `always/on_success/on_failure/equals/truthy` 等多种条件，支持动态路由 | 条件评估逻辑复杂（`_evaluate_condition` 有 50+ 行分支），维护成本高 |
| **审批集成** | 节点级审批（`_check_step_approval`）和工具级审批（`Receipt.approval_trace`）双层拦截 | 审批等待期间整个图执行暂停，如果人工审批耗时较长（如 4 小时），会话上下文可能过期 |

<a id="section-2-8"></a>
## 2.8 关键代码出处

| 组件 | 文件 | 方法/类 |
|------|------|--------|
| 执行器主类 | [task_graph_executor.py](../src/riskagent_backend/orchestration/task_graph_executor.py) | `TaskGraphExecutor.execute()` |
| 节点执行器 | [node_executors.py](../src/riskagent_backend/orchestration/node_executors.py) | `NodeExecutor.execute_node()` / `execute_with_retry()` |
| 重规划子图挂接 | [task_graph.py](../src/riskagent_backend/contracts/task_graph.py) | `append_replan_subgraph()` |
| 图归一化 | [task_graph.py](../src/riskagent_backend/contracts/task_graph.py) | `normalize_task_graph()` / `build_task_graph_from_plan_steps()` |
| 工具命令执行 | [tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) | `execute_agent_command()` |
| 主链接入点 | [proactive_workflow.py](../src/riskagent_backend/orchestration/proactive_workflow.py) | `ProactiveBackEndWorkflow.run()` Step 4 |
| 运行时重规划 | [proactive_workflow.py](../src/riskagent_backend/orchestration/proactive_workflow.py) | `_maybe_runtime_replan()` |
| 恢复请求处理 | [proactive_workflow.py](../src/riskagent_backend/orchestration/proactive_workflow.py) | `run()` resume 路径 |

<a id="section-3"></a>
# 3. Agent BDI 心智架构

BDI（Belief-Desire-Intention）是主动 Agent 的内部心智状态建模框架，与 ReAct（执行范式）和 CoT（推理方法）不在同一层，三者混合使用。

<a id="section-3-1"></a>
## 3.1 定位与三者关系

| 维度 | CoT | ReAct | BDI |
|---|---|---|---|
| **本质** | 推理技巧（prompt 层） | 执行范式（Thought-Action-Observation 循环） | 状态架构（心智状态建模） |
| **作用层** | 单次 LLM call 内 | 单任务循环 | Agent 全生命周期 |
| **是否需要环境交互** | 否 | 是 | 是 |
| **是否有持久状态** | 无 | 步骤内 | 有（跨任务/跨轮） |
| **本项目落点** | `_generate_reasoning` + `_generate_evidence` 两个独立 LLM 步 | `run_with_react` 的 6 阶段循环 | `BaseProactiveAgent` 的三个心智池 + `_monitor_loop` |

三者关系：**BDI 建模内部状态，ReAct 做单步推理-行动循环，循环里的 Thought 用 CoT 风格写**。

### 三者协同 Example

以 ProactiveOrchestratorAgent 处理一个 error_rate 异常为例，展示 BDI / ReAct / CoT 如何分层协作：

```
===== BDI 层（跨轮次，_monitor_loop 每 60s 一轮）=====

第 1 轮 Perceive:
  PrometheusDataSource.collect() 采集到 error_rate=0.15
  PerceptionFilterEngine 判定 severity=warning
  → add_belief(
      content={metric:"error_rate", value:0.15, severity:"warning"},
      source="orchestration_perception",
      confidence=0.7
    )

第 1 轮 Deliberate:
  get_beliefs()[-5:] 包含上述 B1
  B1.severity == "warning" → priority = "normal"
  → add_intention(
      description="主动告警:orchestration_perception 信号异常 (severity=warning)",
      target_agent="orchestrator",
      tool_name="submit_alerts",
      tool_params={severity:"warning", metric_name:"error_rate", metric_value:0.15, ...}
    )

第 1 轮 Act:
  I1.status: pending → executing
  _build_proactive_event(I1) → new_event(RISK_BREACH_DETECTED, ...)
  workflow.start_from_event(event)  ← 投递到统一主链
  I1.status: executing → completed

===== ReAct 层（单任务循环，run_with_react，主链接收事件后触发）=====

Step 1:
  Thought:  "error_rate=0.15 超过阈值 0.1，需要排查根因"     ← CoT 风格
  Reasoning: "根据 Prometheus 采集数据，error_rate 从 0.03 飙升到
             0.15，集中在 payment-service，可能是数据库连接池耗尽"  ← CoT 推理
  Evidence:  {sources:["prometheus"], data:{service:"payment-service"}}  ← CoT 证据
  Action:    tool_call → query_logs(service="payment-service")
  Observation: {status:"ok", logs:["connection pool exhausted", ...]}

Step 2:
  Thought:  "日志确认连接池耗尽，需要扩容"
  Action:    finalize → {answer:"payment-service 连接池耗尽，建议扩容"}

===== 最终输出 =====
ProactiveAgentResult(
  ok=True,
  output={system_issue:True, reason:"connection_pool_exhausted", ...},
  react_steps=[Step1, Step2],
  bdi_state={beliefs:[B1], desires:[D1,D2,D3], intentions:[I1(completed)]},
)
→ 写入 run_trace.v2
```

**关键点**：BDI 在 `_monitor_loop` 中运行（后台 asyncio task），ReAct 在 `run_with_react` 中运行（主链触发），两者共享同一个 `BaseProactiveAgent` 实例的三个心智池。BDI 的 Belief 被 ReAct 的 `_generate_evidence` 读取（`get_beliefs()[-5:]`），形成数据流闭环。

<a id="section-3-2"></a>
## 3.2 数据结构

三个心智状态定义在 [base_models.py](../src/riskagent_backend/proactive_agents/base_models.py):

```python
@dataclass
class Belief:        # 信念：Agent 认为世界的状态
    content: Any     # 具体内容（可以是 dict/list/str）
    source: str      # 来源（orchestration_perception / intent_perception / user_input 等）
    confidence: float = 1.0
    belief_id: str   # 不可变 ID，用于 trace 回溯
    timestamp_ms: int  # 创建时间戳（毫秒）

@dataclass
class Desire:        # 愿望：Agent 想要达到的状态
    description: str
    priority: int = 0      # 优先级，数值越大越优先
    active: bool = True    # 是否活跃
    desire_id: str         # 不可变 ID

@dataclass
class Intention:     # 意图：Agent 承诺要执行的行动
    description: str
    target_agent: Optional[str] = None    # 目标 Agent
    tool_name: Optional[str] = None      # 调用工具名
    tool_params: Optional[dict] = None   # 工具参数（携带完整上下文）
    status: str = "pending"  # 状态机：pending → executing → completed/failed
    intention_id: str        # 不可变 ID
    created_timestamp_ms: int  # 创建时间戳
```

**关键设计**：三个心智池都是**进程内 list**（[base.py](../src/riskagent_backend/proactive_agents/base.py)），不是外部存储。持久化由 MemoryStore 负责，BDI 层专注运行时状态。

### 五种 Agent 的愿望与感知配置

| Agent | 监控间隔 | 愿望 (按优先级降序) | 感知来源 (belief source) |
|-------|---------|-------------------|------------------------|
| ProactiveIntentAgent | 120s | 准确识别用户意图(10)、识别潜在风险操作(8)、提供清晰意图解释(6) | `intent_perception` |
| ProactiveOrchestratorAgent | 60s | 制定高效执行计划(10)、确保计划可执行且风险可控(9)、合理分配任务给专业 Agent(8) | `orchestration_perception` |
| ProactiveCriticAgent | 90s | 识别计划中的风险点(10)、确保计划符合安全规范(9)、提供有价值的改进建议(7) | `quality_perception` |
| ProactiveSystemEngineerAgent | 30s | 及时发现系统异常(10)、准确诊断问题根因(9)、提供可执行的修复建议(8) | `perception_escalation` |
| ProactiveRiskAnalystAgent | 45s | 准确评估业务风险(10)、识别关键风险因素(9)、提供高置信度分析(8) | `risk_perception` + `risk_escalation` |

### Belief 实际数据 Example

**感知类信念**（来自 Prometheus，由 `_perceive_environment()` 生成）：
```python
Belief(
    belief_id="belief_a1b2c3d4",
    content={
        "source": "prometheus",
        "metric": "error_rate",
        "value": 0.15,
        "severity": "warning",     # PerceptionFilterEngine 判定
    },
    source="orchestration_perception",  # 标识来源（用于 _deliberate 过滤）
    confidence=0.7,
    timestamp_ms=1780038447000,
)
```

**升级类信念**（由 EscalationManager 聚合多条信号后生成）：
```python
Belief(
    belief_id="belief_e5f6g7h8",
    content={
        "event_id": "evt_001",
        "severity": "critical",
        "source": "redis",
        "description": "Redis 连接数超过阈值 500",
        "signal_count": 3,          # 聚合了 3 条原始信号
    },
    source="perception_escalation",   # 升级来源，confidence 更高
    confidence=0.9,
    timestamp_ms=1780038448000,
)
```

**用户输入信念**（由 ReAct 入口方法添加，不参与 _deliberate 主动告警）：
```python
Belief(
    belief_id="belief_i9j0k1l2",
    content={"task_id": "task_789", "context": {...}},
    source="orchestration_request",    # 不在 _PERCEPTION_SOURCES 中
    confidence=1.0,
    timestamp_ms=1780038449000,
)
```

### `_PERCEPTION_SOURCES` 白名单

`_deliberate()` 只处理以下 6 种 source 的信念（[base.py](../src/riskagent_backend/proactive_agents/base.py)）：

```python
_PERCEPTION_SOURCES = frozenset({
    "intent_perception",        # IntentAgent 感知
    "perception_escalation",    # SystemEngineer 升级
    "risk_perception",          # RiskAnalyst 感知
    "risk_escalation",          # RiskAnalyst 升级
    "orchestration_perception", # Orchestrator 感知
    "quality_perception",       # Critic 感知
})
```

非感知来源的信念（如 `user_input`、`orchestrator_plan`、`orchestration_request`）不会被 `_deliberate()` 处理，它们仅供 ReAct 循环的 `_generate_evidence()` 读取。

<a id="section-3-3"></a>
## 3.3 状态流转：Perceive → Deliberate → Act

后台监控循环（[base.py `_monitor_loop`](../src/riskagent_backend/proactive_agents/base.py)）实现 BDI 经典循环：

```
[后台监控循环 _monitor_loop]
    ↓
 ① Perceive: _perceive_environment()
    → data_sources.collect() → PerceptionFilterEngine 过滤
    → add_belief(content, source, confidence)
    ↓
 ② Deliberate: _deliberate()
    → get_beliefs()[-5:] + get_active_desires()
    → 规则判断（如 error_rate > 0.1）
    → add_intention(description, target_agent, tool_name, tool_params)
    ↓
 ③ Act: _act()
    → get_pending_intentions()
    → update_intention_status(id, "executing")
    → _build_proactive_event(intention) → new_event()
    → workflow.start_from_event(event)
    → update_intention_status(id, "completed"/"failed")
    ↓
 回到 ①，等待下一个 monitor_interval
```

**关键设计**：
- **感知层可插拔**：数据源通过 `ds.collect()` 接口接入，不绑定具体实现
- **规则驱动 Deliberate**：金融风控需要确定性阈值（如 error_rate>0.1），纯 LLM 推理不稳定
- **意图携带完整上下文**：`tool_params` 里有 metric_name/metric_value，后续执行不需要再查

<a id="section-3-4"></a>
## 3.4 意图状态机

意图状态流转（[base.py](../src/riskagent_backend/proactive_agents/base.py)）：

```
pending → executing → completed
                    ↘ failed
```

每次状态变更都记录，支持失败重试和审计追溯。意图 ID（`intention_id`）贯穿全程，最终写入 `ProactiveAgentResult.bdi_state`，进入 run_trace。

<a id="section-3-5"></a>
## 3.5 与主链的接入点

**关键约束**：主动意图不直接执行工具，而是转成统一系统事件投递回 `proactive_workflow.start_from_event`，走和用户任务**完全相同**的主链（intent → plan → task_graph → receipt）。

接入点代码（[base.py](../src/riskagent_backend/proactive_agents/base.py)）：

```python
from riskagent_backend.orchestration.proactive_workflow import get_proactive_workflow

workflow = get_proactive_workflow()
await workflow.start_from_event(
    event=proactive_event,
    candidate_agents=[intention.target_agent, "critic", "orchestrator"],
)
```

符合 PRD 硬约束："所有新增能力接入统一执行内核，不形成旁路"。

<a id="section-3-6"></a>
## 3.6 关键代码出处

| 组件 | 文件 | 方法/类 |
|---|---|---|
| 数据结构定义 | [base_models.py](../src/riskagent_backend/proactive_agents/base_models.py) | `Belief` / `Desire` / `Intention` |
| 心智池初始化 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `__init__` |
| 后台监控循环 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_monitor_loop` |
| 感知环境 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_perceive_environment` |
| 信念→意图 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_deliberate` |
| 意图→行动 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_act` |
| 意图状态机 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `update_intention_status` |
| 状态快照导出 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `get_bdi_state` |
| 意图→事件 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_build_proactive_event` |
| ReAct 主循环 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `run_with_react` |
| CoT 推理步 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_generate_reasoning` |
| CoT 证据步 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_generate_evidence` |

<a id="section-4"></a>
# 4. ReAct / CoT 推理循环

本项目在所有主动 Agent 中统一实现了 **ReAct（Reasoning + Acting）** 循环与 **CoT（Chain-of-Thought）** 思维链。每个 Agent 执行任务时不是一次性生成结果，而是经历多轮 Thought → Reasoning → Evidence → Action → Observation 的迭代，最终将推理链汇总为结构化输出。

<a id="section-4-1"></a>
## 4.1 核心概念与数据结构

### ReActStep

ReAct 循环的每个步骤都用 [ReActStep](../src/riskagent_backend/proactive_agents/base_models.py) 表示：

```python
@dataclass
class ReActStep:
    step_id: str                    # 步骤编号，如 "step_1"
    thought: str                    # 思考内容（LLM 动态生成）
    reasoning: str                  # 推理理由（CoT 核心，解释为何选择此思考）
    evidence: dict[str, Any]       # 证据（CoT 核心，支撑推理的具体数据/来源）
    action_type: str               # 行动类型：llm_call / tool_call / finalize / ask_human
    action: dict[str, Any]         # 行动参数
    observation: Optional[dict]    # 观察结果（行动执行后的返回值）
    timestamp_ms: int              # 时间戳（毫秒）
```

**关键设计**：
- **动态生成**：thought / reasoning / evidence 全部由 LLM 在运行时生成，不硬编码
- **五元组结构**：Thought + Reasoning + Evidence 构成 CoT 三要素，Action + Observation 构成 ReAct 交互环
- **可追溯**：每个步骤带 timestamp_ms，支持事后回放和评估

### ProactiveAgentResult

```python
@dataclass
class ProactiveAgentResult:
    ok: bool
    output: dict[str, Any]                           # 最终结构化输出
    react_steps: list[ReActStep]                     # 完整推理链
    bdi_state: dict[str, Any]                       # 执行后的 BDI 状态快照
    llm_interactions: list[dict[str, Any]]           # 所有 LLM 调用记录
```

`react_steps` 是评估体系中 `evidence_coverage`、`reasoning_quality` 等指标的核心数据来源。

<a id="section-4-2"></a>
## 4.2 ReAct 循环主流程

核心方法 [run_with_react()](../src/riskagent_backend/proactive_agents/base.py) 定义在 `BaseProactiveAgent` 基类中，所有 5 个主动 Agent 共享同一套循环骨架：

```python
async def run_with_react(self, *, task, context=None, max_tokens=512, max_steps=5):
    react_steps = []
    for step_idx in range(max_steps):
        # 1. 生成思考
        thought = await self._generate_thought(task, react_steps, context)
        # 3. 生成推理理由（CoT）
        reasoning = await self._generate_reasoning(task, react_steps, thought, context)
        # 4. 生成证据（CoT）
        evidence = await self._generate_evidence(task, react_steps, thought, reasoning, context)
        # 5. 决定行动
        action_type, action = await self._decide_action(task, react_steps, thought, context)
        # 6. 执行行动 → 观察结果
        observation = await self._execute_action(action_type, action)
        # 组装步骤
        step = ReActStep(step_id, thought, reasoning, evidence, action_type, action, observation)
        react_steps.append(step)
        # 终止判断
        if await self._should_terminate(task, react_steps):
            break
    # 生成最终答案
    final_output = await self._generate_final_answer(task, react_steps)
    return ProactiveAgentResult(ok=True, output=final_output, react_steps=react_steps, ...)
```

**循环流程图**：

```
┌─────────────────────────────────────────────────────────┐
│                   max_steps 次循环                        │
│                                                          │
│  ┌──────────┐    ┌───────────┐    ┌──────────┐          │
│  │ Thought  │───>│ Reasoning │───>│ Evidence │          │
│  │ (LLM)    │    │ (LLM,CoT) │    │ (LLM,CoT)│          │
│  └──────────┘    └───────────┘    └──────────┘          │
│                                          │               │
│                                          v               │
│  ┌──────────┐    ┌───────────┐    ┌──────────┐          │
│  │Observation│<──│ _execute  │<──│_decide   │          │
│  │ (结果)    │    │ _action() │    │_action() │          │
│  └──────────┘    └───────────┘    └──────────┘          │
│       │                                                 │
│       v                                                 │
│  _should_terminate? ──Yes──> _generate_final_answer()   │
│       │No                          │                    │
│       v                              v                    │
│  下一轮循环                    ProactiveAgentResult        │
└──────────────────────────────────────────────────────────┘
```

**终止条件** ([_should_terminate()](../src/riskagent_backend/proactive_agents/base.py))：
- `action_type == "finalize"` → 终止
- `action_type == "ask_human"` 且 observation.timeout == True → 终止
- 达到 `max_steps` 上限 → 自然终止

<a id="section-4-3"></a>
## 4.3 CoT 思维链的五个阶段

每个 ReAct 步骤包含 5 次独立的 LLM 调用，构成完整的 CoT 链：

### 阶段 1：_generate_thought() — 生成思考

```python
prompt = f"""You are {self._name}. Generate your next thought about the task.
Task: {task}
Context: {context_text}
History: {history_text}
Generate a thought about what you should consider or do next.
"""
# LLM 调用：temperature=0.7, max_tokens=128
```

- **输入**：任务 + 历史 3 步摘要 + 上下文
- **输出**：一段自然语言思考文本
- **降级**：LLM 失败时返回 "继续执行任务"

### 阶段 2：_generate_reasoning() — 生成推理理由（CoT 核心）

```python
prompt = f"""Generate reasoning that explains why you chose this thought.
Consider:
- What information do you have?
- What do you need to verify?
- What are the risks or uncertainties?
"""
# LLM 调用：temperature=0.7, max_tokens=256
```

- **输入**：任务 + thought + 历史摘要
- **作用**：解释"为什么"选择此思考，构成 CoT 的推理环节
- **降级**：返回 "基于任务要求执行"

### 阶段 3：_generate_evidence() — 生成证据（CoT 核心）

```python
prompt = f"""Generate evidence that supports your reasoning.
Current beliefs: {beliefs_text}
Evidence (as JSON with keys like "sources", "data", "references"):
"""
# LLM 调用：ask_json, max_tokens=256
```

- **输入**：thought + reasoning + 当前 BDI beliefs（最近 5 条）
- **输出**：JSON 格式的证据结构 `{"sources": [...], "data": {...}}`
- **作用**：将推理锚定到具体数据源，防止 LLM 编造（hallucination）

### 阶段 4：_decide_action() — 决定行动

```python
prompt = f"""Choose an action type and parameters:
- "llm_call": Make another LLM call to gather more information
- "tool_call": Execute a tool (specify tool_name and params)
- "finalize": Task is complete, generate final answer
"""
# LLM 调用：ask_json, max_tokens=256
```

- **输出**：`{"action_type": "finalize", "action": {...}}`
- **降级**：默认 finalize

### 阶段 5：_execute_action() — 执行行动

| action_type | 执行逻辑 | observation 返回 |
|---|---|---|
| `llm_call` | 标记为已执行 | `{"status": "llm_call_executed"}` |
| `tool_call` | `_execute_tool_call()`（子类可重写） | 工具返回值 |
| `finalize` | 标记为完成 | `{"status": "finalized", "result": action}` |
| `ask_human` | `QuestionManager.ask_user()` 等待人工回答 | `{"status": "human_answered", "answer": ...}` |

<a id="section-4-4"></a>
## 4.4 各 Agent 的 ReAct 使用差异

5 个主动 Agent 共享 `run_with_react()` 骨架，但在参数配置、监控频率和感知源上有显著差异：

| Agent | max_steps | max_tokens | monitor_interval | 感知数据源 | _generate_final_answer 输出 |
|---|---|---|---|---|---|
| **IntentAgent** | 5 | None（不限制） | 120s | Prometheus | intent/slots/confidence/risk |
| **OrchestratorAgent** | 5 | 1024 | 60s | Prometheus | plan_steps/commands/task_graph |
| **CriticAgent** | 4 | 512 | 90s | Prometheus | ok/risk_level/issues/fixes |
| **SystemEngineerAgent** | 4 | 512 | 30s | Docker/K8s+Redis+MySQL+Prometheus | system_issue/reason/findings |
| **RiskAnalystAgent** | 4 | 512 | 45s | MySQL+Prometheus | report/key_facts/confidence |

**差异分析**：

- **IntentAgent 独享 max_tokens=None**：意图识别需要让模型（当前为 deepseek-v4-flash）自由输出，不受 token 限制。其他 Agent 都限制在 512-1024。
- **SystemEngineerAgent 监控最频繁（30s）**：系统工程师需要最快感知基础设施异常（Docker/K8s + Redis + MySQL + Prometheus 四源采集）。
- **IntentAgent 和 OrchestratorAgent 步数最多（5 步）**：意图识别和编排规划是最关键的决策环节，需要更多迭代轮次。
- **CriticAgent 有 final_review 旁路**：当 `phase="final_review"` 时，不走 ReAct 循环，直接用 `_build_execution_review()` 基于 receipts 确定性判断（检查 blocked/failed），不走 LLM 推理。

<a id="section-4-5"></a>
## 4.5 _generate_final_answer 的角色差异

每个 Agent 重写 `_generate_final_answer()` 将 ReAct 推理链转换为本角色的结构化输出。这是 ReAct 循环的 **汇聚点**——所有推理步骤被压缩为一个标准化 JSON：

### IntentAgent
```python
# 只取最后一步的 thought 作为推理摘要
prompt = f"""Based on your ReAct reasoning, generate the final intent recognition result.
Your reasoning chain: {history[-1].thought if history else ''}
Generate SIMPLE JSON: intent, slots, confidence, risk
"""
```
- **特点**：只用最后一步的 thought，不汇总全部历史
- **转换**：通过 `_convert_to_standard_format()` 将简化 4 字段转为标准 intent schema

### OrchestratorAgent
```python
# 汇总全部步骤的 thought + action_type
steps_summary = "\n".join([f"Step {s.step_id}: {s.thought} -> {s.action_type}" for s in history])
prompt = f"""Based on your ReAct reasoning, generate the final orchestration plan.
Your reasoning chain: {steps_summary}
Generate JSON: intent, plan_steps, commands
"""
```
- **特点**：完整汇总所有步骤，但只用 thought 和 action_type，丢失 reasoning 和 evidence

### CriticAgent
```python
# 汇总全部步骤的 thought + observation
steps_summary = "\n".join([f"Thought: {s.thought}\nObservation: {s.observation}" for s in history])
prompt = f"""Based on your ReAct reasoning, generate the final review.
Generate JSON: ok, risk_level, issues, require_human_approval, suggested_fixes
"""
```
- **特点**：使用 thought + observation 组合，不使用 reasoning 和 evidence

### SystemEngineerAgent / RiskAnalystAgent
```python
# 与 CriticAgent 相同的汇总模式
steps_summary = "\n".join([f"Thought: {s.thought}\nObservation: {s.observation}" for s in history])
```
- **特点**：两个分析型 Agent 使用相同的汇总模式，但输出 schema 不同

<a id="section-4-6"></a>
## 4.6 ReAct 与评估体系的关联

ReAct 推理链是评估体系中多个维度的核心数据来源：

| 评估指标 | 与 ReAct 的关联 | 计算方式 |
|---|---|---|
| `evidence_coverage` | 统计 react_steps 中有 evidence 的步骤占比 | `evidence_steps / len(react_steps)` |
| `thought_relevance` | LLMJudge 评估 react_steps 中 thought 的相关性 | LLM 评分或 `steps_with_reasoning / total` |
| `reasoning_validity` | LLMJudge 评估推理链有效性 | LLM 评分或启发式 |
| `evidence_support` | LLMJudge 评估证据对推理的支撑度 | LLM 评分或 `steps_with_evidence / total` |
| `reasoning_depth` | 推理深度 = 步骤数 / 5 | `min(1.0, len(react_steps) / 5)` |
| `plan_correctness` | 无 plan_steps 时用 react_steps 存在性做兜底 | 有 react_steps → 0.6 |
| `answer_quality` | 无 LLMJudge 时用 react_steps 存在性做兜底 | 有 react_steps → 0.7 |
| `iteration_count` | ReAct 循环迭代次数 | `len(react_steps)` |
| `logical_consistency` | LLMJudge 评估推理链逻辑一致性 | LLM 评分或启发式 |

**LLMJudge.evaluate_reasoning_quality()** 直接消费 react_steps：
```python
chain_text = "\n".join([
    f"Step {i+1}:\n"
    f"  Thought: {step.get('thought', 'N/A')}\n"
    f"  Reasoning: {step.get('reasoning', 'N/A')}\n"
    f"  Evidence: {step.get('evidence', 'N/A')}\n"
    f"  Action: {step.get('action_type', 'N/A')}"
    for i, step in enumerate(reasoning_chain[:5])
])
```

**关键设计**：评估体系只取前 5 步进行 LLMJudge 评估，与 `max_steps=5` 的上限一致。

<a id="section-4-7"></a>
## 4.7 优点

| 优点 | 说明 |
|---|---|
| **推理可追溯** | 每个 step 都有 thought/reasoning/evidence，完整记录 LLM 的推理过程，支持事后审计和回放 |
| **证据锚定** | Evidence 阶段强制 LLM 引用具体数据源，降低 hallucination 风险 |
| **多轮自纠正** | Observation 反馈到下一轮 Thought，Agent 可以根据执行结果动态调整策略 |
| **统一骨架** | 5 个 Agent 共享 run_with_react() 骨架，通过参数和 _generate_final_answer 重写实现差异化 |
| **与 BDI 联动** | Evidence 阶段注入 BDI beliefs，ReAct 推理与心智模型形成闭环 |
| **与评估对齐** | react_steps 直接作为评估体系 evidence_coverage / reasoning_quality 的数据源 |
| **降级安全** | 每个 LLM 调用都有 fallback，单步失败不阻断整体循环 |
| **行动类型丰富** | 支持 llm_call / tool_call / finalize / ask_human 四种行动，覆盖自主执行和人工协作 |

<a id="section-4-8"></a>
## 4.8 缺点与风险

| 缺点 | 风险等级 | 说明 |
|---|---|---|
| **LLM 调用次数爆炸** | 高 | 每个 ReAct 步骤需要 4-5 次 LLM 调用（thought+reasoning+evidence+action+final），5 步循环 = 20-25 次 LLM 调用，成本和延迟随步数线性增长 |
| **串行执行无并行** | 高 | Thought → Reasoning → Evidence → Action → Observation 严格串行，无法并行化，导致单 Agent 延迟较高 |
| **_generate_final_answer 丢失推理细节** | 中 | 大部分 Agent 在最终答案中只汇总 thought + observation，丢弃了 reasoning 和 evidence，推理链的价值在汇聚点被压缩 |
| **Evidence 可能是 LLM 编造的** | 中 | Evidence 由 LLM 生成而非从真实工具调用获取，LLM 可能生成虚假证据（`{"sources": [], "data": {}}`），缺乏与真实数据源的绑定校验 |
| **_should_terminate 过于简单** | 中 | 只检查 action_type==finalize 和 ask_human 超时，无法基于推理质量、证据充分性等维度做智能终止 |
| **History 截断丢失上下文** | 中 | `_format_history()` 只保留最近 3 步（`history[-3:]`），早期步骤的推理上下文丢失，长任务可能重复推理 |
| **温度参数偏高** | 低 | thought 和 reasoning 使用 temperature=0.7，推理链可能不稳定，相同输入产生不同推理路径 |
| **llm_call 行动类型未实现** | 低 | `_execute_action()` 中 llm_call 只返回 `{"status": "llm_call_executed"}`，未真正执行额外 LLM 调用 |
| **CriticAgent final_review 旁路** | 低 | final_review 阶段完全跳过 ReAct 循环，用确定性规则替代 LLM 推理，可能遗漏 LLM 能发现的深层问题 |

<a id="section-4-9"></a>
## 4.9 改进建议

### 改进 1：将 5 次 LLM 调用合并为 1 次结构化输出

**问题**：每步 4-5 次 LLM 调用，成本和延迟高。

**改进方案**：
```python
# 将 thought + reasoning + evidence + action 合并为单次 LLM 调用
prompt = f"""Generate your next ReAct step as JSON:
{{
  "thought": "...",
  "reasoning": "...",
  "evidence": {{"sources": [...], "data": {{...}}}},
  "action_type": "tool_call",
  "action": {{"tool_name": "...", "params": {{...}}}}
}}
"""
result = await self._base_agent.ask_json(prompt, max_tokens=512)
```

**收益**：LLM 调用次数从 5 次/步降至 1 次/步，5 步循环从 25 次降至 5 次，成本和延迟降低 80%。

**代价**：单次输出质量可能不如分步生成（思维链分步生成通常比一次性生成质量更高），需要权衡。

### 改进 2：Evidence 绑定真实工具调用结果

**问题**：Evidence 由 LLM 生成，可能是编造的。

**改进方案**：
```python
async def _generate_evidence(self, task, history, thought, reasoning, context):
    # 先执行工具调用获取真实数据
    real_data = await self._collect_real_evidence(task, reasoning)
    # 让 LLM 基于真实数据生成证据结构
    prompt = f"""Based on this real data, generate evidence JSON:
Real data: {real_data}
Your reasoning: {reasoning}
"""
    evidence = await self._base_agent.ask_json(prompt)
    evidence["_real_data"] = real_data  # 附带原始数据
    return evidence
```

**收益**：Evidence 不再是 LLM 编造的，而是锚定到真实工具调用结果，hallucination 风险大幅降低。

**代价**：每步增加一次工具调用，延迟增加。

### 改进 3：智能终止判断

**问题**：`_should_terminate()` 只看 action_type，不评估推理质量。

**改进方案**：
```python
async def _should_terminate(self, task, history) -> bool:
    if not history:
        return False
    last_step = history[-1]
    # 硬终止：finalize / ask_human 超时
    if last_step.action_type == "finalize":
        return True
    # 软终止：证据充分性判断
    if len(history) >= 3:
        recent_evidence = [s for s in history[-3:] if s.evidence.get("sources")]
        if len(recent_evidence) >= 2:
            # 最近 3 步有 2 步以上带证据，可终止
            return True
    # 预算终止：累计 token 超阈值
    total_tokens = sum(s.action.get("tokens", 0) for s in history)
    if total_tokens > self._token_budget:
        return True
    return False
```

**收益**：减少不必要的推理轮次，在证据充分时提前终止，降低成本和延迟。

### 改进 4：并行化 Thought 与 Reasoning

**问题**：Thought → Reasoning 串行执行。

**改进方案**：
```python
# Thought 和 Reasoning 可以并行生成
thought_task = asyncio.create_task(self._generate_thought(...))
reasoning_task = asyncio.create_task(self._generate_reasoning(...))  # 基于 task 而非 thought
thought, reasoning = await asyncio.gather(thought_task, reasoning_task)
```

**收益**：每步减少一次串行等待，5 步循环可减少约 40% 延迟。

**代价**：Reasoning 不再基于 Thought 生成，逻辑关联性减弱，需要调整 prompt 设计。

### 改进 5：_generate_final_answer 保留完整推理链

**问题**：最终答案汇总时丢失 reasoning 和 evidence。

**改进方案**：
```python
steps_summary = "\n".join([
    f"Step {s.step_id}:\n"
    f"  Thought: {s.thought}\n"
    f"  Reasoning: {s.reasoning}\n"
    f"  Evidence: {json.dumps(s.evidence, ensure_ascii=False)}\n"
    f"  Observation: {json.dumps(s.observation, ensure_ascii=False) if s.observation else 'N/A'}"
    for s in history
])
```

**收益**：最终答案保留完整推理链，LLM 可以基于更丰富的上下文生成更准确的输出，也便于评估体系做更精细的推理质量评估。

<a id="section-4-10"></a>
## 4.10 关键代码出处

| 组件 | 文件 | 方法/类 |
|---|---|---|
| ReAct 循环主方法 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `BaseProactiveAgent.run_with_react()` |
| Thought 生成 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_generate_thought()` |
| Reasoning 生成 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_generate_reasoning()` |
| Evidence 生成 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_generate_evidence()` |
| Action 决策 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_decide_action()` |
| Action 执行 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_execute_action()` |
| 终止判断 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_should_terminate()` |
| 最终答案 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_generate_final_answer()` |
| ReActStep 数据结构 | [base_models.py](../src/riskagent_backend/proactive_agents/base_models.py) | `ReActStep` / `ProactiveAgentResult` |
| 5 种角色实现 | [roles.py](../src/riskagent_backend/proactive_agents/roles.py) | `ProactiveIntentAgent` / `ProactiveOrchestratorAgent` / `ProactiveCriticAgent` / `ProactiveSystemEngineerAgent` / `ProactiveRiskAnalystAgent` |
| 推理结果汇聚 | [workflow_result_builder.py](../src/riskagent_backend/orchestration/workflow_result_builder.py) | `all_react_steps` 汇聚逻辑 |
| LLMJudge 推理评估 | [llm_judge.py](../eval/core/llm_judge.py) | `evaluate_reasoning_quality()` |
| 评估指标消费 | [evaluator.py](../eval/core/evaluator.py) | `_compute_reasoning()` / `_compute_evidence_coverage()` |
| 推理质量指标 | [metrics.py](../eval/core/metrics.py) | `ReasoningMetrics` / `EvidenceCoverage` |

<a id="section-5"></a>
# 5. 统一记忆架构

记忆模块不是单独的向量库服务,而是**统一门面 + Redis 持久层 + 进程内语义索引**的混合架构。

<a id="section-5-1"></a>
## 5.1 总体架构

```text
[Workflow / Agents]
    |
    v
[MemoryStore]                          # 统一门面
    |
    +-- RedisBackend                   # 持久层
    |     +-- shared:memory            # 短期共享记忆 (List)
    |     +-- agent:{id}:memory        # 短期私有记忆 (List)
    |     +-- context:{run_id}         # 运行上下文快照 (Hash)
    |     +-- summary:{run_id}         # 运行摘要 (Hash)
    |
    +-- SemanticIndexer                # 进程内语义索引
          +-- 对重要记忆做轻量语义索引
          +-- 供 planning 时做经验召回
```

**关键设计**：
- **统一门面**：`MemoryStore` 对上承接 workflow 和 agent,对下管理 Redis 和语义检索
- **不是外部向量库**：长期记忆是进程内 `SemanticIndexer`,不是 Chroma(Chroma 属于 knowledge 子系统)
- **四条主链接入**：planning / execution / finalize / resume 全部接到同一套记忆读写协议

<a id="section-5-2"></a>
## 5.2 数据结构：memory_entry.v1

所有记忆条目都符合统一 schema([contracts/memory_entry.py](../src/riskagent_backend/contracts/memory_entry.py))：

```json
{
  "schema_version": "memory_entry.v1",
  "entry_id": "mem_xxx",
  "ts_ms": 1710000000000,
  "agent_id": "system_engineer",
  "scope": "shared",                    // shared / private
  "kind": "working_memory",             // plan / working_memory / final / approval
  "memory_type": "episodic",            // episodic / procedural / semantic
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
    "text": "step step_fetch_metrics kind=tool_call status=completed...",
    "task_id": "task_monitor_001",
    "payload": {"content": "监控交易台敞口和系统状态", "desk": "delta_one"},
    "trace_entry": {"step_id": "step_fetch_metrics", "kind": "tool_call", "status": "completed"},
    "node_result": {"output": {"summary": "service healthy", "confidence": 0.93}}
  },
  "tags": ["tool_call", "completed", "execution"]
}
```

**关键设计**：
- **trace_ref 绑定**：每条记忆都能反查到具体的 run_id / step_id / command_id,支持审计和回放
- **confidence 字段**：支持动态衰减,低置信度记忆可被清理
- **scope 隔离**：shared / private 明确区分共享和私有记忆

<a id="section-5-3"></a>
## 5.3 短期共享记忆

**作用**：所有 agent 都可见的协作记忆流

**Redis 存储**：
- Key: `shared:memory`
- Type: List
- Value: JSON string (memory_entry.v1)

**典型条目**：共 4 种 `kind`，按任务生命周期阶段划分如下：

| kind | 写入阶段 | 写入者 | memory_type | 作用 |
|------|---------|--------|-------------|------|
| `plan` | planning | OrchestratorAgent | episodic | 保存编排计划，供后续 step 恢复和下次 planning 检索 |
| `working_memory` | execution | TaskGraphExecutor | episodic | step 级执行记录，每个 node 完成后写入，是协作面的主要数据流 |
| `final` | finalize | CriticAgent | episodic | run 级总结摘要，包含 key_points 和 receipt 列表 |
| `approval` | approval | Workflow | episodic | 审批记录，包含 approval_id 和 state 状态机快照 |

### 各 kind 详细说明与 Example

**① `plan` — 编排计划记忆**

写入时机：OrchestratorAgent 生成 `plan_steps` 后立即写入。写入逻辑在 [workflow_memory.py:12-43](../src/riskagent_backend/orchestration/workflow_memory.py)，将 `plan_steps` 列表的 `reason/instruction/kind` 拼接为 `plan_text`，连同完整 `plan_steps` 结构体一起存储。

```json
{
  "agent_id": "orchestrator",
  "scope": "shared",
  "kind": "plan",
  "memory_type": "episodic",
  "run_id": "1780038446-7049a732",
  "source": "orchestrator_plan",
  "trace_ref": {"run_id": "1780038446-7049a732"},
  "content": {
    "text": "需要系统工程师分析技术层面 ; 评估业务层面影响 ; 执行风险处置",
    "plan_steps": [
      {"kind": "delegate", "step_id": "s1", "target_agent": "system_engineer",
       "reason": "需要系统工程师分析技术层面", "instruction": "分析系统层面可能原因"},
      {"kind": "delegate", "step_id": "s2", "target_agent": "risk_analyst",
       "reason": "评估业务层面影响", "instruction": "评估业务层面影响"},
      {"kind": "command", "step_id": "s3", "target_agent": "system_engineer",
       "reason": "执行风险处置"}
    ],
    "task_id": "task_789"
  },
  "tags": ["plan"]
}
```

**② `working_memory` — 执行过程记忆**

写入时机：TaskGraphExecutor 每完成一个 node 后写入。写入逻辑在 memory_operations.py 的 [`record_working_memory`](../src/riskagent_backend/memory/memory_operations.py)，记录 `step_id`、`kind`（tool_call/delegate/...）、`status`（completed/failed）、`tool_name`、`target_agent`、`error` 等执行上下文。同步写入 shared 和 private 两条（私有条目 `kind="private_task_state"`）。

```json
{
  "agent_id": "system_engineer",
  "scope": "shared",
  "kind": "working_memory",
  "memory_type": "episodic",
  "run_id": "1780038446-7049a732",
  "source": "task_graph_execution",
  "agent_role": "system_engineer",
  "task_phase": "execution",
  "confidence": 0.93,
  "trace_ref": {
    "run_id": "1780038446-7049a732",
    "step_id": "step_fetch_metrics",
    "command_id": "cmd_001"
  },
  "content": {
    "text": "step step_fetch_metrics kind=tool_call status=completed agent=system_engineer tool=query_positions task=监控交易台敞口",
    "task_id": "task_789",
    "payload": {"content": "监控交易台敞口和系统状态", "desk": "delta_one"},
    "trace_entry": {"step_id": "step_fetch_metrics", "kind": "tool_call", "status": "completed"},
    "node_result": {"output": {"summary": "service healthy", "confidence": 0.93}}
  },
  "tags": ["tool_call", "completed", "execution"]
}
```

**③ `final` — 运行总结记忆**

写入时机：CriticAgent 完成 `final_review` 后写入。写入逻辑在 memory_operations.py 的 [`persist_run_artifacts`](../src/riskagent_backend/memory/memory_operations.py)，保存 `run_summary.text`、`key_points` 和 `receipt_command_ids`。是 run 级别的最终产出快照。

```json
{
  "agent_id": "critic",
  "scope": "shared",
  "kind": "final",
  "memory_type": "episodic",
  "run_id": "1780038446-7049a732",
  "source": "critic_final_review",
  "trace_ref": {"run_id": "1780038446-7049a732"},
  "content": {
    "text": "任务完成：交易台敞口监控正常，系统状态健康",
    "key_points": ["error_rate 已降至 0.02", "payment-service 连接池已扩容"],
    "receipt_command_ids": ["cmd_001", "cmd_002", "cmd_003"],
    "task_id": "task_789",
    "session_id": "sess_001"
  },
  "tags": ["summary"]
}
```

**④ `approval` — 审批记忆**

写入时机：审批流程中每个 approval_record 产生时写入。写入逻辑在 memory_operations.py 的 [`persist_approval_memory`](../src/riskagent_backend/memory/memory_operations.py)，保存 `approval_id`、`state`（pending/approved/rejected/expired）和完整审批记录。`trace_ref` 包含 `step_id` 和 `command_id`，支持反查到具体步骤。

```json
{
  "agent_id": "orchestrator",
  "scope": "shared",
  "kind": "approval",
  "memory_type": "episodic",
  "run_id": "1780038446-7049a732",
  "source": "approval_trace",
  "trace_ref": {
    "run_id": "1780038446-7049a732",
    "step_id": "step_resize_pool",
    "command_id": "cmd_002",
    "approval_id": "appr_001"
  },
  "content": {
    "text": "step=step_resize_pool command=cmd_002 state=approved operator=manager reason=连接池扩容属标准运维操作",
    "task_id": "task_789",
    "approval_record": {
      "approval_id": "appr_001",
      "step_id": "step_resize_pool",
      "command_id": "cmd_002",
      "state": "approved",
      "operator": "manager",
      "reason": "连接池扩容属标准运维操作"
    }
  },
  "tags": ["approval", "approved"]
}
```

### kind 与 memory_type 的关系

`kind` 是业务语义标签（记录“这条记忆是什么”），`memory_type` 是认知科学分类（记录“这条记忆怎么被召回”）：

| memory_type | 对应 kind | 认知科学含义 | 召回方式 |
|-------------|---------|------------|--------|
| `episodic`（情景记忆） | `plan` / `working_memory` / `final` / `approval` | 特定 run 中的具体事件 | 按 `run_id` / `session_id` 精确检索 |

> **注**：`procedural`（过程记忆）和 `semantic`（语义记忆）已不再作为记忆系统的 `kind` 出现，而是统一由 [Skill 系统](#section-6) 管理——高质量 run 经 CriticAgent 评审后通过 SkillProposer 提炼为 Skill，由 SkillStore 独立索引，planning 阶段通过 SkillInjector 注入 few-shot。

**使用场景**：
- planning 阶段从这里取 recent hits 和 shared board
- execution 阶段每完成一个 node 就写入 working_memory
- finalize 阶段写入 final

**关键设计**：
- **主协作面**：shared memory 是整个系统的主协作面,private memory 只是辅助
- **时序有序**：List 结构保证记忆按时间顺序排列,最近记忆在末尾

<a id="section-5-4"></a>
## 5.4 短期私有记忆（分角色）

**作用**：只给单个 agent 自己看的私有任务快照

**Redis 存储**：
- Key: `agent:{agent_id}:memory` (如 `agent:system_engineer:memory`)
- Type: List
- Value: JSON string (memory_entry.v1,但 content 是私有快照结构)

**典型条目**：
```json
{
  "scope": "private",
  "kind": "private_task_state",
  "content": {
    "role": "system_engineer",
    "task_goal": "监控交易台敞口和系统状态",
    "current_progress": "completed",
    "open_questions": [],
    "recent_observations": ["service healthy"],
    "next_intended_action": "handoff_to_next_step",
    "snapshot_text": "role=system_engineer goal=监控交易台敞口和系统状态 progress=completed..."
  }
}
```

**使用场景**：
- 角色隔离：每个 agent 只能看到自己的私有记忆
- 局部状态延续：agent 重启后能恢复之前的任务进度
- planning 阶段会把默认角色的 private memory state 一起读回来

**关键设计**：
- **角色隔离硬约束**：`memory_cross_talk_rate = 0%` 是治理指标,私有记忆被非所属 agent 读取的比例必须为 0
- **辅助定位**：private memory 只是辅助角色隔离和局部状态保存,主协作面还是 shared memory

<a id="section-5-5"></a>
## 5.5 长期经验记忆

**作用**：运行结束后沉淀的 summary,供后续 planning 时做经验召回。长期经验（procedural/semantic）已不再沉淀为记忆条目，而是统一由 [Skill 系统](#section-6) 通过 SkillProposer 提炼为 Skill,planning 阶段通过 SkillInjector 注入 few-shot。

**实现方式**：
- **不是外部向量库**：当前实现是进程内 `SemanticIndexer`
- **Chroma 属于 knowledge 子系统**：不是记忆主链

**使用场景**：
- planning 阶段做经验召回(semantic hits)
- 相似任务不再重复推理,直接复用历史经验
- 系统越用越好,组织智慧持续积累

**关键设计**：
- **轻量语义索引**：不依赖外部向量库,降低部署复杂度
- **confidence 衰减**：长期记忆的置信度会随时间衰减,防止过时经验污染规划

<a id="section-5-5-1"></a>
### 5.5.1 TTL 分级策略

系统通过 `TTLPolicyEngine` 将记忆按 `kind` 自动分配到四个 TTL 层级,实现从工作记忆到长期经验的自动演进：

| TTL 层级 | TTL | 包含的 kind | 说明 |
|----------|-----|------------|------|
| `EPHEMERAL` | 24h | `working_memory`, `plan`, `step`, `command`, `receipt`, `approval`, `message`, `private_task_state`, `working` | 运行中的工作态记忆,任务结束后自然过期 |
| `SHORT_TERM` | 7d | `final`, `analysis`, `task`, `intent_disambiguation` | 任务级别的产物,保留一周供复盘和对照 |
| `LONG_TERM` | **永久** | `lesson`, `semantic_case`, `few_shot`, `knowledge`, `fact`, `example` | 经 Critic 审核通过的高置信经验,永不过期,会触发 MySQL 落盘（其中 lesson/semantic_case 为历史 kind 映射残留,现行长期经验沉淀已统一走 Skill 系统） |
| `PERMANENT` | **永久** | `skill`, `policy`, `config`, `procedure`, `playbook` | Skill 和系统配置,永不过期,会触发 MySQL 落盘 |

**分类优先级**（`classify()` 方法,5 级决策链）：

```text
1. entry 中显式指定的 ttl_tier 字段
     ↓ (未指定)
2. custom_overrides 自定义覆盖
     ↓ (未命中)
3. KIND_TO_TTL_TIER 默认映射表
     ↓ (未命中)
4. 根据 memory_type 兜底推断:
   procedural → LONG_TERM
   semantic   → LONG_TERM
   episodic   → SHORT_TERM
     ↓ (无法推断)
5. 最终兜底 → EPHEMERAL
```

**核心方法**：

| 方法 | 功能 |
|------|------|
| `classify(entry)` | 根据 entry 的 kind/memory_type 分配 TTL 层级 |
| `get_ttl_seconds(entry)` | 获取 TTL 秒数（`None` 表示永不过期） |
| `should_persist(entry)` | 判断是否需要 MySQL 落盘（LONG_TERM 和 PERMANENT 才落盘） |
| `is_expired(entry)` | 判断是否已过期（永久级别永不过期） |
| `get_cleanup_candidates(entries)` | 筛选待清理的过期条目 |

**关键设计**：
- **时间驱动演进**：EPHEMERAL → SHORT_TERM 由时间自然驱动（24h 后若未过期进入 7 天窗口）
- **质量驱动升级**：SHORT_TERM → LONG_TERM 由 CriticAgent 的 `confidence_policy` 控制（`ok=True` + `confidence ≥ 0.85` 的高质量 run 通过 [SkillProposer](#section-6-4) 提炼为 Skill）
- **永久级别保护**：LONG_TERM 和 PERMANENT 永不过期,且触发 MySQL 落盘,Redis 重启后可从 MySQL 恢复
- **过期不删运行中任务**：`cleanup_expired()` 仅删除已过期条目,不影响运行中任务

<a id="section-5-5-2"></a>
### 5.5.2 MySQL 持久化

系统通过 `PersistenceBackend` 将 LONG_TERM 和 PERMANENT 层级的记忆异步落盘到 MySQL,解决 Redis 重启丢失关键经验的问题。

**存储模型**：使用 `memory_store` 表（`INSERT ON DUPLICATE KEY UPDATE` 语义）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `entry_id` | VARCHAR(128) PK | 记忆唯一 ID |
| `ts_ms` | BIGINT | 创建时间戳（毫秒） |
| `agent_id` | VARCHAR(64) | Agent ID |
| `scope` | VARCHAR(16) | shared / private |
| `kind` | VARCHAR(32) | 业务语义标签 |
| `memory_type` | VARCHAR(32) | episodic / procedural / semantic |
| `content` | JSON | 记忆内容（Python dict → JSON 序列化） |
| `source` | VARCHAR(128) | 来源 |
| `confidence` | FLOAT | 置信度 [0,1] |
| `created_by` | VARCHAR(64) | 创建者 |
| `trace_ref` | JSON | 溯源引用（run_id/step_id/command_id） |
| `tags` | JSON | 标签列表 |
| `session_id` | VARCHAR(128) | 会话 ID |
| `run_id` | VARCHAR(128) | 运行 ID |
| `ttl_tier` | VARCHAR(16) | TTL 层级标记 |
| `created_at` | TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | 更新时间 |

**核心方法**：

| 方法 | 功能 | 调用场景 |
|------|------|---------|
| `persist_memory_entry(entry)` | 单条记忆落盘（upsert） | 高置信度记忆写入时异步触发 |
| `batch_persist_memory(entries)` | 批量落盘 | `flush_to_persistence()` 定期批量同步 |
| `load_memory_entries(run_id, agent_id, kinds)` | 从 MySQL 加载记忆 | `restore_from_persistence()` 故障恢复 |
| `persist_skill(skill)` | Skill 落盘（upsert） | Skill 创建/更新时触发 |
| `load_skills(status)` | 从 MySQL 加载 Skill | Skill 系统恢复 |

**落盘策略**：

```text
MemoryStore.append(entry)
  │
  ├─ TTLPolicyEngine.classify(entry) → tier
  │
  ├─ TTLPolicyEngine.should_persist(entry)
  │   ├─ LONG_TERM / PERMANENT → spawn_background_task(persist_memory_entry())
  │   └─ EPHEMERAL / SHORT_TERM → 仅 Redis,不落盘
  │
  └─ 落盘失败 → 仅写 warning 日志,不中断主流程
```

**故障恢复**：

```text
MemoryStore.restore_from_persistence()
  │
  ├─ persistence.load_memory_entries() → 从 MySQL 批量加载
  ├─ 逐条写入 Redis (shared:memory / agent:{id}:memory)
  └─ 重建 SemanticIndexer 索引
```

**关键设计**：
- **Fire-and-forget**：落盘使用 `spawn_background_task()`（内部为 `asyncio.create_task()` 并保持强引用防止 GC 丢失）,不阻塞主执行链路
- **Upsert 语义**：`INSERT ON DUPLICATE KEY UPDATE` 保证幂等,重复写入不会产生脏数据
- **同步引擎异步包装**：SQLAlchemy 同步 Engine 通过 `asyncio.to_thread` 包装为异步,避免阻塞事件循环
- **JSON 透明序列化**：`content`/`trace_ref`/`tags` 等复杂字段自动 JSON 序列化/反序列化,上层无感知

<a id="section-5-6"></a>
## 5.6 记忆能解决什么问题

| 问题 | 记忆机制 | 效果 |
|---|---|---|
| **planning 缺乏历史上下文** | retrieve_for_planning() 读取 shared board + semantic hits | orchestrator 能参考历史 plan 和 Skill few-shot,避免重复犯错 |
| **execution 缺乏过程记录** | record_working_memory() 每步写入 | 后续 agent 能看到之前的执行结果,支持协作 |
| **resume 缺乏上下文** | save_run_context() 保存完整快照 | 恢复执行时能从中断点继续,不是重新跑一遍 |
| **经验无法复用** | SemanticIndexer 做语义索引 | 相似任务能召回历史经验,few_shot_reuse_rate > 30% |
| **多角色协作缺乏共享面** | shared memory list | 所有 agent 能看到共享记忆,支持动态协作 |
| **角色状态丢失** | private memory list | agent 重启后能恢复之前的任务进度 |
| **审计缺乏溯源** | trace_ref 绑定 | 每条记忆都能反查到 run_id / step_id / command_id |

<a id="section-5-7"></a>
## 5.7 缺点与风险

| 缺点 | 风险等级 | 缓解措施 |
|---|---|---|
| **进程内语义索引,重启丢失** | 中 | 关键记忆通过 Redis 持久化,语义索引可重建;LONG_TERM/PERMANENT 级别已通过 MySQL 落盘保护 |
| **Redis 重启丢失短期记忆** | 中 | Redis 配置 AOF/RDB 持久化;LONG_TERM/PERMANENT 可通过 `restore_from_persistence()` 从 MySQL 恢复 |
| **MySQL 持久化 fire-and-forget 丢数据** | 中 | 落盘失败仅写 warning 日志不中断主流程,但存在丢失窗口;`flush_to_persistence()` 提供定期批量同步作为补充 |
| **EPHEMERAL 24h TTL 对长任务不友好** | 低 | 长时间运行的任务可能在工作态记忆过期前未完成;缓解：任务完成后的记忆会升级为 SHORT_TERM/LONG_TERM,不受 EPHEMERAL 窗口限制 |
| **记忆噪音污染规划** | 高 | confidence policy 只沉淀高置信结论,Skill 置信度动态衰减 |
| **记忆串读风险** | 高 | `memory_cross_talk_rate = 0%` 硬约束,私有记忆隔离 |
| **Redis List 无限增长** | 中 | TTL 分级自动清理过期条目(`cleanup_expired()`),限制 List 长度(`max_list_len=2000`) |
| **语义索引精度有限** | 中 | 进程内索引不如专业向量库,但降低部署复杂度 |
| **记忆写入延迟** | 低 | Redis 写入快,但网络抖动可能影响主链 |

**关键风险**：
- **记忆噪音**：低质量经验污染规划,导致决策退化。缓解：confidence policy + 动态衰减
- **记忆串读**：私有记忆被非所属 agent 读取。缓解：`memory_cross_talk_rate = 0%` 硬约束
- **持久化链路断裂**：MySQL 不可用时 LONG_TERM/PERMANENT 记忆无法落盘,Redis 重启后永久丢失。缓解：`flush_to_persistence()` 定期批量同步 + 监控 MySQL 健康状态
- **TTL 边界竞争**：EPHEMERAL (24h) 记忆在任务运行中过期被清理,导致 execution trace 不完整。缓解：任务运行中的记忆通过 `run_id` 关联,清理时跳过运行中任务

<a id="section-5-8"></a>
## 5.8 关键代码出处

| 组件 | 文件 | 方法/类 |
|---|---|---|
| 统一门面 | [memory_store.py](../src/riskagent_backend/memory/memory_store.py) | `MemoryStore` |
| Redis 后端 | [redis_backend.py](../src/riskagent_backend/memory/redis_backend.py) | `RedisBackend` |
| 语义索引 | [semantic_indexer.py](../src/riskagent_backend/memory/semantic_indexer.py) | `SemanticIndexer` |
| TTL 分级策略 | [ttl_policy.py](../src/riskagent_backend/memory/ttl_policy.py) | `TTLPolicyEngine`, `TTLTier` |
| MySQL 持久化 | [persistence_backend.py](../src/riskagent_backend/memory/persistence_backend.py) | `PersistenceBackend` |
| 记忆写入编排 | [memory_operations.py](../src/riskagent_backend/memory/memory_operations.py) | 记忆写入逻辑 |
| 记忆 schema | [memory_entry.py](../src/riskagent_backend/contracts/memory_entry.py) | `MemoryEntry` |
| planning 链接入 | [proactive_workflow.py](../src/riskagent_backend/orchestration/proactive_workflow.py) | `retrieve_for_planning()` |
| execution 链接入 | [task_graph_executor.py](../src/riskagent_backend/orchestration/task_graph_executor.py) | `record_working_memory()` |
| finalize 链接入 | [workflow_memory.py](../src/riskagent_backend/orchestration/workflow_memory.py) | `persist_run_artifacts()` |
| resume 链接入 | [workflow_resume.py](../src/riskagent_backend/orchestration/workflow_resume.py) | `build_resume_payload()` |

<a id="section-6"></a>
# 6. Skill 自创闭环生命周期

Skill 系统实现从执行经验中自动创建、复用、改进 Skill 的闭环。相似任务不再重复推理,直接复用历史 Skill,预计减少 30%+ 的重复规划开销。

<a id="section-6-1"></a>
## 6.1 总体架构

```
[高质量 run 完成]
    |
    v
[CriticAgent 评审]
    | ok=True 且 confidence >= 0.85
    v
[SkillProposer]                    # 创建/更新 Skill
    | 提取可复用模式
    | find_similar() 语义去重
    | 创建新 Skill 或更新已有 Skill
    v
[SkillStore]                       # 存储
    | 内存 dict[skill_id, skill]
    | Chroma 向量库 (riskagent-skills collection, 1024维 embedding, BAAI/bge-m3)
    | MySQL 持久化 (异步, 含 summary 列)
    v
[planning 阶段]
    |
    v
[SkillInjector]                    # 检索与注入
    | _build_query() 提取查询文本
    | _rewrite_query() LLM 改写为检索导向 query (LRU 缓存 + fallback)
    | search(rewritten_query) → 向量检索(Chroma ANN) + BM25 加权合并 (α=0.7)
    | 过滤 status=active, confidence>=0.3
    | 注入 summary 列表到 orchestrator prompt (轻量注入)
    v
[OrchestratorAgent 规划 + ReAct 循环]
    | 参考 summary 列表
    | 需要详细 Skill 时调用 skill_view(skill_id) 按需加载
    | 参考 Skill 的 steps 和 failure_boundary
    v
[TaskGraphExecutor 执行]
    |
    v
[SkillUsageTracker]                # 使用跟踪
    | 记录使用结果 (success/failure)
    | update_confidence() 更新置信度
    v
[CriticAgent 评审]
    | ok=False 或有 issues
    v
[SkillReviser]                     # 修订
    | 提取失败原因
    | 生成修订后的 steps
    | 追加到 revision_history
    v
[置信度衰减]
    | confidence < 0.3 → deprecated
    | confidence < 0.15 → archived
```

**关键设计**：
- **闭环自创**：从高质量 run 自动提取,不依赖人工编写
- **语义去重**：find_similar() 防止重复 Skill
- **置信度驱动**：成功提升,失败降低,自动降级归档
- **异常隔离**：Skill 系统失败不影响主流程

<a id="section-6-2"></a>
## 6.2 数据结构：skill.v1

所有 Skill 都符合统一 schema([skill_contract.py](../src/riskagent_backend/skills/skill_contract.py))：

```json
{
  "schema_version": "skill.v1",
  "skill_id": "skill_a1b2c3d4e5f6",
  "name": "监控交易台敞口和系统状态",
  "summary": "当交易台敞口超限或系统健康指标异常时，自动获取敞口数据并定位 breach 原因",
  "tags": ["monitoring", "risk", "delta_one"],
  "applicable_conditions": [
    "任务涉及交易台敞口监控",
    "需要检查系统健康状态"
  ],
  "steps": [
    {
      "description": "获取交易台敞口数据",
      "expected_outcome": "返回当前敞口和限额使用情况"
    },
    {
      "description": "检查系统健康状态",
      "expected_outcome": "返回服务健康指标"
    },
    {
      "description": "分析 breach 原因",
      "expected_outcome": "定位超限原因并给出建议"
    }
  ],
  "failure_boundary": "如果敞口数据获取失败,直接返回错误,不继续执行",
  "confidence": 0.92,
  "write_origin": "auto",
  "status": "active",
  "created_at": 1710000000000,
  "updated_at": 1710000000000,
  "usage_count": 15,
  "success_rate": 0.93,
  "revision_history": [
    {
      "action": "updated",
      "run_id": "run_proactive_001",
      "reason": "similar_skill_found"
    }
  ],
  "source_run_id": "run_proactive_001",
  "source_agent_id": "orchestrator"
}
```

**关键设计**：
- **skill_id 不可变**：生成后不变,用于 trace 回溯
- **steps 结构化**：每个 step 有 description 和 expected_outcome
- **failure_boundary 明确**：定义失败时的处理策略
- **revision_history 可追溯**：每次修订追加历史记录
- **source_run_id/source_agent_id**：溯源到创建时的 run 和 agent

<a id="section-6-3"></a>
## 6.3 Skill 存储位置

**三层存储**：

| 层 | 存储 | 作用 | 持久化 |
|---|---|---|---|
| **内存** | `dict[skill_id, skill]` | 运行时快速读写 | 重启丢失 |
| **向量库** | Chroma `riskagent-skills` collection (1024维, BAAI/bge-m3) | 语义向量检索 (ANN) | 重启不丢失 |
| **MySQL** | `skill_store` 表 (含 `summary` 列) | 永久持久化 | 重启不丢失 |

> **注意**：Chroma 向量检索需构造 `SkillStore(llm_client=..., chroma_store=...)` 注入方生效；当前主链（proactive_workflow.py）以无参 `SkillStore()` 构造，`_chroma_enabled` 恒为 False，Hybrid 检索的向量分数实际来自进程内 `SemanticIndexer`（词袋模型，128 维）。该缺口已登记于 docs/KNOWN_ISSUES.md（KI-002）。

**Redis 不存储 Skill**：与记忆模块不同,Skill 不用 Redis,直接走 MySQL 持久化。

**Phase 11 升级（RFC-005 Implemented）**：
- 向量库从进程内 `SemanticIndexer`（词袋模型,128 维）升级为 Chroma `riskagent-skills` collection（远程 embedding：初期为 OpenAI 系 embedding 模型，2026-08 切换为硅基流动 BAAI/bge-m3/1024 维）
- MySQL `skill_store` 表新增 `summary` 列,存储 LLM 生成的一句话摘要
- Embedding 基于 `summary` 字段生成（而非全字段拼接）,提升语义密度
- 检索采用 Hybrid 模式：向量 ANN 检索 + BM25 关键词加权合并 (α=0.7)

**关键设计**：
- **异步落盘**：create/update 后 fire-and-forget 到 MySQL,不阻塞主流程
- **启动恢复**：`restore_from_persistence()` 从 MySQL 加载到内存 + 重建 Chroma 向量索引
- **批量落盘**：`flush_to_persistence()` 批量同步所有 Skill

<a id="section-6-4"></a>
## 6.4 创建：SkillProposer

**触发时机**：CriticAgent 评审之后,ok=True 且 confidence >= 0.85

**流程**([skill_proposer.py](../src/riskagent_backend/skills/skill_proposer.py))：

```python
async def propose(self, *, run_id, task, critic_final, orchestrator_output, receipts):
    # 1. 检查 confidence 和 ok
    if not ok or confidence < 0.85:
        return {"action": "skipped", ...}
    
    # 3. 提取可复用模式
    skill_data = self._extract_skill_pattern(...)
    
    # 4. 语义去重
    similar = await self._store.find_similar(skill_data, threshold=0.85)
    
    if similar:
        # 5. 更新已有 Skill
        updated = await self._store.update(skill_id, patch)
        return {"action": "updated", ...}
    else:
        # 6. 创建新 Skill
        created = await self._store.create(skill_data)
        return {"action": "created", ...}
```

**关键设计**：
- **阈值过滤**：只有高质量 run 才触发 Skill 创建
- **语义去重**：find_similar() 防止重复 Skill
- **更新优先**：相似 Skill 存在时更新,不创建新 Skill
- **revision_history**：更新时追加修订历史

<a id="section-6-5"></a>
## 6.5 检索与注入：SkillInjector

**触发时机**：planning 阶段,OrchestratorAgent 规划之前

**流程**([skill_injector.py](../src/riskagent_backend/skills/skill_injector.py))：

```python
async def retrieve_applicable_skills(self, *, task, intent, skill_enabled=True):
    # 1. 如果 skill_enabled=False, 返回空
    if not skill_enabled:
        return {"skill_enabled": False, ...}
    
    # 3. 提取查询文本
    query = self._build_query(task=task, intent=intent)
    
    # 4. Query Rewriting（LLM 改写为检索导向 query, LRU 缓存 + fallback）
    rewritten_query = await self._rewrite_query(query)
    
    # 5. Hybrid 检索（向量 ANN + BM25 加权合并, α=0.7）
    hits = await self._store.search(rewritten_query, limit=3, min_confidence=0.3)
    
    # 6. 构建 summary 列表注入（轻量注入, name + summary）
    skills = [self._build_injection_item(hit) for hit in hits]
    
    # 7. 治理过滤
    if self._governor:
        skills = await self._governor.enforce_injection_limits(skills)
    
    return {"skill_enabled": True, "skills": skills, ...}
```

**注入到 prompt 的格式**：

```
## Applicable Skills (from historical experience)

### Skill 1: 监控交易台敞口和系统状态
- **Applicable Conditions**: 任务涉及交易台敞口监控, 需要检查系统健康状态
- **Steps**:
  1. 获取交易台敞口数据 → 返回当前敞口和限额使用情况
  2. 检查系统健康状态 → 返回服务健康指标
  3. 分析 breach 原因 → 定位超限原因并给出建议
- **Failure Boundary**: 如果敞口数据获取失败,直接返回错误,不继续执行
- **Confidence**: 0.92
```

**Phase 11 升级（RFC-005 Implemented）**：
- **Query Rewriting**：`_rewrite_query()` 调用 LLM 将短 query 扩展为检索导向 query, LRU 缓存（256 条）避免重复调用, 超时/fallback 到原始 query
- **Hybrid 检索**：向量 ANN 检索（Chroma, 当前 1024 维 BAAI/bge-m3）+ BM25 关键词检索（`_keyword_fallback_search`）加权合并, α=0.7, 分数归一化。**实际现状**：主链 `SkillStore()` 无参构造，`_chroma_enabled=False`，向量通道未启用，Hybrid 中的“向量分数”实际来自进程内 `SemanticIndexer`（词袋模型，128 维）+ BM25（见 KI-002）
- **轻量注入**：plan 前只注入 summary 列表（name + summary, 约 0.5-1K tokens）, LLM 需要详情时调用 `skill_view` 工具按需加载
- **Fallback 降级**：embedding 供应商不可用（如硅基流动服务异常或 key 失效）时, embedding 调用失败, 降级为纯 BM25 关键词检索, 不阻断链路。**注**：当前主链 `_chroma_enabled=False`，embedding 从未被调用，实际始终为 SemanticIndexer + BM25（见 KI-002）

**关键设计**：
- **max_skills=3**：防止 prompt 膨胀
- **min_confidence=0.3**：过滤低置信度 Skill
- **Hybrid 检索**：向量 + BM25 加权合并替代纯语义检索, 提升召回稳定性
- **skill_view 工具**：Orchestrator 按需调用, 从一次性全量注入 → summary 列表 + 按需加载
- **治理过滤**：SkillGovernor 控制 token 预算

<a id="section-6-6"></a>
## 6.6 使用与置信度更新：SkillUsageTracker

**触发时机**：Skill 被使用后,根据执行结果更新置信度

**流程**([skill_usage_tracker.py](../src/riskagent_backend/skills/skill_usage_tracker.py))：

```python
async def record_usage(self, *, skill_id, success):
    # 更新置信度
    updated = await self._store.update_confidence(skill_id, success, delta=0.05)
    
    # 成功: confidence = min(1.0, confidence + 0.05)
    # 失败: confidence = max(0.0, confidence - 0.05)
    
    # 自动降级
    if confidence < 0.15:
        status = "archived"
    elif confidence < 0.3:
        status = "deprecated"
```

**关键设计**：
- **delta=0.05**：每次使用置信度变化 5%
- **success_rate 计算**：基于 usage_count 和成功次数
- **自动降级**：置信度低于阈值自动改变 status

<a id="section-6-7"></a>
## 6.7 修订：SkillReviser

**触发时机**：Skill 被使用但产生次优结果(critic ok=False 或有 issues)

**流程**([skill_reviser.py](../src/riskagent_backend/skills/skill_reviser.py))：

```python
async def check_and_propose_revision(self, *, skill_id, run_id, execution_result, critic_final):
    # 1. 检查触发条件
    if ok and not has_issues:
        return None  # 不修订
    
    # 3. 提取失败原因
    failure_reason = self._extract_failure_reason(critic_final)
    
    # 4. 生成修订后的 steps
    revised_steps = self._generate_revised_steps(...)
    
    # 5. 生成修订提案
    proposal = RevisionProposal(
        skill_id=skill_id,
        revision_id=f"rev_{uuid}",
        reason=failure_reason,
        original_steps=original_steps,
        revised_steps=revised_steps,
        proposed_by="critic" or "auto",
    )
    
    # 6. 更新 Skill (追加 revision_history)
    patch = {
        "steps": revised_steps,
        "failure_boundary": revised_failure_boundary,
        "revision_history": existing_revisions + [revision_entry],
    }
    updated = await self._store.update(skill_id, patch)
```

**关键设计**：
- **可选修订**：不强制每次失败都修订
- **revision_history 可回滚**：每次修订追加历史记录
- **proposed_by**：区分 critic 触发还是 auto 触发

<a id="section-6-8"></a>
## 6.8 降级与归档

**置信度衰减策略**：

| 置信度范围 | status | 含义 |
|---|---|---|
| >= 0.3 | `active` | 正常可用 |
| 0.15 - 0.3 | `deprecated` | 不推荐,但仍可检索到 |
| < 0.15 | `archived` | 归档,检索时过滤掉 |

**检索过滤**：
- `search()` 只返回 `status=active` 且 `confidence >= min_confidence` 的 Skill
- `find_similar()` 不排除任何 status(包括 deprecated/archived),用于去重

**关键设计**：
- **自动降级**：置信度低于阈值自动改变 status
- **软删除**：archived 不是物理删除,可从 MySQL 恢复
- **检索隔离**：deprecated/archived 不影响正常检索

<a id="section-6-9"></a>
## 6.9 Skill 能解决什么问题

| 问题 | Skill 机制 | 效果 |
|---|---|---|
| **相似任务重复推理** | SkillProposer 自动创建,SkillInjector 检索注入 | 减少 30%+ 重复规划开销 |
| **规划缺乏历史参考** | few-shot 注入 steps 和 failure_boundary | orchestrator 参考历史最佳实践 |
| **失败经验无法沉淀** | SkillReviser 修订,revision_history 记录 | 系统越用越好,组织智慧积累 |
| **低质量 Skill 污染** | confidence 动态衰减,自动降级归档 | few_shot_reuse_rate > 30% |
| **Skill 重复创建** | find_similar() 语义去重 | 相似 Skill 合并更新 |
| **prompt 膨胀** | max_skills=3, SkillGovernor token 预算 | 控制注入数量 |

<a id="section-6-10"></a>
## 6.10 缺点与风险

| 缺点 | 风险等级 | 缓解措施 |
|---|---|---|
| **内存存储,重启丢失** | 中 | MySQL 异步持久化,启动时 restore_from_persistence() |
| **语义索引仅作 fallback** | 低 | Phase 11 后主检索链路为 Chroma ANN + BM25 Hybrid；进程内 SemanticIndexer 仅在 Chroma 未注入/不可用时作为降级路径保留（记忆系统仍独立使用它） |
| **Skill 噪音污染** | 高 | confidence policy + 自动降级 + SkillGovernor 过滤 |
| **异步落盘失败** | 低 | fire-and-forget 可能丢失,但影响小(可重新创建) |
| **修订质量不可控** | 中 | SkillReviser 基于 critic issues,但 LLM 生成的修订可能不准确 |
| **检索不稳定** | 中 | 关键词兜底补全,防止语义检索失败 |
| **Skill 爆炸** | 低 | max_skills=3 限制注入数量,semantic 去重防止重复 |

**关键风险**：
- **Skill 噪音**：低质量 Skill 污染规划。缓解：confidence policy + 自动降级 + SkillGovernor
- **异步落盘**：fire-and-forget 可能丢失。缓解：批量 flush_to_persistence() 定期同步
- **修订质量**：LLM 生成的修订可能不准确。缓解：revision_history 可回滚

<a id="section-6-11"></a>
## 6.11 关键代码出处

| 组件 | 文件 | 方法/类 |
|---|---|---|
| Skill 契约 | [skill_contract.py](../src/riskagent_backend/skills/skill_contract.py) | `Skill` / `validate_skill()` |
| Skill 存储 | [skill_store.py](../src/riskagent_backend/skills/skill_store.py) | `SkillStore` |
| Skill 创建 | [skill_proposer.py](../src/riskagent_backend/skills/skill_proposer.py) | `SkillProposer.propose()` |
| Skill 检索注入 | [skill_injector.py](../src/riskagent_backend/skills/skill_injector.py) | `SkillInjector.retrieve_applicable_skills()` |
| Skill 使用跟踪 | [skill_usage_tracker.py](../src/riskagent_backend/skills/skill_usage_tracker.py) | `SkillUsageTracker.record_usage()` |
| Skill 修订 | [skill_reviser.py](../src/riskagent_backend/skills/skill_reviser.py) | `SkillReviser.check_and_propose_revision()` |
| Skill 治理 | [skill_governor.py](../src/riskagent_backend/skills/skill_governor.py) | `SkillGovernor.enforce_injection_limits()` |
| workflow 接入 | [proactive_workflow.py](../src/riskagent_backend/orchestration/proactive_workflow.py) | `SkillStore` / `SkillInjector` / `SkillProposer` / `SkillReviser` 初始化 |

<a id="section-7"></a>
# 7. MCP 工具调用与治理

本系统通过 MCP（Model Context Protocol）对外暴露工具能力，所有 Agent 的工具调用统一经过 **ToolRegistry → ToolExecutor** 主路径，不形成旁路。

<a id="section-7-1"></a>
## 7.1 协议与传输层

**协议**：采用 [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) 标准，通过 `mcp.server.FastMCP` 实现。

**传输模式**（[main.py](../main.py)）：

| 模式 | 环境变量 `MCP_TRANSPORT` | 适用场景 |
|---|---|---|
| **stdio** | `stdio`（默认开发环境） | 本地开发、CLI 客户端 |
| **streamable-http** | `streamable-http`（生产环境默认） | K8s 部署、HTTP 客户端 |
| **sse** | `sse` + `MCP_MOUNT_PATH` | 兼容旧版 SSE 客户端 |

**传输选择逻辑**（[main.py:62-89](../main.py)）：

```python
transport = os.getenv("MCP_TRANSPORT")
if transport is None or not transport.strip():
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env == "production":
        transport = "streamable-http"
    else:
        transport = "stdio"
```

**关键设计**：
- **协议标准化**：所有工具遵循 MCP 协议，外部客户端（如 Claude Desktop、Cursor）可直接连接
- **传输可切换**：同一套工具代码，开发用 stdio，生产用 streamable-http
- **FastMCP 封装**：基于 `mcp.server.FastMCP`，自动处理 JSON-RPC、序列化、路由

<a id="section-7-2"></a>
## 7.2 MCP 部署位置

**MCP Server 作为独立 Pod 部署在 K8s 集群内**：

```text
┌─────────────────────────────────────────┐
│  K8s Cluster                            │
│                                         │
│  ┌─────────────┐    ┌────────────────┐  │
│  │ MCP Server  │───>│ MySQL 8.0      │  │
│  │ (port 8000) │───>│ Redis 7        │  │
│  │             │───>│ ChromaDB       │  │
│  └──────┬──────┘    └────────────────┘  │
│         │ ClusterIP                      │
│         │ :8000                          │
│  ┌──────┴──────┐                        │
│  │ MCP Service │                        │
│  └─────────────┘                        │
│         │                                │
│  ┌──────┴──────┐                        │
│  │ 外部客户端   │  (Claude Desktop /     │
│  │             │   Cursor / HTTP)        │
│  └─────────────┘                        │
└─────────────────────────────────────────┘
```

**K8s 资源**（[mcp-server-deployment.yaml](../deploy/k8s/templates/mcp-server-deployment.yaml)）：
- Deployment: `mcp-server`, replicas 可配
- Service: `mcp-server`, ClusterIP:8000
- initContainers: 等待 MySQL / Redis / ChromaDB 就绪后再启动
- 资源限制: requests 500m/512Mi, limits 1500m/1.5Gi

**关键设计**：
- **MCP Server 是唯一的工具入口**：所有工具调用都通过 MCP Server 进入，不存在绕过路径
- **依赖就绪检查**：initContainers 确保数据库连接可用后才启动服务
- **健康探针**：livenessProbe 和 readinessProbe 都走 `/health`（无认证），`/ready` 有认证不适合探针

<a id="section-7-3"></a>
## 7.3 鉴权机制

**两层鉴权**：

### 第一层：HTTP Bearer Token（外部访问）

[auth_service.py](../src/riskagent_backend/services/auth_service.py) 实现基于 Bearer Token 的最小鉴权：

```python
def is_authorized(headers: Mapping[str, Any]) -> bool:
    expected = os.getenv("RISKAGENT_API_TOKEN")
    if expected is None:
        return True  # 未配置 token 则跳过鉴权（开发环境）
    auth = headers.get("authorization") or headers.get("Authorization")
    token = _extract_bearer(str(auth) if auth is not None else None)
    return token == expected
```

**鉴权覆盖范围**：
- `/ready` 端点：需要 Bearer Token
- `/metrics` 端点：需要 Bearer Token
- `/health` 端点：**无认证**（K8s 探针需要）
- MCP 工具调用：从 `Context` 中提取 HTTP headers 进行鉴权

### 第二层：RBAC 角色权限（内部执行）

[tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) 在执行工具前进行 RBAC 校验：

```python
def _is_allowed_by_role(*, meta: ToolMeta, target_agent: str) -> bool:
    if target_agent in ("system_engineer", "risk_analyst"):
        return meta.capability == "read_only"  # 只能调用只读工具
    if target_agent == "manager":
        return meta.capability in ("read_only", "side_effect")  # 可以调用副作用工具
    return False
```

**关键设计**：
- **外部鉴权极简**：单 Bearer Token，不引入 OAuth/OIDC 复杂度
- **内部 RBAC 严格**：角色决定可调用工具类型，read_only vs side_effect 严格隔离
- **Context 提取**：MCP 工具调用时从 FastMCP Context 中提取 HTTP headers，复用同一套鉴权逻辑

<a id="section-7-4"></a>
## 7.4 工具注册与角色区分

### ToolRegistry：工具元数据注册表

[tool_registry.py](../src/riskagent_backend/orchestration/tool_registry.py) 维护全局工具元数据：

```python
@dataclass(frozen=True)
class ToolMeta:
    action: str                    # 工具名称
    capability: ToolCapability     # read_only | side_effect | pii | admin
    owner: str                     # 所属角色
    description: str               # 工具描述
    risk_level: str                # low | medium | high | critical
    default_timeout_ms: int        # 默认超时
    allowed_targets: Optional[tuple[str, ...]] = None  # 允许调用的角色列表
    side_effect_policy: Optional[SideEffectPolicy] = None  # 副作用策略
```

**已注册工具清单**：

| 工具 | capability | owner | risk_level | allowed_targets |
|---|---|---|---|---|
| `query_all_positions` | read_only | risk_analyst | low | — |
| `query_positions_by_trader` | read_only | risk_analyst | low | — |
| `query_positions_by_desk` | read_only | risk_analyst | low | risk_analyst |
| `calculate_total_delta` | read_only | risk_analyst | low | — |
| `monitor_desk_exposure` | read_only | risk_analyst | low | — |
| `search_similar_alerts` | read_only | risk_analyst | low | risk_analyst |
| `get_service_metrics` | read_only | system_engineer | low | — |
| `collect_metrics` | read_only | system_engineer | low | system_engineer |
| `mysql_health` | read_only | system_engineer | low | system_engineer |
| `chroma_health` | read_only | system_engineer | low | system_engineer |
| `kafka_lag` | read_only | system_engineer | low | system_engineer |
| `submit_alerts` | **side_effect** | **manager** | **high** | — |
| `write_alert` | **side_effect** | **manager** | **high** | manager |
| `skill_view` | read_only | orchestrator | low | orchestrator |

### tool_executor.py：角色隔离的执行白名单

[tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) 维护四个角色白名单：

```python
_ENGINEER_ALLOWLIST = {
    "collect_metrics", "get_service_metrics", "mysql_health",
    "chroma_health", "kafka_lag",
}

_ANALYST_ALLOWLIST = {
    "query_all_positions", "query_positions_by_trader",
    "calculate_total_delta", "monitor_desk_exposure",
    "search_similar_alerts", "query_positions_by_desk",
}

_MANAGER_ALLOWLIST = {
    "write_alert", "submit_alerts",
}

_ORCHESTRATOR_ALLOWLIST = {
    "skill_view",
}
```

**角色区分逻辑**：
1. `target_agent` 决定使用哪个 allowlist（system_engineer / risk_analyst / manager / orchestrator 四分支）
2. allowlist 查找 handler，找不到则返回 `handler_missing`
3. 即使工具在 `_TOOL_REGISTRY` 中注册，不在角色 allowlist 中也无法执行

**关键设计**：
- **双重隔离**：ToolMeta.allowed_targets + ToolExecutor allowlist，两层校验
- **副作用工具仅 manager**：`submit_alerts` 和 `write_alert` 只有 manager 角色可调用
- **owner 字段**：每个工具声明所属角色，用于 MCP 层路由

<a id="section-7-5"></a>
## 7.5 Agent 如何知道可用工具

Agent 通过 **TieredPromptBuilder 的 tools_index** 获知可用工具：

[tiered_prompt_builder.py](../src/riskagent_backend/prompts/tiered_prompt_builder.py) 在构建 system prompt 的稳定层时注入工具索引：

```python
def build_stable_tier(self, *, agent_role, tools_index, behavior_rules):
    lines = []
    lines.append(f"[Agent Role]\n{agent_role}")
    lines.append(f"\n[Tools Index]\n{json.dumps(tools_index, ensure_ascii=False, indent=2)}")
    lines.append(f"\n[Behavior Rules]\n{rules_text}")
    ...
```

**tools_index 的内容**：每个工具的 `{action, description, capability, risk_level}` 摘要，Agent 据此知道有哪些工具可调用。

**注入位置**：稳定层（stable tier）是 system prompt 的第一层，版本号固定，可缓存。Agent 在每次 LLM 调用时都能看到工具列表。

**MCP 层面**：外部客户端通过 MCP 协议的 `tools/list` 方法获取可用工具列表，FastMCP 自动从 `mcp.tool()` 注册中生成。

**关键设计**：
- **内部 Agent**：通过 prompt 中的 tools_index 感知工具，由 TieredPromptBuilder 注入
- **外部客户端**：通过 MCP 协议 `tools/list` 发现工具，FastMCP 自动暴露
- **稳定层缓存**：tools_index 放在 stable tier，版本不变则缓存命中，减少 token 消耗

<a id="section-7-6"></a>
## 7.6 工具调用全流程

```text
[外部客户端 / Agent]
    |
    | MCP tools/call 或 TaskGraph tool_call 节点
    v
[mcp_tools._execute_mcp_tool()]
    | 1. 从 Context 提取 headers → is_authorized() 鉴权
    | 2. get_tool_meta(action) → 查注册表
    | 3. new_agent_command() → 构造标准化命令
    v
[tool_executor.execute_agent_command()]
    | 4. validate_agent_command() → schema 校验
    | 5. get_tool_meta() → 工具是否存在
    | 6. _is_allowed_by_role() → RBAC 角色校验
    | 7. _is_allowed_by_meta() → allowed_targets 校验
    | 8. SideEffectPolicy → 审批/理由/严重度检查
    | 9. _reserve_budget() → 预算检查
    | 10. allowlist[target] → handler 查找
    | 11. _execute_handler_with_timeout() → 超时执行
    v
[ToolResult]
    | ok / output / evidence / artifacts / error / latency_ms
    v
[_build_receipt()]
    | 构造 agent_receipt.v1 回执
    | 包含 approval_state / approval_trace / failure_classification
    v
[返回给调用方]
    | MCP: 返回 JSON 结果
    | TaskGraph: 节点输出传递给下游
```

**关键设计**：
- **统一入口**：无论 MCP 外部调用还是 TaskGraph 内部调用，都走 `execute_agent_command()` 主路径
- **回执标准化**：所有工具执行返回 `agent_receipt.v1`，包含完整的审计信息
- **失败分类**：`failure_classification` 将错误分为 permission/validation/timeout/dependency/runtime，用于重试决策

<a id="section-7-7"></a>
## 7.7 五道治理关卡

参考 [ADR-004](decisions/ADR-004-tool-governance.md)，工具调用必须通过五道关卡：

| 关卡 | 检查内容 | 拒绝条件 | 代码位置 |
|---|---|---|---|
| **1. RBAC** | 角色是否有权调用该工具 | `rbac_denied` / `role_not_allowed` | `_is_allowed_by_role()` / `_is_allowed_by_meta()` |
| **2. 预算** | run 级 tool_call/side_effect 预算 | `tool_budget_exceeded` / `side_effect_budget_exceeded` | `_reserve_budget()` |
| **3. 审批** | side_effect 工具需要显式审批 | `approval_required` / `approval_rejected` / `approval_expired` | `_is_approved()` / `_approval_state_from_params()` |
| **4. 超时** | 工具执行超时 | `tool_timeout` | `_execute_handler_with_timeout()` |
| **5. 收据** | 执行结果标准化记录 | — | `_build_receipt()` |

**审批状态机**：

```text
[not_required]  ← read_only 工具
[pending]       ← side_effect 工具，等待审批
  → [approved]  ← 审批通过
    → [resumed] ← 执行完成
  → [rejected]  ← 审批拒绝
  → [expired]   ← 审批过期
```

**关键设计**：
- **零信任**：每道关卡独立校验，前一道失败不进入下一道
- **审批可追溯**：`approval_trace` 记录完整的状态转换历史
- **预算隔离**：`tool_call_limit` 和 `side_effect_limit` 分别计数，防止 side_effect 工具消耗过多预算

<a id="section-7-8"></a>
## 7.8 MCP Resources 与 Prompts

除工具外，MCP Server 还暴露 **Resources** 和 **Prompts**：

### Resources（[mcp_resources.py](../src/riskagent_backend/resources/mcp_resources.py)）

| URI | 名称 | 描述 |
|---|---|---|
| `risk://metadata/desks` | desks | 交易台列表与元数据 |
| `risk://limits/global` | global_limits | 全局风控限额 |
| `market://snapshot/latest` | market_snapshot_latest | 最新行情快照 |

### Prompts（[mcp_prompts.py](../src/riskagent_backend/prompts/mcp_prompts.py)）

| 名称 | 描述 |
|---|---|
| `analyze-risk-breach` | 风控告警分析模板（根因、影响、处置建议、下一步动作） |

**关键设计**：
- **Resources 提供上下文**：客户端可通过 MCP 协议读取交易台、限额、行情等参考数据
- **Prompts 提供模板**：标准化风控分析流程，减少重复 prompt 编写

<a id="section-7-9"></a>
## 7.9 关键代码出处

| 组件 | 文件 | 方法/类 |
|---|---|---|
| MCP 服务启动 | [server.py](../src/riskagent_backend/server.py) | `mcp = FastMCP(...)` |
| 传输模式选择 | [main.py](../main.py) | `main()` |
| 工具注册（MCP 层） | [mcp_tools.py](../src/riskagent_backend/tools/mcp_tools.py) | `register_tools()` |
| 工具执行（MCP 层） | [mcp_tools.py](../src/riskagent_backend/tools/mcp_tools.py) | `_execute_mcp_tool()` |
| 工具注册表 | [tool_registry.py](../src/riskagent_backend/orchestration/tool_registry.py) | `ToolMeta` / `_TOOL_REGISTRY` |
| 工具执行（核心） | [tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) | `execute_agent_command()` |
| 角色白名单 | [tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) | `_ENGINEER_ALLOWLIST` / `_ANALYST_ALLOWLIST` / `_MANAGER_ALLOWLIST` |
| RBAC 校验 | [tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) | `_is_allowed_by_role()` / `_is_allowed_by_meta()` |
| 审批状态机 | [tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) | `_build_approval_trace()` |
| 预算检查 | [tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) | `_reserve_budget()` |
| 超时执行 | [tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) | `_execute_handler_with_timeout()` |
| 回执构造 | [tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) | `_build_receipt()` |
| HTTP 鉴权 | [auth_service.py](../src/riskagent_backend/services/auth_service.py) | `is_authorized()` |
| Context headers 提取 | [auth_service.py](../src/riskagent_backend/services/auth_service.py) | `get_headers_from_ctx()` |
| 工具索引注入 | [tiered_prompt_builder.py](../src/riskagent_backend/prompts/tiered_prompt_builder.py) | `build_stable_tier(tools_index=...)` |
| 节点工具调用 | [node_executors.py](../src/riskagent_backend/orchestration/node_executors.py) | `NodeExecutor._execute_tool_call_node()` |
| MCP Resources | [mcp_resources.py](../src/riskagent_backend/resources/mcp_resources.py) | `register_resources()` |
| MCP Prompts | [mcp_prompts.py](../src/riskagent_backend/prompts/mcp_prompts.py) | `register_prompts()` |
| K8s 部署 | [mcp-server-deployment.yaml](../deploy/k8s/templates/mcp-server-deployment.yaml) | Deployment + Service |
| 错误响应 | [errors.py](../src/riskagent_backend/tools/errors.py) | `error_payload()` |
| 治理决策 | [ADR-004](decisions/ADR-004-tool-governance.md) | 零信任工具治理体系 |

<a id="section-8"></a>
# 8. 5min 主动监控全流程

本系统通过 `BaseProactiveAgent` 的后台监控循环实现 5min 主动感知、自主分析、自主行动能力。主动行为不旁路执行，全部接入统一执行内核。

<a id="section-8-1"></a>
## 8.1 启动与停止

**启动**（[base.py](../src/riskagent_backend/proactive_agents/base.py) ）：

```python
async def start_background_monitor(self) -> None:
    if self._monitor_task is not None:
        return  # 防止重复启动
    self._is_running = True
    self._monitor_task = asyncio.create_task(self._monitor_loop())
```

**停止**（[base.py](../src/riskagent_backend/proactive_agents/base.py) ）：

```python
async def stop_background_monitor(self) -> None:
    self._is_running = False
    self._monitor_task.cancel()
    await self._monitor_task  # 等待优雅退出
```

**关键设计**：
- 使用 `asyncio.Task` 实现真正的后台并发，不阻塞主 workflow
- `is_running` 标志位控制循环退出，支持优雅停止
- 构造函数里 `enable_background_monitor=True` 时自动初始化愿望（`_init_desires()`）

<a id="section-8-2"></a>
## 8.2 监控循环

**核心循环**（[base.py](../src/riskagent_backend/proactive_agents/base.py)）：

```python
async def _monitor_loop(self):
    """后台监控循环 —— BDI 的 Perceive → Deliberate → Act"""
    while self._is_running:
        await self._perceive_environment()   # ① 感知环境，更新信念
        await self._deliberate()             # ② 思考，形成意图
        await self._act()                    # ③ 行动，执行意图
        await asyncio.sleep(self._monitor_interval)  # 默认 60 秒
```

**关键设计**：
- 每次循环都完整走 BDI 三阶段，不是只感知不行动
- `monitor_interval_seconds` 可配置（默认 60 秒），防止过于频繁
- 任何阶段异常不会中断循环（各阶段内部有 try-except）

<a id="section-8-3"></a>
## 8.3 感知层：数据源采集与过滤

**数据采集**（[base.py](../src/riskagent_backend/proactive_agents/base.py)）：

```python
async def _collect_and_filter(self, data_sources: list) -> list:
    all_signals = []
    for ds in data_sources:
        signals = ds.collect()  # 调数据源的 collect() 接口
        all_signals.extend(signals)
    return self._filter_engine.filter_batch(all_signals)  # 过滤升级
```

**关键设计**：
- **数据源可插拔**：任何实现 `collect() -> list[PerceptionSignal]` 的对象都能接入
- **过滤引擎**：`PerceptionFilterEngine` 过滤噪声，只升级 WARNING/CRITICAL 信号
- **懒加载**：感知模块在首次使用时初始化，避免循环导入

**典型数据源**（Phase 10 实现）：
- 系统指标采集（error_rate、latency、throughput）
- 市场信号订阅（价格波动、成交量异常）
- 仓位变化监控（breach、limit utilization）

<a id="section-8-4"></a>
## 8.4 信念更新

**感知环境**（[base.py](../src/riskagent_backend/proactive_agents/base.py)）：

```python
async def _perceive_environment(self) -> None:
    """感知环境 - 更新信念（子类可重写）"""
    # 子类实现：采集信号 → 过滤 → add_belief(content, source, confidence)
    pass
```

**信念写入**（[base.py](../src/riskagent_backend/proactive_agents/base.py)）：

```python
def add_belief(self, content: Any, source: str, confidence: float = 1.0) -> Belief:
    belief = Belief(content=content, source=source, confidence=confidence)
    self._beliefs.append(belief)
    return belief
```

**关键设计**：
- 信念池是**进程内 list**，读写快，无网络延迟
- 每个信念带 `source` 字段，后续 Deliberate 阶段可按来源过滤
- `confidence` 支持动态衰减（低置信度信念可被清理）

<a id="section-8-5"></a>
## 8.5 意图形成

**思考过程**（[base.py](../src/riskagent_backend/proactive_agents/base.py)）：

```python
async def _deliberate(self) -> None:
    """思考 - 根据信念和愿望形成意图"""
    recent_beliefs = self.get_beliefs()[-5:]  # 取最近 5 个信念
    active_desires = self.get_active_desires() # 取活跃愿望
    
    for belief in recent_beliefs:
        # 仅处理来自感知模块的信念（泛化：不再硬编码 system_metrics）
        if belief.source not in _PERCEPTION_SOURCES:
            continue

        content = belief.content if isinstance(belief.content, dict) else {}
        severity = str(content.get("severity", "")).lower()
        metric = content.get("metric")
        value = content.get("value")

        # 优先按 severity 字段判定（escalation 类 + perception 类均携带 severity）
        if severity == "critical":
            priority = "high"
        elif severity == "warning":
            priority = "normal"
        elif metric == "error_rate" and isinstance(value, (int, float)) and value > 0.1:
            # 兼容旧版 perception 信念：仅有 metric/value，无 severity
            priority = "high" if value > 0.2 else "normal"
            severity = "critical" if value > 0.2 else "warning"
        else:
            continue

        alert_message = (
            content.get("description")
            or content.get("message")
            or f"{belief.source} 信号异常 (metric={metric}, value={value})"
        )
        self.add_intention(
            description=f"主动告警:{belief.source} 信号异常 (severity={severity})",
            target_agent="orchestrator",
            tool_name="submit_alerts",
            tool_params={
                "alert_type": "system_error",
                "severity": severity,
                "priority": priority,
                "message": alert_message,
                "metric_name": metric,
                "metric_value": value,
                "source": belief.source,
            },
        )
```

**关键设计**：
- **规则驱动**：金融风控需要确定性阈值（error_rate>0.1），纯 LLM 推理不稳定
- **泛化感知源**：使用 `_PERCEPTION_SOURCES` frozenset 白名单过滤信念，不再硬编码单个 source
- **优先 severity 字段判定**：escalation 类和 perception 类信念均携带 `severity` 字段，优先按 critical/warning 映射 priority；保留旧版 `error_rate>0.1` 阈值检查作为后向兼容
- **意图携带完整上下文**：`tool_params` 里有 metric_name/metric_value/source，后续执行不需要再查
- **子类可重写**：不同 Agent 可重写 `_deliberate()` 实现不同的意图形成逻辑

<a id="section-8-6"></a>
## 8.6 意图执行与事件投递

**行动过程**（[base.py](../src/riskagent_backend/proactive_agents/base.py)）：

```python
async def _act(self) -> None:
    """行动 - 执行意图"""
    pending_intentions = self.get_pending_intentions()
    
    for intention in pending_intentions:
        self.update_intention_status(intention.intention_id, "executing")
        
        try:
            if intention.target_agent:
                proactive_event = self._build_proactive_event(intention=intention)
                workflow = get_proactive_workflow()
                await workflow.start_from_event(
                    event=proactive_event,
                    candidate_agents=[intention.target_agent, "critic", "orchestrator"],
                )
            self.update_intention_status(intention.intention_id, "completed")
        except Exception as e:
            self.update_intention_status(intention.intention_id, "failed")
```

**关键设计**：
- **意图状态机**：`pending → executing → completed/failed`，每次状态变更都记录
- **不直接执行工具**：意图转成 `proactive_event` 投递回统一 workflow
- **候选 Agent 列表**：`[target_agent, "critic", "orchestrator"]` 保证至少有 critic 审查
- **符合 PRD 硬约束**："所有新增能力接入统一执行内核，不形成旁路"

<a id="section-8-7"></a>
## 8.7 主链执行

主动事件投递后，走和用户任务**完全相同**的主链：

```
proactive_event → workflow.start_from_event()
    → IntentAgent 识别意图
    → 记忆检索（shared memory + semantic indexer）
    → OrchestratorAgent 规划
    → CriticAgent 审查
    → TaskGraphExecutor 执行
        → delegate / tool_call / finalize
        → ToolExecutor → receipt
    → 审批（如需要）
    → finalize output
    → persist and trace（run_trace.v2）
```

**关键设计**：
- 主动行为与用户行为**共享同一套执行内核**
- 所有工具调用产出 receipt，可审计、可回放
- 完整 trace 记录，支持事后复盘

<a id="section-8-8"></a>
## 8.8 频率控制与预算熔断

**频率控制**：
- `monitor_interval_seconds`：循环间隔（默认 60 秒）
- `ProactiveBudgetManager`：频控/token budget/熔断

**预算熔断**（Phase 10 实现）：
- 异常风暴下自动熔断，防止资源滥用
- 按角色选模型降本（简单路由用轻量模型，复杂推理用强模型）
- 提示词缓存分层（stable_tier 前缀复用命中提供商缓存）

**关键设计**：
- 主动性不是无限制的，受预算约束
- 熔断后系统降级为被动响应模式
- 成本可控是 5min 主动监控的前提

<a id="section-8-9"></a>
## 8.9 关键代码出处

| 组件 | 文件 | 方法/类 |
|---|---|---|
| 启动监控 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `start_background_monitor` |
| 停止监控 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `stop_background_monitor` |
| 监控循环 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_monitor_loop` |
| 数据采集 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_collect_and_filter` |
| 感知环境 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_perceive_environment` |
| 信念写入 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `add_belief` |
| 意图形成 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_deliberate` |
| 意图执行 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_act` |
| 意图→事件 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `_build_proactive_event` |
| 事件投递 | [base.py](../src/riskagent_backend/proactive_agents/base.py) | `workflow.start_from_event` |
| 感知过滤引擎 | [perception/](../src/riskagent_backend/perception/) | `PerceptionFilterEngine` |
| 升级管理 | [perception/](../src/riskagent_backend/perception/) | `EscalationManager` |
| 预算熔断 | [governance/proactive_budget.py](../src/riskagent_backend/governance/proactive_budget.py) | `ProactiveBudgetManager` |

<a id="section-9"></a>
# 9. REST BFF 服务层

REST BFF（Backend For Frontend）服务层是 Phase 13 新增的产品能力层，为浏览器提供友好的 REST API 和 SSE 事件流，打通 `提交任务 → 轮询状态 → 展示智能体 → 展示结果` 的联调闭环。

<a id="section-9-1"></a>
## 9.1 端点概览

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/tasks` | POST | 提交任务，返回 task_id + pending |
| `/api/tasks/{task_id}` | GET | 获取任务详情（状态、步骤、结果、错误） |
| `/api/tasks/{task_id}/graph` | GET | 获取 TaskGraph DAG 快照（节点、边、图级状态） |
| `/api/tasks/{task_id}/memory` | GET | 获取任务维度的记忆视图 |
| `/api/agents` | GET | 获取最小智能体状态列表（派生态，弱一致） |
| `/api/memory` | GET | 获取最近结构化记忆快照和聚合摘要 |
| `/api/stream` | GET | SSE 事件流，实时推送 agent_snapshot / memory_snapshot / graph_snapshot / heartbeat |

除上述 7 个 BFF 端点外，server.py 还提供 5 个基础设施端点：`/health`、`/ready`、`/metrics`、`/api/llm/usage`、`/api/llm/cost-model`

<a id="section-9-2"></a>
## 9.2 运行时任务注册表

[runtime_task_store.py](../src/riskagent_backend/services/runtime_task_store.py) 维护运行中任务的状态快照，解决运行中任务无可轮询状态的问题：

- 任务创建时注册 `task_id` / `run_id` / `status=pending`
- 工作流执行中更新 `status=running` / `steps` / `graph_snapshot`
- 任务完成后更新 `status=completed` / `result` / `error`
- 任务详情的权威来源优先级：运行时注册表 > MemoryStore.get_run_context > RunTraceStore.get_snapshot

<a id="section-9-3"></a>
## 9.3 SSE 事件流与快照去重

`GET /api/stream` 返回 `text/event-stream`，推送四类事件：

| 事件类型 | 内容 |
|----------|------|
| `agent_snapshot` | 智能体状态列表 |
| `memory_snapshot` | 记忆快照和聚合摘要 |
| `graph_snapshot` | TaskGraph DAG 快照 |
| `heartbeat` | 心跳保活 |

**快照去重**：SSE 推送前对快照做内容哈希比对，相同快照不重复推送，避免前端重连抖动和无效事件洪泛。

<a id="section-9-4"></a>
## 9.4 脱敏机制

所有 API 响应在返回前经过脱敏处理，确保不暴露 Redis 原始结构或明文敏感信息：

- `_mask_secret_text()`：对 API Key、密码等敏感字段做掩码处理
- `_sanitize_public_text()`：对公开文本做安全清洗，移除潜在敏感信息
- 验收标准：全部响应无明文 API Key

<a id="section-9-5"></a>
## 9.5 nginx 反向代理

前端通过 nginx 反向代理将 `/api/*` 请求转发到后端 mcp-server 服务（K8s ClusterIP）。nginx 配置不在本仓库，前端代码也不在本仓库。

<a id="section-9-6"></a>
## 9.6 缺点与风险

| 缺点 | 风险等级 | 说明 |
|------|---------|------|
| **ClusterIP 无 Ingress** | 中 | 当前仅 K8s ClusterIP 暴露，外部访问需 port-forward 或 Ingress 控制器 |
| **前端代码不在本仓库** | 中 | 前端 MVP 页面代码独立维护，接口变更需手动同步 |
| **运行时注册表与持久化状态短暂不一致** | 低 | 运行时注册表是内存态，任务完成后异步持久化到 MemoryStore |
| **智能体状态是派生态** | 低 | `GET /api/agents` 来源于工作流单例角色对象和最近 trace，不能承诺强一致 |

<a id="section-10"></a>
# 10. LLM 成本治理

LLM 成本治理是 Phase 14 新增的治理层，对多 Agent 调用的 token 消耗和成本进行全维度统计、预估和熔断控制。

<a id="section-10-1"></a>
## 10.1 TokenTracker

TokenTracker（[token_tracker.py](../src/riskagent_backend/llm/token_tracker.py)）按 `agent_name + stage` 双维度统计 token 消耗，使用滑动窗口设计：

- **维度**：每个 Agent 的每个执行阶段（intent / plan / execute / finalize 等）独立统计
- **滑动窗口**：**1h + 24h 两个窗口**同时维护（`__init__(window_s=3600, daily_window_s=86400)`）；5min 仅是 CostCircuitBreaker 的预算档位标签，不由 TokenTracker 维护
- **数据结构**：内存中的 `deque[TokenUsageRecord]`（小时窗口 + 日窗口各一个 deque），按时间戳自动淘汰过期记录

<a id="section-10-2"></a>
## 10.2 cost_model.py 定价表

[cost_model.py](../src/riskagent_backend/llm/cost_model.py) 内置 `PRICING_TABLE` 模型定价表，单价单位为 **USD per 1K tokens**：

- `get_pricing(model)` 按模型名查询，返回 `{"prompt": float, "completion": float}`（每 1K token 的美元价格）；未知模型回退 `default` 条目
- `calculate_call_cost(prompt_tokens, completion_tokens, model)` 计算单次调用成本（美元，保留 6 位小数）
- `calculate_chain_cost(records)` 汇总完整链路成本，按 stage 维度拆分
- `generate_cost_estimate_table(summary)` 基于 TokenTracker 实测数据生成 5min / 1h / 24h / 7d 四窗口成本预估表

**定价表覆盖范围**：

| 条目类型 | 示例 |
|---------|------|
| DeepSeek 官方模型名（无供应商前缀） | `deepseek-v4-flash`（prompt $0.00010 / completion $0.00020 per 1K）、`deepseek-v4-pro` |
| 带供应商前缀的历史兼容条目 | `deepseek/deepseek-chat` 等，与官方同名模型定价一致 |
| Embedding 模型 | `BAAI/bge-m3`（硅基流动免费额度，$0.00；embedding 无 completion 计费） |
| 其他对照模型 | `openai/gpt-4o`、`google/gemini-2.0-flash-exp:free` 等 |
| `default` 兜底 | prompt $0.00014 / completion $0.00028 per 1K |

定价表可通过 `/api/llm/cost-model` 端点查询。当前仅 USD 计价，无 CNY 换算。

<a id="section-10-3"></a>
## 10.3 CostCircuitBreaker 三级熔断

CostCircuitBreaker（[cost_circuit_breaker.py](../src/riskagent_backend/governance/cost_circuit_breaker.py)）实现三级熔断机制，防止 LLM 成本失控：

| 级别 | 时间窗口标签 | token_limit | cost_limit | 触发条件 |
|------|---------|---------|---------|----------|
| L1 | 5min | 50,000 | $0.01 | `summary.total_tokens > token_limit` **或** `summary.cost_estimate > cost_limit` |
| L2 | 1h | 500,000 | $0.10 | 同上 |
| L3 | 24h | 10,000,000 | $2.00 | 同上 |

**熔断行为**：三级触发返回同构 `{"should_block": bool, "reason": str, "level": str}`，唯一消费方 `ProactiveBudgetManager` 统一阻断本次主动运行（不区分级别差异行为）。

**恢复机制**：固定 30 秒冷却（`cooldown_s=30`），冷却期满后自动重置该级别的 `_tripped` 标志。

<a id="section-10-4"></a>
## 10.4 与 ProactiveBudgetManager 集成

CostCircuitBreaker 与 `ProactiveBudgetManager` 联动：

- `ProactiveBudgetManager` 负责频控和 token budget 上限
- `CostCircuitBreaker` 负责成本维度的熔断
- 两者协同：频控先触发（防止瞬时风暴），成本熔断后触发（防止累计超标）

<a id="section-10-5"></a>
## 10.5 暴露端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/llm/usage` | GET | 查询 by_agent_stage 维度的 token 统计 |
| `/api/llm/cost-model` | GET | 查询内置定价表和成本预估 |

成本预估表支持 5min / 1h / 24h / 7d 四种时间窗口的预估。

<a id="section-10-6"></a>
## 10.6 缺点与风险

| 缺点 | 风险等级 | 说明 |
|------|---------|------|
| **纯内存存储** | 中 | TokenTracker 和 CostCircuitBreaker 数据存储在内存中，服务重启后丢失统计数据 |
| **定价表需手动更新** | 低 | 供应商定价变更时需手动更新 cost_model.py |
| **预估精度依赖历史数据** | 低 | 新部署时无历史数据，预估精度较低 |

<a id="section-11"></a>
# 11. 评估体系

本项目的评估体系采用 **自动化指标 + LLM 辅助评估 + 质量门禁** 三层架构，覆盖 7 大维度、40+ 项指标。

<a id="section-11-1"></a>
## 11.1 参考框架与基准

评估体系参考了以下业界框架：

| 框架 | 来源 | 参考内容 |
|---|---|---|
| **GAIA** | Meta AI | General AI Assistant Benchmark，任务准确度维度 |
| **BackEndBench** | 学术界 | Multi-Agent Collaboration Benchmark，协作深度维度 |
| **PlanBench** | 学术界 | Planning and Execution Benchmark，计划正确性维度 |
| **GEMMAS** | 学术界 | Graph-based Evaluation Metrics for Multi-Agent Systems，信息多样性 |
| **CoT Benchmarks** | 学术界 | Chain-of-Thought 推理质量评估 |

**关键设计**：
- **多框架融合**：不依赖单一基准，综合 5 个框架的核心维度
- **领域定制**：在通用框架基础上增加金融风控领域特有指标（如工具风险、记忆价值）
- **可插拔**：指标定义与计算解耦，可通过 `get_metric_definitions()` 动态扩展

<a id="section-11-2"></a>
## 11.2 评估维度与指标体系

**7 大维度 + 1 行为维度**：

```
OverallMetrics (综合评分)
├─ TaskAccuracy (任务准确度)        权重 0.23
├─ Comprehension (问题理解度)      权重 0.14
├─ Collaboration (协作深度)        权重 0.18
├─ Efficiency (执行效率)           权重 0.13
├─ Reasoning (推理质量)            权重 0.14
├─ ToolRisk (工具风险)             权重 0.09
└─ Memory (记忆价值)               权重 0.09

BehavioralMetrics (行为指标，用于质量门禁)
├─ workflow_success (工作流成功率)
├─ task_success_rate (任务成功率)
├─ tool_selection_accuracy (工具选择准确率)
├─ receipt_binding_rate (回执绑定率)
├─ approval_correctness (审批正确性)
├─ dangerous_action_block_rate (危险动作拦截率)
├─ message_trace_completeness (消息追踪完整性)
├─ factuality_score (事实性得分)
├─ evidence_coverage (证据覆盖率)
└─ ... 其他行为指标
```

**综合评分公式**：

```
overall_score = 0.23 * task_accuracy
             + 0.14 * comprehension
             + 0.18 * collaboration
             + 0.13 * efficiency
             + 0.14 * reasoning
             + 0.09 * tool_risk
             + 0.09 * memory
```

<a id="section-11-3"></a>
## 11.3 指标计算方式

<a id="section-11-3-1"></a>
### 11.3.1 任务准确度 (TaskAccuracyMetrics)

| 指标 | 计算方式 | 数据来源 |
|---|---|---|
| `intent_match_score` | expected_intent vs actual_intent，完全匹配=1.0，部分匹配=0.5，有输出=0.7 | ground_truth.intent + trace.intent |
| `plan_correctness` | min(1.0, actual_steps / expected_steps)，无期望则启发式 | ground_truth.expected_steps + trace.plan_steps |
| `execution_success_rate` | trace.success ? 1.0 : 0.0 | trace.success |
| `answer_quality` | LLMJudge 评估（accuracy/completeness/relevance/clarity） | LLMJudge.evaluate_answer_quality() |

<a id="section-11-3-2"></a>
### 11.3.2 问题理解度 (ComprehensionMetrics)

| 指标 | 计算方式 | 数据来源 |
|---|---|---|
| `intent_recognition_f1` | 基于 slots 匹配的 Precision/Recall 计算真正 F1 | ground_truth.entities + trace.intent.slots |
| `entity_extraction_f1` | 复用 intent_recognition_f1 | 同上 |
| `ambiguity_resolution` | 启发式：有 intent=0.7，有 intent+react_steps=0.85 | trace |
| `context_understanding` | 启发式：基于 trace 完整性分级 | trace |

<a id="section-11-3-3"></a>
### 11.3.3 协作深度 (CollaborationMetrics)

| 指标 | 计算方式 | 数据来源 |
|---|---|---|
| `agent_participation_rate` | matched_agents / expected_agents | ground_truth.expected_agents + trace.agent_outputs |
| `information_diversity` | unique_thoughts / total_steps | trace.react_steps |
| `message_exchange_depth` | min(1.0, message_count / 10) | trace.messages |
| `role_specialization` | active_agents >= 3 → 0.85, >= 2 → 0.7, >= 1 → 0.5 | trace.agent_outputs |
| `conflict_resolution_rate` | 启发式：success + active_agents >= 2 → 0.85 | trace |

<a id="section-11-3-4"></a>
### 11.3.4 执行效率 (EfficiencyMetrics)

| 指标 | 计算方式 | 数据来源 |
|---|---|---|
| `latency_ms` | end_time - start_time | trace |
| `token_count` | trace.tokens_used | trace |
| `token_efficiency` | min(1.0, output_size / tokens) | trace |
| `tool_success_rate` | successful_tools / total_tools | trace.tool_calls |
| `tool_timeout_rate` | timeout_tools / total_tools | trace.tool_calls |
| `tool_retry_rate` | retried_tools / total_tools | trace.tool_calls |

<a id="section-11-3-5"></a>
### 11.3.5 推理质量 (ReasoningMetrics)

| 指标 | 计算方式 | 数据来源 |
|---|---|---|
| `thought_relevance` | LLMJudge 或 steps_with_reasoning / total_steps | LLMJudge / trace.react_steps |
| `reasoning_validity` | LLMJudge 或启发式 | LLMJudge / trace |
| `evidence_support` | steps_with_evidence / total_steps | trace.react_steps |
| `logical_consistency` | LLMJudge 或启发式 | LLMJudge / trace |
| `reasoning_depth` | min(1.0, step_count / 5) | trace.react_steps |

<a id="section-11-3-6"></a>
### 11.3.6 工具风险 (ToolRiskMetrics)

| 指标 | 计算方式 | 数据来源 |
|---|---|---|
| `side_effect_detection` | 有副作用工具 ? 0.9 : 0.8 | trace.tool_calls |
| `permission_compliance` | 与审批合规挂钩 | trace.tool_calls |
| `risk_assessment_accuracy` | requires_approval 与实际审批轨迹一致性 | risk_assessment + trace |
| `approval_flow_compliance` | 期望审批且有审批轨迹 ? 0.9 : 0.3 | trace.tool_calls |
| `dangerous_action_blocked` | 危险工具均有审批状态 ? 1.0 | trace.tool_calls |

<a id="section-11-3-7"></a>
### 11.3.7 记忆价值 (MemoryMetrics)

| 指标 | 计算方式 | 数据来源 |
|---|---|---|
| `memory_hit_rate` | hit_count > 0 ? 1.0 : 0.0 | trace.memory_hits |
| `memory_usefulness` | 0.6 * max(hit_rate, summary_ratio) + 0.4 * evidence_coverage | trace |
| `resume_success_rate` | resume_attempted && success ? 1.0 : 0.0 | trace.resume_memory_state |
| `few_shot_reuse_rate` | planning_memory.few_shot_example_count | trace.planning_memory |
| `role_drift_rate` | planning_memory.role_drift_rate（越低越好） | trace.planning_memory |
| `memory_cross_talk_rate` | planning_memory.memory_cross_talk_rate（越低越好） | trace.planning_memory |

<a id="section-11-4"></a>
## 11.4 LLM 辅助评估

对于主观指标，采用 **LLM-as-Judge** 模式，由独立 LLM 评估器打分：

[llm_judge.py](../eval/core/llm_judge.py) 提供 6 种评估能力：

| 评估方法 | 评估维度 | 输出 |
|---|---|---|
| `evaluate_answer_quality()` | 答案质量（accuracy/completeness/relevance/clarity） | 4 维分数 + overall |
| `evaluate_reasoning_quality()` | 推理质量（thought_relevance/validity/evidence/consistency/depth） | 5 维分数 + overall |
| `evaluate_collaboration_quality()` | 协作质量（role_specialization/information_complementarity/efficiency/conflict） | 4 维分数 + overall |
| `evaluate_risk_assessment()` | 风险评估（risk_identification/severity/mitigation/compliance） | 4 维分数 + overall |
| `evaluate_intent_match()` | 意图匹配（semantic_alignment/completeness/specificity） | 3 维分数 + overall |
| `evaluate_ambiguity_resolution()` | 歧义消解（ambiguity_identified/clarification_quality/assumption_transparency） | 3 维分数 + overall |

**关键设计**：
- **独立错误处理**：每个评估维度独立 try-catch，一个失败不影响其他
- **降级策略**：LLM Judge 失败时返回 0.5 默认分，不阻断评估流程
- **确定性优先**：行为事实（如工具调用、审批轨迹）用确定性规则判定，不依赖 LLM Judge

<a id="section-11-5"></a>
## 11.5 质量门禁

质量门禁（Quality Gate）是评估体系的 **硬约束层**，用于判定评估结果是否可发布：

[gate.py](../eval/gate.py) + [default.json](../eval/gates/default.json)

### Blocking 门禁（不通过则阻断发布）

| 指标 | 阈值 | 含义 |
|---|---|---|
| `task_success_rate` | >= 0.8 | 任务成功率不低于 80% |
| `tool_selection_accuracy` | >= 0.75 | 工具选择准确率不低于 75% |
| `receipt_binding_rate` | >= 0.95 | 回执绑定率不低于 95% |
| `replan_success_rate` | >= 0.7 | 重规划成功率不低于 70% |
| `approval_correctness` | >= 0.95 | 审批正确性不低于 95% |
| `resume_success_rate` | >= 0.7 | 恢复成功率不低于 70% |
| `dangerous_action_block_rate` | >= 0.95 | 危险动作拦截率不低于 95% |
| `message_trace_completeness` | >= 0.95 | 消息追踪完整性不低于 95% |
| `factuality_score` | >= 0.7 | 事实性得分不低于 0.7 |
| `evidence_coverage` | >= 0.6 | 证据覆盖率不低于 60% |

### Warning 门禁（不通过产生告警但不阻断）

| 指标 | 阈值 | 含义 |
|---|---|---|
| `workflow_success` | >= 0.85 | 工作流成功率 |
| `tool_success_rate` | >= 0.85 | 工具成功率 |
| `memory_hit_rate` | >= 0.4 | 记忆命中率 |
| `memory_usefulness` | >= 0.45 | 记忆有用性 |
| `replan_quality` | >= 0.7 | 重规划质量 |
| `latency_ms` | <= 5000 | 延迟上限 5 秒 |
| `token_count` | <= 8000 | Token 消耗上限 |
| `information_diversity` | >= 0.3 | 信息多样性 |
| `role_specialization` | >= 0.5 | 角色专业化 |

**门禁结果**：

```python
@dataclass
class GateResult:
    passed: bool              # 是否通过 blocking 门禁
    reasons: list[str]        # 未通过的原因列表
    metrics_summary: dict     # 关键指标摘要
    warnings: list[str]       # warning 告警列表
    decision_log: list[dict]  # 每个指标的决策日志
```

<a id="section-11-6"></a>
## 11.6 测试数据集

**Gold 数据集**（[eval/datasets/gold/](../eval/datasets/gold/)）：

| 文件 | 用途 |
|---|---|
| `cases.jsonl` | 标准测试用例（21 条） |
| `labels.adjudicated.jsonl` | 仲裁后标注结果 |
| `labels.annotator_a.jsonl` | 标注员 A 的标注 |
| `labels.annotator_b.jsonl` | 标注员 B 的标注 |

**Benchmark 数据集**（[eval/benchmarks/](../eval/benchmarks/)）：

| 类别 | 场景 | 用例数 |
|---|---|---|
| `basic` | 基础查询 | 10 |
| `simple` | 简单任务 | 8 |
| `medium` | 中等复杂度 | 8 |
| `complex` | 复杂分析 | 10 |
| `collaboration` | 多 Agent 协作 | 8 |
| `memory` | 记忆复用 | 4 |
| `reasoning` | 推理能力 | 8 |
| `recovery` | 故障恢复 | 4 |
| `approval` | 审批流程 | 4 |
| `safety` | 安全合规 | 12 |
| `prompt_layering` | 分层 Prompt | 6 |
| `real_world` | 真实场景 | 8 |

**总计**: 90 条

**场景分类**（cases.jsonl 中的 scenario_class）：
- Simple / Medium / Complex / Recovery / Approval / Memory / Safety

**标注一致性**：通过 [compute_iaa.py](../eval/scripts/compute_iaa.py) 计算 Inter-Annotator Agreement，确保标注质量。

<a id="section-11-7"></a>
## 11.7 评估报告

[report.py](../eval/core/report.py) 支持三种报告格式：

| 格式 | 用途 | 特点 |
|---|---|---|
| **JSON** | 程序化消费、CI/CD 集成 | 完整指标 + 逐 case 结果 + 决策日志 |
| **Markdown** | 人工审阅、PR 评审 | 表格化指标 + case 结果表 |
| **HTML** | 可视化展示 | 进度条、卡片布局、颜色编码 |

**报告内容**：
- Summary：总用例数、通过率、综合评分
- Dataset Summary：数据集类别分布
- Metrics Overview：7 大维度详细指标
- Behavioral Metrics：行为指标（用于门禁）
- Comparison：与历史/benchmark 的对比
- Case Results：逐 case 结果表

<a id="section-11-8"></a>
## 11.8 优点

| 优点 | 说明 |
|---|---|
| **多维度覆盖** | 7 大维度 + 行为维度，覆盖任务准确度、理解力、协作、效率、推理、安全、记忆 |
| **双轨评估** | 确定性规则（行为事实）+ LLM Judge（主观质量），互补短板 |
| **质量门禁硬约束** | blocking/warning 两级门禁，不达标不可发布，保障上线质量 |
| **指标定义可追溯** | `get_metric_definitions()` 提供公式、数据来源、阈值、门禁规则 |
| **LLM Judge 降级策略** | LLM 评估失败时返回默认分，不阻断流程 |
| **标注一致性保障** | IAA 计算确保人工标注质量 |
| **多报告格式** | JSON/Markdown/HTML 满足不同消费场景 |
| **场景分类覆盖** | 12 类 benchmark 场景，覆盖从简单查询到复杂多步推理 |
| **行为指标独立** | BehavioralMetrics 与 OverallMetrics 分离，门禁不受主观评分影响 |

<a id="section-11-9"></a>
## 11.9 缺点与风险

| 缺点 | 风险等级 | 说明 |
|---|---|---|
| **启发式指标占比高** | 高 | 多个维度（理解度、协作、效率）依赖启发式规则而非真实测量，可能给出虚高分数 |
| **LLM Judge 一致性不稳定** | 高 | LLM 评估器本身有随机性，相同输入可能给出不同分数，缺乏 Kappa/Fleiss 等一致性度量 |
| **Gold 数据集规模小** | 中 | 仅 21 条标准用例，统计显著性不足，容易过拟合 |
| **缺乏端到端基准对比** | 中 | 没有与业界标准 benchmark（如 GAIA 官方数据集）的定量对比 |
| **效率指标粗糙** | 中 | token_efficiency 用 output_size / tokens 计算，不能真实反映 token 价值 |
| **协作指标依赖 trace 完整性** | 中 | 如果 trace 记录不完整，协作指标会系统性偏低 |
| **权重固定不可调** | 低 | 综合评分权重硬编码，无法根据不同场景动态调整 |
| **无回归检测** | 低 | 缺乏自动化的回归检测机制，无法发现指标劣化趋势 |
| **LLM Judge 成本高** | 低 | 每个 case 需要多次 LLM 调用，评估成本随用例数线性增长 |

<a id="section-11-10"></a>
## 11.10 关键代码出处

| 组件 | 文件 | 方法/类 |
|---|---|---|
| 主评估器 | [evaluator.py](../eval/core/evaluator.py) | `Evaluator` |
| 指标定义 | [metrics.py](../eval/core/metrics.py) | `OverallMetrics` / `BehavioralMetrics` / `get_metric_definitions()` |
| LLM 辅助评估 | [llm_judge.py](../eval/core/llm_judge.py) | `LLMJudge` |
| 质量门禁 | [gate.py](../eval/gate.py) | `evaluate_quality_gate()` / `GateResult` |
| 门禁阈值配置 | [default.json](../eval/gates/default.json) | blocking + warning 阈值 |
| 报告生成 | [report.py](../eval/core/report.py) | `ReportGenerator` |
| 标注一致性 | [compute_iaa.py](../eval/scripts/compute_iaa.py) | `compute_simple_agreement()` |
| Gold 数据集 | [cases.jsonl](../eval/datasets/gold/cases.jsonl) | 21 条标准用例 |
| Benchmark 数据集 | [eval/benchmarks/](../eval/benchmarks/) | 12 类场景基准 |
| CLI 入口 | [cli.py](../eval/cli.py) | 命令行评估工具 |

<a id="section-12"></a>
# 12. 渠道接入与调度

Phase 7 交付（口径：抽象层收口）。Gateway 的正式承诺收敛为抽象层与统一路由，具体平台适配器为兼容实现、未挂载主服务入口（当前对外入口为 REST BFF + MCP，见第 9、7 章）。调度能力（`CronManager` + `run_cron_triggered_workflow()`）库层已实现并有单元测试覆盖，但生产入口未挂载（详见 §12.2）。

<a id="section-12-1"></a>
## 12.1 多平台网关（gateway/）

- **抽象层**：[adapter.py](../src/riskagent_backend/gateway/adapter.py) 定义 `GatewayAdapter` 基类与 `GatewayMessage` 统一消息格式，新增平台只需实现该接口
- **统一路由**：[router.py](../src/riskagent_backend/gateway/router.py) 按消息类型决定入口（user_task 或 system_event），网关只做入口适配，不改变执行内核
- **兼容实现**：`slack_adapter.py` / `wechat_work_adapter.py` 为示例级实现，不在正式验收范围（Phase 7 口径）
- 测试：tests/unit/test_gateway.py

<a id="section-12-2"></a>
## 12.2 内置调度（scheduling/）

- **CronManager**：[cron_manager.py](../src/riskagent_backend/scheduling/cron_manager.py) 提供 `CronTask` 定义、任务 CRUD、自然语言转 cron 表达式（`parse_natural_language()`）、触发检测与递归防护（`check_recursion()`）
- **库层实现完整、生产未挂载**：`CronManager` 与 `run_cron_triggered_workflow()`（[proactive_workflow.py](../src/riskagent_backend/orchestration/proactive_workflow.py)）均有单元测试覆盖，但 src/ 中从未实例化 `CronManager`、未注册触发回调，`server.py` 启动流程不含调度器。`proactive_workflow.py` 导入 `CronTask` 仅为类型标注用途。`check_recursion()` 递归防护同为库级能力，无生产调用方
- **设计意图**：Cron 触发的任务统一走 `system_event → ModeratorAgent → TaskGraphExecutor` 执行内核，不允许绕过治理体系
- **场景模板**：[cron_templates.py](../src/riskagent_backend/scheduling/cron_templates.py) 预置金融风控定时任务模板
- 测试：tests/unit/test_cron_manager.py、test_cron_manager_enhanced.py
- 该缺口已登记于 docs/KNOWN_ISSUES.md（KI-001）

<a id="section-12-3"></a>
## 12.3 CLI 辅助（cli/）

- [replay.py](../src/riskagent_backend/cli/replay.py) 提供 run 回放命令行工具（开发调试用）；完整评估工具链见第 11 章 `eval/cli.py`
