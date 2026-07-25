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
make k8s-deploy       # 生产
make k8s-deploy-dev   # 开发
```

> `--create-namespace` 标志会在 namespace 不存在时由 Helm 自动创建，无需手动 `kubectl create namespace`。
> Secret 默认由 `templates/secrets.yaml` 从 values 自动生成；如需覆盖默认密钥，可在部署后用 `kubectl create secret` 手动更新。

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
kubectl get pods -n riskagent
kubectl get svc -n riskagent

### 3. 访问服务
kubectl port-forward svc/mcp-server 8000:8000 -n riskagent
kubectl port-forward svc/grafana 3000:3000 -n riskagent

## 卸载
make k8s-uninstall

## 环境配置
- 默认: values.yaml
- 开发: values-dev.yaml (make k8s-deploy-dev)
- 生产: values-prod.yaml (make k8s-deploy)
