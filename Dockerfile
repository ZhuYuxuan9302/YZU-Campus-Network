# 使用官方 Python 精简版镜像（脚本要求 Python 3.9+）
FROM python:3.12-slim

# 日志实时输出（避免缓冲导致 docker logs 延迟）
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 先复制依赖清单单独安装，利用 Docker 层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 以非 root 用户运行脚本
RUN useradd --create-home appuser
COPY --chown=appuser:appuser main.py ./

USER appuser

CMD ["python", "main.py"]
