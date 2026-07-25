# RFC-005: Skill 语义检索升级（向量库 + 远程 Embedding + Summary 字段）

| 字段 | 值 |
|------|-----|
| Status | Proposed |
| Date | 2026-07-22 |
| Author | RiskAgent-BackEnd 项目组 |

## Update Log

| 日期 | 变更 |
|------|------|
| 2026-07-22 | 初始创建，提出 Skill 语义检索升级三项需求 |

## 上下文

当前 Skill 系统的语义检索依赖进程内 `SemanticIndexer`（`src/riskagent_backend/memory/semantic_indexer.py`），其核心实现为：

1. **向量化**：词袋模型（Bag-of-Words），分词后 `hash(token) % 128` 映射到 128 维向量，L2 归一化
2. **相似度计算**：`cosine * 0.7 + token_overlap * 0.3`
3. **存储**：进程内 `dict[entry_id, entry]`，重启丢失
4. **比对文本**：`SkillStore._build_skill_text()` 将 Skill 的 `name + tags + applicable_conditions + steps[].description + steps[].expected_outcome + failure_boundary` 全字段拼接

该方案存在三个核心缺陷：

### 缺陷一：无语义理解能力

词袋模型只做字面 token 匹配，同义词、近义词无法关联：

| Query 文本 | Skill 文本 | 词袋得分 | 语义实际关系 |
|------------|-----------|---------|-------------|
| "监控交易台敞口" | "监测持仓超限" | 0.0（无共同 token） | 语义高度相关 |
| "检查系统健康" | "诊断服务状态" | 0.0（无共同 token） | 语义高度相关 |
| "分析 breach 原因" | "定位超限根因" | 0.0（无共同 token） | 语义高度相关 |

导致 Skill 召回率低，相似任务无法复用历史经验，`few_shot_reuse_rate` 难以达到 PRD 目标 > 30%。

### 缺陷二：进程内存储不可恢复

`SemanticIndexer._index` 是进程内 `dict`，进程重启后全部丢失。虽然有 MySQL 持久化兜底（`restore_from_persistence()` 可从 MySQL 重新加载 Skill），但加载后需全量重建向量索引，Skill 数量增长后重建耗时不可忽略。

### 缺陷三：全字段拼接稀释语义密度

当前 `_build_skill_text()` 将 6 类字段拼接为比对文本。steps 中的 `expected_outcome` 等字段引入大量噪音，语义向量被无关文本稀释，导致相似度计算不精准。

## 决策

对 Skill 语义检索链路做三项升级，构成一个完整的改造闭环：

| 编号 | 需求 | 核心变更 |
|------|------|---------|
| 需求一 | Skill 转为向量库存储 | `SemanticIndexer` 进程内 dict → 独立向量库 |
| 需求二 | 远程调用 OpenRouter 模型计算语义相似度 | 词袋向量 → 远程 LLM embedding |
| 需求三 | Skill 新增 summary 摘要字段 | 全字段拼接 → 一句话摘要作为语义比对锚点 |

三项需求的关系：

```
[需求三: summary 字段]  →  定义语义比对的锚点文本（高语义密度）
        |
        v
[需求二: OpenRouter embedding]  →  为 summary 生成真正的语义向量
        |
        v
[需求一: 向量库存储]  →  持久化向量并支持 ANN 检索
```

实施顺序：需求三先行（schema 变更），再做需求二（远程 embedding），最后做需求一（向量库迁移）。

## 方案设计

### 需求一：Skill 转为向量库存储

**目标**：将 Skill 的语义索引从进程内 `SemanticIndexer`（dict + 词袋向量）迁移至独立向量库，实现持久化存储和高效 ANN 检索。

**具体要求**：

- Skill 创建/更新时，自动基于 `summary` 字段生成 embedding 并写入向量库
- Skill 查询时，通过向量库做 ANN（近似最近邻）检索，替代当前的遍历式余弦计算
- 向量库重启后数据不丢失，无需全量重建索引
- 需保持与现有 `SkillStore.search()` 接口兼容，上层调用方（`SkillInjector`）无感知

**受影响组件**：

| 组件 | 文件 | 变更 |
|------|------|------|
| `SemanticIndexer` | `memory/semantic_indexer.py` | Skill 检索场景下废斥或降级为兜底方案（记忆系统仍可使用） |
| `SkillStore._index_skill()` | `skills/skill_store.py` | 改为写入向量库 |
| `SkillStore.search()` | `skills/skill_store.py` | 改为调用向量库 ANN 检索 |
| `SkillStore._keyword_fallback_search()` | `skills/skill_store.py` | 保留作为兜底（向量库不可用时降级） |
| `SkillStore.restore_from_persistence()` | `skills/skill_store.py` | 改为从向量库恢复 |

**接口兼容性**：

`SkillStore.search(query, limit, min_confidence)` 签名不变，内部实现从遍历 dict 改为调用向量库 API。`SkillInjector` 和 `SkillProposer.find_similar()` 无需修改。

### 需求二：远程调用 OpenRouter 模型计算语义相似度

**目标**：Skill 查询时不再用本地词袋向量计算相似度，改为远程调用 OpenRouter 提供的 embedding 接口，为 query 文本和 Skill `summary` 生成语义向量后计算相似度。

**具体要求**：

- 通过 OpenRouter API 调用 embedding 模型，为 query 文本和 Skill `summary` 生成语义向量
- 向量维度和模型名称待定（取决于选用的 OpenRouter 模型，见待解决问题）
- 需处理远程调用延迟和失败兜底：网络超时/API 异常时回退到关键词匹配（`_keyword_fallback_search`）
- 需考虑调用成本：Skill 的 embedding 在创建/更新时生成并缓存（写入向量库），query embedding 每次实时生成
- 需符合项目现有 `LLMClient` 的调用规范和治理约束（超时、重试、成本追踪）

**调用链路**：

```
[Agent task 描述]
    |
    v
[SkillInjector._build_query()]  →  query 文本
    |
    v
[OpenRouter embedding API]  →  query 向量（实时生成）
    |
    v
[向量库 ANN 检索]  →  top-K Skill（基于 summary 向量预存）
    |
    v
[过滤: status=active, confidence>=0.3]
    |
    v
[关键词兜底补全（若结果不足 max_skills）]
```

**与现有 LLMClient 的关系**：

项目已有 `LLMClient`（`src/riskagent_backend/llm/`）封装 LLM 调用。OpenRouter embedding 调用应复用或扩展现有 client，不绕过治理约束。具体实现方式待定：
- 方案 A：在 `LLMClient` 中新增 `embed()` 方法
- 方案 B：新建独立的 `EmbeddingClient` 类

### 需求三：Skill 新增 summary 摘要字段

**目标**：每个 Skill 增加一个 `summary` 字段，用一句话概括该 Skill 的用途，专门用于与来自 Agent 的 task 描述进行语义相似度比对的锚点文本。

**具体要求**：

- `skill.v1` schema 新增字段 `summary: str`，类型为字符串，长度建议 30-80 字
- `summary` 由 `SkillProposer` 在创建 Skill 时自动生成（从 task + orchestrator_output 中提炼一句话概括）
- `summary` 作为语义检索的主要比对文本（替代当前 `_build_skill_text()` 拼接全字段的方式）
- Skill 更新时如果核心 steps 发生变化，`summary` 应同步刷新
- 向量库中存储的 embedding 基于 `summary` 生成，而非拼接全字段

**Schema 变更示例**：

```json
{
  "schema_version": "skill.v1",
  "skill_id": "skill_a1b2c3d4e5f6",
  "name": "监控交易台敞口和系统状态",
  "summary": "当交易台敞口超限或系统健康指标异常时，自动获取敞口数据并定位 breach 原因",
  "tags": ["monitoring", "risk", "delta_one"],
  "applicable_conditions": [
    "任务涉及交易台敞口监控",
    "需要检查系统健康状态"
  ],
  "steps": [...],
  "failure_boundary": "...",
  "confidence": 0.92,
  ...
}
```

**为什么用 summary 而非全字段拼接**：

| | 全字段拼接（当前） | summary 字段（提案） |
|---|---|---|
| 文本来源 | name + tags + conditions + steps + failure_boundary | 一句话人工/LLM 概括 |
| 语义密度 | 低（噪音字段稀释） | 高（提炼核心意图） |
| 向量质量 | 被无关文本干扰 | 聚焦核心语义 |
| 存储成本 | 高（全字段向量化） | 低（单字段向量化） |
| 匹配精度 | query "监控敞口" vs steps "返回服务健康指标" → 噪音 | query "监控敞口" vs summary "敞口超限时自动定位 breach 原因" → 精准 |

**summary 生成策略**（待定，见待解决问题）：

- 方案 A：`SkillProposer` 创建 Skill 时调用 LLM 生成一句话概括
- 方案 B：`SkillProposer` 用规则从 `task.payload.content` + `orchestrator_output.intent` 提取关键短语拼接
- 方案 C：混合策略——规则提取初稿 + LLM 润色

**受影响组件**：

| 组件 | 文件 | 变更 |
|------|------|------|
| `skill_contract.py` | `skills/skill_contract.py` | `normalize_skill()` 增加 `summary` 默认值；`validate_skill()` 校验非空 |
| `SkillProposer._extract_skill_pattern()` | `skills/skill_proposer.py` | 新增 `summary` 生成逻辑 |
| `SkillStore._build_skill_text()` | `skills/skill_store.py` | 向量化文本来源改为 `summary`（而非全字段拼接） |
| `persistence_backend.py` | `memory/persistence_backend.py` | `_build_skill_row()` / `_parse_skill_row()` 增加 `summary` 字段映射 |
| MySQL `skill_store` 表 | `deploy/k8s/sql/` | 新增 `summary` 列（ALTER TABLE） |

## 与现有架构约束的兼容性

- **ADR-001（多 Agent 架构）**：本升级不改变多 Agent 协作架构，只增强 Skill 检索能力
- **ADR-003（统一记忆架构）**：`SemanticIndexer` 在记忆系统（长期经验记忆）中仍可保留进程内词袋模式，本 RFC 只针对 Skill 检索链路做升级，记忆系统不受影响
- **ADR-004（零信任工具治理）**：OpenRouter embedding 调用属于外部 API 调用，需纳入成本追踪和超时治理，但不涉及副作用工具审批
- **ADR-005（run_trace.v2）**：embedding 调用应记录到 trace（作为 LLM interaction 的一种），支持回放和成本审计
- **不形成旁路**：Skill 检索仍在 `proactive_workflow._build_orchestrator_context()` 中调用，不绕过统一执行内核

## Drawbacks / 缺点

### 远程依赖引入延迟和故障风险

词袋模型是进程内计算，零延迟、零外部依赖。改为远程 embedding 后：

- 每次查询增加一次网络往返（预计 100-500ms）
- OpenRouter API 不可用时 Skill 检索降级为关键词匹配，召回质量下降
- 生产环境需要监控 OpenRouter 可用性和延迟

**缓解**：Skill 的 embedding 预生成并缓存（写入向量库），只有 query embedding 需要实时生成。关键词兜底在 API 故障时自动生效。

### 成本不可控

远程 embedding 按调用量计费。如果每次 planning 阶段都调用 OpenRouter，成本随任务量线性增长。

**缓解**：
- Skill embedding 只在创建/更新时生成一次，写入向量库缓存
- query embedding 每次实时生成，但单次调用成本极低（embedding 模型价格远低于 chat 模型）
- 可考虑对高频 query 做 embedding 缓存（LRU）

### 向量库部署复杂度

新增向量库组件，增加部署和运维复杂度。

**缓解**：
- 项目已有 Chroma（knowledge 子系统），可复用现有部署
- 或选择 pgvector（PostgreSQL 扩展），不引入新组件

### summary 生成质量不稳定

如果 `summary` 由 LLM 生成，可能存在幻觉或概括不准确的问题。

**缓解**：
- summary 生成时可注入 task 原文作为上下文，减少幻觉
- Skill 创建已有 `confidence >= 0.85` 门槛过滤，低质量 run 不会生成 Skill
- summary 可在 SkillReviser 修订时一并更新

## Alternatives / 替代方案

### 方案 A：只升级向量化算法，不引入远程调用

**描述**：用本地 embedding 模型（如 `sentence-transformers`）替代词袋模型，不依赖远程 API。

**Pros**：
- 无网络延迟和外部依赖
- 无 API 调用成本
- 数据不出本地，满足数据安全要求

**Cons**：
- 需引入 PyTorch 或 ONNX runtime，部署体积增大
- 本地模型效果不如大参数量远程模型
- GPU 资源需求（CPU 推理延迟高）

**评估**：适合对延迟和数据安全要求极高的场景。但如果项目已接受远程 LLM 调用（当前已用 deepseek/deepseek-v4-pro），则 embedding 远程调用的风险增量可接受。

### 方案 B：只做 summary 字段，不改向量化方案

**描述**：新增 `summary` 字段，但仍用词袋模型做相似度计算，只是比对文本从全字段拼接改为 summary。

**Pros**：
- 改动最小，无新依赖
- 语义密度提升有一定效果（减少噪音）

**Cons**：
- 词袋模型的根本缺陷（同义词无法匹配）未解决
- 召回率提升有限

**评估**：可作为过渡方案。如果先做需求三验证效果，再决定是否做需求一和需求二。

### 方案 C：复用 Chroma（knowledge 子系统）

**描述**：项目已有 Chroma 向量库（用于 knowledge 子系统），直接复用作为 Skill 向量存储。

**Pros**：
- 不引入新组件，零部署成本
- 已有运维经验

**Cons**：
- knowledge 子系统和 Skill 系统共用 Chroma，职责边界模糊
- 需要确认 Chroma 是否支持多 collection 隔离

**评估**：需进一步确认 Chroma 的多 collection 支持。如果可行，这是最省力的方案。

## Unresolved Questions / 待解决问题

### 1. OpenRouter embedding 模型选型

- OpenRouter 提供哪些 embedding 模型？（需调研 API 文档）
- 候选模型：`text-embedding-3-small` / `text-embedding-3-large`（OpenAI via OpenRouter）/ 其他
- 向量维度取决于模型选择（如 1536 维 / 3072 维）
- 选用标准：效果 vs 成本 vs 延迟 的权衡

### 2. 向量库选型

| 候选 | 优势 | 劣势 |
|------|------|------|
| Chroma（已有） | 零部署成本，已有运维经验 | 职责边界模糊，需确认多 collection |
| Qdrant | 高性能 ANN，支持过滤 | 新增组件 |
| Milvus | 大规模场景优势 | 运维复杂度高，当前 Skill 量级不需要 |
| pgvector | 复用 MySQL/PostgreSQL，无新组件 | MySQL 不支持 pgvector，需换 PostgreSQL |

### 3. EmbeddingClient 实现方式

- 在 `LLMClient` 中新增 `embed()` 方法 vs 新建独立 `EmbeddingClient` 类
- 是否需要纳入 `ProactiveBudgetManager` 的成本治理
- 超时和重试策略

### 4. summary 生成策略

- LLM 生成 vs 规则提取 vs 混合策略
- 如果用 LLM 生成，用哪个模型？（复用 deepseek/deepseek-v4-pro 还是更轻量的模型？）
- summary 质量如何度量？是否需要人工抽检？

### 5. 向前兼容

- 已有的 Skill（没有 `summary` 字段）如何迁移？
- 是否需要批量补生成 summary？
- `normalize_skill()` 对缺失 `summary` 的旧 Skill 做什么兜底？

### 6. Phase 归属

- 本升级是否归属为 Phase 11？
- 还是作为 Phase 5（技能自创闭环）的增强迭代？
- PRD 里程碑表如何回写？

## 相关文档

- `docs/decisions/RFC-001-hermes-upgrade.md` — Hermes 五柱升级提案（Skill 系统的原始 RFC）
- `docs/phases/phase-5-skill-creation.md` — Phase 5 技能自创闭环详细 checkpoint
- `docs/ARCHITECTURE.md` — 第 4 章 Skill 自创闭环生命周期
- `docs/PRD.md` — 产品需求文档
- `src/riskagent_backend/skills/skill_store.py` — Skill 存储与检索实现
- `src/riskagent_backend/skills/skill_injector.py` — Skill 注入器
- `src/riskagent_backend/skills/skill_proposer.py` — Skill 创建器
- `src/riskagent_backend/memory/semantic_indexer.py` — 当前语义索引器（词袋模型）
