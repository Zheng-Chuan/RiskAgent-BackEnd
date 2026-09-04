# RiskAgent-BackEnd

## 项目概述

这是一个面向金融风控场景的 Proactive Multi-Agent 系统  
它把用户任务和系统事件统一收敛到同一套执行内核中  
主链路已经具备下面这些真实能力

- 任务统一经过 `intent -> retrieve planning memory -> orchestrator_plan -> critic_plan -> task_graph execution -> receipts approvals replan -> finalize -> persist and trace`
- 系统事件先经过 `ModeratorAgent` 再进入同一套 workflow
- resume 请求会先构造 resume payload 并恢复 task_graph execution_state memory_state run_summary 再回到同一套 workflow
- 所有工具执行都走统一 `command -> receipt` 主链
- step 级审批 恢复执行 运行时 replan 已接到真实执行链路
- 记忆检索会真实参与规划 恢复和 Skill 沉淀（长期经验沉淀由 SkillProposer → Skill 系统承担）
- `run_trace.v2` 全链路记录每次运行的关键事件并持久化（覆盖范围与能力细节见 ARCHITECTURE §1 Step 8）
- replay 和评测会直接消费统一 trace
- benchmark v2 已收敛为 `basic simple medium complex collaboration memory reasoning recovery approval safety prompt_layering real_world` 十二类，共 90 条用例

## 当前口径

这个仓库现在只对外讲已经被真实代码 真实 trace 和真实 benchmark 证明过的能力  
不再保留任何和当前实现不一致的宣传性文档

## 文档体系

本项目从现在开始采用 `文档先行` 和 `docs as code` 的迭代方式  
所有重大改动都先更新文档 再开始编码 最后通过验收回写文档状态  
文档和代码必须在同一个 PR 中演进 不允许代码落地后长期不补文档  
如果实现和文档冲突 先停下来修正文档口径或重新讨论设计 再继续开发

当前文档体系按职责分层:

- `README.md`: 对外总览和目录 只讲已经被代码 测试 trace 评测证明过的能力
- `docs/PRD.md`: 产品总纲 范围边界 目标 非目标 和文档索引
- `docs/STRATEGY.md`: 产品战略 PR/FAQ 对外叙事 高频事实以引用指向权威源
- `docs/ARCHITECTURE.md`: 运行时主链和系统结构的权威说明
- `docs/decisions/ADR-*.md`: 已经接受的架构决策和 trade-off 记录
- `docs/decisions/RFC-*.md`: 大改动提案和待决问题 通过后再进入实现
- `docs/phases/*.md`: 分阶段迭代计划 checkpoint exit criteria 和交付物
- `docs/ci-cd.md`: CI/CD 流水线说明
- `monitoring/README.md`: Prometheus/Grafana 可观测性栈使用说明
- `deploy/k8s/README.md`: K8s Helm 部署专题
- `docs/MEMORY.md`: 记忆系统设计专题
- `docs/INTERVIEW.md`: 面试准备材料
- `docs/RESUME.md`: 简历素材以及其他专题文档
- `docs/KNOWN_ISSUES.md`: 已知缺口登记（库层实现但未挂载生产的能力等）

文档迭代流程:

1. 先在 `RFC` 或对应 phase 文档里写清楚目标 约束 trade-off 风险 验收方式
2. 方案确认后 在 `PRD` `ARCHITECTURE` `ADR` 中沉淀权威口径
3. 编码时和代码同 PR 更新相关文档 不允许只改代码不解释文档影响
4. 验收通过后 回写 phase 状态 证据路径 和 README 对外口径
5. 如果方案被回退或收缩 必须同步清理 README PRD ARCHITECTURE phases ADR RFC 的冲突表述

这套方式主要参考了几类成熟实践:

- Google Engineering Practices 的文档和代码同变更原则  
  [Documentation Best Practices](https://google.github.io/styleguide/docguide/best_practices.html)
- Google Code Review 对 design tests documentation 的同时审查  
  [Code Review Introduction](https://google.github.io/eng-practices/review/)
- Microsoft 的 ADR 治理方式  
  [Maintain an architecture decision record](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- Meta 开源项目 React 的 RFC 机制  
  [React RFCs](https://github.com/reactjs/rfcs)
- Kubernetes 的 KEP 结构化提案和验收字段  
  [KEP Template](https://github.com/kubernetes/enhancements/blob/master/keps/NNNN-kep-template/README.md)

文档治理的默认规则:

- 重大改动先文档后代码
- 文档和代码同 PR
- 已接受决策进 ADR
- 未定方案先走 RFC
- 验收必须能反查到代码 测试 和评测证据
- 过时文档要及时删除或降级 不能和现行口径并存

## 代码入口

- 编排入口 / 主工作流: `src/riskagent_backend/orchestration/proactive_workflow.py`
- 任务图执行: `src/riskagent_backend/orchestration/task_graph_executor.py` + `node_executors.py`
- 工具治理: `src/riskagent_backend/orchestration/tool_executor.py`
- 统一记忆: `src/riskagent_backend/memory/memory_store.py`
- 统一 trace: `src/riskagent_backend/observability/run_trace.py`
- 评测入口: `eval/cli.py`

## 文档

- [docs/PRD.md](docs/PRD.md)
- [docs/STRATEGY.md](docs/STRATEGY.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/ci-cd.md](docs/ci-cd.md)
- [docs/MEMORY.md](docs/MEMORY.md)
- [docs/INTERVIEW.md](docs/INTERVIEW.md)
- [docs/RESUME.md](docs/RESUME.md)
- [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)
- [docs/decisions/](docs/decisions/)
- [docs/phases/](docs/phases/)
- [monitoring/README.md](monitoring/README.md)（含本地默认口令，生产必须经 GF_SECURITY_ADMIN_PASSWORD / values 覆盖）

## 文档治理约定

- 现状注记块统一格式：`> **现状注记 YYYY-MM-DD**：原文为验收时点口径；当前实况见 XXX（KI-0NN / ARCHITECTURE §N.N）`（新增注记一律用此格式；phases/、decisions/ 及既存历史注记保留原写法不回改）
- 单一事实源映射（其他文档只保留一句结论 + 指向权威源，不重复罗列细节）：

| 高频事实 | 唯一权威源 | 其他文档写法 |
|---|---|---|
| LLM 网关供应商/模型/定价 | `.env.example` + [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §10.2 | 一句结论 + 括注指向权威源 |
| 提示分层实测数字 | [CHANGELOG 2026-07-09「Phase 9 收口」P0-3 小节](CHANGELOG.md#phase-9-收口---2026-07-09) | 指向该条目 + KI-011 不可复核注记 |
| Chroma 向量通道状态 | [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) KI-002（现状注记权威处 ARCHITECTURE §6.3） | 只保留一句结论 +（见 KI-002） |
| 调度挂载状态 | [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) KI-001（现状注记权威处 ARCHITECTURE §12.2） | 只保留一句结论 +（见 KI-001） |
| run_trace.v2 追踪能力细节 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §1 Step 8 | 短结论 + 指向对应章节 |

> **适用边界**：本表约束“现状口径类”表述；phases/、decisions/RFC-*、RESUME 素材属历史归档，只追加注记不改写原文，故仍保留数字副本（当前分布见 [KI-011 证据清单](docs/KNOWN_ISSUES.md#ki-011)）；README/PRD/STRATEGY 自身同样受约束——结论句不得复述机制细节。

- 修复 KI 时须按 [缺陷修复同步 checklist](docs/KNOWN_ISSUES.md#缺陷修复同步-checklist) 同步各引用处。

## 开发环境

本项目使用项目内虚拟环境 `.venv`（Python 3.13）：

```bash
# 首次初始化
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 运行测试
PYTHONPATH=src python -m pytest tests/ -v

# 启动服务
make up
```

## K8s 部署

```bash
# 创建 Secret（首次部署）
kubectl create secret generic riskagent-secrets \
  --from-literal=MYSQL_ROOT_PASSWORD=root \
  --from-literal=MYSQL_PASSWORD=change_me \
  --from-literal=MYSQL_USER=admin \
  --from-literal=LLM_API_KEY=your-api-key \
  --from-literal=LLM_EMBEDDING_API_KEY=<硅基流动 key>

# 部署
make k8s-deploy

# 卸载
make k8s-uninstall
```

详见 [deploy/k8s/README.md](deploy/k8s/README.md)

## 测试入口

- `tests/unit`: 纯逻辑和 contract 测试
- `tests/integration`: 真实 adapter 和基础设施对接测试
- `tests/workflows`: 面向主工作流的回归测试 当前收敛为三个回归文件: `test_monitoring_workflow_regression.py` `test_unified_memory_workflow_regression.py` `test_approval_resume_workflow_regression.py`（monitoring、unified memory、审批-恢复三条主链）
- `tests/acceptance`: 发布前验收测试
- `tests/scenarios`: 场景级端到端测试
- `tests/diagnostics`: 手工诊断脚本（非 pytest 收集范围）
- 推荐执行: `pytest tests/unit`
- 基础设施接线: `pytest tests/integration`
- 主工作流回归: `pytest tests/workflows`
- 发布前验收: `pytest tests/acceptance`

## 评测入口

- 统一评测 CLI: `python -m eval.cli run --category all --output <run>.json`
- Phase 2 memory A/B: `python eval/scripts/run_memory_ab.py --category memory`
- Phase 8 one-shot benchmark: `make eval-prompt-benchmark`
- Phase 8 固定 case 集: `eval/benchmarks/prompt_layering/one_shot_cases.jsonl`

## 当前进展

- `Phase 2`: memory relevance gate 和 resume completeness contract 已落地, A/B 退化已修复 (Phase 9 Checkpoint 15.1.3 已通过)
- `Phase 7`: Gateway public API 已收口到 `GatewayAdapter` `GatewayMessage` `GatewayRouter`
- `Phase 8`: 对照实验已完成, 提示分层实测数据见 [CHANGELOG 2026-07-09「Phase 9 收口」P0-3 小节](CHANGELOG.md#phase-9-收口---2026-07-09)（证据文件未入库、不可复核，见 KNOWN_ISSUES KI-011）
- `Phase 9`: 所有 8 个 checkpoint 全部通过, P0-1 (修复 Memory A/B 退化), P0-2 (Prompt A/B 对照实验), P0-3 (成本收益报告) 全部完成
- **Phase 10**: 5min 主动感知与自主运维 — ✓ 完成 — 全链路验证通过（2026-08-03），感知→告警→LLM处置→Trace completed（常驻感知守护进程 + 真实数据源接入 + 预过滤层 + K8s 适配）（Checkpoint 16.4.1 部分实现，见 KI-003/KI-004）
- **Phase 11**: Skill 语义检索升级 — ✓ Implemented — 6 项需求全部实施（2026-08-08），Chroma 向量库 + 远程 Embedding（网关与模型详情见 ARCHITECTURE §10.2 / .env.example）+ Summary 摘要字段 + Hybrid 检索（向量 + BM25, α=0.7）+ Query Rewriting（LLM 改写 + LRU 缓存）+ skill_view 工具，验收时 158/158 Skill 相关测试通过；当前实测共 213 条 Skill 相关测试（`PYTHONPATH=src python -m pytest tests/unit -k skill --collect-only` 收集数，2026-08 实测），K8s 部署验证通过（Helm revision 18），已知限制：Chroma 向量通道生产未启用，实际为 SemanticIndexer + BM25（见 KNOWN_ISSUES KI-002，现状注记权威处 ARCHITECTURE §6.3）
- **Phase 12**: BDI 信念去重与意图幂等性修复 — ✓ 完成 — 6 个 Checkpoint 全部实施，36 测试通过（2026-08-07），双层去重防护（信念层 + 意图层），RFC-006 Accepted, Implemented
- **Phase 13**: REST BFF 浏览器闭环与记忆可观测性 — ✓ 完成 — K8s 验收全部通过（2026-08-07），9 项验收全部通过（含 /health 基础设施端点与脱敏验证；BFF 业务端点实为 7 个，参见 ARCHITECTURE §9.1）+ 5/5 前端联调通过，SSE 实时推送验证，脱敏验证通过
- **Phase 14**: 性能验证与 LLM 成本模型 — 方向二十已完成 — LLM 成本模型 4 个 Checkpoint 全部完成（2026-08-07），37 个测试通过，成本计算不再为 0，by_agent_stage 维度统计，三级熔断器（5min/1h/24h（5min 为档位标签，实际共用 1h 窗口，见 KI-012）），成本预估表（5min/1h/24h/7d），集成 ProactiveBudget，新增 /api/llm/cost-model 端点；方向二十一（系统压测）与方向二十二（SLO 定义）已按决策取消
