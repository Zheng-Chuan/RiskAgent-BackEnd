# Phase 12: BDI 信念去重与意图幂等性修复

## 目标

修复 BDI 心智模型 Deliberate 阶段的设计缺陷：同一信念在多轮监控循环中被重复处理，导致生成重复意图并多次投递事件。该缺陷在 Phase 10 的 5 分钟主动监控全链路验证中暴露——5 分钟内 LLM 调用达 133 次，长时间运行必然产生"信念风暴"导致成本失控。

RFC: [RFC-006-bdi-belief-dedup-intention-idempotency](../decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md)（Accepted, Implemented）

## 实施摘要

采用两层防护机制，确保既不重复生成意图，也不重复投递事件：

### 第一层：信念处理标记

在 `Belief` 数据模型中新增 `processed: bool` 和 `processed_at: float | None` 字段。`_deliberate()` 处理信念后标记为 `processed=True`，后续轮次跳过已处理的信念。

### 第二层：信念列表周期性清理

新增 `_cleanup_beliefs()` 方法，在每轮 `_monitor_loop` 的 `_deliberate()` 完成后，清理已处理且超过保留窗口（默认 300s）的信念，避免信念列表无限增长。

### 第三层：意图内容去重

在 `add_intention()` 中增加内容去重检查：如果已存在相同 `description + tool_name + tool_params` 的 pending 意图，跳过创建，返回已存在的意图。

## Checkpoint 实施情况

| Checkpoint | 内容 | 状态 | 验证方式 |
|------------|------|------|----------|
| 1 | `Belief`/`Intention` 模型新增字段 | ✅ 完成 | `TestBeliefDedupFields` + `TestIntentionSourceBeliefId`（4 个测试） |
| 2 | `_deliberate()` 去重逻辑 | ✅ 完成 | `test_deliberate_skips_processed_belief` + `test_deliberate_marks_belief_processed`（2 个测试） |
| 3 | `_cleanup_beliefs()` 方法 | ✅ 完成 | `TestCleanupBeliefs`（4 个测试） |
| 4 | `add_intention()` 内容去重 | ✅ 完成 | `TestAddIntentionDedup`（4 个测试） |
| 5 | 5 轮去重集成测试 | ✅ 完成 | `test_dedup_5_rounds_same_signal`（1 个测试） |
| 6 | `get_bdi_state()` 导出新字段 | ✅ 完成 | `TestBdiStateExport`（3 个测试） |

## 代码变更文件

| 文件 | 变更内容 |
|------|----------|
| `src/riskagent_backend/proactive_agents/base_models.py` | Belief 新增 `processed`/`processed_at` 字段；Intention 新增 `source_belief_id` 字段 |
| `src/riskagent_backend/proactive_agents/base.py` | `_deliberate()` 跳过已处理信念并标记；`_cleanup_beliefs()` 自动清理；`add_intention()` 内容去重；`get_bdi_state()` 导出新字段 |

## 验证结果

- **测试文件**：`tests/unit/test_bdi.py` + `tests/unit/test_deliberate_chain.py`
- **测试结果**：36/36 通过（12 原有 + 24 新增），无回归
- **运行命令**：`PYTHONPATH=src python -m pytest tests/unit/test_bdi.py tests/unit/test_deliberate_chain.py -v`

## 保留窗口策略

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_age_seconds` | 300s（5 分钟） | 已处理信念的保留时长，超时后从列表移除 |
| 信念列表上限 | 无硬上限 | 靠 `[-5:]` + `_cleanup_beliefs()` 联合控制，实际不会超过 10-15 条 |
| 意图列表上限 | 无硬上限 | 靠状态机 + 内容去重控制，`completed`/`failed` 的意图可定期清理 |

## 详情参考

完整的设计方案、缺陷根因分析、替代方案对比和未决问题详见 [RFC-006](../decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md)。
