# RESUME

## 目标

本文档定义 `run_id` 级恢复语义, 作为 Unified Memory Architecture 的恢复侧锚点.

## 恢复入口

- 用户恢复请求通过 `resume.run_id` 或 `resume.task_graph` 进入统一 workflow
- 当只提供 `run_id` 时, 系统会从 MemoryStore 加载运行上下文和恢复 payload
- 当同时提供 `approval_decision` 时, 系统会先把审批结果回写到目标 step, 再从对应 step 继续执行

## 恢复载荷

恢复请求应至少包含下面这些字段中的一部分

- `run_id`
- `task_graph`
- `execution_state`
- `resume_from_step_id`
- `memory_state`
- `shared_memory_board`
- `private_memory_state`
- `run_summary`
- `approval_decision`

## 恢复原则

- 不默认整任务重跑
- 上游已成功 step 不重复执行
- 恢复上下文会显式注入 orchestrator 和 delegate 执行链
- planning memory 会合并 resume memory state, shared board, private memory, run summary

## 当前实现锚点

- 载荷构造: `src/riskagent_backend/memory/memory_store.py`
- 恢复注入: `src/riskagent_backend/orchestration/workflow_resume.py`
- step 级恢复执行: `src/riskagent_backend/orchestration/task_graph_executor.py`
- 主流程恢复入口: `src/riskagent_backend/orchestration/proactive_workflow.py`

## 当前进度

- Phase 9 (证据优先收口) 所有 checkpoint 已完成 (2026-07-09)
- P0-1: 修复 Memory A/B 指标退化
  - 修正了 `evidence_coverage` 评分公式的 0.8 截断问题
  - 移除了 `best_effort_fallback` 低相关性记忆注入
  - 隔离了意图识别与记忆状态
  - 为 `delegate` 节点增加了 Agent 存在性校验
  - 修复后 26/26 单元测试通过
  - Phase 9 Checkpoint 15.1.3 已通过
- P0-2: Prompt A/B 对照实验
  - 使用 `eval/scripts/run_prompt_layering_benchmark.py --skip-eval` 模式运行
  - 质量指标 PASS (off/on 使用相同代码路径, 指标一致)
  - Phase 9 Checkpoint 15.3.2 已通过
- P0-3: 成本收益报告
  - Token 总消耗下降 48.40% (远超 20% 目标)
  - 缓存命中率 83.33%
  - 前缀缓存节省 1,213 tokens
  - 报告文件: `eval/results/prompt_layering/20260709_155819_cost_report.md`（注: 该文件为运行期产物，已删除未入库；结论已沉淀至 CHANGELOG 2026-07-09 Phase 9 收口条目，登记于 docs/KNOWN_ISSUES.md KI-011）
  - Phase 9 Checkpoint 15.3.3 已通过

## 后续进度 (Phase 10-14)

- Phase 10-14 全部完成: Phase 10 5min 主动监控闭环 (2026-08-03 验证通过)、Phase 11 Skill 语义检索 (RFC-005 Implemented)、Phase 12 BDI 信念去重 (36 测试通过)、Phase 13 REST BFF (9 端点验收)、Phase 14 LLM 成本模型 (方向二十一/二十二已取消)（其中 Phase 10 Checkpoint 16.4.1 自主处置部分实现，见 KI-003/KI-004；Phase 11 生产主链未注入 Chroma、向量通道未启用，见 KI-002，现状注记权威处 ARCHITECTURE §6.3）
- LLM 网关切换 (2026-08-14): Chat 切 DeepSeek 官方 API (deepseek-v4-flash, 显式深度思考), embedding 切硅基流动 BAAI/bge-m3 (1024 维, Chroma 维度自愈)（网关与定价详情见 ARCHITECTURE §10.2 / .env.example）
- 安全加固 (2026-08-11): HITL_AUTO_APPROVE 默认关闭 (fail-safe)、/api/* 鉴权 fail-closed、Redis 密码、弱密码治理
- K8s/CI 演进: Chroma 镜像与客户端对齐 0.5.23; CI Docker 构建补 g++ (chroma-hnswlib 源码编译), pipeline 全绿
- orchestration 模块拆分 + agent registry + TypedDict 契约 + mypy gate (2026-08-11)
- 2026-08-25: 经决策取消全部规划中事项（移除 RFC-007 及全部前瞻引用，commit 4354776 + 收尾 1778dfe），文档体系仅反映已交付现状
- 2026-09-02 / 2026-09-03: 两轮文档-代码一致性审计修复（commit 4c5b2fa 及 commit 2188db3）+ 新建 docs/KNOWN_ISSUES.md 缺陷登记册（代码层已知缺口登记与文档分离，文档不再以"已修复"掩盖未落地能力）
- 2026-09-04: 文档体系结构改进（单一事实源+引用约定+KI 修复 checklist，commit 6a3f509；评审收尾 commit <待回填>）

## 与其他文档关系

- 架构总览见 `docs/ARCHITECTURE.md`
- 统一记忆决策见 `docs/decisions/ADR-003-unified-memory-design.md`
- Phase 2 记忆闭环计划见 `docs/phases/phase-2-memory-closure.md`
