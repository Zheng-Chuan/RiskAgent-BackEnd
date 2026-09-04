# RiskAgent K8s 部署指南

## 前置条件
- kubectl 已安装并配置好集群
- Helm 3.x 已安装
- Docker 镜像已构建并推送到镜像仓库（见 `make docker-build`）
- 若使用火山 CR 等私有仓库，请先在目标 namespace 创建拉镜像 Secret，并在 `values.yaml` 的 `global.imagePullSecrets` 中引用
- 若需公网或域名访问 `mcp-server`，请在 values 中启用 `ingress.enabled=true`

## 部署步骤

### 1. 部署 Helm Chart（自动创建 namespace）

生产环境：
```bash
helm upgrade --install riskagent deploy/k8s/ \
  -f deploy/k8s/values-prod.yaml \
  --set image.repository=<your-image-repo> \
  --set image.tag=<immutable-tag> \
  -n riskagent --create-namespace
```

开发环境：
```bash
helm upgrade --install riskagent deploy/k8s/ \
  -f deploy/k8s/values-dev.yaml \
  -n riskagent --create-namespace
```

或使用 Makefile 快捷命令：
```bash
make k8s-deploy       # 生产：-f values-prod.yaml，支持 IMAGE_TAG（默认 latest）与 K8S_NAMESPACE（默认 riskagent）变量
make k8s-deploy-dev   # 开发：-f values-dev.yaml，namespace 固定 riskagent，镜像 tag 取自 values-dev（dev）
```

示例（指定镜像 tag 与 namespace）：

```bash
make k8s-deploy IMAGE_TAG=v1.2.3 K8S_NAMESPACE=<ns>
```

> `--create-namespace` 标志会在 namespace 不存在时由 Helm 自动创建，无需手动 `kubectl create namespace`。
>
> Secret 默认由 `templates/secrets.yaml` 从 values 自动生成；如需覆盖默认密钥，可在部署后用 `kubectl create secret` 手动更新。
>
> **警示（namespace 变量作用域）**：仅 `make k8s-deploy` 支持 `K8S_NAMESPACE` 变量；`k8s-deploy-dev` / `k8s-status` / `k8s-uninstall` 在 Makefile 中硬编码 `-n riskagent`。用非默认 namespace 部署后，状态查看与卸载须手动执行 `helm status riskagent -n <ns>` / `helm uninstall riskagent -n <ns>`。
>
> **警示（勿当 staging 用）**：`k8s-deploy` 走 `values-prod.yaml`（生产级资源），仓库无 `values-staging.yaml`；不要以「改 namespace」的方式把生产部署当 staging 环境用。

火山 CR 示例:
```bash
kubectl create secret docker-registry volc-cr-secret \
  --docker-server=<your-cr-registry> \
  --docker-username=<your-cr-username> \
  --docker-password=<your-cr-password> \
  -n riskagent

helm upgrade --install riskagent deploy/k8s/ \
  -f deploy/k8s/values-prod.yaml \
  --set image.repository=<your-image-repo> \
  --set image.tag=<immutable-tag> \
  --set global.imagePullSecrets[0].name=volc-cr-secret \
  --set ingress.enabled=true \
  --set ingress.host=<your-host> \
  -n riskagent --create-namespace
```

### 2. 验证
```bash
make k8s-status       # helm status riskagent + kubectl get pods,svc -n riskagent
# 或手动：
kubectl get pods -n riskagent
kubectl get svc -n riskagent
```

### 3. 访问服务
```bash
kubectl port-forward svc/mcp-server 8000:8000 -n riskagent
kubectl port-forward svc/grafana 3000:3000 -n riskagent   # grafana 在 values-ci / values-local-e2e 中被禁用
```

## 卸载
```bash
make k8s-uninstall    # helm uninstall riskagent -n riskagent
```

## 环境配置（values 文件）
`values.yaml` 为默认基线（覆盖 `.env.example` 绝大多数配置项；已知缺口：`LLM_COST_PROMPT_PER_1K` / `LLM_COST_COMPLETION_PER_1K` 未纳入 values 与 configmap，生产无法经 Helm 覆盖成本单价，见 [docs/KNOWN_ISSUES.md](../../docs/KNOWN_ISSUES.md) KI-007），其余 values 文件均为其覆盖层：
- `values-dev.yaml`：开发环境——降配资源、镜像 tag `dev`（`make k8s-deploy-dev`）
- `values-prod.yaml`：生产环境——`pullPolicy: Always` + 更大持久化卷（`make k8s-deploy`）
- `values-ci.yaml`：CI（GitHub Actions kind 集群）专用——资源进一步缩减、`image.pullPolicy: Never`（kind load 模式）、禁用 Prometheus/Grafana 以节省 runner 资源；由 `.github/workflows/ci.yml` 使用，非手动部署目标（资源明细见 `docs/ci-cd.md`）
- `values-local-e2e.yaml`：本地 E2E 演示专用——显式开启 `security.allowUnauthenticated=true` 与 `hitl.autoApprove=true` 逃生舱（前端/验收脚本不携带 Token、无人值守自动审批），并禁用 Prometheus/Grafana；**生产环境严禁使用**（`values.yaml` 中两项默认均为 `false`）
