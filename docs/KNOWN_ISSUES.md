# KNOWN ISSUES — 已确认缺陷登记册

## 定位声明

本文件登记**当前代码/配置中已确认的缺陷**：即行为与设计意图不符、与文档曾声称的能力不符、或存在运行隐患的问题，供后续按优先级修复。

> **本清单不是需求路线图。** 项目已于 **2026-08-25** 经决策取消全部规划中的功能需求（移除 RFC-007 治理与能力追赶路线及全部规划 feature flag，见 [CHANGELOG.md](../CHANGELOG.md) 2026-08-25 条目）。本文件中的每一条都是"现在代码里就存在的 bug / 隐患"，**不是**"未来要做的功能"。bug 是 bug、需求是需求，二者不可混淆。

- **登记范围**：仅收录经源码/配置逐条核实、可复现证据的缺陷。
- **修复策略**：本批缺陷的代码修复由项目维护者后续自行处理；本文件仅负责如实登记，不代改代码逻辑。
- **发现轮次**：全部 12 条于 **2026-09-03 第三轮文档诚实性审计**中核实登记。
- **状态口径**：所有条目当前状态均为**未修复**（本文件创建时点）。

---

## 缺陷总览

| ID | 严重度 | 标题 | 状态 |
|----|--------|------|------|
| [KI-001](#ki-001) | High | 调度链路未挂载（CronManager 生产入口缺失） | 未修复 |
| [KI-002](#ki-002) | High | Skill Chroma 向量通道未注入（语义检索恒走词袋） | 未修复 |
| [KI-003](#ki-003) | High | 补救动作绕过治理（无五道关卡/无 receipt/工具缺失） | 未修复 |
| [KI-004](#ki-004) | Medium | remediation Skill 沉淀仅内存（重启丢失） | 未修复 |
| [KI-005](#ki-005) | Medium | embedding base_url 代码默认值与部署配置不一致 | 未修复 |
| [KI-006](#ki-006) | Medium | docker-compose 未透传 12 个已声明变量 | 未修复 |
| [KI-007](#ki-007) | Medium | K8s configmap 缺成本单价变量 | 未修复 |
| [KI-008](#ki-008) | Medium | requirements.txt 缺显式依赖（aiohttp / starlette） | 未修复 |
| [KI-009](#ki-009) | Low | 迁移脚本 006 无执行通道 | 未修复 |
| [KI-010](#ki-010) | Low | tool_executor.py Optional 未导入（惰性注解掩盖） | 未修复 |
| [KI-011](#ki-011) | Low | 评测证据文件未入库（实测数字不可复核） | 未修复 |
| [KI-012](#ki-012) | Medium | 成本熔断 5min 档位与数据窗口错配 | 未修复 |

---

<a id="ki-001"></a>
## KI-001 · 调度链路未挂载（CronManager 生产入口缺失）

- **严重度**：High
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- `CronManager` 类定义于 [cron_manager.py](../src/riskagent_backend/scheduling/cron_manager.py)（`class CronManager`，约 L130），但在 `src/` 全目录中**从未被实例化**——`CronManager()` 构造调用只出现在 `tests/`（`tests/unit/test_cron_manager.py`、`tests/unit/test_cron_manager_enhanced.py`、`tests/integration/test_cron_workflow.py` L280/L357/L442/L479、`tests/acceptance/test_self_improving_loop.py` L956）。
- `run_cron_triggered_workflow()`（[proactive_workflow.py](../src/riskagent_backend/orchestration/proactive_workflow.py) L272）在 `src/` 中**零生产调用方**，唯一调用点在 `tests/integration/test_cron_workflow.py`。
- `set_trigger_callback()`（cron_manager.py L523）与 `check_recursion()`（cron_manager.py L297）在 `src/` 中**无调用方**，调用点全部位于 `tests/`。
- `proactive_workflow.py` L69 `from ...scheduling.cron_manager import CronTask` 仅导入 `CronTask` 数据类用于类型标注，并非挂载调度器。
- 服务入口 [server.py](../src/riskagent_backend/server.py) 的启动流程只启动常驻感知守护进程（`start_proactive_monitors()`），**不含任何调度器/cron 启动逻辑**（全文无 `CronManager`、`cron`、`scheduler` 启动调用）。

### 核验命令

```bash
# src/ 中是否有 CronManager 实例化（预期：src/ 无，仅类定义与 __init__ 导出；构造调用全在 tests/）
grep -rn "CronManager(" src/ tests/
# run_cron_triggered_workflow 的调用方（预期：src/ 仅定义处，调用全在 tests/）
grep -rn "run_cron_triggered_workflow" src/ tests/
# server.py 是否启动调度器（预期：无 cron/scheduler 启动）
grep -niE "cron|scheduler|CronManager" src/riskagent_backend/server.py
```

### 影响

定时触发（cron）能力**实际不可用**：库层实现与单测完整，但无生产入口挂载，用户无法通过运行中的服务创建/触发任何定时任务。

> 关联文档：[ARCHITECTURE.md](ARCHITECTURE.md) §12.2 已如实标注"库层实现完整、生产未挂载"。注意 [CHANGELOG.md](../CHANGELOG.md) 顶部条目曾概括为"CronManager 已接入主链"，该措辞与代码实况及 ARCHITECTURE §12.2 不符，以本条为准。

---

<a id="ki-002"></a>
## KI-002 · Skill Chroma 向量通道未注入（语义检索恒走词袋）

- **严重度**：High
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- 主链在 [proactive_workflow.py](../src/riskagent_backend/orchestration/proactive_workflow.py) L101 以**无参** `SkillStore()` 构造 skill store，未传入 `chroma_store=` 也未传入 `llm_client=`。
- [skill_store.py](../src/riskagent_backend/skills/skill_store.py) 的 `_chroma_enabled` 属性（L63）判定为 `self._llm_client is not None and self._chroma_store is not None`；因主链无参构造，二者均为 `None`，故 `_chroma_enabled` **恒为 False**。
- 因此 `_index_skill()`（L135，分支 L141）、`delete()`（L220，分支 L227）、`_semantic_search()`（L249，分支 L258）中的 Chroma 分支永不进入，Skill 语义检索**始终回退到进程内 `SemanticIndexer`（词袋模型）**。
- `chroma_store=` 注入仅存在于测试 mock：`SkillStore(llm_client=..., chroma_store=...)` 的调用点全部位于 `tests/unit/test_skill_store.py`（14 处），`src/` 中无任何注入。

### 核验命令

```bash
# 主链 SkillStore 构造是否传 chroma_store（预期：无参 SkillStore()）
grep -rn "SkillStore(" src/
# chroma_store= 注入点分布（预期：仅 tests/）
grep -rn "chroma_store=" src/ tests/
# _chroma_enabled 判定条件
grep -n "_chroma_enabled" src/riskagent_backend/skills/skill_store.py
```

### 影响

[RFC-005](decisions/RFC-005-skill-semantic-retrieval-upgrade.md) 需求一设计的 Chroma ANN（近似最近邻）向量检索在生产链路**未生效**，Skill 检索质量退化为词袋匹配，与文档声称的"语义向量检索"能力不符。

---

<a id="ki-003"></a>
## KI-003 · 补救动作绕过治理（无五道关卡 / 无 receipt / 工具缺失）

- **严重度**：High
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- [perception/remediation.py](../src/riskagent_backend/perception/remediation.py) 的 `_execute_low_risk_action()`（L112）只做**规则判定 + 日志记录**：根据信号来源返回 `RemediationAction` 枚举（RESTART_SUGGESTION / LOG_ALERT / LOG_NOTIFICATION）与描述字符串，随后 `logger.info(...)`（L143）。处置**不经过** `tool_executor` 的五道关卡（RBAC / 审批 / 预算 / 超时 / receipt），也**无 receipt 产出**。
- `RemediationResult(... success=True ...)`（L138）为**无条件置位**——不论是否真正执行任何副作用，`success` 恒为 True，`self._total_successful` 随之无条件 +1（L146）。
- phase-10 文档曾声称的**容器状态查询 / 容器重启 / 缓存清理** MCP 工具在代码中**不存在**：[tool_registry.py](../src/riskagent_backend/orchestration/tool_registry.py) 的 `_TOOL_REGISTRY`（L30）共 **14 个工具**、[mcp_tools.py](../src/riskagent_backend/tools/mcp_tools.py) `register_tools()`（L19）注册 **8 个工具**，两处均无容器/重启/缓存清理类工具（`grep -iE "container|restart|docker|cache_clear"` 于 `src/riskagent_backend/tools/` 零命中）。
- `_remediation_manager` property（[proactive_agents/base.py](../src/riskagent_backend/proactive_agents/base.py) L448，经 `_get_remediation_manager()` 懒加载 L58）在 `src/` 中**无消费者**：`self._remediation_manager` 无任何调用点，`remediate()` 生产链路无调用方（仅 `tests/unit/test_remediation_p5_p9.py` 调用）。

### 核验命令

```bash
# remediation 是否经 tool_executor / 是否有 receipt（预期：无）
grep -niE "tool_executor|receipt|execute_agent_command" src/riskagent_backend/perception/remediation.py
# success=True 无条件置位
grep -n "success=True" src/riskagent_backend/perception/remediation.py
# 注册工具总数（预期：registry 14 个 action，mcp_tools 8 个 mcp.tool()）
grep -c "ToolMeta(" src/riskagent_backend/orchestration/tool_registry.py
grep -c "mcp.tool()" src/riskagent_backend/tools/mcp_tools.py
# 容器类工具是否存在（预期：零命中）
grep -rniE "container|restart|docker|cache_clear" src/riskagent_backend/tools/
# _remediation_manager 消费者（预期：仅 base.py 定义处）
grep -rn "_remediation_manager" src/
```

### 影响

主动监控的"处置"环节实为**只读日志建议**，不产生任何真实副作用，却对外报告 `success=True`；文档曾声称的容器治理工具并不存在。这与"自主处置受五道关卡治理"的设计意图严重不符，属于治理可信度缺陷。

> 关联文档：[phase-10-active-monitoring.md](phases/phase-10-active-monitoring.md) L57/L148 已如实标注工具未落地、处置不经治理，并引用本条 KI-003。

---

<a id="ki-004"></a>
## KI-004 · remediation Skill 沉淀仅内存（重启丢失）

- **严重度**：Medium
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- [perception/remediation.py](../src/riskagent_backend/perception/remediation.py) 的 `_try_create_skill()`（L153）将处置经验写入**进程内 dict** `self._skill_patterns`（L75 初始化，L164-176 写入），无任何持久化后端。进程重启即全部丢失。
- 该方法**未接入** `SkillProposer` / `SkillStore`：全文无 `SkillStore`、`SkillProposer`、`create()`、`PersistenceBackend` 引用。所谓"沉淀为 Skill"仅是内存字典累加 `occurrence_count`，`result.skill_created = True`（L177）为形式化置位。
- `SkillProposer` 的持久化路径（经 `SkillStore.create → PersistenceBackend`）仅接入 `workflow_finalization` 工作流收尾链路，与 remediation 处置链路无关。

### 核验命令

```bash
# _skill_patterns 是否为纯内存 dict、是否接持久化（预期：内存 dict，无 SkillStore/PersistenceBackend）
grep -nE "_skill_patterns|SkillStore|SkillProposer|PersistenceBackend|_try_create_skill" src/riskagent_backend/perception/remediation.py
```

### 影响

remediation 声称的"处置经验沉淀为可复用 Skill"能力**不具备持久性**，重启后归零，无法形成跨进程的经验积累闭环。

> 关联文档：[phase-10-active-monitoring.md](phases/phase-10-active-monitoring.md) L18 已于 2026-09-03 复核撤下原"已修复"标注，并引用本条 KI-004。

---

<a id="ki-005"></a>
## KI-005 · embedding base_url 代码默认值与部署配置不一致

- **严重度**：Medium
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- [config_pydantic.py](../src/riskagent_backend/config_pydantic.py) 中 `llm_embedding_base_url` 字段（L71）默认值为**空串** `""`，其 description 与 [config.py](../src/riskagent_backend/config.py) `get_llm_embedding_base_url()`（L150）docstring 均称"为空时回退 LLM_BASE_URL"。
- 回退逻辑（config.py L156-159）：值为空时 `return get_llm_base_url()`。而当前主 LLM Base URL 默认为 DeepSeek 官方 `https://api.deepseek.com`（docker-compose.yml L102），**DeepSeek 官方 API 不提供 `/embeddings` 端点**。
- 因此在未显式配置 `LLM_EMBEDDING_BASE_URL` 的情况下裸跑，`llm_client.py` L377 `url = f"{...}/embeddings"` 会打到 DeepSeek 官方 → **404**。
- 实际所有部署配置均**硬编码硅基流动**兜底：docker-compose.yml（L105/L157 `https://api.siliconflow.cn/v1`）、deploy/k8s/values.yaml（L138）、values-ci.yaml（L63）、values-local-e2e.yaml（L65）。代码默认值（空串回退 DeepSeek）与部署默认值（硅基流动）不一致，靠部署层硬编码掩盖了代码层的错误回退。

### 核验命令

```bash
# 代码默认值与回退逻辑
grep -n "llm_embedding_base_url" src/riskagent_backend/config_pydantic.py
grep -n "get_llm_embedding_base_url" src/riskagent_backend/config.py
# 各部署配置硬编码硅基流动
grep -rn "EMBEDDING_BASE_URL\|embeddingBaseUrl" docker-compose.yml deploy/k8s/
```

### 影响

若脱离现有部署模板（如新环境仅依赖代码默认值 + `.env` 未设该变量），embedding 调用将打到无 embeddings 端点的 DeepSeek 官方而 404 失败。代码默认回退目标与"embedding 需独立供应商"的设计事实自相矛盾。

---

<a id="ki-006"></a>
## KI-006 · docker-compose 未透传 12 个已声明变量

- **严重度**：Medium
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

[docker-compose.yml](../docker-compose.yml) 的 `mcp-server.environment`（L83-116）缺失以下 **12 个**在 `.env.example` 与代码中已声明的变量，导致用户在 `.env` 修改这些值时容器内不生效：

1. `HITL_AUTO_APPROVE`（.env.example L64；config_pydantic.py L101 `hitl_auto_approve`）
2. `CHROMA_SKILLS_COLLECTION`（.env.example L32；config_pydantic.py L153）
3. `SKILL_QUERY_REWRITE_ENABLED`（.env.example L29；config_pydantic.py L166）
4. `SKILL_QUERY_REWRITE_TIMEOUT`（.env.example L30；config_pydantic.py L169）
5. `SKILL_QUERY_REWRITE_CACHE_SIZE`（.env.example L31；config_pydantic.py L172）
6. `SKILL_HYBRID_VECTOR_WEIGHT`（.env.example L33；config_pydantic.py L177）
7. `REDIS_HOST`（.env.example L41；config_pydantic.py L94）
8. `REDIS_PORT`（.env.example L42；config_pydantic.py L95）
9. `REDIS_DB`（.env.example L43；config_pydantic.py L96）
10. `LLM_COST_PROMPT_PER_1K`（.env.example L67；token_tracker.py L451 经 `safe_env_float` 读取）
11. `LLM_COST_COMPLETION_PER_1K`（.env.example L68；token_tracker.py L452）
12. `REDIS_PASSWORD`（.env.example L44；config_pydantic.py L97 `redis_password` 字段、L208-209 用于构造 `redis_url`；[redis_source.py](../src/riskagent_backend/perception/data_sources/redis_source.py) L41 读取）

> 排除项：`MYSQL_ROOT_PASSWORD`（.env.example L3）虽在 `.env.example` 声明，但仅由 docker-compose `mysql` 服务使用、未被 `src/` 任何代码读取，故不计入本条“已声明却未透传给 mcp-server”的清单。

> 说明：compose 已通过 `REDIS_URL`（L91）整体覆盖 Redis 连接，故 `REDIS_HOST/PORT/DB/PASSWORD` 四者在本部署形态下即便透传也会被 `REDIS_URL` 优先覆盖（config_pydantic.py L203 `redis_url` 属性显式 URL 优先；`REDIS_PASSWORD` 已被插入 `REDIS_URL` 的 `redis://:${REDIS_PASSWORD}@...`）；但作为"已声明却未透传"的变量仍登记在此，供非 compose 部署形态参考。当前这些变量的缺失**恰好**由 pydantic 默认值 / `safe_env_float` 默认值兜底，与 `.env.example` 示例值一致，故未暴露为运行故障。

### 核验命令

```bash
# 逐个确认 compose mcp-server 段是否透传（预期：均无命中）
for v in HITL_AUTO_APPROVE CHROMA_SKILLS_COLLECTION SKILL_QUERY_REWRITE_ENABLED \
         SKILL_QUERY_REWRITE_TIMEOUT SKILL_QUERY_REWRITE_CACHE_SIZE SKILL_HYBRID_VECTOR_WEIGHT \
         REDIS_HOST REDIS_PORT REDIS_DB LLM_COST_PROMPT_PER_1K LLM_COST_COMPLETION_PER_1K; do
  echo -n "$v: "; grep -c "$v" docker-compose.yml
done
# REDIS_PASSWORD 未作为独立 env 透传给 mcp-server（仅被插入 REDIS_URL）——
# 提取 mcp-server.environment 段确认无独立 REDIS_PASSWORD 键（预期：0）
sed -n '/^  mcp-server:/,/^  test-runner:/p' docker-compose.yml | grep -cE "^[[:space:]]+REDIS_PASSWORD:"
```

### 影响

配置"漂移"隐患：用户在 `.env` 中调整这些参数后 `docker compose up` 不生效，行为与预期不符；一旦 pydantic 默认值与 `.env.example` 示例值不再一致，将直接暴露为运行期配置错误。

---

<a id="ki-007"></a>
## KI-007 · K8s configmap 缺成本单价变量

- **严重度**：Medium
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- `LLM_COST_PROMPT_PER_1K` / `LLM_COST_COMPLETION_PER_1K` 由 [token_tracker.py](../src/riskagent_backend/llm/token_tracker.py) `_estimate_cost()`（L451-452）经 `safe_env_float` 读取，用于覆盖内置定价表。
- 这两个变量**不在** K8s [configmap.yaml](../deploy/k8s/templates/configmap.yaml) 与 [values.yaml](../deploy/k8s/values.yaml) 中（`grep -rn "LLM_COST" deploy/` 零命中）。
- 因此生产环境无法经 Helm values 覆盖成本单价，只能回退到 `cost_model.PRICING_TABLE` 内置定价。

### 核验命令

```bash
# deploy/ 下是否存在成本单价变量（预期：零命中）
grep -rn "LLM_COST" deploy/
# 代码读取点
grep -n "LLM_COST_PROMPT_PER_1K\|LLM_COST_COMPLETION_PER_1K" src/riskagent_backend/llm/token_tracker.py
```

### 影响

生产环境成本单价不可经 Helm 配置化覆盖，模型定价变动时只能改代码/镜像，运维灵活性缺失；与 KI-006 中 compose 缺失同源，属成本可观测性配置链路不完整。

---

<a id="ki-008"></a>
## KI-008 · requirements.txt 缺显式依赖（aiohttp / starlette）

- **严重度**：Medium
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- `aiohttp` 被 [llm/llm_client.py](../src/riskagent_backend/llm/llm_client.py) L19 `import aiohttp` **直接导入**，但 [requirements.txt](../requirements.txt) 中**未声明** aiohttp（全文无该条目）。
- `starlette` 被 [server.py](../src/riskagent_backend/server.py) L16-17 直接导入（`from starlette.requests import Request` / `from starlette.responses import ...`），requirements.txt 中**未显式声明**，仅靠 `mcp[cli]`（L2）的传递依赖间接引入。

### 核验命令

```bash
# 代码直接导入点
grep -rn "^import aiohttp\|^from starlette\|^import starlette" src/
# requirements.txt 是否声明（预期：均无命中）
grep -niE "aiohttp|starlette" requirements.txt
```

### 影响

依赖契约不完整：aiohttp 完全未在依赖清单声明，一旦传递依赖链变化即 `ImportError`；starlette 作为直接导入的一级依赖仅靠 mcp 传递引入，版本不受本仓库约束，存在被上游升级破坏的隐患。

---

<a id="ki-009"></a>
## KI-009 · 迁移脚本 006 无执行通道

- **严重度**：Low
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- [db/migrations/006_add_skill_summary_column.sql](../db/migrations/006_add_skill_summary_column.sql) 存在，但**未被任何自动化初始化通道引用**：
  - docker-compose.yml 的 mysql 服务只挂载 `003`/`004`/`005` 三个迁移脚本到 `/docker-entrypoint-initdb.d`（L18-20），**未挂载 006**。
  - K8s [mysql-statefulset.yaml](../deploy/k8s/templates/mysql-statefulset.yaml) 的 `mysql-initdb` ConfigMap 只打包 `sql/01_init_db.sql`~`sql/04_memory_store.sql`（L17-24），**不含 006**（且 K8s 用的是 `deploy/k8s/sql/` 目录，与 `db/migrations/` 为两套脚本）。
- 该脚本对应 RFC-005 需求三的 skill `summary` 字段列，老库升级需**手动执行** 006。

### 核验命令

```bash
# compose 挂载的迁移脚本（预期：仅 003-005）
grep -n "db/migrations" docker-compose.yml
# K8s initdb 打包的脚本（预期：仅 sql/01-04）
grep -n "Files.Get" deploy/k8s/templates/mysql-statefulset.yaml
# 006 是否被任何地方引用（预期：零命中）
grep -rn "006_add_skill_summary" docker-compose.yml deploy/
```

### 影响

对**新建库**无影响（初始化脚本可能已含该列定义）；但对**已存在的老库**，006 迁移不会自动执行，需人工介入，存在"文档称已迁移、实际库结构未升级"的漂移风险。

---

<a id="ki-010"></a>
## KI-010 · tool_executor.py Optional 未导入（惰性注解掩盖）

- **严重度**：Low
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- [orchestration/tool_executor.py](../src/riskagent_backend/orchestration/tool_executor.py) 的 `ToolResult` dataclass 字段 `error: Optional[str]`（L46）使用了 `Optional`，但文件顶部 `from typing import Any, Callable`（L6）**未导入 Optional**。
- 该 NameError 被 L1 `from __future__ import annotations` **惰性化掩盖**：所有注解被当作字符串延迟求值，dataclass 定义时不解析类型，故导入模块不报错。
- 但任何对该类调用 `typing.get_type_hints(ToolResult)` 的操作都会在解析 `Optional[str]` 时抛 `NameError: name 'Optional' is not defined`。

### 核验命令

```bash
# typing 导入行是否含 Optional（预期：仅 Any, Callable）
grep -n "^from typing" src/riskagent_backend/orchestration/tool_executor.py
# Optional 使用点
grep -n "Optional" src/riskagent_backend/orchestration/tool_executor.py
# 复现 NameError（预期：抛 NameError）
python -c "import typing; from riskagent_backend.orchestration.tool_executor import ToolResult; typing.get_type_hints(ToolResult)"
```

### 影响

运行期常规路径不受影响（惰性注解掩盖）；但一旦引入需要运行时解析类型的机制（如 pydantic、`get_type_hints`、某些序列化/校验库），即触发 `NameError`。属潜伏型导入缺陷。

---

<a id="ki-011"></a>
## KI-011 · 评测证据文件未入库（实测数字不可复核）

- **严重度**：Low
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- `eval/results/`、`eval/reports/` 目录**当前不存在**于仓库（`ls eval/` 无此二目录）。
- 多份文档引用的"实测"数字因此**不可复核**：
  - Token 总消耗下降 **48.40%**、缓存命中率 **83.33%**、前缀缓存节省 1,213 tokens —— 见 [phase-8-prompt-optimization.md](phases/phase-8-prompt-optimization.md) L68/L93/L100、[phase-9](phases/phase-9-evidence-first-hardening.md) L101、[STRATEGY.md](STRATEGY.md) L140、[PRD.md](PRD.md) §11「LLM token 成本较当前下降 20% 以上」行、[RESUME.md](RESUME.md) L56-59、[RFC-001](decisions/RFC-001-hermes-upgrade.md) L289、[RFC-002](decisions/RFC-002-evidence-first-hardening.md) L235。
  - 引用的报告路径 `eval/results/prompt_layering/20260709_155819_cost_report.md`、`eval/results/memory_ab/...`（phase-2 L59/L111）均指向不存在的文件。
- `.gitignore` L60-61 注释意图为“保留 `.gitkeep`、忽略其余产物”，但实际仅 `eval/results/.gitkeep` 一条模式（并未忽略 `eval/results/` 产物，注释与模式亦相互矛盾）；且 `git ls-files eval/results` 零命中——该目录与 `.gitkeep` 在仓库中均不存在，即历史上从未有任何评测结果入库。

### 核验命令

```bash
# 目录是否存在（预期：No such file or directory）
ls eval/results eval/reports
# 历史上是否有任何评测结果入库（预期：零命中）
git ls-files eval/results
# 引用实测数字的文档位置
grep -rn "48.40%\|83.33%" docs/
```

### 影响

文档中大量"实测"结论缺乏可复核的证据文件支撑，审计/复现者无法验证数字真实性。RESUME.md L59 已注明"该路径已删除，报告内容已纳入验收文档"，属已知的证据缺失，登记在此以明确"数字结论目前不可独立复核"。

> 关联文档：[phase-8-prompt-optimization.md](phases/phase-8-prompt-optimization.md) L93 已标注报告为运行期产物、已删除未入库，并引用本条 KI-011。

---

<a id="ki-012"></a>
## KI-012 · 成本熔断 5min 档位与数据窗口错配

- **严重度**：Medium
- **状态**：未修复
- **发现轮次**：2026-09-03 第三轮审计

### 现象与证据

- [governance/cost_circuit_breaker.py](../src/riskagent_backend/governance/cost_circuit_breaker.py) 的 `BUDGETS`（L29-33）定义三级预算档位，其中含 `"5min": {"token_limit": 50000, "cost_limit": 0.01}`。
- `check()`（L41）读取 `get_token_tracker().summary()`（L50），并对**每个档位**用同一份 `summary` 的 `summary["total_tokens"]`（L72）与 `summary["cost_estimate"]`（L89）做比较。
- 但 [token_tracker.py](../src/riskagent_backend/llm/token_tracker.py) 的 `summary()`（L238）返回的 `total_tokens`（L247/L313）来自 `self._records`，其清理窗口为 `_window_s`（默认 **3600s = 1h**，见 `__init__` L99 与 `_cleanup_locked` L349）。TokenTracker **只有 1h（`_records`）与 24h（`_daily_records`）两个窗口**，无 5min 窗口。
- 因此 "5min" 档位标签与其实际比较的数据（1h 累计值）**不一致**：5min 档实际是按 1h 窗口的累计 token/cost 判断是否熔断。

### 核验命令

```bash
# 熔断档位定义（含 5min=$0.01）
grep -n "5min\|BUDGETS\|token_limit\|cost_limit" src/riskagent_backend/governance/cost_circuit_breaker.py
# TokenTracker 窗口只有 1h/24h
grep -n "window_s\|daily_window_s\|_records\|_daily_records" src/riskagent_backend/llm/token_tracker.py
# summary()["total_tokens"] 来源窗口
grep -n "total_tokens\|def summary" src/riskagent_backend/llm/token_tracker.py
```

### 影响

5min 档熔断阈值（50K tokens / $0.01）本意是"5 分钟内"的快速熔断保护，实际却按 1h 累计值判断，会在 1h 累计超过 50K tokens 时（远早于真正的 5min 高频场景）就触发 5min 档熔断——档位语义与统计窗口错配，熔断时机与设计意图不符。

---

## 附：登记与维护约定

- 本文件为**缺陷登记册**，非需求文档；新增条目须满足"代码/配置中已确认、有可复现证据"，并沿用 `KI-0NN` 编号与本文格式。
- 每条须写明**核验命令**，确保登记册本身可被独立复核、绝对真实。
- 缺陷修复后，将对应条目状态由"未修复"更新为"已修复（commit/日期）"，**不删除历史记录**，保留缺陷发现与修复的完整轨迹。

### 缺陷修复同步 checklist

本 checklist 用于防止"单点修复、多点漏灌"导致文档口径漂移。

修复任一 KI 条目时，须同步更新以下位置后再提交：

- [ ] KNOWN_ISSUES.md：对应条目状态改为「已修复（commit <hash>，YYYY-MM-DD）」，原现象/证据描述保留不删（历史归档）
- [ ] ARCHITECTURE.md：引用该 KI 的现状注记（grep "KI-0NN" 定位）改为已修复口径
- [ ] README.md / PRD.md：引用该 KI 的「已知限制」描述同步更新
- [ ] STRATEGY.md / MEMORY.md / RESUME.md：引用该 KI 的段落同步更新（grep 确认）
- [ ] phases/ 中带该 KI 注记的验收文档：追加现状注记（不改历史原文）
- [ ] CHANGELOG.md：新增修复条目（附 commit hash）
