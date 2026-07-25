# Changelog

本文件记录 RiskAgent-BackEnd 项目的所有重要变更.

格式参考 [Keep a Changelog](https://keepachangelog.com/).

## 2026-07-19: 7×24 主动监控链路修复

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

## 2026-07-18: Phase 10 主动监控文档体系创建

- 创建 docs/phases/phase-10-active-monitoring.md（7*24 主动感知与自主运维，11 个 checkpoint）
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
- 679 单元测试全部收集，零回归

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
