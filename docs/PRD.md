# RiskAgent-BackEnd PRD

## 1. 文档目标

本文档是 RiskAgent-BackEnd 项目的产品需求总纲. 详细的分阶段规划, 技术决策和产品战略分别存放在独立文档中.

- **产品战略与客户价值**: [docs/STRATEGY.md](./STRATEGY.md)
- **技术决策记录**: [docs/decisions/](./decisions/)
- **分阶段详细规划**: [docs/phases/](./phases/)
- **架构设计**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md)
- **CI/CD 流水线**: [docs/ci-cd.md](./ci-cd.md)
- **记忆系统设计**: [docs/MEMORY.md](./MEMORY.md)
- **面试准备**: [docs/INTERVIEW.md](./INTERVIEW.md)
- **简历素材**: [docs/RESUME.md](./RESUME.md)
- **已知缺口登记**: [docs/KNOWN_ISSUES.md](./KNOWN_ISSUES.md)

---

## 2. 项目定位

把 RiskAgent-BackEnd 从"有骨架的多 Agent 工作流原型"升级为"简历表述和代码实现严格一致的可验证系统", 并在此基础上进一步升级为"自我改进的智能风控平台".

### 2.1 成功标准

- 简历中的每个关键能力都有对应代码模块, 测试, 文档, 评测样例
- 主流程必须形成 `intent -> retrieve planning memory -> orchestrator_plan -> critic_plan -> task_graph execution -> receipts approvals replan -> finalize -> persist and trace` 真实闭环
- 工具调用必须产出真实 receipt, 并被后续 Agent 消费
- 记忆必须在任务前检索, 任务中更新, 任务后沉淀, 并支持恢复执行
- 副作用动作必须在真实审批链上通过或被拒绝
- 评测体系必须以真实执行行为为基础, 不依赖默认值和启发式补分

### 2.2 非目标

- 做成通用办公 Agent
- 引入过重的分布式中间件
- 先做非常复杂的前端界面
- 追求海量工具数量

本期只做一件事: 让金融风控场景下的 Multi-Agent 闭环真实可运行, 可评测, 可解释, 可复盘.

---

## 3. 用户与场景

### 3.1 核心用户

- Risk Manager
- Desk Head
- 风控运营人员
- 平台研发和模型研发人员

### 3.2 核心场景

- 查询某 desk 当前头寸并分析 breach 原因
- 针对多 desk 异常同时排查, 自动拆分子任务并合并结论
- 对副作用动作 (写告警, 提交告警) 执行审批
- 根据历史类似案例和长期记忆给出更稳健的行动建议
- 在执行失败后基于上下文和回执恢复运行

---

## 4. 架构约束（绝对不变）

系统始终保持 Multi-Agent 架构, 绝不退化为单 Agent 系统.

- 多角色 Agent 体系不变 (IntentAgent, OrchestratorAgent, CriticAgent, SystemEngineerAgent, RiskAnalystAgent, ModeratorAgent)

> **角色命名约定**：上述为架构概念名；代码实现类为 `ProactiveIntentAgent` / `ProactiveOrchestratorAgent` / `ProactiveCriticAgent` 等（见 ARCHITECTURE.md §1 注记及 §4.10 完整映射）。
- Hermes 能力增强每个 Agent, 不是替代多 Agent 协作
- 统一执行内核不变: `intent -> orchestrator plan -> task_graph -> parallel delegation -> critic review -> finalize`
- 角色隔离不变: 独立 private memory, 独立推理链, 独立 RBAC

> 详见: [ADR-001: 多Agent架构](./decisions/ADR-001-multi-agent-architecture.md)

---

## 5. 核心里程碑

| 阶段 | 目标 | 状态 | 详情 |
| :--- | :--- | :--- | :--- |
| Phase 0 | 对齐与止血 | ✓ 完成 | [phase-0-alignment.md](./phases/phase-0-alignment.md) |
| Phase 1 | 真实执行闭环 | ✓ 完成 | [phase-1-execution-loop.md](./phases/phase-1-execution-loop.md) |
| Phase 2 | 记忆闭环和恢复执行 | ✓ 完成 | [phase-2-memory-closure.md](./phases/phase-2-memory-closure.md) |
| Phase 3 | 事件驱动和主动协作 | ✓ 完成 | [phase-3-event-driven.md](./phases/phase-3-event-driven.md) |
| Phase 4 | 评测和门禁生产化 | ✓ 完成 | [phase-4-evaluation.md](./phases/phase-4-evaluation.md) |
| Phase 5 | 技能自创闭环 | ✓ 完成 | [phase-5-skill-creation.md](./phases/phase-5-skill-creation.md) |
| Phase 6 | 记忆永久化与上下文压缩 | ✓ 完成 | [phase-6-memory-persistence.md](./phases/phase-6-memory-persistence.md) |
| Phase 7 | 调度与多平台 | ✓ 抽象层收口完成 | [phase-7-scheduling-gateway.md](./phases/phase-7-scheduling-gateway.md) |
| Phase 8 | 提示词优化与自我改进闭环 | ✓ 完成 | [phase-8-prompt-optimization.md](./phases/phase-8-prompt-optimization.md) |
| Phase 9 | 证据优先收口与验收补强 | ✓ 完成 | [phase-9-evidence-first-hardening.md](./phases/phase-9-evidence-first-hardening.md) |
| Phase 10 | 5min 主动感知与自主运维 | ✓ 完成 — 全链路验证通过（2026-08-03）（Checkpoint 16.4.1 部分实现，见 KI-003/KI-004） | [phase-10-active-monitoring.md](./phases/phase-10-active-monitoring.md) |
| Phase 11 | Skill 语义检索升级（向量库 + 远程 Embedding + Summary + Hybrid 检索 + Query Rewriting + skill_view） | ✓ Implemented — 6 项需求全部实施，158/158 测试通过（Phase 11 验收时点；当前 Skill 相关测试共 213 条，见 README），K8s 部署验证（2026-08-08）（生产主链未注入 Chroma，见 KI-002） | [phase-11-skill-semantic-retrieval.md](./phases/phase-11-skill-semantic-retrieval.md) |
| Phase 12 | BDI 信念去重与意图幂等性修复 | ✓ 完成 — 6 个 Checkpoint 全部实施，36 测试通过（2026-08-07） | [phase-12-bdi-belief-dedup.md](./phases/phase-12-bdi-belief-dedup.md), [RFC-006](./decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md) |
| Phase 13 | REST BFF 浏览器闭环与记忆可观测性 | ✓ 完成 — K8s 验收全部通过（2026-08-07） | [phase-13-rest-bff-bootstrap.md](./phases/phase-13-rest-bff-bootstrap.md) |
| Phase 14 | 性能验证与 LLM 成本模型 | ✓ 已完成 — LLM 成本模型 4 Checkpoint 完成，37 测试通过（test_cost_model 24 + test_cost_report 13，2026-08-07）；方向二十一（系统压测）、方向二十二（SLO 定义）已取消 | [phase-14-performance-verification.md](./phases/phase-14-performance-verification.md) |

---

## 6. 关键技术决策

| 决策 | 状态 | 文档 |
| :--- | :--- | :--- |
| 多Agent架构作为绝对约束 | Decided, Implemented | [ADR-001](./decisions/ADR-001-multi-agent-architecture.md) |
| TaskGraph DAG 调度设计 | Implemented | [ADR-002](./decisions/ADR-002-task-graph-design.md) |
| 统一记忆架构 | Implemented | [ADR-003](./decisions/ADR-003-unified-memory-design.md) |
| 零信任工具治理 | Implemented | [ADR-004](./decisions/ADR-004-tool-governance.md) |
| run_trace.v2 全链路追踪 | Implemented | [ADR-005](./decisions/ADR-005-run-trace-v2.md)（能力细节见 [ARCHITECTURE](./ARCHITECTURE.md) §1 Step 8） |
| Hermes 五柱升级提案 | Accepted and Implemented | [RFC-001](./decisions/RFC-001-hermes-upgrade.md) |
| Evidence-First 收口提案 | Accepted and Completed | [RFC-002](./decisions/RFC-002-evidence-first-hardening.md) |
| 5min 主动感知与自主运维架构 | Accepted, Completed | [RFC-003](./decisions/RFC-003-active-monitoring.md) |
| K8s 全量迁移 | Accepted, Implemented | [RFC-004](./decisions/RFC-004-k8s-migration.md) |
| Skill 语义检索升级（向量库 + 远程 Embedding + Summary + Hybrid + Query Rewrite + skill_view） | Accepted, Implemented | [RFC-005](./decisions/RFC-005-skill-semantic-retrieval-upgrade.md) |
| BDI 信念去重与意图幂等性修复 | Accepted, Implemented | [RFC-006](./decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md) |
| LLM 成本模型与三级熔断 | Implemented | [Phase 14 方向二十](./phases/phase-14-performance-verification.md) |

---

## 7. 功能需求清单

| 编号 | 需求 | 关联阶段 |
| :--- | :--- | :--- |
| FR-1 | 系统必须支持任务图级规划和执行 | [Phase 1](./phases/phase-1-execution-loop.md) |
| FR-2 | 系统必须支持真实工具调用回执 | [Phase 1](./phases/phase-1-execution-loop.md) |
| FR-3 | 系统必须支持 step 级审批和恢复 | [Phase 3](./phases/phase-3-event-driven.md) |
| FR-4 | 系统必须支持消息驱动协作 | [Phase 3](./phases/phase-3-event-driven.md) |
| FR-5 | 系统必须支持语义记忆检索和经验沉淀 | [Phase 2](./phases/phase-2-memory-closure.md) |
| FR-6 | 系统必须支持任务失败后的恢复执行 | [Phase 2](./phases/phase-2-memory-closure.md) |
| FR-7 | 系统必须支持 trace 回放 | [Phase 1](./phases/phase-1-execution-loop.md) |
| FR-8 | 系统必须支持基于真实行为事件的评测 | [Phase 4](./phases/phase-4-evaluation.md) |
| FR-9 | Skill 必须支持向量库存储与远程模型语义检索 | [RFC-005](./decisions/RFC-005-skill-semantic-retrieval-upgrade.md) |
| FR-10 | Skill 检索必须通过远程调用 embedding 模型（硅基流动 BAAI/bge-m3）计算语义相似度（现状：主链向量通道未启用，见 KI-002） | [RFC-005](./decisions/RFC-005-skill-semantic-retrieval-upgrade.md) |
| FR-11 | 每个 Skill 必须包含一句话摘要字段，用于与 task 描述做语义比对 | [RFC-005](./decisions/RFC-005-skill-semantic-retrieval-upgrade.md) |
| FR-12 | BDI 监控循环中同一信念不得重复生成意图，已处理的信念必须被标记跳过 | [RFC-006](./decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md) |
| FR-13 | `add_intention` 必须对相同 description+tool_params 的 pending 意图做内容去重 | [RFC-006](./decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md) |
| FR-14 | 监控循环每轮必须清理已处理且超过保留时长的信念，防止信念列表无限膨胀 | [RFC-006](./decisions/RFC-006-bdi-belief-dedup-intention-idempotency.md) |
| FR-15 | 系统必须提供浏览器友好的 memory REST BFF 视图接口 | [Phase 13](./phases/phase-13-rest-bff-bootstrap.md) |
| FR-16 | memory 对外输出必须经过结构化映射与脱敏处理, 不直接暴露 Redis 原始结构 | [Phase 13](./phases/phase-13-rest-bff-bootstrap.md) |
| FR-17 | 系统必须提供浏览器友好的 SSE 事件流接口, 实时推送智能体状态与记忆视图 | [Phase 13](./phases/phase-13-rest-bff-bootstrap.md) |
| FR-18 | 系统必须提供浏览器友好的 TaskGraph REST BFF 视图接口 | [Phase 13](./phases/phase-13-rest-bff-bootstrap.md) |
| FR-19 | 系统必须通过 SSE 实时推送任务级 TaskGraph 快照 | [Phase 13](./phases/phase-13-rest-bff-bootstrap.md) |

---

## 8. 非功能需求

- NFR-1: 所有关键状态都必须可持久化
- NFR-2: 所有副作用动作都必须可审计
- NFR-3: 所有最终结论都必须可追溯到输入, receipt 或 memory
- NFR-4: 评测结果必须可复现
- NFR-5: 每个阶段都要有单测, 集成测试, benchmark 样例

---

## 9. 风险与取舍

### 主要风险

- 引入任务图和事件驱动后, 系统复杂度会显著上升
- 记忆系统一旦做错, 会带来错误迁移和错误强化
- 过度主动性会造成噪声事件和成本失控
- 技能噪音: 低质量 Skill 污染规划, 导致决策退化
- 持久化迁移: Redis -> DB 迁移期间的数据一致性风险

### 设计取舍

- 优先把真实执行闭环做通, 再扩充 Agent 数量
- 优先做金融风控高价值场景, 不追求通用性
- 优先保证 trace 和评测可信, 再追求漂亮指标
- 优先做可恢复和可审批, 再追求极致自治
- 优先做技能自创闭环, 这是 Hermes 最核心的差异化能力

---

## 10. 发布准入标准

以下条件同时满足, 才允许对外按照简历口径讲完整能力:

- `intent -> retrieve planning memory -> orchestrator_plan -> critic_plan -> task_graph execution -> receipts approvals replan -> finalize -> persist and trace` 已在代码和 benchmark 中成立
- 真实工具调用, 审批, 回执, 恢复都有 case 证明
- 记忆检索已经真实参与规划和恢复
- 评测结果中关键计数项全部来自真实事件
- README, ARCHITECTURE, PRD 的能力口径保持一致
- 浏览器可通过 REST 和 SSE 读取真实执行的 TaskGraph DAG 快照

---

## 11. Hermes 升级状态与成功标准

当前代码对 Hermes 五柱的实际落地状态如下:

- 技能自创闭环: 已接入主链并完成核心测试
- 永久化记忆与上下文压缩: 已实现主链能力, A/B 退化已修复 (Phase 9 Checkpoint 15.1.3 已通过)
- 内置调度系统: 调度库层已实现、生产未挂载（见 KNOWN_ISSUES KI-001；现状注记权威处为 ARCHITECTURE §12.2）
- 多平台网关: 正式承诺收敛为 `GatewayAdapter` 抽象层与统一路由. 代码库当前仍保留兼容性平台适配器实现, 但不作为对外交付承诺
- 提示词优化与自我改进闭环: 三层 prompt 分离已实现, 对照实验已完成, 实测数据见 [CHANGELOG 2026-07-09「Phase 9 收口」P0-3 小节](../CHANGELOG.md#phase-9-收口---2026-07-09)（证据文件未入库、不可复核，见 KNOWN_ISSUES KI-011）

Hermes 五柱升级（Phase 5-8）已完成（与 STRATEGY.md 口径一致），实测结果见下表及 STRATEGY.md FAQ「Hermes 升级的 ROI 是什么？」。以下为历史验收标准及其达成状态：

| 标准 | 状态 |
|------|------|
| 系统具备从执行经验中自动创建和改进 Skill 的能力 | ✅ Phase 5 完成 |
| 关键记忆跨会话永久保存, 不因 Redis 重启而丢失 | ✅ Phase 6 完成 |
| 支持自然语言定义的定时风控任务 | ⚠️ 调度库层已实现、生产未挂载（见 KI-001，现状注记权威处 ARCHITECTURE §12.2） |
| 正式能力口径只承诺 GatewayAdapter 抽象层和统一路由 | ✅ Phase 7 口径已收敛 |
| LLM token 成本较当前下降 20% 以上 | ✅ 已达成（Phase 8）——实测数据见 [CHANGELOG 2026-07-09「Phase 9 收口」P0-3 小节](../CHANGELOG.md#phase-9-收口---2026-07-09)（不可复核，详见 KI-011） |
| 自我改进结论可通过单次成组对照验收稳定复现 | ⚠️ Phase 8 完成单次对照实验 PASS，未做多次重跑验证“稳定复现”；且证据文件未入库（KI-011） |
| 所有新增能力都接入统一执行内核, 不形成旁路 | ⚠️ KI-003：remediation 动作绕过统一执行内核（不经五道关卡、无 receipt）；另调度能力未挂载=未接入（KI-001） |

> **口径收敛说明**：五柱中四柱已完整交付并通过验收；调度柱库层已实现、生产未挂载，该缺口如实登记于 KNOWN_ISSUES.md（KI-001，现状注记权威处为 ARCHITECTURE §12.2），不影响其他四柱的完成判定。

---

## 12. 相关文档

- [产品战略 (PR/FAQ)](./STRATEGY.md)
- [架构设计](./ARCHITECTURE.md)
- [技术决策](./decisions/)
- [分阶段规划](./phases/)
- [CI/CD 流水线](./ci-cd.md)
- [记忆系统设计](./MEMORY.md)
- [面试准备](./INTERVIEW.md)
- [简历素材](./RESUME.md)
- [已知缺口登记](./KNOWN_ISSUES.md)
- [README](../README.md)
