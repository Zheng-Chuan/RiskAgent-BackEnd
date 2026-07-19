# RiskMonitor K8s 部署指南

## 前置条件
- kubectl 已安装并配置好集群
- Helm 3.x 已安装
- Docker 镜像已构建并推送到镜像仓库（见 `make docker-build`）

## 部署步骤

### 1. 部署 Helm Chart（自动创建 namespace）

生产环境：
```bash
helm upgrade --install riskmonitor deploy/k8s/ \
  -f deploy/k8s/values-prod.yaml \
  -n riskmonitor --create-namespace
```

开发环境：
```bash
helm upgrade --install riskmonitor deploy/k8s/ \
  -f deploy/k8s/values-dev.yaml \
  -n riskmonitor --create-namespace
```

或使用 Makefile 快捷命令：
```bash
make k8s-deploy       # 生产
make k8s-deploy-dev   # 开发
```

> `--create-namespace` 标志会在 namespace 不存在时由 Helm 自动创建，无需手动 `kubectl create namespace`。
> Secret 默认由 `templates/secrets.yaml` 从 values 自动生成；如需覆盖默认密钥，可在部署后用 `kubectl create secret` 手动更新。

### 2. 验证
kubectl get pods -n riskmonitor
kubectl get svc -n riskmonitor

### 3. 访问服务
kubectl port-forward svc/riskmonitor-mcp-server 8000:8000 -n riskmonitor
kubectl port-forward svc/riskmonitor-grafana 3000:3000 -n riskmonitor

## 卸载
make k8s-uninstall

## 环境配置
- 默认: values.yaml
- 开发: values-dev.yaml (make k8s-deploy-dev)
- 生产: values-prod.yaml (make k8s-deploy)
