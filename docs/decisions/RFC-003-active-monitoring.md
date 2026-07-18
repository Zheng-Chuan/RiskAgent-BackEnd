# RFC-003: 7*24 主动感知与自主运维架构

| 字段 | 值 |
|------|-----|
| Status | Accepted, In Progress |
| Date | 2026-07-18 |
| Author | RiskMonitor-MultiAgent 项目组 |

## Update Log

| 日期 | 变更 |
|------|------|
| 2026-07-18 | 初始创建 |

## 上下文

当前系统是被动触发模式：用户任务、Cron 定时触发、系统事件才会执行。`BaseProactiveAgent` 已有完整的 BDI 后台监控骨架（`start_background_monitor` / `_monitor_loop` / `_perceive_environment` / `_deliberate` / `_act`），但三个断点导致主动监控无法工作：

1. **`start_background_monitor()` 从未被任何入口调用**：`start_agents()` 在 `proactive_workflow.py:107` 聚合调用它，但仅在 `run()` 内部（请求级生命周期）触发，`server.py` 启动入口不启动常驻感知协程。
2. **`_perceive_environment()` 为空壳**：方法体是 `pass`，未接入 Docker API、Redis INFO、MySQL SHOW STATUS、Prometheus 指标流等真实监控数据源。
3. **`ProactiveMultiAgentWorkflow` 是一次性请求-响应模式**：执行完毕即退出，无常驻协程维持后台循环。

## 决策

补全「持续感知」和「常驻进程」两个缺失组件，使系统从被动响应升级为主动感知→分析→行动的 7*24 闭环。

## 方案设计

### 1. 常驻感知守护进程
在 `server.py` 的 startup 事件中创建 `asyncio.Task`，调用 `BaseProactiveAgent.start_background_monitor()`，维持 `_monitor_loop` 循环。循环中捕获所有异常，记录日志后 sleep 5s 重启，确保不因单次异常导致整个监控停止。

### 2. 真实感知数据源接入
`_perceive_environment()` 接入以下数据源：
- **Docker API**：`docker stats` 获取容器 CPU/内存/网络指标，`docker events` 订阅容器启停事件
- **Redis INFO**：内存使用、连接数、慢查询
- **MySQL SHOW STATUS**：连接数、慢查询、InnoDB 状态
- **Prometheus 指标流**：通过 HTTP 拉取 `/metrics` 端点

### 3. 轻量级预过滤层
在 `_perceive_environment()` 和 `_deliberate()` 之间增加阈值规则判断，不调 LLM：
- 正常状态直接跳过，不触发 Agent 推理
- 仅在指标超阈值时触发 `_deliberate()`
- LLM 推理频率控制（每小时不超过 N 次调用，复用 `ProactiveBudgetManager`）

### 4. 自主处置与人类升级
- **简单问题自主处置**：容器重启、缓存清理等低风险操作，自动执行（受五道关卡治理，经 `tool_executor` 主路径）
- **复杂问题人类升级**：通过 TaskGraph `ask_human` 节点升级，包含问题描述、建议方案、影响范围
- **处置结果追踪**：所有处置动作记录到 `run_trace.v2`，成功处置通过 `SkillProposer` 沉淀为 Skill

## 与现有 BDI 骨架的衔接

BDI 五段骨架已完整存在，仅需激活和完善：

| 骨架方法 | 当前状态 | 需要做的 |
|---------|---------|---------|
| `start_background_monitor()` | 已实现，从未被常驻入口调用 | 在 `server.py` startup 中调用 |
| `_monitor_loop()` | 已实现 | 增加异常自愈逻辑 |
| `_perceive_environment()` | 空壳 `pass` | 接入 Docker/Redis/MySQL/Prometheus 数据源 |
| `_deliberate()` | 已实现 | 增加预过滤层，仅在异常时触发 |
| `_act()` | 已实现 | 增加自主处置和人类升级分支 |

## 与现有架构约束的兼容性

- **ADR-001（多 Agent 架构）**：所有处置动作经 `ModeratorAgent` 路由进入统一执行内核，不退化
- **ADR-004（零信任工具治理）**：新增 MCP 工具（`docker_stats`/`redis_info`/`mysql_health_check`）注册到 `tool_registry`，受五道关卡治理
- **ADR-005（run_trace.v2）**：所有感知、分析、处置事件记录到 trace
- **不形成旁路**：所有处置动作走 `tool_executor` 主路径，不绕过治理

## 相关文档

- `docs/phases/phase-10-active-monitoring.md` — Phase 10 详细 checkpoint
- `docs/ARCHITECTURE.md` — 系统架构主链路
- `docs/PRD.md` — 产品需求文档
- `src/riskmonitor_multiagent/proactive_agents/base.py` — BDI 骨架实现
