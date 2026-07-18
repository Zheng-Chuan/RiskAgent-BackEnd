# RiskMonitor K8s 部署指南

## 前置条件
- kubectl 已安装并配置好集群
- Helm 3.x 已安装
- Docker 镜像已构建并推送到镜像仓库

## 部署步骤

### 1. 创建 Secret
kubectl create secret generic riskmonitor-secrets \
  --from-literal=MYSQL_ROOT_PASSWORD=root \
  --from-literal=MYSQL_PASSWORD=change_me \
  --from-literal=MYSQL_USER=admin \
  --from-literal=LLM_API_KEY=your-api-key \
  -n riskmonitor

### 2. 部署
make k8s-deploy

### 3. 验证
kubectl get pods -n riskmonitor
kubectl get svc -n riskmonitor

### 4. 访问服务
kubectl port-forward svc/riskmonitor-mcp-server 8000:8000 -n riskmonitor
kubectl port-forward svc/riskmonitor-grafana 3000:3000 -n riskmonitor

## 卸载
make k8s-uninstall

## 环境配置
- 默认: values.yaml
- 开发: values-dev.yaml (make k8s-deploy-dev)
- 生产: values-prod.yaml (make k8s-deploy)
