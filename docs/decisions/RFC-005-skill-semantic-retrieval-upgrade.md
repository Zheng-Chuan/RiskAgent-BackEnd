# RFC-005: Skill 语义检索升级（向量库 + 远程 Embedding + Summary + Hybrid 检索 + Query Rewriting + skill_view）

| 字段 | 值 |
|------|-----|
| Status | Implemented |
| Date | 2026-07-22 |
| Author | RiskAgent-BackEnd 项目组 |

## Update Log

| 日期 | 变更 |
|------|------|
| 2026-07-22 | 初始创建，提出 Skill 语义检索升级三项需求 |
| 2026-08-07 | Status 从 Proposed 更新为 Accepted；6 个待解决问题全部填写决策结果；新增需求四（Hybrid 检索）、需求五（Query Rewriting）、需求六（skill_view 工具）三项优化方案设计；更新实施顺序与 Drawbacks |
| 2026-08-08 | Status 从 Accepted 更新为 Implemented；6 项需求全部实施完成：需求三 summary 字段（commit 249fe2e）、需求二远程 Embedding（commit c7b80d0）、需求六 skill_view 工具（commit 5e2833d）、需求一 Chroma 向量库迁移、需求五 Query Rewriting（commit 57daf39）、需求四 Hybrid 检索（commit 4cbd799）、审查修复（commit 16c2886）；K8s 部署验证通过（Helm revision 18，Docker 镜像 k8s-local-v4）；158/158 Skill 专项测试通过；6 个集成点全部验证 PASS；已知限制：OpenRouter 账户余额不足（402）时 Fallback 降级机制正常工作 |
| 2026-08-14 | LLM 网关切换（commit 06ea0ab）：embedding 链路从 OpenRouter `text-embedding-3-small`（1536 维）切换到硅基流动 SiliconFlow `BAAI/bge-m3`（1024 维）；新增 `LLM_EMBEDDING_BASE_URL` / `LLM_EMBEDDING_API_KEY` 解耦配置（为空时回退主 LLM 配置）；Chroma 维度不匹配自动自愈（`restore_from_persistence()` 时删除并重建 collection，1536→1024 无需手动迁移）；Resolved Question 1 的选型决策被推翻，见其 superseded 标注 |

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

对 Skill 语义检索链路做六项升级，构成一个完整的改造闭环（需求一至三为原提案，需求四至六为 2026-08-07 新增优化）：

> **注**：下表及下文关系图中“OpenRouter embedding”为提案时点口径；2026-08-14 起实现已改为独立 embedding 端点（现行供应商：硅基流动 SiliconFlow，BAAI/bge-m3），见 Update Log 2026-08-14 条目与需求二章节统一注记。

| 编号 | 需求 | 核心变更 |
|------|------|--------|
| 需求一 | Skill 转为向量库存储 | `SemanticIndexer` 进程内 dict → 独立向量库 |
| 需求二 | 远程调用 OpenRouter 模型计算语义相似度 | 词袋向量 → 远程 LLM embedding |
| 需求三 | Skill 新增 summary 摘要字段 | 全字段拼接 → 一句话摘要作为语义比对锚点 |
| 需求四 | Hybrid 检索（向量 + BM25 加权合并） | 纯向量检索 → 向量 + BM25 加权合并，复用 `_keyword_fallback_search()` |
| 需求五 | Query Rewriting（检索导向查询改写） | 直接用 task 描述做 query → LLM 改写为检索导向 query |
| 需求六 | Agent 自主发现（skill_view 工具） | plan 前一次性注入完整 Skill → summary 列表 + 按需调用 `skill_view` |

六项需求的关系：

```
[需求三: summary 字段]  →  定义语义比对的锚点文本（高语义密度）
        |
        v
[需求二: OpenRouter embedding]  →  为 summary 生成真正的语义向量
        |
        v
[需求一: 向量库存储]  →  持久化向量并支持 ANN 检索
```

实施顺序：需求三先行（schema 变更），再做需求二（远程 embedding），再做需求一（向量库迁移），随后做需求四（Hybrid 检索）、需求五（Query Rewriting）、需求六（skill_view 工具）。完整顺序见下文“实施顺序”章节。

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

> **2026-08-14 实现口径更新**：本章节描述的 OpenRouter embedding 调用为提案时点口径。实际实现已改为独立 embedding 端点（`LLM_EMBEDDING_BASE_URL` / `LLM_EMBEDDING_API_KEY` 解耦配置），现行供应商为硅基流动 SiliconFlow（`BAAI/bge-m3`，1024 维），详见 Update Log 2026-08-14 条目；下文各小节中“OpenRouter”字样均按此口径理解，不再逐句改写。

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

### 需求四：Hybrid 检索（向量 + BM25 加权合并）

**目标**：在向量 ANN 检索的基础上，保留并复用现有 `_keyword_fallback_search()` 作为 BM25 通道，与向量检索加权合并，提升召回质量与稳定性。参考来源：AutoSkill + Cursor + LlamaIndex 的 Hybrid 检索实践。

**背景**：当前 RFC-005 原方案为纯向量检索。纯向量检索在短 query 或领域术语场景下存在召回波动，BM25 关键词匹配对精确术语命中更稳定，二者加权合并可互补长短。

**具体要求**：

- 向量检索（Chroma ANN）返回 Top-K 结果，每个结果有 cosine 相似度分数
- BM25 检索（复用现有 `SkillStore._keyword_fallback_search()`）返回 Top-K 结果，每个结果有关键词匹配分数
- 加权合并公式：`final_score = α * vector_score + (1-α) * bm25_score`，默认 α=0.7
- 合并后按 `final_score` 去重、排序、截断到 `limit`
- α 可通过环境变量 `SKILL_HYBRID_VECTOR_WEIGHT` 配置，取值范围 [0.0, 1.0]
- 分数需归一化到 [0, 1] 区间再做加权（vector_score 和 bm25_score 量纲不同）

**受影响组件**：

| 组件 | 文件 | 变更 |
|------|------|------|
| `SkillStore.search()` | `skills/skill_store.py` | 在现有向量检索后，调用 `_keyword_fallback_search()` 作为 BM25 通道，加权合并后排序返回 |
| `SkillStore._keyword_fallback_search()` | `skills/skill_store.py` | 从“兜底补全”角色升级为“BM25 检索通道”，输出归一化分数 |
| 环境变量配置 | `config.py` / `config_pydantic.py` | 新增 `SKILL_HYBRID_VECTOR_WEIGHT` 配置项，默认 0.7 |

**调用链路**：

```
[query 文本]
    |
    +---> [向量检索: Chroma ANN]  →  Top-K (vector_score)
    |
    +---> [BM25 检索: _keyword_fallback_search()]  →  Top-K (bm25_score)
    |
    v
[分数归一化 + 加权合并: final = α*vector + (1-α)*bm25]
    |
    v
[去重 → 排序 → 截断到 limit]
    |
    v
[过滤: status=active, confidence>=min_confidence]
```

**与现有 `_keyword_fallback_search()` 的关系**：

当前 `_keyword_fallback_search()` 的角色是“向量检索结果不足时的兜底补全”。需求四将其升级为“与向量检索并行的 BM25 检索通道”，两者结果加权合并而非补全。原“结果不足时兜底”的语义由加权合并自然覆盖（BM25 通道会补充向量检索未命中的结果）。

### 需求五：Query Rewriting（检索导向查询改写）

**目标**：在 `SkillInjector._build_query()` 之后、`SkillStore.search()` 之前，增加 `_rewrite_query()` 步骤，将短 query 扩展为检索导向 query，弥补 embedding 对短查询的弱点。参考来源：AutoSkill 的 query rewriting 实践。

**背景**：当前直接用 task 描述做 query。短 query（如“监控敞口”）的 embedding 向量信息密度低，向量检索召回不稳定。将短 query 扩展为包含同义词、近义词和上下文描述的检索导向 query，可显著提升召回质量。

**具体要求**：

- 在 `SkillInjector._build_query()` 之后、`SkillStore.search()` 之前，增加 `_rewrite_query()` 步骤
- 用 LLM（复用 `deepseek/deepseek-chat`）将原始 query 改写为检索导向的 query：
  - 保留原始意图
  - 扩展同义词和近义词
  - 补充上下文（如“监控敞口” → “监控交易台敞口风险 检测持仓超限 风险指标异常”）
- 改写后的 query 同时用于向量检索和 BM25 检索
- query embedding 缓存（LRU），避免相同 query 重复调用 embedding API
- 如果 LLM 不可用或超时，fallback 到原始 query（不阻断检索链路）

**受影响组件**：

| 组件 | 文件 | 变更 |
|------|------|------|
| `SkillInjector._rewrite_query()` | `skills/skill_injector.py` | 新增方法，调用 LLMClient 改写 query |
| `SkillInjector.retrieve_applicable_skills()` | `skills/skill_injector.py` | 在 `_build_query()` 后调用 `_rewrite_query()`，再调 `search()` |
| query embedding LRU 缓存 | `skills/skill_injector.py` | 新增 `functools.lru_cache` 或自定义 LRU，缓存 query → embedding 映射 |
| 环境变量配置 | `config.py` / `config_pydantic.py` | 新增 `SKILL_QUERY_REWRITE_ENABLED`（默认 true）、`SKILL_QUERY_REWRITE_TIMEOUT`（默认 3s） |

**LLM prompt 设计参考**（参考 AutoSkill 的 extraction prompt）：

```
你是一个检索查询改写器。将用户的短查询扩展为检索导向的查询，要求：
1. 保留原始意图
2. 扩展同义词和近义词
3. 补充领域上下文
4. 输出为一行短语，不超过 50 字

原始查询: {original_query}

改写后的查询:
```

**LRU 缓存设计**：

- 缓存键：`hash(original_query)`
- 缓存值：改写后的 query 字符串
- 缓存容量：256 条（可通过 `SKILL_QUERY_REWRITE_CACHE_SIZE` 配置）
- 缓存命中时不调用 LLM，直接返回缓存的改写结果
- query embedding 缓存与 query rewrite 缓存分离：rewrite 缓存的是改写后的文本，embedding 缓存的是改写后文本的向量

**Fallback 机制**：

- LLM 调用超时（默认 3s）→ 使用原始 query
- LLM 返回空或非法内容 → 使用原始 query
- `SKILL_QUERY_REWRITE_ENABLED=false` → 跳过改写，直接用原始 query
- Fallback 时记录 warning 日志，不阻断检索链路

### 需求六：Agent 自主发现（skill_view 工具）

**目标**：将 `skill_view` 作为工具暴露给 Orchestrator，LLM 在 ReAct 循环中需要详细参考某个 Skill 时主动调用，而非在 plan 生成前一次性注入 max_skills 个完整 Skill 内容。参考来源：Cursor Agent Skills 标准。

**背景**：当前 `SkillInjector` 在 plan 生成前一次性注入 `max_skills` 个完整 Skill（含 steps, applicable_conditions, failure_boundary 等），每个 Skill 可能占 500-1000 tokens，注入 3 个完整 Skill 约 3K tokens。当 Skill 数量增长后，一次性注入完整内容造成 token 浪费（LLM 可能只需要参考其中 1 个）。

**具体要求**：

- 在 plan 生成前仍做一次 Skill 检索，但只注入 summary 列表（`name + summary`，约 3K tokens 总量上限）
- 新增 `skill_view` 工具（在 `tools/` 目录下注册），Orchestrator 可在 ReAct 循环中调用：
  - 输入：`skill_id` 或 `skill_name`
  - 输出：完整 Skill 内容（steps, applicable_conditions, failure_boundary, confidence 等）
- 工具权限：`owner=orchestrator`（遵循 ADR-004 零信任工具治理）
- LLM 在需要详细参考某个 Skill 时主动调用 `skill_view`，而非一次性注入全部内容
- 减少 token 消耗：从注入 N 个完整 Skill → 只注入 summary 列表 + 按需加载

**受影响组件**：

| 组件 | 文件 | 变更 |
|------|------|------|
| `skill_view` 工具 | `tools/skill_view_tool.py`（新建） | 工具定义：输入 skill_id/skill_name，输出完整 Skill 内容 |
| `SkillInjector.retrieve_applicable_skills()` | `skills/skill_injector.py` | 注入策略变更：从注入完整 Skill 改为注入 summary 列表 |
| `SkillInjector._build_injection_item()` | `skills/skill_injector.py` | 新增 `summary_only` 模式，只输出 name + summary |
| 工具注册 | `orchestration/tool_executor.py` / `governance/` | 注册 `skill_view` 工具，owner=orchestrator |
| Orchestrator prompt | `prompts/agent_prompts/` | 提示 LLM 可调用 `skill_view` 获取 Skill 详情 |

**skill_view 工具定义**：

```python
{
    "name": "skill_view",
    "description": "查看指定 Skill 的完整内容（steps, applicable_conditions, failure_boundary）。在 plan 生成前你已收到 Skill summary 列表，需要详细参考某个 Skill 时调用此工具。",
    "owner": "orchestrator",
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "Skill ID"},
            "skill_name": {"type": "string", "description": "Skill 名称（与 skill_id 二选一）"}
        }
    },
    "output": "完整 Skill 内容（JSON）"
}
```

**注入策略变更**：

| | 当前策略 | 新策略 |
|---|---|---|
| plan 前注入内容 | N 个完整 Skill（steps + conditions + boundary） | N 个 summary 条目（name + summary） |
| token 消耗 | 3 个完整 Skill ≈ 3K-9K tokens | summary 列表 ≈ 0.5-1K tokens |
| Skill 详情获取 | 一次性全量注入 | LLM 按需调用 `skill_view` |
| 适用场景 | Skill 数量少 | Skill 数量增长后 |

**与 ReAct 循环的集成**：

```
[plan 生成前]
    |
    v
[SkillInjector.retrieve_applicable_skills()]
    →  注入 summary 列表（name + summary）到 orchestrator context
    |
    v
[Orchestrator 生成 plan]
    →  plan 中引用了某个 skill_id 但需要详情
    |
    v
[ReAct 循环中调用 skill_view(skill_id)]
    →  返回完整 Skill 内容
    |
    v
[Orchestrator 基于完整 Skill 内容调整 plan/step]
```

### 实施顺序

基于需求间依赖关系，实施顺序如下：

| 顺序 | 需求 | 依赖 | 说明 |
|------|------|------|------|
| 1 | 需求三：summary 字段 | 无 | schema 变更先行，定义语义比对锚点 |
| 2 | 需求二：远程 embedding | 需求三 | 为 summary 生成语义向量 |
| 3 | 需求一：向量库存储 | 需求二 | 持久化向量并支持 ANN 检索 |
| 4 | 需求四：Hybrid 检索 | 需求一 | 在向量检索基础上叠加 BM25 通道 |
| 5 | 需求五：Query Rewriting | 需求二 | 改写后 query 送入 embedding 和检索 |
| 6 | 需求六：skill_view 工具 | 需求三 | 依赖 summary 字段做轻量注入，工具独立开发 |

```
[需求三: summary] → [需求二: embedding] → [需求一: 向量库]
                                                |
                                  +-------------+-------------+
                                  |             |             |
                          [需求四: hybrid] [需求五: rewrite] [需求六: skill_view]
```

## 与现有架构约束的兼容性

- **ADR-001（多 Agent 架构）**：本升级不改变多 Agent 协作架构，只增强 Skill 检索能力
- **ADR-003（统一记忆架构）**：`SemanticIndexer` 在记忆系统（长期经验记忆）中仍可保留进程内词袋模式，本 RFC 只针对 Skill 检索链路做升级，记忆系统不受影响
- **ADR-004（零信任工具治理）**：OpenRouter embedding 调用属于外部 API 调用，需纳入成本追踪和超时治理，但不涉及副作用工具审批
- **ADR-005（run_trace.v2）**：embedding 调用应记录到 trace（作为 LLM interaction 的一种），支持回放和成本审计
- **不形成旁路**：Skill 检索仍在 `proactive_workflow._build_orchestrator_context()` 中调用，不绕过统一执行内核
- **需求四（Hybrid 检索）**：复用现有 `SkillStore._keyword_fallback_search()` 作为 BM25 通道，不引入新组件；加权合并在 `SkillStore.search()` 内部完成，上层调用方无感知
- **需求五（Query Rewriting）**：LLM 调用通过 `LLMClient` 发起，复用现有超时/重试/成本追踪治理；fallback 到原始 query 时不阻断检索链路
- **需求六（skill_view 工具）**：`skill_view` 作为纯读工具注册到 `tool_executor`，`owner=orchestrator`，遵循 ADR-004 零信任工具治理；无副作用，不需审批链

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

### Hybrid 检索增加 BM25 通道延迟

需求四在向量检索之外叠加 BM25 检索通道，`SkillStore.search()` 单次调用的延迟增加约 5-10ms（BM25 为进程内遍历计算，无网络往返）。

**缓解**：5-10ms 延迟在可接受范围内（向量检索本身的网络往返延迟为 100-500ms）。BM25 与向量检索可并行执行进一步降低增量延迟。`SKILL_HYBRID_VECTOR_WEIGHT` 设为 1.0 可完全禁用 BM25 通道。

### Query Rewriting 增加一次 LLM 调用

需求五在检索前增加一次 LLM 调用做 query 改写，增加约 100-200ms 延迟和少量 token 成本。

**缓解**：
- LRU 缓存命中时不调用 LLM（高频 query 场景下缓存命中率预期较高）
- LLM 不可用或超时（3s）时 fallback 到原始 query，不阻断检索链路
- 可通过 `SKILL_QUERY_REWRITE_ENABLED=false` 完全禁用

### skill_view 工具增加 ReAct 步数

需求六将 Skill 详情获取从“一次性注入”改为“按需调用”，Orchestrator 在需要 Skill 详情时需多执行 1-2 个 ReAct 步骤调用 `skill_view`。

**缓解**：
- token 消耗总体下降（从注入 N 个完整 Skill → summary 列表 + 按需加载），即使多 1-2 步 ReAct，总 token 消耗仍低于一次性全量注入
- `skill_view` 是纯读工具（无副作用），不需审批链，执行延迟低
- 只有 LLM 判断需要 Skill 详情时才调用，非必选步骤

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

**评估**：适合对延迟和数据安全要求极高的场景。但如果项目已接受远程 LLM 调用（提案时点已用 deepseek/deepseek-v4-pro，历史口径；现为 DeepSeek 官方 deepseek-v4-flash），则 embedding 远程调用的风险增量可接受。

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

## Resolved Questions / 已决策问题

以下 6 个问题均于 2026-08-07 确认决策。

### 1. OpenRouter embedding 模型选型

**决策**：选用 `text-embedding-3-small`（1536 维），经 OpenRouter 调用。

- 效果与成本平衡最佳：1536 维足够覆盖 Skill 语义检索场景
- 价格远低于 `text-embedding-3-large`（3072 维），且 Skill 检索对维度上限要求不高
- 经 OpenRouter 统一网关调用，与现有 chat 模型调用路径一致

> **Superseded（2026-08-14 被推翻）**：因 LLM 网关切换（commit 06ea0ab），改用硅基流动 SiliconFlow `BAAI/bge-m3`（1024 维）：DeepSeek 官方无 embeddings 端点，硅基流动不提供 text-embedding-3-small；维度变化由 Chroma 维度自愈机制处理。见 Update Log 2026-08-14 条目。

### 2. 向量库选型

**决策**：复用 Chroma，新建 `riskagent-skills` collection。

- 复用项目已有 Chroma（knowledge 子系统已部署），零新增组件成本
- 通过独立 collection `riskagent-skills` 隔离 Skill 数据，职责边界清晰
- 已有 Chroma 运维经验，不增加运维复杂度

### 3. EmbeddingClient 实现方式

**决策**：在 `LLMClient` 中新增 `embed()` 方法（方案 A）。

- 复用现有超时、重试、成本追踪治理体系，不新建独立类
- embedding 调用纳入 `ProactiveBudgetManager` 成本治理（与 chat 调用同体系）
- 超时和重试策略与 chat 调用一致（复用 `LLMClient` 现有配置）

### 4. summary 生成策略

**决策**：纯 LLM 生成（不用混合策略），参考 AutoSkill 的 extraction prompt。

- 复用 `deepseek/deepseek-chat` 生成一句话概括
- SkillProposer 在创建 Skill 时调用 LLM 生成 summary，注入 task 原文作为上下文减少幻觉
- summary 质量由 Skill 创建已有的 `confidence >= 0.85` 门槛间接保障
- SkillReviser 修订时同步刷新 summary

### 5. 向前兼容

**决策**：清空旧 Skill，不考虑向前兼容。

- 当前 Skill 数量少且均为原型阶段产物，无生产数据
- 旧 Skill 无 summary 字段，迁移补生成成本高于重建
- `normalize_skill()` 对缺失 `summary` 的旧 Skill 不做兜底，直接要求新 Skill 必须有 summary

### 6. Phase 归属

**决策**：归属 Phase 11。

- 本升级作为独立阶段（Phase 11）实施，不作为 Phase 5 增强迭代
- PRD 里程碑表 Phase 11 状态更新为“RFC-005 Accepted”
- 包含需求一至需求六共 6 项子需求，按“实施顺序”章节交付

## 相关文档

- `docs/decisions/RFC-001-hermes-upgrade.md` — Hermes 五柱升级提案（Skill 系统的原始 RFC）
- `docs/phases/phase-5-skill-creation.md` — Phase 5 技能自创闭环详细 checkpoint
- `docs/ARCHITECTURE.md` — 第 6 章 Skill 自创闭环生命周期
- `docs/PRD.md` — 产品需求文档
- `src/riskagent_backend/skills/skill_store.py` — Skill 存储与检索实现（需求一/四：向量库 + Hybrid 检索）
- `src/riskagent_backend/skills/skill_injector.py` — Skill 注入器（需求五/六：query rewriting + summary 注入）
- `src/riskagent_backend/skills/skill_proposer.py` — Skill 创建器（需求三：summary 生成）
- `src/riskagent_backend/memory/semantic_indexer.py` — 当前语义索引器（词袋模型，需求一后降级）
- `src/riskagent_backend/llm/llm_client.py` — LLMClient（需求二：embed() 方法；需求五：query rewriting LLM 调用）
- `src/riskagent_backend/orchestration/tool_executor.py` — 工具治理（需求六：skill_view 工具注册）
- `src/riskagent_backend/skills/skill_governor.py` — Skill 治理器（注入预算控制）
