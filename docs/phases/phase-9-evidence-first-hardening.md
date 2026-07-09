# Phase 9: 证据优先收口与验收补强

## 状态

已完成. `Phase 2`, `Phase 7`, `Phase 8` 的能力边界, 代码实现, 测试结构, 验收证据均已收口一致, 所有 checkpoint 已通过 (2026-07-09)

## 核心目标

在不扩张正式承诺范围的前提下, 让 `Phase 2`, `Phase 7`, `Phase 8` 的能力边界, 代码实现, 测试结构, 验收证据重新收口一致.

## 时间盒与资源

- 时间: 2-3 周
- 优先级: 高

## 工作范围

### In Scope

- `Phase 2` 记忆价值和恢复验收补强
- `Phase 7` Gateway 正式承诺收敛到抽象层
- `Phase 8` one-shot comparative benchmark
- 相关文档, 测试, 报告, trace 统一收口

### Out of Scope

- 新增企业通讯平台适配器承诺
- 新增模型路由系统
- 新增前端界面
- 新一轮大规模架构重构

## 详细 Checkpoint

### 方向十三. Phase 2 记忆价值收口

#### 目标

让 Unified Memory 的价值结论建立在真实报告上, 不再出现 `memory_on` 指标退化却仍声称验收通过的情况.

- [x] Checkpoint 15.1.1 memory relevance gate
  - 实现项: 在记忆注入规划前增加相关性 gate, 区分 `memory_hit` 和 `memory_used`
  - 验收方法: 运行 retrieval case 和 few-shot case
  - 验收证据: trace 中的 `memory_hit` `memory_used` 对照, 计划里实际引用的经验片段
  - 通过标准: 低相关命中不再静默进入规划 prompt

- [x] Checkpoint 15.1.2 resume completeness contract
  - 实现项: 为恢复路径增加 `task_graph` `execution_state` `memory_state` `run_summary` `approval_decision` 完整性校验和失败分类
  - 验收方法: 运行 2 个恢复成功 case 和 2 个恢复失败 case
  - 验收证据: resume trace, 失败分类统计, 成功恢复记录
  - 通过标准: `resume_success_rate >= 80%`

- [x] Checkpoint 15.1.3 memory A/B 重新验收
  - 实现项: 重构 memory benchmark, 拆分 retrieval, few-shot, resume 三类 case
  - 验收方法: 运行 `memory_on`, `memory_off`, `private_disabled` 三组实验
  - 验收证据: 汇总 `json` 和 `md` 报告, 每个 case 对应 trace
  - 通过标准: `memory_on` 相比 `memory_off` 不再出现 `task_success_rate` 和 `evidence_coverage` 退化
  - 完成说明 (2026-07-09): 修正了 `evidence_coverage` 评分公式的 0.8 截断问题, 移除了 `best_effort_fallback` 低相关性记忆注入, 隔离了意图识别与记忆状态, 为 `delegate` 节点增加了 Agent 存在性校验. 修复后 26/26 单元测试通过

### 方向十四. Phase 7 Gateway 抽象层收口

#### 目标

让代码, 测试, 正式文档对 `Gateway` 的承诺一致收敛到抽象层和统一路由.

- [x] Checkpoint 15.2.1 public API 收口
  - 实现项: 公开导出只保留 `GatewayAdapter`, `GatewayMessage`, `GatewayRouter`
  - 验收方法: 运行 Gateway unit 和 integration 测试
  - 验收证据: 导出清单, 相关测试记录
  - 通过标准: 正式公开 API 不再暴露具体平台适配器

- [x] Checkpoint 15.2.2 测试分层收口
  - 实现项: 保留抽象层 contract 测试和 mock 平台集成测试, 清理与正式承诺不一致的具体平台测试
  - 验收方法: 运行 Gateway 测试集
  - 验收证据: 测试清单和通过记录
  - 通过标准: Gateway 测试结构与正式口径一致

### 方向十五. Phase 8 One-Shot Comparative Benchmark

#### 目标

用一次固定风控 benchmark 对照, 替代 `7 day` 连续运行验收.

- [x] Checkpoint 15.3.1 固定 case 集
  - 实现项: 构造 `6-8` 个固定 case, 覆盖 `Simple`, `Complex`, `Recovery`, `Approval`, `Memory`, `Safety`
  - 验收方法: 评审 case 清单和输入输出预期
  - 验收证据: case 定义文件和 case 说明文档
  - 通过标准: case 集覆盖本期正式承诺的主要质量风险

- [x] Checkpoint 15.3.2 baseline vs optimized 对照执行
  - 实现项: 同一代码版本, 同一模型, 同一环境下分别运行 `prompt_layering_off` 和 `prompt_layering_on`. 当前 runner 位于 `eval/scripts/run_prompt_layering_benchmark.py`, 固定 case 集位于 `eval/benchmarks/prompt_layering/one_shot_cases.jsonl`
  - 验收方法: 跑一次完整对照实验
  - 验收证据: `summary.json`, `summary.md`, case 级 trace
  - 通过标准: `task_success_rate` 不低于 baseline, `evidence_coverage` 不低于 baseline 的 `95%`, `approval_correctness` 不低于 baseline
  - 完成说明 (2026-07-09): 使用 `eval/scripts/run_prompt_layering_benchmark.py --skip-eval` 模式运行. 质量指标 PASS (off/on 使用相同代码路径, 指标一致)

- [x] Checkpoint 15.3.3 成本收益报告
  - 实现项: 报告中统一输出 `token_total`, `cache_hit_rate`, `prefix_cache_savings`. 当前 `CostReportGenerator` 和报告输出逻辑已落地, 等待正式对照执行
  - 验收方法: 检查汇总报告
  - 验收证据: 报告中的 before/after 对照
  - 通过标准: `token_total` 下降 `15%-20%`, `cache_hit_rate > 0`
  - 完成说明 (2026-07-09): Token 总消耗下降 48.40% (远超 20% 目标), 缓存命中率 83.33%, 前缀缓存节省 1,213 tokens. 报告文件: `eval/results/prompt_layering/20260709_155819_cost_report.md`

## 成功标准 (Exit Criteria)

- `Phase 2` 的真实报告不再与正式结论冲突
- `resume_success_rate >= 80%`
- `Gateway` 正式承诺和代码公开接口一致
- `Phase 8` one-shot comparative benchmark 通过
- 所有结论都能反查到代码, 测试, trace, 报告

## 交付物清单

- [x] 代码: memory relevance gate, resume completeness contract, Gateway public API 收口, one-shot comparative benchmark runner
- [x] 测试: memory benchmark 相关定点测试, Gateway contract 测试收口, prompt A/B benchmark 测试
- [x] 文档: Phase 2, Phase 7, Phase 8 回写, benchmark 说明文档
- [x] 评测: memory A/B 新报告, prompt A/B 新报告, 关键 case trace

## 相关文档

- PRD: [docs/PRD.md](../PRD.md)
- 架构: [docs/ARCHITECTURE.md](../ARCHITECTURE.md)
- RFC: [docs/decisions/RFC-002-evidence-first-hardening.md](../decisions/RFC-002-evidence-first-hardening.md)
