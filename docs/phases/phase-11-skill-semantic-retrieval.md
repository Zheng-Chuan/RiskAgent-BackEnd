# Phase 11: Skill 语义检索升级

| 字段 | 值 |
|------|-----|
| Status | Implemented |
| RFC | [RFC-005](../decisions/RFC-005-skill-semantic-retrieval-upgrade.md) |
| Start Date | 2026-08-07 |
| Complete Date | 2026-08-08 |
| Phase | 11 |

> **2026-08-14 更新**：LLM 网关切换后 embedding 链路从 OpenRouter `text-embedding-3-small`（1536 维）切换到硅基流动 SiliconFlow `BAAI/bge-m3`（1024 维），新增 `LLM_EMBEDDING_BASE_URL` / `LLM_EMBEDDING_API_KEY` 解耦配置；Chroma 集合维度不匹配时自动自愈（`restore_from_persistence()` 启动时重建向量索引，1536→1024 无需手动迁移）。下文部分描述为 2026-08-08 实施时点的历史口径，已逐处标注。

## 目标

将 Skill 语义检索链路从进程内词袋模型升级为完整的语义检索闭环，包含向量库存储、远程 Embedding、Summary 摘要字段、Hybrid 检索、Query Rewriting 和 skill_view 按需加载工具，共 6 项子需求。

### 核心问题

旧方案存在三个缺陷：

1. **无语义理解能力**：词袋模型只做字面 token 匹配，同义词/近义词无法关联，Skill 召回率低
2. **进程内存储不可恢复**：`SemanticIndexer._index` 是进程内 dict，进程重启后全部丢失
3. **全字段拼接稀释语义密度**：6 类字段拼接为比对文本，steps 中的 expected_outcome 等字段引入大量噪音

## 6 项需求实施情况

### 需求三：Skill 新增 summary 摘要字段

- **Commit**: `249fe2e`
- **状态**: ✅ 已实施
- **实现**:
  - `skill.v1` schema 新增 `summary: str` 字段（30-80 字）
  - `SkillProposer` 创建 Skill 时调用 LLM（`deepseek/deepseek-chat`，2026-08-08 实施时点历史口径，当时走 OpenRouter；现默认 `deepseek-v4-flash` 走 DeepSeek 官方 API）生成一句话摘要
  - 注入 task 原文作为上下文，减少幻觉
  - MySQL `skill_store` 表新增 `summary` 列（db/migrations/006_add_skill_summary_column.sql）
  - `normalize_skill()` 校验 summary 非空
  - Embedding 基于 `summary` 字段生成（而非全字段拼接）

### 需求二：远程 Embedding（LLMClient.embed()）

- **Commit**: `c7b80d0`
- **状态**: ✅ 已实施
- **实现**:
  - `LLMClient` 新增 `embed()` 方法
  - 调用独立 embedding 端点（`LLM_EMBEDDING_BASE_URL`）生成向量：2026-08-08 实施时为 OpenRouter `text-embedding-3-small`（1536 维）；2026-08-14 起切换为硅基流动 SiliconFlow `BAAI/bge-m3`（1024 维），维度变化由 Chroma 维度自愈机制处理（启动时自动重建索引）
  - 复用现有超时、重试、成本追踪治理体系
  - 纳入 `ProactiveBudgetManager` 成本治理
  - 超时/failure 时 fallback 到关键词匹配

### 需求六：skill_view 工具

- **Commit**: `5e2833d`
- **状态**: ✅ 已实施
- **实现**:
  - 新建 `tools/skill_view_tool.py`
  - 输入：`skill_id` 或 `skill_name`
  - 输出：完整 Skill 内容（steps, applicable_conditions, failure_boundary, confidence 等）
  - 工具权限：`owner=orchestrator`（遵循 ADR-004 零信任工具治理）
  - 纯读工具，无副作用，不需审批链
  - Orchestrator prompt 提示 LLM 可调用 `skill_view` 获取详情
  - 注入策略变更：plan 前只注入 summary 列表（name + summary），LLM 按需调用 `skill_view`

### 需求一：Chroma 向量库迁移

- **Commit**: 最新 commit
- **状态**: ✅ 已实施
- **实现**:
  - 复用项目已有 Chroma（knowledge 子系统）
  - 新建 `riskagent-skills` collection，独立隔离 Skill 数据
  - `SkillStore._index_skill()` 改为写入 Chroma 向量库
  - `SkillStore.search()` 改为调用 Chroma ANN 检索
  - `SkillStore.restore_from_persistence()` 从 MySQL 加载 + 重建 Chroma 索引
  - `SkillStore._keyword_fallback_search()` 保留作为兜底/ BM25 通道
  - 上层调用方（`SkillInjector`, `SkillProposer`）接口无感知

### 需求五：Query Rewriting

- **Commit**: `57daf39`
- **状态**: ✅ 已实施
- **实现**:
  - `SkillInjector._rewrite_query()` 新增方法
  - 调用 LLM（`deepseek/deepseek-chat`，2026-08-08 实施时点历史口径；现默认 `deepseek-v4-flash` 走 DeepSeek 官方 API）将短 query 扩展为检索导向 query
  - LRU 缓存（256 条，可通过 `SKILL_QUERY_REWRITE_CACHE_SIZE` 配置）
  - 超时（3s, 可通过 `SKILL_QUERY_REWRITE_TIMEOUT` 配置）
  - Fallback：LLM 不可用/超时/返回空 → 使用原始 query，不阻断检索链路
  - 可通过 `SKILL_QUERY_REWRITE_ENABLED` 配置开关（默认 true）
  - 改写后 query 同时用于向量检索和 BM25 检索

### 需求四：Hybrid 检索

- **Commit**: `4cbd799`
- **状态**: ✅ 已实施
- **实现**:
  - 向量检索（Chroma ANN）返回 Top-K + cosine 相似度分数
  - BM25 检索（复用 `_keyword_fallback_search()`）返回 Top-K + 关键词匹配分数
  - 加权合并：`final_score = α * vector_score + (1-α) * bm25_score`，默认 α=0.7
  - 可通过 `SKILL_HYBRID_VECTOR_WEIGHT` 配置
  - 分数归一化到 [0, 1] 后加权
  - 合并后去重、排序、截断到 limit

### 审查修复

- **Commit**: `16c2886`
- **状态**: ✅ 已实施
- **内容**: 代码审查中发现的问题修复

### K8s 部署验证

- **Commit**: `ec54dbd`
- **状态**: ✅ 已验证（Helm revision 18）
- **内容**:
  - ConfigMap 包含 Skill 检索相关环境变量：4 个 SKILL_ 变量（SKILL_QUERY_REWRITE_ENABLED / SKILL_QUERY_REWRITE_TIMEOUT / SKILL_QUERY_REWRITE_CACHE_SIZE / SKILL_HYBRID_VECTOR_WEIGHT）+ CHROMA_SKILLS_COLLECTION（现状口径；实施时点曾描述 6 个变量，实际不存在 SKILL_EMBEDDING_MODEL 与 CHROMA_URL，embedding 模型由 LLM_EMBEDDING_MODEL 控制）
  - MySQL skill_store 表包含 summary 列（migration 006）
  - Docker 镜像 `k8s-local-v4` 部署成功
  - 所有 Pod 正常运行

## 验证结果

### Skill 专项测试

| 测试类别 | 通过数 | 状态 |
|----------|--------|------|
| summary 字段生成 | 全部通过 | ✅ |
| LLMClient.embed() | 全部通过 | ✅ |
| skill_view 工具 | 全部通过 | ✅ |
| Chroma 向量库 | 全部通过 | ✅ |
| Query Rewriting | 全部通过 | ✅ |
| Hybrid 检索 | 全部通过 | ✅ |
| 集成测试 | 全部通过 | ✅ |
| **总计** | **158/158** | ✅ PASS |

### 6 个集成点验证

| 集成点 | 状态 | 说明 |
|--------|------|------|
| summary 字段注入 Skill 创建链路 | PASS | SkillProposer → SkillStore → MySQL |
| embed() 方法接入 LLMClient | PASS | LLMClient.embed() → SiliconFlow（硅基流动，2026-08-14 切换；实施时点为 OpenRouter） |
| Chroma 向量库存储与检索 | PASS | SkillStore.search() → Chroma ANN |
| Query Rewriting 接入 SkillInjector | PASS | _build_query() → _rewrite_query() → search() |
| Hybrid 检索加权合并 | PASS | 向量 + BM25 → final_score |
| skill_view 工具注册到 Orchestrator | PASS | tool_executor → skill_view_tool.py |

### K8s 部署状态

| 项目 | 状态 | 详情 |
|------|------|------|
| ConfigMap 环境变量 | ✅ | SKILL_ 相关 4 个变量 + CHROMA_SKILLS_COLLECTION 全部注入（现状口径） |
| MySQL migration | ✅ | skill_store 表 summary 列已添加 |
| Docker 镜像 | ✅ | k8s-local-v4 部署成功 |
| Pod 状态 | ✅ | 所有 Pod 正常运行 |
| Helm revision | 18 | 部署版本号 |

## 已知限制

### embedding 供应商不可用时的降级行为（历史背景：OpenRouter 402）

- **历史背景**：2026-08-08 验证时点 OpenRouter API 返回 402 Payment Required，触发该降级链路验证；2026-08-14 起 embedding 供应商已切换为硅基流动 SiliconFlow（BAAI/bge-m3）
- **影响**：embedding 供应商不可用时，远程 Embedding 调用失败
- **Fallback 行为**：自动降级为纯 BM25 关键词检索，不阻断检索链路
- **验证**：Fallback 机制正常工作，Skill 检索功能可用（召回质量下降但不中断）

### 预存测试失败（9 个）

- **原因**：MySQL/Redis 连接依赖，在无基础设施环境下预期失败
- **影响**：不影响 Skill 专项测试的 158/158 通过率
- **说明**：这些是基础设施连接测试，与 Phase 11 实现无关

## Exit Criteria

| 验收标准 | 状态 | 说明 |
|----------|------|------|
| 需求三：summary 字段实施 | ✅ | commit 249fe2e |
| 需求二：远程 Embedding 实施 | ✅ | commit c7b80d0 |
| 需求六：skill_view 工具实施 | ✅ | commit 5e2833d |
| 需求一：Chroma 向量库迁移 | ✅ | 最新 commit |
| 需求五：Query Rewriting 实施 | ✅ | commit 57daf39 |
| 需求四：Hybrid 检索实施 | ✅ | commit 4cbd799 |
| Skill 专项测试 158/158 通过 | ✅ | 全部通过 |
| 6 个集成点验证 PASS | ✅ | 全部通过 |
| K8s 部署验证通过 | ✅ | Helm revision 18 |
| embedding 供应商不可用时 Fallback 降级正常 | ✅ | 已验证（验证时点为 OpenRouter 402；现行供应商为硅基流动） |
| 文档与代码状态一致 | ✅ | RFC-005 Implemented |

## 相关文档

- [RFC-005: Skill 语义检索升级](../decisions/RFC-005-skill-semantic-retrieval-upgrade.md)
- [ARCHITECTURE.md 第 6 章: Skill 自创闭环生命周期](../ARCHITECTURE.md)
- [PRD.md](../PRD.md)
- [STRATEGY.md](../STRATEGY.md)
