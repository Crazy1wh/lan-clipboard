# 基础镜像默认走国内加速器（本机直连 Docker Hub 被墙）；
# CI/公网构建可传 build-arg 覆盖为官方源：--build-arg PYTHON_IMAGE=python:3.11-slim
ARG PYTHON_IMAGE=docker.1ms.run/library/python:3.11-slim
FROM ${PYTHON_IMAGE}

ARG BUILD_REPOSITORY=""
ARG BUILD_BRANCH=""
ARG BUILD_SHA=""
ARG BUILD_COMMIT_DATE=""
ARG BUILD_TIME=""
ENV BUILD_REPOSITORY=${BUILD_REPOSITORY} \
    BUILD_BRANCH=${BUILD_BRANCH} \
    BUILD_SHA=${BUILD_SHA} \
    BUILD_COMMIT_DATE=${BUILD_COMMIT_DATE} \
    BUILD_TIME=${BUILD_TIME}

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY app.py .
COPY static ./static

VOLUME /app/data
EXPOSE 8010

# PORT 环境变量可覆盖端口（需同步修改 docker-compose 的端口映射）
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8010}"]
