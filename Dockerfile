# ============================================================
# Album Spectrogram Generator — Docker 镜像
# 基于 Python 3.12 Slim + SoX
# ============================================================

FROM python:3.12-slim AS base

# 元信息
LABEL maintainer="album-spectrogram"
LABEL description="专辑频谱图生成器 — SoX + Pillow + imgbb"

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ---- 系统依赖 ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    sox \
    libsox-fmt-all \
    fonts-noto-cjk \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# ---- 工作目录 ----
WORKDIR /app

# ---- Python 依赖（利用 Docker 缓存层） ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- 复制应用代码 ----
COPY . .

# ---- 创建输出目录 ----
RUN mkdir -p /app/output

# ---- 默认端口 ----
EXPOSE 5000

# ---- 健康检查 ----
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/')" || exit 1

# ---- 启动（gunicorn 生产模式） ----
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "600", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
