# Phase 10: 7*24 主动感知与自主运维

## 状态

规划中. 在 Phase 0-9 全部完成的基础上, 补全持续感知和常驻进程两个缺失组件, 使系统从被动响应升级为主动感知 → 分析 → 行动的 7*24 闭环.

## 核心目标

当前系统是被动触发模式: 用户任务或系统事件到达后才执行, 执行完毕即退出, 无常驻协程维持后台循环. 这一模式与 `Proactive Multi-Agent` 的定位存在根本差距, 具体表现为:

1. `start_background_monitor()` 已实现但从未被任何入口调用, `server.py` 启动后不持有常驻感知协程.
2. `_perceive_environment()` 方法为空壳, 未接入 Docker / Redis / MySQL / Prometheus 等真实监控数据源.
3. 整个 `ProactiveMultiAgentWorkflow` 是一次性请求-响应模式, 缺少周期性轮询和自主触发能力.

本 Phase 的核心改造:

- 在 `server.py` 中启动常驻后台监控协程, 维持 7*24 心跳.
- 为 `_perceive_environment()` 接入真实监控数据源 (Docker 容器状态 / Redis 指标 / MySQL 健康 / Prometheus 指标).
- 实现轻量级预过滤层, 用规则和阈值前置过滤绝大多数正常信号, 避免 LLM 成本爆炸.
- 简单问题自主处置 (容器重启 / 缓存清理), 复杂问题升级人类, 处置结果可追踪并沉淀为 Skill.

## 时间盒与资源

- 时间: 4 周
- 优先级: 高

## 工作范围

### In Scope

- 常驻感知协程: `server.py` 启动后台守护协程, 周期性调用 `_perceive_environment()`.
- Docker / Redis / MySQL / Prometheus 四类数据源接入, 产出结构化感知快照.
- 轻量级预过滤层: 阈值规则引擎, 正常信号就地消化, 异常信号升级.
- 异常升级触发: 预过滤命中后生成 `system_event`, 经 `ModeratorAgent` 路由进入统一执行内核.
- LLM 频率控制: 对 LLM 调用做预算和频控, 防止感知风暴放大成本.
- 自主处置: 容器重启 / 缓存清理等低风险操作, 受五道关卡治理.
- 人类升级流程: 复杂问题通过 `ask_human` 节点升级人类, 附带完整证据链.
- 处置结果追踪与 Skill 沉淀: 处置动作产出 receipt 并进入 run_trace, 高置信经验沉淀为 Skill.
- 新增 MCP 工具: 容器状态查询 / 容器重启 / 缓存清理 / Prometheus 指标查询.

### Out of Scope

- 前端监控仪表盘: 归属前端项目, 本期仅保证后端数据可被消费.
- 多集群监控: 本期仅覆盖单机 Docker Compose 编排内的基础设施.
- 通知通道扩展: 本期不新增邮件 / 钉钉 / 企业微信适配器, 复用现有 Gateway 抽象层.
- ML 异常检测: 本期使用规则阈值, 不引入时序预测或异常检测模型.

## 详细 Checkpoint

### 方向十六. 常驻感知守护进程

#### 目标

让 `server.py` 启动后持有常驻后台协程, 周期性感知环境, 并具备异常自愈能力, 不再是一次性请求-响应模式.

- [ ] Checkpoint 16.1.1 server.py 启动常驻感知协程
  - 实现项: 在 `server.py` 的 FastMCP 启动钩子中启动 `ProactiveMultiAgentWorkflow` 的常驻后台监控协程, 周期性调用 `_perceive_environment()`; 协程需具备优雅退出 (graceful shutdown) 能力, 服务停止时正确释放资源
  - 验收方法: 启动 `server.py`, 观察日志中周期性感知心跳; 发送 SIGTERM, 观察协程优雅退出
  - 验收证据: server 运行日志, 感知协程心跳记录, 优雅退出 trace
  - 通过标准: 常驻协程在服务存活期间持续运行, 无协程泄漏; SIGTERM 后协程在 5 秒内完成退出, 无残留任务

- [ ] Checkpoint 16.1.2 异常自愈
  - 实现项: 感知协程自身具备异常恢复能力, 单次感知失败不导致协程退出; 连续失败达到阈值时触发熔断并升级人类; 感知协程与用户任务执行隔离, 互不阻塞
  - 验收方法: 注入数据源连接异常, 观察协程是否保持运行; 注入连续失败, 观察熔断触发
  - 验收证据: 异常注入日志, 熔断触发 trace, 协程存活记录
  - 通过标准: 单次异常不中断协程; 连续 5 次失败触发熔断并升级; 感知协程异常不影响用户任务

### 方向十七. 真实感知数据源接入

#### 目标

让 `_perceive_environment()` 不再是空壳, 接入 Docker / Redis / MySQL / Prometheus 四类真实数据源, 产出结构化感知快照供预过滤层消费.

- [ ] Checkpoint 16.2.1 Docker 数据源接入
  - 实现项: 通过 Docker SDK (或 `docker` CLI 封装) 采集容器状态 (running / exited / restarting)、资源占用 (CPU / 内存)、健康检查结果; 覆盖 docker-compose.yml 编排内的所有服务容器
  - 验收方法: 运行感知协程, 对比 `docker ps -a` 输出与感知快照中的容器状态字段
  - 验收证据: 感知快照 JSON, Docker SDK 调用记录, 容器状态字段对照表
  - 通过标准: 编排内所有容器的 running / exited 状态与 `docker ps` 一致, 资源占用数值偏差 < 5%

- [ ] Checkpoint 16.2.2 Redis 数据源接入
  - 实现项: 通过 redis-py 连接 Redis (6379), 采集连接数、内存使用、键空间命中率、慢查询、持久化状态; 连接失败时降级为空快照而非中断协程
  - 验收方法: 运行感知协程, 对比 `redis-cli INFO` 输出与感知快照中的 Redis 指标字段
  - 验收证据: 感知快照 JSON, redis-py 调用记录, Redis INFO 对照表
  - 通过标准: 连接数 / 内存使用 / 键空间命中率与 `redis-cli INFO` 一致; 连接失败时快照标记 `source=redis status=unavailable` 且协程不中断

- [ ] Checkpoint 16.2.3 MySQL 数据源接入
  - 实现项: 复用现有 `data_access` 层连接 MySQL (3307), 采集连接池状态、慢查询计数、表行数趋势 (alerts / audit_events / memory_store); 复用 `check_mysql_ready` 健康检查逻辑
  - 验收方法: 运行感知协程, 对比 `SHOW GLOBAL STATUS` 输出与感知快照中的 MySQL 指标字段
  - 验收证据: 感知快照 JSON, data_access 调用记录, MySQL STATUS 对照表
  - 通过标准: 连接数 / 慢查询计数与 `SHOW GLOBAL STATUS` 一致; 健康检查复用 `check_mysql_ready`, 不引入旁路

- [ ] Checkpoint 16.2.4 Prometheus 数据源接入
  - 实现项: 通过 httpx 查询 Prometheus (9090) HTTP API, 采集已注册的 riskmonitor 业务指标 (orchestrator_runs_total / token 指标 / 工具调用指标); 支持 PromQL 查询封装
  - 验收方法: 运行感知协程, 对比 `curl localhost:9090/api/v1/query` 输出与感知快照中的 Prometheus 指标字段
  - 验收证据: 感知快照 JSON, httpx 请求记录, Prometheus API 对照表
  - 通过标准: 业务指标值与 Prometheus API 直接查询一致; 查询失败时快照标记 `source=prometheus status=unavailable` 且协程不中断

### 方向十八. 轻量级预过滤与 LLM 升级

#### 目标

用规则和阈值前置过滤绝大多数正常信号, 避免 LLM 成本爆炸; 仅异常信号升级到 LLM 分析和统一执行内核.

- [ ] Checkpoint 16.3.1 阈值规则引擎
  - 实现项: 实现规则引擎, 预定义阈值规则 (如容器 exited、Redis 内存 > 80%、MySQL 慢查询 > 阈值、业务指标异常波动); 规则匹配产出标准化 `PerceptionSignal` 结构, 标注 severity (info / warning / critical) 和数据源
  - 验收方法: 注入正常信号和异常信号, 观察规则匹配结果; 检查 `PerceptionSignal` 结构完整性
  - 验收证据: 规则定义文件, 信号匹配日志, `PerceptionSignal` 样例
  - 通过标准: 正常信号 (info) 不升级; 异常信号 (warning / critical) 正确命中规则并产出标准化信号; 规则可配置不硬编码

- [ ] Checkpoint 16.3.2 异常升级触发
  - 实现项: 预过滤命中的 warning / critical 信号生成 `system_event`, 经 `ModeratorAgent` 路由进入统一执行内核 (`ProactiveMultiAgentWorkflow.run()`), 不形成旁路; 升级事件附带完整感知快照作为证据
  - 验收方法: 注入 critical 信号, 观察是否生成 `system_event` 并进入主链执行; 检查 run_trace 中事件链路完整性
  - 验收证据: 升级事件 trace, ModeratorAgent 路由记录, run_trace.v2 事件链
  - 通过标准: critical 信号 100% 生成 `system_event` 并进入统一执行内核; 事件链路在 run_trace.v2 中完整可追溯; 不存在绕过主链的旁路

- [ ] Checkpoint 16.3.3 LLM 频率控制
  - 实现项: 对感知升级触发的 LLM 调用纳入 `ProactiveBudgetManager` 预算治理, 设置感知链路独立的 token budget 和频控上限; 触发熔断后降级为纯规则处置, 不再调用 LLM
  - 验收方法: 注入高频异常信号, 观察频控和熔断行为; 检查预算消耗记录
  - 验收证据: 预算消耗记录, 频控触发日志, 熔断降级 trace
  - 通过标准: 感知链路 LLM 调用受预算约束, 超限触发熔断; 熔断后降级为纯规则处置不调用 LLM; 感知链路 LLM 成本不超过总预算的 20%

### 方向十九. 自主处置与人类升级

#### 目标

简单问题由系统自主处置 (容器重启 / 缓存清理), 复杂问题升级人类, 处置结果全程追踪并沉淀为 Skill.

- [ ] Checkpoint 16.4.1 简单问题自主处置
  - 实现项: 为常见低风险问题实现自主处置动作 (容器重启 / 缓存清理), 通过新增 MCP 工具执行, 受五道关卡治理 (RBAC → 预算 → 审批 → 超时重试 → 收据); 处置动作产出标准化 receipt 并进入 run_trace
  - 验收方法: 注入容器 exited 信号, 观察系统是否自主重启容器; 检查 receipt 和 run_trace 记录
  - 验收证据: 处置动作 trace, 工具调用 receipt, 容器恢复记录
  - 通过标准: 低风险问题自主处置成功率 >= 90%; 所有处置动作经五道关卡且产出 receipt; 不存在绕过 tool_executor 的旁路

- [ ] Checkpoint 16.4.2 复杂问题人类升级
  - 实现项: 复杂问题 (无法用规则处置或处置失败) 通过 `ask_human` 节点升级人类, 升级消息附带完整证据链 (感知快照 + 诊断结果 + 候选处置方案); 人类决策后系统继续执行
  - 验收方法: 注入复杂异常信号, 观察是否触发 `ask_human` 升级; 模拟人类决策, 观察系统恢复执行
  - 验收证据: 升级消息记录, `ask_human` 节点 trace, 人类决策回执
  - 通过标准: 复杂问题 100% 触发 `ask_human` 升级; 升级消息包含完整证据链; 人类决策后系统正确恢复执行

- [ ] Checkpoint 16.4.3 处置结果追踪与 Skill 沉淀
  - 实现项: 所有处置结果 (自主/人类) 进入 run_trace.v2 全链路追踪; 高置信处置经验经 `SkillProposer` 沉淀为 Skill, 纳入技能自创闭环; 失败经验同样记录用于后续改进
  - 验收方法: 运行处置 case, 检查 run_trace 中处置链路完整性; 检查 Skill 沉淀记录
  - 验收证据: 处置链路 run_trace, Skill 沉淀记录, 失败经验记录
  - 通过标准: 所有处置动作在 run_trace.v2 中完整可追溯; 高置信经验成功沉淀为 Skill; 失败经验同样记录可查

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| 感知风暴放大 LLM 成本 | 异常频发时 LLM 调用失控, 成本爆炸 | 轻量级预过滤层前置消化正常信号; 感知链路独立 token budget; 熔断后降级为纯规则处置 |
| 自主处置误操作 | 系统误重启关键容器导致服务中断 | 自主处置仅限白名单低风险动作; 所有处置经五道关卡治理; 高风险操作强制 `ask_human` 升级 |
| 感知协程资源泄漏 | 长期运行协程泄漏内存或任务 | 协程具备优雅退出能力; 连续失败熔断; 感知协程与用户任务隔离执行 |
| 数据源连接不稳定 | 基础设施波动导致感知快照缺失 | 单数据源失败降级为空快照不中断协程; 快照标记 `status=unavailable`; 多数据源交叉验证 |
| 主动任务与用户任务冲突 | 主动协作挤占用户任务资源 | `ProactiveBudgetManager` 预算隔离; 用户任务豁免规则; 并发上限控制 |

## 成功标准 (Exit Criteria)

- `server.py` 启动后常驻感知协程持续运行, 不再是一次性请求-响应模式
- `_perceive_environment()` 接入 Docker / Redis / MySQL / Prometheus 四类真实数据源, 产出结构化感知快照
- 轻量级预过滤层过滤绝大多数正常信号, 感知链路 LLM 成本不超过总预算的 20%
- 简单问题自主处置成功率 >= 90%, 所有处置经五道关卡且产出 receipt
- 复杂问题 100% 触发 `ask_human` 人类升级, 附带完整证据链
- 所有处置动作在 run_trace.v2 中完整可追溯, 高置信经验沉淀为 Skill
- 感知协程异常不影响用户任务执行, 连续失败触发熔断

## 交付物清单

- [ ] 代码: server.py 常驻感知协程, `_perceive_environment()` 四类数据源接入, 预过滤规则引擎, 自主处置动作, 新增 MCP 工具 (容器状态查询 / 容器重启 / 缓存清理 / Prometheus 指标查询)
- [ ] 测试: 感知协程生命周期测试, 数据源接入对照测试, 预过滤规则匹配测试, 自主处置集成测试, 人类升级流程测试, LLM 频控熔断测试
- [ ] 文档: Phase 10 文档回写, 感知数据源对照说明, 预过滤规则配置说明
- [ ] 评测: 感知快照准确性基准, 自主处置成功率基准, LLM 成本控制基准, 端到端 7*24 运行 trace

## 相关文档

- PRD: [docs/PRD.md](../PRD.md)
- 架构: [docs/ARCHITECTURE.md](../ARCHITECTURE.md)