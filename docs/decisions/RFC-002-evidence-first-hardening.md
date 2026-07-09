# RFC-002: Evidence-First Hardening Round

**状态**: Accepted and Completed  
**日期**: 2026-06-27  
**作者**: RiskMonitor-MultiAgent 项目组

## Motivation / 动机

当前项目已经完成了一轮主链收口, 但文档审计暴露出 3 类问题:

1. `Phase 2` 的核心能力已经实现, 但真实 A/B 报告没有证明 `memory_on` 优于 `memory_off`
2. `Phase 7` 的正式文档口径已经收敛为 `GatewayAdapter` 抽象层和统一路由, 但代码形态仍保留具体平台适配器暴露, 容易制造误解
3. `Phase 8` 的核心模块已经实现, 但原来的 `7 day` 连续运行验收不适合当前阶段, 需要替换为一次可复现的成组对照验收

这一轮不追求新增愿景功能, 而是做 `evidence-first` 的工程收口:

- 让 `Phase 2` 的价值结论和真实报告一致
- 让 `Phase 7` 的代码形态和正式承诺一致
- 让 `Phase 8` 的结论可以通过一次固定 benchmark 稳定得出

## Goals / 目标

- 让 `Phase 2` 的正式验收重新建立在真实指标之上
- 让 `Phase 7` 的对外交付边界收敛到抽象层和统一路由
- 让 `Phase 8` 拥有一次可复现的 one-shot comparative benchmark
- 让所有结论都能反查到代码, 测试, trace, 报告 4 类证据

## Non-Goals / 非目标

- 不新增新的平台适配器承诺
- 不在本轮引入新的外部模型路由策略
- 不做前端界面或可视化产品化
- 不重新设计 Phase 0 到 Phase 8 的总体架构

## Proposal / 提案概述

本轮优化拆成 3 条并行主线:

### 主线一. Phase 2 记忆价值收口

把重点从 "记忆模块存在" 转为 "记忆确实提升结果且不造成退化".

计划做法:

- 增加 `memory relevance gate`, 只把与当前任务高相关的经验注入规划链路
- 把 `few-shot reuse` 和 `shared memory recall` 的命中逻辑分开记录, 避免单一命中指标掩盖质量退化
- 增加 `resume payload completeness` 检查, 明确恢复失败到底是检索失败, 上下文缺失, 还是执行状态丢失
- 构造一组更聚焦的 memory benchmark, 分别验证 `retrieval quality`, `few-shot usefulness`, `resume success`

预期结果:

- `memory_on` 相比 `memory_off` 不再出现 `task_success_rate` 和 `evidence_coverage` 退化
- `resume_success_rate` 有明确提升路径和可复现实验

### 主线二. Phase 7 Gateway 抽象层收口

把项目正式承诺彻底收敛为 `GatewayAdapter` 抽象层, `GatewayMessage`, `GatewayRouter`, 以及统一执行入口.

计划做法:

- 把具体平台适配器从公开 API 中移除
- 保留抽象层, 路由层, 消息归一化契约
- 更新测试分层, 只保留抽象层契约测试和 mock 平台集成测试
- 在文档中明确 "具体平台适配器不是本轮正式验收项"

预期结果:

- 文档, 代码, 测试对 `Phase 7` 的描述一致
- 项目对外只承诺 `GatewayAdapter` 抽象层和统一路由

### 主线三. Phase 8 One-Shot Comparative Benchmark

用一次固定 benchmark 对照替代 `7 day` 连续运行验收.

计划做法:

- 构造 `6-8` 个固定风控 case, 覆盖 `Simple`, `Complex`, `Recovery`, `Approval`, `Memory`, `Safety`
- 同一代码版本, 同一模型, 同一环境下分别运行 `prompt_layering_off` 和 `prompt_layering_on`
- 统一输出 `json` 和 `md` 报告
- 统一输出关联 trace 路径, 便于审计和回放

核心指标:

- `task_success_rate`
- `evidence_coverage`
- `approval_correctness`
- `token_total`
- `cache_hit_rate`
- `prefix_cache_savings`

通过标准:

- `task_success_rate` 不低于 baseline
- `evidence_coverage` 不低于 baseline 的 `95%`
- `approval_correctness` 不低于 baseline
- `token_total` 下降 `15%-20%`
- `cache_hit_rate > 0`

## Detailed Design / 详细设计

### 1. Phase 2 记忆收口设计

#### 1.1 Retrieval Gate

在记忆注入前增加显式相关性判定:

- query 和 memory entry 按 `intent`, `risk domain`, `tool context`, `failure boundary` 做匹配
- 低相关命中只记录到 trace, 不进入 few-shot 注入
- trace 中区分 `memory_hit` 和 `memory_used`

#### 1.2 Resume Completeness Contract

恢复路径增加完整性校验:

- 必须检查 `task_graph`, `execution_state`, `memory_state`, `run_summary`, `approval_decision`
- 任一关键字段缺失时, trace 明确记录失败分类
- 为 `resume_success_rate` 提供稳定的失败归因

#### 1.3 Evidence Benchmark Split

memory benchmark 拆成 3 类:

- `memory_retrieval_case`
- `memory_few_shot_case`
- `memory_resume_case`

每类单独统计, 防止单一聚合结果掩盖问题

### 2. Phase 7 Gateway 收口设计

#### 2.1 Public API Contract

公开导出只保留:

- `GatewayAdapter`
- `GatewayMessage`
- `GatewayRouter`

具体平台适配器不再属于公开 API

#### 2.2 Test Contract

保留 2 类测试:

- 抽象层 contract 测试
- mock 平台集成测试

移除或降级与正式承诺不一致的具体平台适配器测试

### 3. Phase 8 Benchmark 设计

#### 3.1 固定 Case 集

建议首版构造以下 6 个 case:

1. 简单仓位查询
2. 复杂风险汇总
3. 副作用审批流程
4. 失败后恢复执行
5. 历史经验复用
6. 安全拒绝场景

#### 3.2 报告结构

输出文件:

- `eval/results/prompt_layering/<timestamp>_summary.json`
- `eval/results/prompt_layering/<timestamp>_summary.md`
- `eval/results/prompt_layering/<timestamp>_cost_report.md`
- 每个 case 对应 trace 路径

报告中必须同时给出:

- baseline 指标
- optimized 指标
- delta
- 结论

## Alternatives / 替代方案

### 方案 A. 继续沿用旧口径

优点:

- 不需要新增文档和验收资产

缺点:

- `Phase 2` 和 `Phase 8` 的结论继续缺少可信证据
- `Phase 7` 的代码和文档继续不一致

结论:

- 不采用

### 方案 B. 只修文档不修代码

优点:

- 成本低

缺点:

- 无法解决 `Phase 2` 指标退化
- 无法让 `Phase 7` 的代码形态真正收敛
- `Phase 8` 仍然缺少真实对照结果

结论:

- 不采用

## Risks / 风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 记忆相关性 gate 过严导致复用下降 | 中 | 中 | 先保守上线, 保留 trace 对照 |
| Gateway 收口影响现有兼容性用法 | 中 | 中 | 先移出公开导出, 再清理调用点 |
| one-shot benchmark case 设计不合理 | 中 | 高 | 固定 case 集, 同模型同环境, 强制保留 trace |

## Rollout / 推进顺序

1. 先完成本 RFC 和 `Phase 9` 文档评审
2. 再按 `Phase 2 -> Phase 7 -> Phase 8` 的顺序编码
3. 最后统一运行 benchmark 和验收

## Acceptance / 验收原则

- 文档先行
- 代码和文档同 PR
- 验收以真实报告为准
- 结论必须能反查到 trace

## Update Log

- 2026-07-09: Phase 9 所有 8 个 checkpoint 全部通过。Memory A/B 退化已修复（evidence_coverage 评分公式修正、best_effort_fallback 移除、意图识别隔离、delegate 存在性校验）。Prompt A/B 对照实验完成。成本收益报告生成（Token 下降 48.40%）。
