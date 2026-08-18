FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    && arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
        amd64) kubectl_arch="amd64" ;; \
        arm64) kubectl_arch="arm64" ;; \
        *) echo "unsupported architecture: ${arch}" && exit 1 ;; \
      esac \
    && curl -fsSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/v1.31.0/bin/linux/${kubectl_arch}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖清单以利用构建缓存
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt
 
# 复制应用代码
COPY main.py .
COPY src ./src
# .env 文件由 K8s Secret 注入，不烘焙进镜像（.dockerignore 已排除 .env*）
# COPY .env.example ./  # 如需默认配置可取消注释

# 暴露 MCP Server 端口(可选; 未来可能用于 HTTP/可观测性等场景)
# MCP 通常走 stdio, 这里保留端口便于扩展
EXPOSE 8000

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动 MCP Server
CMD ["python", "main.py"]
