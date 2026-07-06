# 后端 FastAPI 服务镜像
#
# 构建与运行统一通过 docker compose 完成（见 docker-compose.yml 和 README）：
#   docker compose up -d --build

FROM python:3.12-slim

WORKDIR /app

# 先装依赖再拷代码，充分利用 Docker 层缓存（改代码不用重装依赖）
COPY requirements.txt .

# torch/torchvision 从 PyTorch CPU 源安装，避免拉取数 GB 的 CUDA 版本；
# 容器内训练走 CPU，需要 GPU 训练时在宿主机直接运行后端即可
RUN pip install --no-cache-dir torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
