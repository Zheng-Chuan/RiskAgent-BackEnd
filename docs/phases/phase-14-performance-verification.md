# Phase 14: 性能验证与 LLM 成本模型

## 状态

方向二十（LLM 成本模型）已完成；方向二十一（系统压测）、方向二十二（SLO 定义）已取消

## 背景

Phase 10 的 5 分钟主动监控全链路验证已于 2026-08-03 完成. 验证过程中收集到以下性能数据点:

- LLM 调用次数：133 次 / 5 分钟（deepseek/deepseek-chat）
- LLM 调用频率：约 26.6 次/分钟
- 监控循环间隔：SystemEngineer 30s, RiskAnalyst 45s, Orchestrator 60s, Critic 90s, Intent 120s
- 每轮监控循环可能触发：意图识别（1 次 LLM）+ 编排规划（1 次 LLM）+ 评审（1 次 LLM）+ ReAct 循环（3-5 次 LLM）
- Trace 记录：15 个 entry / 每次完整链路

当前缺乏以下关键能力：

1. **LLM 调用成本模型**：每次调用 token 消耗未量化，供应商定价（2026-08-07 规划时点为 OpenRouter 历史口径；2026-08-14 起为 DeepSeek 官方 + 硅基流动）未纳入计算，日/月成本估算缺失

> **Phase 10 验证暴露的可靠性问题**：信念累积（同一 Redis 异常在 10 轮感知循环中被重复处理）、LLM 调用频率线性增长（不做去重时 133 次/5min → ~38304 次/天）、成本模型缺失（无法量化主动监控的运行成本）. 详见 [RFC-006](../decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md) 的 Phase 10 验证发现.

## 核心目标

1. 建立 LLM 调用成本模型，量化主动监控的运行成本

## 时间盒与资源

- 时间: 3 周
- 优先级: 高
- 依赖: Phase 10 已完成 ✅, RFC-006 BDI 去重已完成 ✅（2026-08-07）

## 工作范围

### In Scope

- LLM 调用成本模型：量化每次 LLM 调用的 token 消耗（prompt tokens + completion tokens），建立成本预估表
- LLM 调用预算上限与熔断阈值定义，与 Phase 10 的 ProactiveBudget 治理集成

### Out of Scope

- 前端性能监控仪表盘：归属前端项目，本期仅保证后端数据可被消费
- LLM 模型选型优化：本期不更换模型，仅在当前 deepseek/deepseek-chat 基线上量化成本（Phase 14 时点口径；2026-08-14 起 Chat 已切换 DeepSeek 官方 `deepseek-v4-flash`）
- 系统压测与 SLO 定义：已取消，不纳入 Phase 14 范围

## 详细 Checkpoint

### 方向二十. LLM 成本模型

#### 目标

量化主动监控的 LLM 调用成本，建立可预测的成本预估模型和预算熔断机制.

- [x] Checkpoint 20.1.1 Token 消耗量化 ✅
  - 实现项: 在 LLM 调用链路中采集每次调用的 prompt tokens + completion tokens，按 Agent 角色和调用阶段分类统计
  - 验收方法: 运行一次完整监控链路，检查 token 统计记录与 LLM API 返回值一致（2026-08-07 验收时点为 OpenRouter，历史口径）
  - 验收证据: token 消耗明细表（按 Agent × 阶段维度）
  - 通过标准: 每次调用均有 token 消耗记录，统计值与 API 返回值偏差 < 1%
  - 实施结果: TokenUsageRecord 新增 agent_name + stage 字段，summary() 输出 by_agent_stage 维度聚合

- [x] Checkpoint 20.1.2 单次链路成本计算 ✅
  - 实现项: 基于供应商定价计算单次完整监控链路的平均 LLM 成本（意图识别 + 编排规划 + 评审 + ReAct 循环）（2026-08-07 实施时点为 OpenRouter 定价，历史口径）
  - 验收方法: 对比 5 次完整链路的实际成本与计算模型预估值
  - 验收证据: 成本计算模型 + 5 次实测对照表
  - 通过标准: 模型预估值与实际成本偏差 < 10%
  - 实施结果: cost_model.py 内置定价表（2026-08-07 实施时点为 OpenRouter 定价：deepseek/deepseek-chat: prompt $0.14/1M, completion $0.28/1M；2026-08-14 commit 06ea0ab 后更新为 DeepSeek 官方模型名定价 + BAAI/bge-m3 免费条目），calculate_call_cost() 成本不再为 0

- [x] Checkpoint 20.1.3 成本预估表 ✅
  - 实现项: 建立 5min / 1h / 24h / 7d 四个时间窗口的成本预估表，区分「有信念去重」和「无信念去重」两种场景
  - 验收方法: 对照 Phase 10 的 133 次/5min 实测数据验证 5min 预估准确性
  - 验收证据: 成本预估表（4 时间窗口 × 2 场景）
  - 通过标准: 5min 预估值与 Phase 10 实测值偏差 < 15%；去重场景成本降低 > 80%
  - 实施结果: generate_cost_estimate_table() 输出 5min/1h/24h/7d 四窗口，去重场景成本降低 80%（403 次/7d vs 2016 次/7d）

- [x] Checkpoint 20.1.4 预算上限与熔断阈值 ✅
  - 实现项: 定义 LLM 调用预算上限（5min / 1h / 24h 三级），超限触发熔断降级为纯规则处置
  - 验收方法: 注入高频异常信号触发预算超限，观察熔断行为
  - 验收证据: 预算配置文件 + 熔断触发 trace
  - 通过标准: 超限后 30s 内触发熔断；熔断后不产生 LLM 调用；与 ProactiveBudget 集成无旁路
  - 实施结果: CostCircuitBreaker 三级熔断（5min/1h/24h），集成 ProactiveBudgetManager，超限触发阻断

### 方向二十实施结果摘要

- **实施日期**: 2026-08-07
- **Checkpoint 完成情况**: 4 个 Checkpoint（20.1.1 ~ 20.1.4）全部完成
- **测试覆盖**: 24 个新增测试全部通过，742/747 现有测试无回归（2026-08-07 验收时点；成本相关测试现已扩至 37 个：cost_model 24 + cost_report 13）
- **关键成果**:
  1. 成本计算不再为 0 — cost_model.py 内置定价表（实施时点为 OpenRouter 定价，历史口径；2026-08-14 起为 DeepSeek 官方定价 + BAAI/bge-m3 免费条目），calculate_call_cost() 正确计算 prompt + completion 成本
  2. by_agent_stage 维度 — TokenTracker 新增 agent_name + stage 字段，支持按 Agent × 阶段聚合统计
  3. 三级熔断器 — CostCircuitBreaker 支持 5min/1h/24h 三级预算上限，超限触发熔断降级
  4. 成本预估表 — generate_cost_estimate_table() 输出 5min/1h/24h/7d 四窗口预估，区分去重/未去重场景
  5. API 端点 — 新增 /api/llm/cost-model 端点，支持查询成本模型和定价信息
  6. ProactiveBudget 集成 — CostCircuitBreaker 接入 ProactiveBudgetManager，与现有治理体系无旁路
- **新增文件**:
  - `src/riskagent_backend/llm/cost_model.py` — 定价表 + 成本计算 + 预估表
  - `src/riskagent_backend/governance/cost_circuit_breaker.py` — 三级成本熔断器
  - `tests/unit/test_cost_model.py` — 24 个测试用例
- **修改文件**:
  - `src/riskagent_backend/llm/token_tracker.py` — TokenUsageRecord 新增 agent_name + stage 字段
  - `src/riskagent_backend/server.py` — 新增 /api/llm/cost-model 端点
  - `src/riskagent_backend/governance/proactive_budget.py` — 集成 CostCircuitBreaker
  - `.env.example` — 新增 LLM_COST_PROMPT_PER_1K / LLM_COST_COMPLETION_PER_1K 配置项

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 成本模型定价与实际偏差 | 成本预估不准确 | 定期同步当前供应商定价表（现为 DeepSeek 官方 + 硅基流动）；使用 default 兜底定价 |

## 实施计划

| 阶段 | 内容 | 依赖 | 预计工时 |
|------|------|------|---------|
| P0 | LLM 成本模型（Checkpoint 20.1.x） | Phase 10 完成 ✅ | 1 周 |

核心原则：量化成本（P0）为主动监控提供成本可观测性.

## 分阶段中间验收标准

### P0 验收: LLM 成本模型

| 验收项 | 方法 | 通过标准 | 证据类型 |
|--------|------|---------|---------|
| Token 消耗量化 | 运行完整链路检查 token 记录 | 每次调用有 token 记录，偏差 < 1% | token 明细表 |
| 单次链路成本 | 5 次实测 vs 模型预估 | 偏差 < 10% | 成本对照表 |
| 成本预估表 | 对照 Phase 10 实测 | 5min 偏差 < 15% | 预估表 |
| 预算熔断 | 注入高频信号触发超限 | 30s 内触发熔断 | 熔断 trace |

关键中间结果: 成本预估表 + 预算熔断配置 是主动监控成本可观测性的核心交付物.

## 最终验收: LLM 成本模型

| 维度 | 内容 |
|------|------|
| 测试方法 | 完成 P0 全部 checkpoint，产出成本模型 + 预算熔断机制 |
| 通过标准 | LLM 成本模型偏差 < 10%；成本预估表覆盖 4 时间窗口；熔断器与 ProactiveBudget 集成无旁路 |
| 验收证据 | 成本预估表 + 熔断 trace + /api/llm/cost-model 端点响应 |

## 成功标准 (Exit Criteria)

- LLM 调用成本模型建立，单次链路成本预估偏差 < 10%
- 5min / 1h / 24h / 7d 四级成本预估表产出，区分去重/未去重场景
- LLM 调用预算上限和熔断阈值定义，与 ProactiveBudget 集成无旁路
- /api/llm/cost-model 端点可用，支持查询成本模型和定价信息

## 关联文档

- Phase 10: [phase-10-active-monitoring.md](./phase-10-active-monitoring.md)（已完成 — 全链路验证通过 2026-08-03）
- RFC-003: [../decisions/RFC-003-active-monitoring.md](../decisions/RFC-003-active-monitoring.md)（已完成）
- RFC-006: [../decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md](../decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md)（Accepted, Implemented — Phase 12 已完成 2026-08-07）
