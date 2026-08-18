# RFC-007: 治理与能力追赶路线（治理可信度生产准入）

| 字段 | 值 |
|------|-----|
| Status | Accepted, Not Implemented |
| Date | 2026-08-18 |
| Author | RiskAgent-BackEnd 项目组 |

## Update Log

| 日期 | 变更 |
|------|------|
| 2026-08-18 | 初始立项。确立治理可信度五项准入门槛、三态灰度策略、P0/P1/P2 追赶路线与性能预算。状态 Accepted, Not Implemented，尚未动工实施 |

> **口径声明**：本 RFC 全部章节以「决策/规划」口径书写。文中所有代码锚点仅用于描述**现状缺口**，不代表对应治理能力已经实施。治理五项（分级审批 / 独立验证器 / 可回滚 / pass^k 一致性 / 注入防御）在本 RFC 立项时点均为 **Not Implemented**。

## 1. 上下文与动机

金融风控场景的生产准入门槛是**治理可信度**。自愈能力再强，若治理不可信，就不敢上生产。我们给出五项硬性准入条件，**五项不齐，自愈能力一律不得进入生产执行路径**：

1. **分级审批**：按风险等级决定放行 / 单审批 / 强制人工，而非全有全无的单一开关。
2. **独立验证器**：执行结果由独立于执行方的验证层裁决，避免"自己验证自己"。
3. **可回滚**：每个有副作用的命令都要有可执行的补偿路径，且补偿本身同样受治理。
4. **pass^k 一致性**：关键能力在多次重复下保持稳定，而非单次侥幸通过。
5. **注入防御**：对外部输入（告警文本、工单内容）具备 prompt 注入识别与隔离能力。

### 对标依据

以下结论来自对业界顶尖多 Agent 项目与前沿研究的调研，作为本 RFC 五项准入与路线设计的依据：

| 对标对象 | 核心启示 |
|---------|---------|
| **MAST 论文** | 多 Agent 系统失败率可达 86%，常输给"单 agent 重试"基线。**每引入一个新机制，都必须证明它带来了可验证的收益**，否则不准入。这是本 RFC 设立 MAST 闸门的直接依据。 |
| **τ-bench** | 提出 pass^k 一致性指标：同一任务重复 k 次全部通过才算稳定。单次通过不构成能力证据。 |
| **AgentDojo** | 对抗性注入测试基准：将恶意指令混入正常输入考察系统是否被劫持。注入防御必须有对抗性评测集。 |
| **Voyager** | 技能"验证才入库"：新技能必须通过评测才进入可复用技能库，防止污染。 |
| **Reflexion** | 失败反思回灌：从失败轨迹提取教训写入记忆，供后续任务复用。 |
| **Letta** | sleep-time 维护：在低峰期对记忆 / 状态做后台整理与冲突消解。 |
| **Azure SRE Agent** | 四层架构（信号 → 推理 → 治理 → 执行）：治理层独立于执行层，是生产级自愈的分层前提。 |

> **结论**：治理可信度不是可选项，而是金融风控自愈上生产的**硬前置**。本 RFC 的目标就是把这五项准入从缺口补齐到可验收。

## 2. 五大维度差距地图

对五个维度逐项给出现状锚点与缺口。所有锚点均已在代码中核验，描述的是**现状缺口**，不是已修复项。

### 2.1 编排内核（对标 LangGraph checkpoint / persistence / interrupt）

| 现状锚点 | 说明 |
|---------|------|
| `orchestration/task_graph_executor.py` `resume_from_step_id` | 恢复语义已存在 |
| `orchestration/workflow_resume.py` | resume 五必填字段校验已存在 |
| `services/runtime_task_store.py` L303-307 | `RuntimeTaskStore` 为纯内存 `dict`，进程重启即丢 |

**现状缺口**：恢复语义虽已存在，但任务状态依赖调用方携带，`RuntimeTaskStore` 是纯内存结构，**无 checkpoint 持久化、无 resume REST 端点**。进程一旦重启，运行中任务状态全部丢失，无法从断点恢复。

### 2.2 记忆系统（对标 Letta / Mem0 / Zep）

| 现状锚点 | 说明 |
|---------|------|
| `memory/memory_helpers.py` `dedupe_memory_hits` | 检索侧有去重 |
| `memory/memory_operations.py` → `memory_store` append | 写入路径为追加式 |

**现状缺口**：检索侧有去重，但**写入路径无冲突消解 / supersede 机制**。新旧矛盾记忆会同时留存，检索可能命中过时结论，造成"记忆串读"。

### 2.3 评测可观测（对标 Google ADK eval pipeline / τ-bench）

| 现状锚点 | 说明 |
|---------|------|
| `eval/core/evaluator.py` L1190 | 串行执行 |
| `eval/core/metrics.py` | 指标全为 case 级 |

**现状缺口**：评测串行执行、每 case 只跑一次（**无 pass^k**）；指标全为 case 级（**无轨迹级**）。

**已具备的资产**（供后续复用）：12 类 90 条基准 + gold 数据集 + gate 基础设施 + `results/run_traces` 3800+ 条真实轨迹。

### 2.4 自愈治理安全（对标 Azure SRE Agent / D-SAC）

| 现状锚点 | 说明 |
|---------|------|
| `orchestration/hitl_policy.py` | 审批为全有全无单一开关，fail-safe 默认关闭 |
| `orchestration/node_executors.py` L180-183 | `HITL_AUTO_APPROVE` 唯一注入点 |
| `contracts/approval.py` L21 | `APPROVAL_RISK_LEVEL_VALUES` 枚举已存在但无分级处方 |
| `skills/skill_reviser.py` `revision_history` | 全库无回滚能力，仅此雏形 |

**现状缺口**：审批为全有全无单一开关；风险等级枚举已存在但**无分级处方**；全库**无回滚能力**；变更关联 RCA 仅 prompt 层；**无 prompt 注入防御**。这是五项准入中缺口最集中的一维。

### 2.5 互操作生态（对标 A2A 协议）

| 现状锚点 | 说明 |
|---------|------|
| `gateway/` router + adapter 模式 | slack / wechat_work 为兼容性实现 |

**现状缺口**：已有 gateway router + adapter 模式，但**无 A2A 协议**，agent 之间 / 系统之间缺乏标准化互操作。

## 3. 决策一：三态灰度策略

每个新治理能力都按三态演进，**不允许一步跳到 enforce**：

```
off → shadow → enforce
```

| 态 | 行为 |
|----|------|
| `off` | 能力关闭，代码路径不生效 |
| `shadow` | 只记录不拦截，经 run_trace 积累真实流量证据 |
| `enforce` | 真正拦截 / 放行 |

**切换约束**：`shadow → enforce` 的切换**必须有 kind 集群的观测证据**，并将切换记录写入本 RFC 的 Update Log。

**理由**：金融系统中，治理误拦截（false positive）与漏放（false negative）同样有害。shadow 阶段允许用真实流量观察误报 / 漏报分布；回退只需关闭 flag，无需回滚代码。这与 MAST"先证明可验证收益再准入"的原则一致。

## 4. 决策二：治理五项（P0，约 2-3 周）与性能预算表

P0 聚焦五项准入本身，目标是让治理可信度达标。各项性能预算如下表，实施时以本表为硬约束。

| 能力 | 设计要点 | 性能预算 |
|------|---------|---------|
| **分级审批** | 复用 `contracts/approval.py` 风险等级枚举，处方 LOW=自动放行+审计 / MEDIUM=单审批 / HIGH+CRITICAL=强制人工；`HITL_AUTO_APPROVE` 语义保留且仅对 LOW 生效 | 规则查表 P99 ≤ 5ms |
| **独立验证器** | 确定性层先行（receipt 契约 + evidence_refs + postcondition 断言，不走 LLM）；LLM 独立裁决为可选后端，仅 HIGH 级触发、15s 硬超时 fail-closed、走 `llm/cache.py` | 确定性层不引入 LLM 延迟；LLM 路径 15s 硬超时 |
| **可回滚** | rollback journal 表（command_id / 副作用目标 / before_snapshot / 补偿描述 / 30 天过期）；补偿是与正向操作相同的 side_effect 命令，走完整五道关卡 + HIGH 级审批 + 独立验证器；首批补偿为软语义（告警软失效 / skill 归档 / 提交撤回），不做物理删除 | journal 写入异步，不阻塞主链路 |
| **pass^k 一致性** | eval CLI `--repeat k`（默认 1，完全向后兼容）；成本控制三件套：分级 k（仅 safety/approval/injection 类 k=3）+ 早停 + 评测器 Semaphore 并行化（并发度 2 起步）+ judge 缓存 | 默认 k=1 时零额外成本 |
| **注入防御** | 评测侧先行（AgentDojo 式 injection 基准 ≥20 条）；运行时热路径只做确定性规则（正则模式 + 指令隔离标记 + 长度截断）；疑似样本异步 LLM 深检（采样默认 10%） | 热路径 P99 ≤ 2ms |

### 成本护栏

新治理引入的 LLM 调用必须纳入 `token_tracker` tier 与 `cost_circuit_breaker`，防止治理本身造成成本失控。

**总体预算**：治理全开后，5min 监控闭环 token 增量 ≤ 30%。

> **基线**：5min ≈ 133 calls / 780K tokens ≈ $0.12（见 `cost_model.py` Phase 10 实测）。治理新增开销在此基线上核算。

## 5. 决策三：P1 能力增强（约 2-3 周）

治理达标后，补齐编排内核 / 记忆 / 评测 / 自我改进四类能力增强。全部为规划项。

| 能力 | 规划要点 |
|------|---------|
| **checkpoint 持久化** | MySQL 主存 `run_checkpoint` 表 + 异步降级写 fail-open；挂 `workflow_execution.py` `_on_node_completed` 钩子，零改方法签名；可选 Redis 热缓存；resume REST 端点走统一鉴权 |
| **记忆冲突消解** | Chroma 相似度召回 top-3；latest-wins + `superseded_by` 标记不删除；异步管道，不阻塞读路径 |
| **轨迹级评测** | `eval/cli.py` 新增 `trajectory` 子命令，离线消费 3800+ 存量 `run_trace.v2`，零 LLM 成本；顺带 run_traces 日期分目录归档 |
| **自我改进科学路径** | Voyager 式 skill quarantine：eval 通过才转 active；Reflexion 式失败反思：从失败 run_trace 提取 lesson 写记忆 |
| **sleep-time 维护** | cron_manager 凌晨低峰执行：TTL 清理 + checkpoint 过期清理 + 冲突扫描，独立预算窗口 |

## 6. 决策四：P2 生态扩展（约 1 周）

| 能力 | 规划要点 |
|------|---------|
| **A2A 协议适配器** | 完全复用 gateway router + adapter 模式与 `auth_service` fail-closed 鉴权；Agent Card + task 端点映射；**不允许绕过治理的 agent 间直连** |
| **CheckpointStore 可插拔** | 将 CheckpointStore 抽象为可插拔接口，命名对齐 LangGraph `thread_id` / `checkpoint_id`，为未来接入留口子（**不引入 LangGraph 本体**） |

## 7. 规划中的 feature flag 清单

> 下表全部为**规划中** flag。实施时才引入代码，遵循 `config_pydantic.py` 默认关闭惯例。立项时点这些 flag 在代码中均不存在。

| flag 名 | 默认值 | 所属能力 |
|---------|--------|---------|
| `HITL_APPROVAL_MODE` | `tiered_shadow` | 分级审批 |
| `INDEPENDENT_VALIDATOR_ENABLED` | `false` | 独立验证器 |
| `INDEPENDENT_VALIDATOR_MODE` | `shadow` | 独立验证器 |
| `ROLLBACK_JOURNAL_ENABLED` | `false` | 可回滚 |
| `ROLLBACK_EXECUTE_ENABLED` | `false` | 可回滚 |
| `INJECTION_GUARD_ENABLED` | `false` | 注入防御 |
| `INJECTION_GUARD_MODE` | `shadow` | 注入防御 |
| `CHECKPOINT_PERSISTENCE_ENABLED` | `false` | checkpoint 持久化 |
| `MEMORY_CONFLICT_RESOLUTION_ENABLED` | `false` | 记忆冲突消解 |
| `SKILL_VALIDATE_BEFORE_STORE` | `false` | skill quarantine |
| `REFLEXION_ENABLED` | `false` | 失败反思回灌 |
| `A2A_ENABLED` | `false` | A2A 协议适配器 |

> 全部标注「规划中，实施时才引入代码，遵循 config_pydantic.py 默认关闭惯例」。

## 8. 验收标准与 MAST 闸门

每项能力给出可执行验收命令（pytest 新增测试文件 + 对应 eval.cli 类别运行）。实施时按此落地。

### 双向指标示例

| 能力 | 正向指标 | 反向保护指标 |
|------|---------|-------------|
| 注入防御 | 注入拦截率 ≥ 90% | simple/medium 通过率不降 |
| 记忆冲突消解 | 冲突消解正确率 ≥ 90% | 记忆命中率不降 |
| checkpoint 持久化 | kill 进程恢复成功率 100% | 主链路 P99 延迟增量 ≤ 预算 |

> 每项能力同时考核"做对了"与"没伤到别人"，避免治理误伤正常链路。

### MAST 闸门

依据 MAST"无验证收益的机制不准入"原则：

- **无验证收益的机制不转 enforce**。任何治理项在 shadow 阶段拿不出 kind 集群的可验证收益证据，一律保持 shadow 或回退 off。
- **每项转 enforce 需独立验收记录**，记录写入本 RFC 的 Update Log，不做批量放行。

## 9. Rejected Alternatives

| 被拒方案 | 拒绝理由 |
|---------|---------|
| 引入 LangGraph 本体替换任务图内核 | 现有 resume 语义已存在，仅缺持久层。包装现有 `RuntimeTaskStore` + MySQL 侵入最小，且可回退；引入本体改动面过大 |
| 验证器默认走 LLM | 成本 / 延迟不可控，违反成本护栏。确定性层先行，LLM 仅作 HIGH 级可选后端 |
| 物理删除式回滚 | 金融审计要求保留完整痕迹。首批补偿一律用软语义（软失效 / 归档 / 撤回） |
| 注入防御直接 enforce | 误杀正常告警的代价高于漏报观察期。先 shadow 观察误报分布再决定是否 enforce |
| checkpoint 放 P0 最先 | 为保持 P0 聚焦治理五项准入，checkpoint 持久化归入 P1，避免 P0 范围膨胀 |

## 兼容性说明

| 约束来源 | 兼容性 |
|---------|--------|
| ADR-004 五道关卡 | ✅ 分级审批 / 独立验证器 / 可回滚均在现有五道关卡框架内扩展，不形成旁路 |
| ADR-001 多 Agent 架构 | ✅ A2A 适配器复用 gateway router + adapter，agent 间调用仍走统一主链 |
| RFC-003 5min 主动监控 | ✅ 成本护栏以 5min 闭环 token 基线核算，治理增量受控 |
| PRD §10 准入标准 | ✅ 所有新增能力接入统一执行内核，不形成旁路 |

## Unresolved Questions

| 问题 | 当前倾向 | 待确认 |
|------|---------|--------|
| 分级审批 LOW/MEDIUM/HIGH 边界的具体工具清单 | 按 `contracts/approval.py` 枚举映射 | 实施时逐工具核定处方 |
| rollback journal `before_snapshot` 的体积上限 | 设上限并截断 | 金融审计与存储成本的平衡 |
| 注入防御异步深检采样率 | 默认 10% | shadow 阶段据真实误报率调整 |
| pass^k 分级 k 的类别清单 | safety/approval/injection 类 k=3 | 成本预算核定后确认 |
| CheckpointStore 抽象是否提前到 P1 | P2 | 若 P1 checkpoint 落地顺利可考虑 |
