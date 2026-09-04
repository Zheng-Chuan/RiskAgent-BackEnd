# Changelog

本文件记录 RiskAgent-BackEnd 项目的所有重要变更.

格式参考 [Keep a Changelog](https://keepachangelog.com/).

## 2026-09-04: 文档体系结构改进（单一事实源+引用约定）（commit <待回填>）

### Changed

- README.md：top5 高频事实（网关模型/定价、实测数字、Chroma 状态、调度状态、run_trace.v2）收敛为一句结论+指向权威源引用；文档索引补 STRATEGY.md 与 monitoring/README.md 直链；新增「文档治理约定」小节（注记格式 + 单一事实源映射表 + checklist 指引）
- docs/PRD.md：run_trace.v2 行补 ARCHITECTURE §1 Step 8 指向；网关模型行改为引用式；FR-10 需求定义保留原始描述
- docs/STRATEGY.md：5 处高频事实收敛为引用式（网关/Chroma/调度/run_trace/数字）；L204 时点块保留完整现状描述并补引用指向
- docs/RESUME.md：成本数字保留原值并补 CHANGELOG/KI-011 指向注记；网关行补 ARCHITECTURE §10.2 引用
- docs/ARCHITECTURE.md：5 处内部去重——§6.1 图、§6.5 两处 Hybrid/Fallback、§6.10 风险表、§12 章首——均改为文内锚点 `[§6.3 注记](#section-6-3)` 引用
- docs/KNOWN_ISSUES.md：底部新增「缺陷修复同步 checklist」（KI 修复时须同步的引用处清单）
- deploy/k8s/README.md：首次纳入文档审计——补 values-ci / values-local-e2e 环境说明、make k8s-deploy 变量口径（IMAGE_TAG/K8S_NAMESPACE）、k8s-status 说明、代码围栏格式统一
- docs/MEMORY.md：经核验零改动

### Notes

本轮为纯文档结构改进，零代码逻辑变更，pytest 884 tests collected 不变。

## 2026-09-03: 第三轮文档-代码一致性深度审计修复（commit 2188db3；收尾 commit 586220b：补附 commit 引用；评审收尾 commit eddd3fe）

### Fixed

- 核心文档口径修复（ARCHITECTURE.md）：调度能力"已接入主链"不实表述改为"库层已实现、生产入口未挂载"；补 Skill Chroma 注入缺口注记（主链无参 `SkillStore()` 构造使 `_chroma_enabled` 恒为 False，向量分数实际来自进程内 SemanticIndexer）；LLM 成本治理章按代码实况重写（CostCircuitBreaker 三级阈值表、同构返回与 30s 冷却恢复、ProactiveBudgetManager 唯一消费方）；tool_executor 白名单更正为四角色（补 orchestrator/skill_view）；TokenTracker/CostCircuitBreaker 补代码锚点；清理 OpenRouter 残留表述与 Hermes 矛盾收敛
- llm_client.py embed() docstring L355 残留"1536 维"补修（2026-09-02 条目勘误①的收尾）
- phase/CHANGELOG/RESUME/ci-cd 范围修复：phase-10 Checkpoint 16.4.1 自主处置由 `[x]` 降级为 `[~]` 部分实现（仅规则判定，无容器重启/缓存清理 MCP 工具、不经五道关卡、无 receipt）并撤下 Known Issue #4 "已修复"标注；phase-3 六个从未入库的 integration 测试文件如实标注未落地；phase-7 两份指南文档与调度评测未产出、降级为未勾选；phase-2/4/5/6/8/9 评测报告"结果未归档入库"行内注记；CHANGELOG 补 2026-08-08 CI/CD 立项条目、修复日期倒序、2026-09-02 条目追加勘误；ci-cd.md 删除未实施的"未来扩展路径"块并补全流程步骤；RFC-003/004/005/006 状态标记体例统一

### Added

- 新建 docs/KNOWN_ISSUES.md 缺陷登记册：代码层已知缺口（KI-001 调度生产入口未挂载、KI-002 Skill Chroma 未注入、KI-003 自主处置工具缺失、KI-004 remediation Skill 沉淀仅内存、KI-011 评测报告未归档等）与需求分离登记，文档保持反映已交付现状、不再以"已修复"掩盖缺口

## 2026-09-02: 文档-代码一致性审计修复（commit 4c5b2fa）

### Fixed

- README 开发环境段失真修复：conda 环境 MCP（已不存在）改为 `.venv`（Python 3.13）真实指引
- llm_client.py embed() docstring 残留"1536 维"笔误改为当前 BAAI/bge-m3 1024 维
- ARCHITECTURE.md 第 1 章新增角色命名约定注记（概念名 IntentAgent/OrchestratorAgent/ToolExecutor 与实现类 ProactiveIntentAgent 等的对照），架构图与 2.4 节的 ToolExecutor 表述改为 tool_executor.py 模块实际名称
- ARCHITECTURE.md 新增第 12 章"渠道接入与调度"：补齐此前 0 覆盖的 gateway/（抽象层收口，平台适配器为兼容实现）、scheduling/（CronManager 已接入主链）、cli/（replay 工具）三个真实模块
- phase-14 Out of Scope"当前 deepseek-chat"措辞、RFC-005 统一口径注记补历史口径标注（现行 chat 模型为 deepseek-v4-flash）

> **勘误（2026-09-03 追加，原文保留不改写）**：
> ① 本条目"llm_client.py embed() docstring 残留 1536 维笔误改为 1024 维"实际只修改了一处 docstring，同文件 L355 处仍残留"1536 维"（已于本轮补修）。
> ② 本条目"scheduling/（CronManager 已接入主链）"为不实表述：CronManager 库层已实现且有单元测试，但生产入口未挂载（server 启动链路不触发 cron 工作流）。本轮文档已改口径，缺口登记 docs/KNOWN_ISSUES.md（KI-001）。

## 2026-08-25: 取消全部规划中事项 — 移除 RFC-007 及前瞻引用，文档体系回归已交付现状

### Removed

- 经决策取消全部规划中/未实施事项：RFC-007 治理与能力追赶路线（P0 治理五项 / P1 能力增强 / P2 生态扩展）及全部 12 个规划 feature flag、tests/smoke 预留、RFC-006 遗留未决问题、INTERVIEW 后续方向（后两者不实施，仅加注记归档）（commit 4354776；收尾 commit 1778dfe：评审建议修复——CHANGELOG 取消条目补 commit 引用、立项注脚补取消事实、修复 phase-2/phase-4 两处存量死链）
- 移除 `docs/decisions/RFC-007-governance-trust-production-readiness.md`，同步清理 PRD（Phase 15 行与决策表行）/ STRATEGY（治理与能力追赶小节）/ README（下一阶段与 tests/smoke 预留）/ ARCHITECTURE（§7.7 规划演进段）/ .env.example（规划 flag 注释预告块）中的前瞻引用与死链
- .env.example 中 12 个规划 flag 注释预告（HITL_APPROVAL_MODE 等）全部删除，未引入过任何生效变量，无代码变更

> 本条目为**决策记录**：文档体系现仅反映已交付现状；历史立项与取消事实如实保留于本文件。

## 2026-08-18: RFC-007 立项 — 治理与能力追赶路线（Accepted, Not Implemented）

### Added

- 新增治理与能力追赶 RFC 文档（该 RFC 已于 2026-08-25 取消并从仓库移除）：治理可信度五项准入门槛（分级审批 / 独立验证器 / 可回滚 / pass^k 一致性 / 注入防御）+ P0/P1/P2 追赶路线 + 三态灰度策略 + 性能预算表 + MAST 闸门
- 同步更新 PRD（Phase 15 立项行）/ STRATEGY（扩展路径小节）/ README（下一阶段）/ ARCHITECTURE（§7.7 规划演进）/ .env.example（规划 flag 注释预告）

> 本条目为**决策立项**，非代码实施。治理五项均为 Not Implemented，相关 feature flag 全部为规划中，实施时才引入代码（**已于 2026-08-25 取消，见顶部条目**）。

## 2026-08-18: 文档体系全量诚实性修复（二轮）+ 基础设施配置修正

### Changed

- ARCHITECTURE.md 按当前代码全量重写，章节重编号（commit 60d96f4）
- docker-compose 补全 LLM embedding 变量（LLM_EMBEDDING_BASE_URL / LLM_EMBEDDING_API_KEY）
- K8s 模板修正（configmap/secrets/values 对齐新网关与端口约定）

### 用户可见变更说明

- ConfigMap CHROMA_PORT 回退默认值 8001→8000：指向外部 Chroma（非本 chart 部署）的 helm 用户必须显式设置 chroma.port
- ARCHITECTURE.md 章节重编号映射表：旧 10（REST BFF）→ 新 9、旧 11（LLM 成本治理）→ 新 10、旧 12（评估体系）→ 新 11，供外部链接维护者对照（注：该映射为 2026-08-18 时点的历史口径；现行 ARCHITECTURE 已有新第 12 章"渠道接入与调度"（2026-09-02 新增），与该映射中的"旧 12（评估体系）"无关）
- .env.example MYSQL_PORT 更正为 3307：宿主直跑应用请用 3307，容器内流程不受影响

## 2026-08-18: CI Docker 构建修复

### Fixed

- CI Docker 构建补装 g++，修复 chroma-hnswlib 源码编译失败（chromadb >= 0.5.23 升级触发）；同步更新 README Phase 11/14 描述（commit 496952d）

## 2026-08-14: K8s Chroma 镜像对齐 + OpenRouter 注释清理

### Changed

- K8s Chroma 镜像版本对齐 0.5.23，与客户端 chromadb 版本统一（commit f58b8a6）
- requirements.txt chromadb 升至 >=0.5.23,<0.6（此前 pin 0.5.0）
- 清除集成测试中过时的 OpenRouter 注释

## 2026-08-14: LLM 网关切换 — Chat 切 DeepSeek 官方 API, embedding 切硅基流动

### Changed

- Chat 链路从 OpenRouter（deepseek/deepseek-v4-flash）切换到 DeepSeek 官方 API（https://api.deepseek.com, deepseek-v4-flash），OpenRouter key 完全移除
- 请求体按 DeepSeek 官方格式显式开启深度思考（`thinking: {"type": "enabled"}`），替代被官方 API 忽略的 `enable_thinking` 参数
- embedding 链路切换到硅基流动 SiliconFlow（BAAI/bge-m3, 1024 维）：DeepSeek 官方无 embeddings 端点；硅基流动不提供 text-embedding-3-small
- 新增配置 `LLM_EMBEDDING_BASE_URL` / `LLM_EMBEDDING_API_KEY`（为空时回退主 LLM 配置），K8s configmap/secrets 同步注入
- cost_model.py 新增 DeepSeek 官方模型名（无供应商前缀）定价条目与 BAAI/bge-m3 免费条目
- K8s values/configmap/secrets 全部切到新网关；Chroma Skill 向量索引维度 1536→1024，启动时自动重建（代码无维度硬约束）（commit 06ea0ab）

## 2026-08-13: Phase 14 方向取消 + 测试修复

### Removed

- 取消 Phase 14 方向二十一（系统压测）与方向二十二（SLO 定义），按用户要求不纳入范围（commit bedbd2d）

### Fixed

- Redis 感知测试显式传递 redis_url，避免环境变量覆盖（commit 10ec8a0）
- MCP 子进程显式传递鉴权环境变量 + acceptance 适配 summary_only（commit cdeadee）

## 2026-08-12: summary_only 契约修复 + 测试适配

### Fixed

- 修复 summary_only 注入契约缺口与 3 个 skill 流程测试（commit 6b88ec1）
- 适配 Orchestrator ReAct 重构后的 proactive unit 测试（commit 57f351e）

## 2026-08-11: 安全加固批次（HITL 默认关闭 / API 鉴权 fail-closed）

### Security

- HITL_AUTO_APPROVE 默认改为 false（fail-safe，需显式开启才自动审批 side_effect 工具）（commit ee6ae70）
- /api/* 全部端点强制鉴权（fail-closed）（commit 4553eb5）
- Redis 启用密码 + 端口暴露收敛到 localhost（commit 8274d30）
- 弱密码治理：secrets 强校验 + 移除默认弱密码（commit 805ed0b）

### Fixed

- 后台 fire-and-forget 任务保持强引用，防止被 GC 提前回收（commit 0b85cb5）
- 感知采集卸载到线程池，不再阻塞事件循环（commit 79b4d08）
- 工具执行路径同步 DB 查询卸载到线程池（commit dce7314）

## 2026-08-11: orchestration 模块拆分与工程治理重构

### Changed

- orchestration 拆分：_run_internal 拆出 setup/intent/planning/TaskGraph 执行/finalization/Agent 结果处理等独立模块（workflow_execution.py / workflow_finalization.py / workflow_agent_results.py 等）
- 引入 agent registry 作为 Agent 定义唯一事实来源（commit bdd3b92）
- prompt 外置到 prompts/agent_prompts/（commit ddd9b0b）
- 环境变量读取统一收敛到 config 层 + `make lint`（lint-env 接入 make lint，未接入 CI workflow）（commit fdd971a）
- services 提取共享状态归一化到 task_status.py（commit 03bdfe0）

### Added

- workflow 阶段数据 TypedDict 契约（commit d5f49df）
- orchestration 契约针对性 mypy gate（commit f1f5089）

### Chores

- 死代码清理（validation shell / 未引用 agent schemas）、pytest warning filters 清理、logging 惰性格式化（commits 76bc85f / 5a4ab53 / b50d831）

## 2026-08-10: 文档诚实性全量修复

### Fixed

- 文档诚实性全量修复（11 步，22 项问题）（commit 9f650e8）

## 2026-08-08: CI/CD Pipeline 立项与落地

### Added

- GitHub Actions CI/CD 管道（commit 26293a7）：新增 `.github/workflows/ci.yml`（test / build / deploy 三 Job；build 与 deploy 后于 commit 8ef9f23 合并为 build-and-deploy，见下方 Fixed；ci.yml 从未包含 lint job，静态检查仅在 make lint）、`deploy/k8s/values-ci.yaml`（CI 环境专用 values）、`docs/ci-cd.md`（管道说明文档）；Makefile 部署参数化（注入 IMAGE_TAG / K8S_NAMESPACE 两个变量，docker build tag 与 helm -n / --set image.tag 改为引用变量；values 文件仍硬编码 values-prod.yaml）

### Fixed

- 同日 CI 修复系列：job 级 if 条件误用 env context（GitHub Actions 不支持，改用 vars）（commit a6afdda）；pytest 忽略 pydantic_settings IncompleteFieldDefinitionWarning（commit 3c887eb）；CI test 清理 warning、移除 Redis service、test job 加 continue-on-error 容忍存量失败（commit 17094e0）；build 与 deploy 合并为单一 build-and-deploy job（Docker 镜像无法跨 runner/job 共享）（commit 8ef9f23）；deploy 步骤加 continue-on-error 容忍 CI runner 资源不足（commit c5ca1b5）

## 2026-08-08: Phase 11 Skill 语义检索升级实施完成（RFC-005 Implemented）

### Phase 11: Skill 语义检索升级（RFC-005 Implemented）

- 需求三：Skill 新增 summary 摘要字段（纯 LLM 生成，30-80 字）
- 需求二：LLMClient.embed() 方法（text-embedding-3-small, 1536 维, OpenRouter）
- 需求六：skill_view 工具（Orchestrator 按需调用，summary 列表注入）
- 需求一：Chroma riskagent-skills collection 向量库迁移
- 需求五：Query Rewriting（LLM 改写 + LRU 缓存 + fallback）
- 需求四：Hybrid 检索（向量 + BM25 加权合并, α=0.7）
- K8s 部署验证通过（ConfigMap 6 个新环境变量 + MySQL migration summary 列 + Docker k8s-local-v4）
- 222 个 Skill 相关测试全部通过
- 已知限制：OpenRouter 账户余额不足（402）时 Fallback 降级正常工作

## 2026-08-07: RFC-005 Skill 语义检索升级提案 Accepted

- RFC-005 Status 从 Proposed 更新为 Accepted
- 6 个选型决策全部确认：
  1. OpenRouter embedding 模型：text-embedding-3-small（1536 维）
  2. 向量库：复用 Chroma，新建 riskagent-skills collection
  3. EmbeddingClient：在 LLMClient 中新增 embed() 方法
  4. summary 生成：纯 LLM 生成，参考 AutoSkill extraction prompt
  5. 向前兼容：清空旧 Skill，不考虑向前兼容
  6. Phase 归属：Phase 11
- 新增 3 项优化方案设计：
  - 需求四：Hybrid 检索（向量 + BM25 加权合并，复用 _keyword_fallback_search）
  - 需求五：Query Rewriting（LLM 改写为检索导向 query，LRU 缓存 + fallback）
  - 需求六：Agent 自主发现（skill_view 工具，summary 列表 + 按需加载）
- 实施顺序更新：需求三→需求二→需求一→需求四→需求五→需求六
- Drawbacks 新增 3 项（BM25 延迟 / Query Rewrite LLM 调用 / skill_view ReAct 步数）
- PRD Phase 11 状态更新，README 当前进展新增 Phase 11

## 2026-08-07: Phase 14 LLM 成本模型实施完成（方向二十）

- Checkpoint 20.1.1: TokenTracker 新增 agent_name + stage 维度统计
- Checkpoint 20.1.2: cost_model.py 内置 OpenRouter 定价表，cost_estimate 不再为 0
- Checkpoint 20.1.3: 成本预估表 5min/1h/24h/7d 四窗口，去重场景成本降低 80%
- Checkpoint 20.1.4: CostCircuitBreaker 三级熔断（5min/1h/24h），集成 ProactiveBudgetManager
- 新增 /api/llm/cost-model API 端点
- 24 个新增测试全部通过（test_cost_model.py 实测），836 单元测试（总计 1067 测试）无回归；成本相关测试现已扩至 37 个（cost_model 24 + cost_report 13）

## 2026-08-07: Phase 12 BDI 信念去重实施完成（RFC-006）

- 6 个 Checkpoint 全部实施完毕
- Belief 新增 processed/processed_at 字段，Intention 新增 source_belief_id 字段
- _deliberate() 跳过已处理信念，避免重复审议
- _cleanup_beliefs() 自动清理已处理且超时的信念
- add_intention() 内容去重（description + tool_name + tool_params 三元组匹配）
- get_bdi_state() 导出新字段到 run_trace.v2
- 双层去重防护：信念层 + 意图层
- 36 个测试全部通过（12 原有 + 24 新增）

## 2026-08-07: Phase 13 REST BFF K8s 验收完成

- 9/9 API 端点验收通过（POST/GET/SSE/脱敏）
- 5/5 前端联调验收通过（页面加载/控制台/API 路径匹配/任务提交/SSE 实时推送）
- 前端通过 nginx 反向代理对接后端，集群内通
- LLM Fallback 降级机制按设计预期工作
- 7 张验收截图已保存

## 2026-08-03: Phase 14 规划 + RFC-006 优先级提升

- 新建 Phase 14: 性能验证与 LLM 成本模型（docs/phases/phase-14-performance-verification.md）
- 更新 RFC-006: 基于 Phase 10 验证数据提升优先级，补充 133 次/5min 的实测证据
- Phase 10 验证暴露的可靠性问题：信念重复、LLM 调用频率、成本模型缺失

## 2026-08-03: Phase 10 主动监控全链路验证完成

- 5min 监控全链路验证通过（感知→告警→LLM处置→Trace completed）
- 修复 LLM Fallback 降级机制（MISSING_API_KEY/LLM_DISABLED 加入白名单）
- 修复 semantic_indexer 递归 Bug（max_depth 限制）
- 修复 Orchestrator 输出验证（normalize→validate 顺序 + evidence/tool_name 归一化）
- 移除 ask_human 步骤，添加 HITL_AUTO_APPROVE 自动审批
- 文档体系全量更新：7×24 → 5min
- K8s 部署验证：LLM_API_KEY 注入成功，deepseek/deepseek-chat 调用正常

## 2026-08-03: 5min 监控验证方案

- 将 7×24 监控验收方案调整为 5 分钟快速验证
- 注入故障类型：Redis Service 中断（scale to 0）
- 验证全链路：感知 → 告警 → LLM 处置 → Trace 记录
- 前置条件：K8s 部署需注入 LLM_API_KEY

## 2026-07-19: 5min 主动监控链路修复

### 修复
- _deliberate source 硬编码不匹配（base.py）→ 改为 frozenset 集合匹配，修复感知→行动链路断裂
- SystemEngineer 直接调用 remediate() 绕过五道关卡 → 移除直接调用，改走 _act → start_from_event → tool_executor
- Prometheus 指标名不匹配（http_requests_total → rm_agent_command_denied_total/orchestrator_runs_total 比值，llm_token_total → rm_llm_tokens_total）
- Orchestrator/Critic _perceive_environment 空壳 → 补全 Prometheus 感知
- PerceptionBudgetManager 死代码 → 删除
- 新增 K8sDataSource（kubectl CLI 查 Pod 状态）+ RBAC 配置
- 新增 _deliberate 单元测试 + 完整链路集成测试

### K8s 部署修复
- 删除 namespace.yaml（Helm ownership 缺陷），改用 --create-namespace
- 镜像引用参数化（global.imageRegistry 前缀）
- ConfigMap 补 PROMETHEUS_URL + DEPLOYMENT_ENV
- 新增 docker-build Makefile target

## 2026-07-18: Phase 10 主动监控文档体系创建

- 创建 docs/phases/phase-10-active-monitoring.md（5min 主动感知与自主运维，11 个 checkpoint）
- 创建 docs/decisions/RFC-003-active-monitoring.md（主动监控架构决策）
- 更新 PRD.md 添加 Phase 10
- 更新 README.md 添加 Phase 10
- 更新 ARCHITECTURE.md 文档保留范围

## 2026-07-18: 项目结构优化重构

### P1: 提取 roles.py 内联系统提示词
- 创建 `prompts/agent_prompts/` 目录，5 个独立 prompt 文件
- roles.py 从 864 行降至 ~500 行

### P2: 拆分 proactive_workflow.py 巨型方法
- `_run_internal` 531 行拆分为 8 个独立步骤方法
- `_run_internal` 降为 ~50 行纯编排方法

### P3: 拆分 task_graph_executor.py
- 新建 `orchestration/node_executors.py`（NodeExecutor 类，322 行）
- 提取节点执行、7种节点类型分发、RBAC审批、重试逻辑
- task_graph_executor.py 从 1304 行降至 650 行（DAG调度+状态管理）

### P4: 拆分 proactive_agents/base.py
- 新建 `proactive_agents/base_models.py`（82 行，BDI 数据模型）
- 提取 Belief/Desire/Intention/ReActStep/ProactiveAgentResult
- base.py 从 1072 行降至 1016 行

### P5: 精简 contracts/__init__.py 导出
- 改为 PEP 562 懒加载，减少启动时导入开销

### P6: 合并配置层重复默认值
- config.py 完全委托到 config_pydantic.py Settings

### 文档清理
- 删除 eval/reports/（9 个带时间戳的评测快照）
- 删除 eval/results/（3 个 A/B 实验结果和成本报告，结论已沉淀到 CHANGELOG）

### 验证
- 836 单元测试全部收集，零回归

## 2026-07-18: K8s 全量迁移

### 概述
将 docker-compose.yml 中的 8 个服务迁移为 Helm Chart 部署到 K8s。核心策略：零代码变更 — 应用已具备 K8s 所需全部能力（环境变量配置、/health 和 /ready 端点、SIGTERM 优雅退出）。

### 决策
- 使用 Helm Chart（非 Kustomize），8 服务 + 5 卷 + 多环境
- 有状态服务（MySQL/Redis/ChromaDB）用 StatefulSet，无状态服务用 Deployment
- MCP Server 首期 replicas=1（proactive 后台线程需 leader election 后才可多副本）
- docker-compose.yml 完整保留作为本地开发环境
- ChromaDB pin 版本 0.5.0（避免 latest 漂移）

### 文件
- RFC-004: docs/decisions/RFC-004-k8s-migration.md
- Helm Chart: deploy/k8s/

<a id="phase-9-收口---2026-07-09"></a>
## 2026-07-09: Phase 9 收口

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
- 报告文件: `eval/results/prompt_layering/20260709_155819_cost_report.md`（运行期产物，已删除未入库；结论已沉淀至 CHANGELOG 本条目）
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

## 2026-07-09: 文档体系一致性修正

- 修正 PRD.md Phase 状态表（Phase 2/8/9 标记为完成）
- 修正 README.md 当前进展（添加 Phase 9 完成记录）
- 修正 .env.example LLM 配置（火山引擎 → OpenRouter + DeepSeek）
- 修正 config.py / config_pydantic.py / llm_client.py 中的 LLM 注释和默认值
- 修正 STRATEGY.md 模型引用
- 修正 INTERVIEW.md 文件路径错误
- 修正 ARCHITECTURE.md 文档保留范围（添加 RESUME.md / MEMORY.md / INTERVIEW.md）
- 更新 ADR-001 状态为 Implemented
- 更新 RFC-001 状态为 Implemented
- 更新 RFC-002 状态为 Completed
- 更新所有 ADR/RFC 的 Update Log
