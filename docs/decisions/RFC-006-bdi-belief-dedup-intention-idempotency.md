# RFC-006: BDI 信念去重与意图幂等性修复

| 字段 | 值 |
|------|-----|
| Status | Proposed |
| Date | 2026-07-18 |
| Author | RiskAgent-BackEnd 项目组 |

## Update Log

| 日期 | 变更 |
|------|------|
| 2026-07-18 | 初始创建，提出 BDI 信念去重与意图幂等性修复方案 |

## 上下文

### 问题概述

在 5min 主动监控循环（`_monitor_loop`）中，BDI 心智模型的 Deliberate 阶段存在一个设计缺陷：**同一信念会在多轮监控循环中被重复处理，导致生成重复意图并多次投递事件**。

### 缺陷根因分析

涉及代码位于 `src/riskagent_backend/proactive_agents/base.py`：

**1. 信念列表不清理**

`_monitor_loop`（第 353-383 行）每轮执行 `_perceive_environment()` → `_deliberate()` → `_act()`，但**从不调用 `clear_beliefs()`**。`_perceive_environment()` 每轮往 `_beliefs` 列表追加新信念，旧信念永久残留：

```python
# _perceive_environment (子类实现, 如 roles.py:71-88)
for sig in filtered:
    self.add_belief(content={...}, source="intent_perception", confidence=0.7)
# ← 没有 clear_beliefs()，B1 在下一轮仍然存在
```

**2. `_deliberate()` 无去重检查**

`_deliberate()`（第 422-484 行）取 `get_beliefs()[-5:]` 遍历处理，但**不检查该信念是否已经生成过意图**：

```python
recent_beliefs = self.get_beliefs()[-5:]  # 包含历史信念
for belief in recent_beliefs:
    if belief.source not in _PERCEPTION_SOURCES:
        continue
    # severity 匹配...
    self.add_intention(...)  # ← 无条件生成，不检查是否已处理过此 belief_id
```

**3. 状态机只防止"重复执行"，不防止"重复生成"**

`get_pending_intentions()`（第 220-222 行）只返回 `status == "pending"` 的意图，所以同一个 Intention 对象不会被 `_act()` 重复执行。但 `_deliberate()` 会在下一轮为同一个 B1 生成**新的** I2、I3、I4……

### 缺陷影响

| 影响项 | 严重程度 | 说明 |
|--------|---------|------|
| 重复事件投递 | **高** | 同一个异常信号被多次投递到统一主链，导致 OrchestratorAgent 重复规划和执行 |
| 成本失控 | **中** | 每次 `_act()` 投递事件后触发主链完整执行（LLM 调用 + 工具执行），重复投递直接乘以 LLM 调用成本 |
| 噪声事件风暴 | **高** | 感知层如果每 60s 产出 1 条信号，B1 在 `[-5:]` 窗口内停留 5 轮 = 5 分钟，期间生成 5 个重复意图 |
| 违反 PRD 硬约束 | **高** | PRD 第 9 节"过度主动性会造成噪声事件和成本失控"风险项直接命中 |
| 审计追踪混乱 | **中** | `run_trace.v2` 中出现多条几乎相同的 intention 记录，审计回放时难以区分 |

### 复现场景

```
第 1 轮 _monitor_loop (T=0s):
  _perceive_environment()  →  add_belief(B1: error_rate=0.15, severity=warning)
  _deliberate()           →  B1 匹配 → add_intention(I1, status=pending)
  _act()                  →  I1 → event → workflow.start_from_event() → I1=completed

第 2 轮 _monitor_loop (T=60s):
  _perceive_environment()  →  add_belief(B2: error_rate=0.15, severity=warning)  ← 同一异常仍在
  _deliberate()           →  get_beliefs()[-5:] = [B1, B2]
                           →  B1 仍然匹配（severity=warning）→ add_intention(I2)  ← 重复！
                           →  B2 也匹配 → add_intention(I3)  ← 也重复！
  _act()                  →  I2 → event → 又投递一次
                           →  I3 → event → 再投递一次

第 3-5 轮：B1 始终在 [-5:] 窗口内 → 持续生成重复意图
第 6 轮：B1 终于滚出窗口 → 停止（但已产生 5+ 个重复事件）
```

## 决策

### 修复方案：信念去重 + 意图幂等性双重保障

采用**两层防护**，确保既不重复生成意图，也不重复投递事件：

### 第一层：信念处理标记（防止 `_deliberate()` 重复生成）

在 `Belief` 数据模型中新增 `processed: bool` 字段，`_deliberate()` 处理信念后标记为 `processed=True`，后续轮次跳过已处理的信念。

### 第二层：信念列表周期性清理（防止无限膨胀）

在每轮 `_monitor_loop` 的 `_deliberate()` 完成后，清理已处理且超过保留窗口的信念，避免信念列表无限增长。

### 第三层：意图内容去重（兜底防护）

在 `add_intention()` 中增加内容去重检查：如果已存在相同 `description + tool_name + tool_params` 的 pending 意图，跳过创建。

## 方案设计

### 1. 数据模型变更

**文件**：`src/riskagent_backend/proactive_agents/base_models.py`

#### Belief 模型新增字段

```python
@dataclass
class Belief:
    """信念 - 对世界状态的认知."""
    belief_id: str
    content: dict[str, Any]
    source: str
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    processed: bool = False           # ← 新增：是否已被 _deliberate() 处理过
    processed_at: float | None = None  # ← 新增：处理时间戳
```

#### Intention 模型新增字段

```python
@dataclass
class Intention:
    """意图 - 打算执行的行动."""
    intention_id: str
    description: str
    target_agent: str | None = None
    tool_name: str | None = None
    tool_params: dict[str, Any] | None = None
    status: str = "pending"
    source_belief_id: str | None = None    # ← 新增：生成此意图的信念 ID
    created_at: float = field(default_factory=time.time)  # ← 新增：创建时间戳
```

### 2. Deliberate 去重逻辑

**文件**：`src/riskagent_backend/proactive_agents/base.py`，`_deliberate()` 方法

```python
async def _deliberate(self) -> None:
    recent_beliefs = self.get_beliefs()[-5:]
    active_desires = self.get_active_desires()

    for belief in recent_beliefs:
        # 新增：跳过已处理的信念
        if belief.processed:
            continue

        if belief.source not in _PERCEPTION_SOURCES:
            continue

        # ... severity 判断逻辑不变 ...

        intention = self.add_intention(
            description=f"主动告警:{belief.source} 信号异常 (severity={severity})",
            target_agent="orchestrator",
            tool_name="submit_alerts",
            tool_params={...},
            source_belief_id=belief.belief_id,   # ← 新增：关联信念 ID
        )

        # 新增：标记信念已处理
        belief.processed = True
        belief.processed_at = time.time()
```

### 3. 信念列表周期性清理

**文件**：`src/riskagent_backend/proactive_agents/base.py`，新增 `_cleanup_beliefs()` 方法

```python
def _cleanup_beliefs(self, *, max_age_seconds: float = 300) -> int:
    """清理已处理且超过保留时长的信念.

    Args:
        max_age_seconds: 已处理信念的保留时长（秒），默认 300s（5 分钟）

    Returns:
        清理数量
    """
    now = time.time()
    before = len(self._beliefs)
    self._beliefs = [
        b for b in self._beliefs
        if not b.processed or (now - (b.processed_at or b.timestamp)) < max_age_seconds
    ]
    removed = before - len(self._beliefs)
    if removed > 0:
        logger.debug(f"[{self._name}] Cleaned {removed} processed beliefs")
    return removed
```

在 `_monitor_loop` 中调用：

```python
async def _monitor_loop(self) -> None:
    while self._is_running:
        try:
            await self._perceive_environment()
            await self._deliberate()
            await self._act()
            self._cleanup_beliefs()    # ← 新增：每轮清理
            consecutive_errors = 0
        except asyncio.CancelledError:
            break
        # ... 错误处理不变 ...
        await asyncio.sleep(self._monitor_interval)
```

### 4. 意图内容去重

**文件**：`src/riskagent_backend/proactive_agents/base.py`，`add_intention()` 方法

```python
def add_intention(
    self,
    description: str,
    target_agent: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_params: Optional[dict[str, Any]] = None,
    source_belief_id: Optional[str] = None,   # ← 新增参数
) -> Intention:
    # 新增：内容去重检查
    pending = self.get_pending_intentions()
    for existing in pending:
        if (existing.description == description
            and existing.tool_name == tool_name
            and existing.tool_params == tool_params):
            logger.debug(
                f"[{self._name}] Skipping duplicate intention: {description}"
            )
            return existing  # 返回已存在的意图，不创建新的

    intention = Intention(
        description=description,
        target_agent=target_agent,
        tool_name=tool_name,
        tool_params=tool_params,
        status="pending",
        source_belief_id=source_belief_id,
    )
    self._intentions.append(intention)
    return intention
```

### 5. 保留窗口策略

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_age_seconds` | 300s（5 分钟） | 已处理信念的保留时长，超时后从列表移除 |
| 信念列表上限 | 无硬上限 | 靠 `[-5:]` + `_cleanup_beliefs()` 联合控制，实际不会超过 10-15 条 |
| 意图列表上限 | 无硬上限 | 靠状态机 + 内容去重控制，`completed`/`failed` 的意图可定期清理 |

> **注意**：`max_age_seconds=300s` 与 `[-5:]` 窗口的关系——窗口控制 `_deliberate()` 可见的信念范围，清理控制内存占用。两者独立工作，不冲突。

## 受影响组件

| 组件 | 文件 | 变更类型 | 说明 |
|------|------|---------|------|
| Belief 模型 | `base_models.py` | 新增字段 | `processed`, `processed_at` |
| Intention 模型 | `base_models.py` | 新增字段 | `source_belief_id`, `created_at` |
| `_deliberate()` | `base.py` | 修改 | 跳过 `processed=True` 的信念；标记已处理；传入 `source_belief_id` |
| `add_intention()` | `base.py` | 修改 | 增加 `source_belief_id` 参数；增加内容去重检查 |
| `_monitor_loop()` | `base.py` | 修改 | 每轮调用 `_cleanup_beliefs()` |
| `_cleanup_beliefs()` | `base.py` | 新增方法 | 清理已处理且过期的信念 |
| `get_bdi_state()` | `base.py` | 修改 | 导出 `processed` 和 `source_belief_id` 字段 |
| 各子类 `_perceive_environment()` | `roles.py` | 无需修改 | 感知层只负责 `add_belief()`，去重在 Deliberate 层完成 |

## 与现有架构约束的兼容性

| 约束来源 | 约束内容 | 兼容性 |
|---------|---------|--------|
| ADR-001 | 多 Agent 架构，不形成旁路 | ✅ 意图仍通过 `_act()` → `workflow.start_from_event()` 投递到统一主链，不改变执行路径 |
| ADR-005 | run_trace.v2 全链路追踪 | ✅ `processed` 和 `source_belief_id` 字段会通过 `get_bdi_state()` 导入 trace，增加可追溯性 |
| RFC-003 | 5min 主动感知与自主运维 | ✅ 修复 RFC-003 实现中的缺陷，不改变架构设计 |
| PRD §9 风险项 | "过度主动性会造成噪声事件和成本失控" | ✅ 直接缓解此风险 |
| PRD §10 准入标准 | "所有新增能力都接入统一执行内核, 不形成旁路" | ✅ 不新增执行路径，只是防止重复投递 |

## Drawbacks

| 缺点 | 影响 | 缓解措施 |
|------|------|---------|
| `Belief` 模型新增字段 | 需要更新序列化/反序列化逻辑 | `processed` 默认 `False`，旧数据兼容 |
| 信念清理可能丢失审计信息 | 已处理信念被清理后无法在 BDI 状态中查看 | `run_trace.v2` 在每轮记录 `get_bdi_state()` 快照，审计信息已在 trace 中保留 |
| `_cleanup_beliefs` 的 `max_age_seconds` 需要调优 | 过短可能丢掉仍需处理的信念，过长则内存占用增加 | 默认 300s 可覆盖 5 轮监控循环（60s 间隔），实际部署后根据信号频率调整 |
| 意图内容去重可能误判 | 相同 description 但不同上下文的意图被跳过 | 去重条件包含 `tool_params` 全量比对，只有完全相同才跳过；不同 metric/value 的告警不会被误判 |

## Alternatives

### 替代方案 A：每轮 `clear_beliefs()`

在 `_monitor_loop` 的 `_deliberate()` 后调用 `clear_beliefs()`，每轮清空所有信念。

| 优点 | 缺点 |
|------|------|
| 实现最简单 | ReAct 循环（`run_with_react`）中的信念会被误清；ReAct 的 `_generate_evidence` 方法依赖 `get_beliefs()` 获取历史信念 |
| 无内存累积 | 无法区分"已被处理"和"尚未被处理但本轮无匹配"的信念 |

**结论**：不采用，会破坏 ReAct 循环的信念依赖。

### 替代方案 B：信念 TTL 机制

每条信念创建时设置 TTL（如 120s），过期自动从列表移除。

| 优点 | 缺点 |
|------|------|
| 自动化程度高 | 需要引入后台定时器或惰性清理逻辑 |
| TTL 可配置 | TTL 值难以统一设定——感知信号和用户输入的合理 TTL 不同 |

**结论**：不采用，过度工程化。`_cleanup_beliefs()` + `processed` 标记已足够。

### 替代方案 C：只做意图去重，不标记信念

在 `add_intention()` 中做内容去重，但不修改 `Belief` 模型。

| 优点 | 缺点 |
|------|------|
| 改动最小 | `_deliberate()` 仍然会遍历所有历史信念做无意义的 severity 检查，浪费 CPU |
| | 无法追溯"哪个信念生成了哪个意图"，审计能力不提升 |

**结论**：不采用，治标不治本。

## Unresolved Questions

| 问题 | 当前倾向 | 待确认 |
|------|---------|--------|
| `_cleanup_beliefs` 的 `max_age_seconds` 默认值 | 300s | 需要根据实际监控间隔和信号频率调优 |
| 是否需要在意图列表也做定期清理 | 暂不需要 | 长时间运行后意图列表可能累积大量 completed/failed 记录，未来可考虑加 `_cleanup_intentions()` |
| `get_bdi_state()` 是否需要导出 `processed` 字段 | 是 | 已纳入方案，但需要确认 trace 解析工具是否需要适配 |

## Checkpoints

| Checkpoint | 内容 | 验证标准 |
|------------|------|---------|
| 1 | `Belief`/`Intention` 模型新增字段 | 单测覆盖字段默认值和序列化 |
| 2 | `_deliberate()` 去重逻辑 | 单测：同一信念在两轮 `_deliberate()` 中只生成一个意图 |
| 3 | `_cleanup_beliefs()` 方法 | 单测：已处理信念在 `max_age_seconds` 后被清理，未处理的保留 |
| 4 | `add_intention()` 内容去重 | 单测：相同 description+tool_params 的 pending 意图不重复创建 |
| 5 | `_monitor_loop` 集成 | 集成测试：模拟 5 轮监控循环，验证同一异常信号只投递一次事件 |
| 6 | `run_trace.v2` 兼容性 | 验证 `get_bdi_state()` 新增字段在 trace 中正确记录 |
