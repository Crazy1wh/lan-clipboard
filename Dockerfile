# 基础镜像默认走国内加速器（本机直连 Docker Hub 被墙）；
# CI/公网构建可传 build-arg 覆盖为官方源：--build-arg PYTHON_IMAGE=python:3.11-slim
ARG PYTHON_IMAGE=docker.1ms.run/library/python:3.11-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static ./static

VOLUME /app/data
EXPOSE 8010

# PORT 环境变量可覆盖端口（需同步修改 docker-compose 的端口映射）
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8010}"]
