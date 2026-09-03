# CI/CD Pipeline

## 概述

本项目使用单文件 GitHub Actions workflow（`.github/workflows/ci.yml`），包含 2 个 Job 组成的流水线：

```
test (单元测试) → build-and-deploy (Docker 构建 + kind 部署 + 冒烟测试)
```

## 触发条件

| 事件 | 执行的 Job | 说明 |
|------|-----------|------|
| Pull Request → main | `test` | 仅运行单元测试，快速反馈 |
| Push → main | `test` → `build-and-deploy` | 全链路执行：测试、构建、部署 |

## Job 说明

### 1. test — 单元测试

- **运行环境**：`ubuntu-latest` + Python 3.13
- **依赖服务**：无外部依赖（单元测试 conftest 已 mock LLM 调用）
- **命令**：`PYTHONPATH=src python -m pytest tests/unit/ -v --tb=short`

### 2. build-and-deploy — Docker 构建 + kind 集群部署

- **触发条件**：仅在 main 分支 push 时执行（PR 时跳过）
- **前提**：依赖 test job 完成（job 级 `needs: test`）；但 test job 的 pytest 步骤带 `continue-on-error: true`（容忍预存在的测试失败），因此单元测试失败不会阻断 build-and-deploy 执行
- **镜像 Tag**：`sha-<12位 commit SHA>`，保证可追溯
- **可选推送**：当 `vars.DOCKER_REGISTRY` 不为空时，推送到远端 registry（如 GHCR）；为空时仅本地构建，供后续 kind load 使用
- **权限**：`packages: write`（用于 GHCR 推送）
- **部署条件**：`vars.DEPLOY_TARGET != 'cloud'`
- **流程**：
  1. 构建 Docker 镜像（`sha-<12位 commit SHA>` tag）
  2. Push to registry (if configured)：当 `env.DOCKER_REGISTRY != ''` 时，docker login + tag + push 到远端 registry（如 GHCR）；为空时跳过此步
  3. 使用 `helm/kind-action` 创建临时 kind 集群
  4. `kind load docker-image` 将构建好的镜像加载到 kind 节点
  5. Helm 部署：使用 `deploy/k8s/values-ci.yaml` + `--set image.tag` + `--set image.pullPolicy=Never`
  6. `kubectl wait --for=condition=ready --timeout=600s` 等待 mcp-server Pod 就绪（该步骤带 `continue-on-error`，等待超时不阻断后续流程）
  7. 冒烟测试：port-forward + curl 健康检查（该步骤同样带 `continue-on-error` 容错语义：CI runner 资源有限，部署侧验证失败仅作告警不阻断 job 结果）
  8. 无论成功失败，输出 Pod 状态（`if: always()`）

## 扩展点

通过 GitHub Repository Variables 配置（Settings → Secrets and variables → Actions → Variables）：

| Variable | 默认值 | 说明 |
|----------|--------|------|
| `DOCKER_REGISTRY` | `''`（空） | 空=本地 kind load 模式；设为 `ghcr.io/zheng-chuan/` 切换 GHCR 推送 |
| `DEPLOY_TARGET` | `kind` | `kind`=CI 临时集群；`cloud`=云端 K8s（需额外配置） |
| `IMAGE_NAME` | `riskagent/backend` | Docker 镜像名称 |

## 本地复现

### 运行单元测试

```bash
PYTHONPATH=src python -m pytest tests/unit/ -v --tb=short
```

### 构建 Docker 镜像

```bash
make docker-build IMAGE_TAG=sha-xxxxxx
```

### 部署到 kind（CI 模式）

```bash
# 前提：已安装 kind 并创建集群
kind create cluster --name ci-test

# 构建镜像
make docker-build IMAGE_TAG=sha-xxxxxx

# 加载到 kind
kind load docker-image riskagent/backend:sha-xxxxxx --name ci-test

# Helm 部署
helm upgrade --install riskagent deploy/k8s/ \
  -f deploy/k8s/values-ci.yaml \
  --set image.tag=sha-xxxxxx \
  --set image.pullPolicy=Never \
  --create-namespace -n riskagent
```

## CI values 说明

`deploy/k8s/values-ci.yaml` 针对 GitHub Actions runner（7GB RAM）进行了降配：

| 组件 | CPU Request/Limit | Memory Request/Limit | 持久化 |
|------|-------------------|----------------------|--------|
| mcp | 250m / 1 | 384Mi / 1Gi | — |
| mysql | 250m / 1 | 512Mi / 2Gi | 2Gi |
| redis | 50m / 250m | 128Mi / 256Mi | 1Gi |
| chroma | 100m / 500m | 256Mi / 512Mi | 1Gi |

Prometheus 和 Grafana 在 CI 中禁用，减少资源消耗。
