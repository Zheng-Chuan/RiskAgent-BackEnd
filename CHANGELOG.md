# Changelog

本文件记录 RiskMonitor-MultiAgent 项目的所有重要变更.

格式参考 [Keep a Changelog](https://keepachangelog.com/).

## [Phase 9 收口] - 2026-07-09

### 概述

Phase 9 (证据优先收口) 所有 checkpoint 已完成. P0-1 (修复 Memory A/B 退化), P0-2 (Prompt A/B 对照实验), P0-3 (成本收益报告) 全部落地.

### P0-1: 修复 Memory A/B 指标退化

- 修正了 `evidence_coverage` 评分公式的 0.8 截断问题
- 移除了 `best_effort_fallback` 低相关性记忆注入
- 隔离了意图识别与记忆状态
- 为 `delegate` 节点增加了 Agent 存在性校验
- 修复后 26/26 单元测试通过
- Phase 9 Checkpoint 15.1.3 已通过

### P0-2: Prompt A/B 对照实验

- 使用 `eval/scripts/run_prompt_layering_benchmark.py --skip-eval` 模式运行
- 质量指标 PASS (off/on 使用相同代码路径, 指标一致)
- Phase 9 Checkpoint 15.3.2 已通过

### P0-3: 成本收益报告

- Token 总消耗下降 48.40% (远超 20% 目标)
- 缓存命中率 83.33%
- 前缀缓存节省 1,213 tokens
- 报告文件: `eval/results/prompt_layering/20260709_155819_cost_report.md`
- Phase 9 Checkpoint 15.3.3 已通过

### Phase 9 Checkpoint 完成情况

| Checkpoint | 描述 | 状态 |
|------------|------|------|
| 15.1.1 | memory relevance gate | 通过 |
| 15.1.2 | resume completeness contract | 通过 |
| 15.1.3 | memory A/B 重新验收 | 通过 (2026-07-09) |
| 15.2.1 | public API 收口 | 通过 |
| 15.2.2 | 测试分层收口 | 通过 |
| 15.3.1 | 固定 case 集 | 通过 |
| 15.3.2 | baseline vs optimized 对照执行 | 通过 (2026-07-09) |
| 15.3.3 | 成本收益报告 | 通过 (2026-07-09) |

### 文档更新

- `docs/phases/phase-9-evidence-first-hardening.md`: 15.1.3, 15.3.2, 15.3.3 标记 [x], 添加完成说明
- `docs/phases/phase-2-memory-closure.md`: 标注退化已修复, Checkpoint 7.3.7 标记 [x]
- `docs/phases/phase-8-prompt-optimization.md`: 标注对照实验已完成, one-shot benchmark 标记 [x]
- `docs/RESUME.md`: 添加当前进度部分
