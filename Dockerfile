# ── 阶段：构建依赖 ────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# sentence-transformers / chromadb 等包编译时需要 gcc
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（极速包管理器）
RUN pip install --no-cache-dir uv

COPY requirements.txt .
# 用 uv 安装依赖，--system 直接装到系统 Python，无需虚拟环境
RUN uv pip install --system --no-cache -r requirements.txt


# ── 阶段：运行时镜像 ──────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# 拷贝已安装的 Python 包
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 拷贝项目代码（.dockerignore 已排除 .env / data/ / __pycache__ 等）
COPY . .

# 创建数据目录占位（实际内容由 volume 挂载）
RUN mkdir -p /app/data

# Streamlit 默认端口
EXPOSE 8501

# 禁用 Streamlit 遥测、关闭 CORS 限制（容器内必须绑定 0.0.0.0）
CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--browser.gatherUsageStats=false"]
