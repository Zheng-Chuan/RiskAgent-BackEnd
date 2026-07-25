# RFC-004: K8s 全量迁移

| 字段 | 值 |
|------|-----|
| Status | Accepted |
| Date | 2026-07-18 |
| Author | RiskAgent Team |

## 背景
当前所有中间件通过 docker-compose.yml 部署，包含 8 个服务。docker-compose 适合本地开发，但生产环境需要 K8s 的弹性伸缩、滚动更新和自愈能力。

## 决策
将 docker-compose.yml 中的 8 个服务迁移为 Helm Chart 部署到 K8s。

### 策略选择

| 决策点 | 选择 | 理由 |
|--------|------|------|
| Helm vs Kustomize | Helm | 8 服务 + 5 卷，Helm 模板化减少重复 YAML，原生回滚支持 |
| 代码变更 | 零变更 | 应用已具备环境变量配置、健康端点、SIGTERM handler |
| StatefulSet vs Deployment | 有状态用 STS，无状态用 Deployment | MySQL/Redis/Chroma 需稳定 PVC + 网络标识 |
| MCP Server 副本数 | 1（首期） | proactive 后台线程需 leader election 才能多副本 |
| docker-compose.yml | 完整保留 | 本地开发环境不变 |

### 被拒绝方案
- Kustomize: 8 服务 Helm 模板化更优
- HPA + Leader Election: 需代码变更，违反零代码变更原则
- Kompose 自动转换: 生成质量不可控

## 影响
- 新增 deploy/k8s/ 目录（Helm Chart）
- 新增 .dockerignore（安全加固）
- Makefile 添加 k8s-deploy/k8s-uninstall target
- 不修改任何 .py 代码文件
- docker-compose.yml 完整保留

## Update Log
- 2026-07-18: RFC 创建，Status=Accepted
