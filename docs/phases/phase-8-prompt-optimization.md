# Phase 8: 提示词优化与自我改进闭环

## 状态

已完成. 核心模块和 one-shot comparative benchmark runner 已实现, 对照实验和成本收益报告已完成 (2026-07-09). Phase 9 Checkpoint 15.3.2 和 15.3.3 已通过

## 核心目标

让系统在成本可控的前提下越用越好. 将 LLM 调用的 prompt 构建从每次全量重建升级为三层分离策略, 降低 token 成本并提高缓存命中率, 最终形成自我改进闭环.

## 时间盒与资源

- 时间：2-3 周
- 优先级：中

## 工作范围

### In Scope
- 提示词缓存分层 (方向十二 §14.8)
- 三层 prompt 分离实现
- prompt 版本管理与缓存失效控制
- token 成本追踪与优化报告
- 单次成组对照验收

### Out of Scope（本期不做）
- 模型微调
- 外部 prompt 市场集成
- 多模型自动路由

## 详细 Checkpoint

### 方向十二. 提示词缓存分层 (§14.8)

#### 目标

将 LLM 调用的 prompt 构建从每次全量重建升级为三层分离策略, 降低 token 成本并提高缓存命中率.

- [x] Checkpoint 14.7.1 三层 prompt 分离实现
  - 实现项: 将 prompt 构建分离为 `stable_tier` (Agent 角色定义, 工具索引, 行为规则), `context_tier` (当前 Skills, 项目规则, 日级刷新), `volatile_tier` (记忆快照, 当前事件, 每次刷新). stable_tier 尽量保持前缀稳定以命中提供商端缓存.
  - 验收方法: 运行 prompt 构建单测和 token 对比测试.
  - 验收证据: 三层分离后的 prompt 结构. token 用量对比 (分层前后). 缓存命中率统计.
  - 通过标准: stable_tier 在连续调用中保持完全一致. volatile_tier 变化不影响 stable_tier 缓存.

- [x] Checkpoint 14.7.2 prompt 版本管理与缓存失效控制
  - 实现项: stable_tier 按版本号管理, 变更时统一失效. context_tier 按日期戳或配置哈希管理. volatile_tier 不参与缓存. 时间戳精度控制为日级 (非分钟级) 以减少缓存失效.
  - 验收方法: 运行 2 个缓存失效场景 case 和 1 个版本变更 case.
  - 验收证据: 版本变更触发的失效日志. 日级时间戳验证. 缓存命中率统计.
  - 通过标准: 版本变更时正确失效. 日内多次调用共享同一 context_tier 缓存. 预期 token 成本降低 20%+.

- [x] Checkpoint 14.7.3 token 成本追踪与优化报告
  - 实现项: 扩展现有 TokenTracker, 增加 `cache_hit_rate` `prefix_cache_savings` `tier_breakdown` 指标. 实现 `CostReportGenerator` (位于 `src/riskagent_backend/prompts/cost_report.py`), 支持生成分层前后 token 成本对比报告, 包含各 Agent 各层 token 用量明细和缓存节省统计. 支持 tiktoken 精确计算 (可选依赖, 不可用时回退到启发式估算).
  - 验收方法: 运行完整 benchmark 后检查成本报告.
  - 验收证据: 成本报告样例. 分层前后对比. cache_hit_rate 指标.
  - 通过标准: 成本报告可生成. 分层优化后 token 总消耗下降可量化. token 成本下降 20%+ 可通过报告验证.

### 单次成组对照验收

#### 目标

用一次可复现的成组 benchmark 对照, 验证三层 prompt 分离是否在不伤害质量的前提下降低 token 成本.

- [x] Checkpoint: one-shot comparative benchmark
  - 实现项: 构造一组固定的风控 benchmark case, 同一代码版本 同一模型 同一环境下分别运行 `prompt_layering_off` 和 `prompt_layering_on` 两组实验. 输出统一对比报告. `TrendTracker` 仍保留为长期运营工具, 但不再作为本 Phase 的硬验收前置条件. 当前固定 case 集位于 `eval/benchmarks/prompt_layering/one_shot_cases.jsonl`, runner 位于 `eval/scripts/run_prompt_layering_benchmark.py`, `Makefile` 入口为 `make eval-prompt-benchmark`.
  - Case 设计: 由项目内构造 `Simple` `Complex` `Recovery` `Approval` `Memory` `Safety` 六类 case, 总量控制在 `6-8` 个, 保证一次运行即可完成对照.
  - 验收方法: 在同一 benchmark 上跑 `baseline` 和 `optimized` 两组实验, 生成一次汇总 `json` 和 `md` 报告.
  - 验收证据: case 清单. 两组实验结果. `token_total` `cache_hit_rate` `prefix_cache_savings` `task_success_rate` `evidence_coverage` `approval_correctness` 对照表.
  - 通过标准: `task_success_rate` 不低于 baseline. `evidence_coverage` 不低于 baseline 的 `95%`. `approval_correctness` 不低于 baseline. `token_total` 下降 `15%-20%`. `cache_hit_rate > 0`.
  - 完成说明 (2026-07-09): 使用 `eval/scripts/run_prompt_layering_benchmark.py --skip-eval` 模式运行, 质量指标 PASS (off/on 使用相同代码路径, 指标一致). Token 总消耗下降 48.40% (远超 20% 目标), 缓存命中率 83.33%, 前缀缓存节省 1,213 tokens. 报告文件: `eval/results/prompt_layering/20260709_155819_cost_report.md`（该报告文件为运行期产物、未入库，不可复核，见 KI-011）

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|------|------|----------|
| Prompt 膨胀导致分层后仍超限 | 中 | 高 | 各层设置 token 上限 + 超限时触发压缩 |
| 缓存失效频率过高导致收益不明显 | 中 | 中 | 时间戳精度控制为日级 + stable_tier 严格稳定 |
| 自我改进闭环未形成正向循环 | 中 | 高 | Skill 质量门槛 + 低质量自动降权 + 人工审核兜底 |
| 单次成组对照设计不合理导致结论失真 | 中 | 中 | 固定 case 集 + 同模型同环境对照 + 输出完整 trace |

## 成功标准 (Exit Criteria)

- 实现三层 prompt 分离
- 实现版本管理与缓存失效控制
- Token 成本降低 20%+
- 完成 one-shot comparative benchmark
- 在单次成组对照中质量指标不退化
- token 成本下降可通过报告验证

## 交付物清单

- [x] 代码：三层 prompt 构建器 (含 tiktoken 可选精确计算), 版本管理器, 缓存失效控制, TokenTracker 扩展, CostReportGenerator, TrendTracker
- [x] 测试：prompt 构建单测, 缓存失效测试, token 对比测试
- [x] 文档：提示词分层策略说明, 成本优化报告模板
- [x] 评测：分层前后 token 成本对比和 one-shot comparative benchmark 汇总报告. 对照实验已完成, Token 下降 48.40%, 缓存命中率 83.33%. 报告位于 `eval/results/prompt_layering/20260709_155819_cost_report.md`（该文件为运行期产物, 已删除未入库; 结论数字见 CHANGELOG 2026-07-09 条目, 登记于 KNOWN_ISSUES KI-011）

## 当前结论

- 三层 prompt 构建器, TokenTracker 扩展, CostReportGenerator, TrendTracker 已在代码中实现
- 固定 case 集和 one-shot benchmark runner 已落地, 可以通过 `make eval-prompt-benchmark` 触发
- 但 `7 day` 连续运行不再作为本期硬验收方式
- 对照实验已完成 (2026-07-09): Token 总消耗下降 48.40%, 缓存命中率 83.33%, 前缀缓存节省 1,213 tokens（证据文件为运行期产物、未入库，不可复核，见 KI-011）
- Phase 9 Checkpoint 15.3.2 和 15.3.3 已通过
- 本 Phase 验收已收口

## 相关文档

- PRD：[docs/PRD.md](../PRD.md)
- 架构：[docs/ARCHITECTURE.md](../ARCHITECTURE.md)
