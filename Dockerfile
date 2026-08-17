# 基础镜像走国内加速器（本机直连 Docker Hub 被墙；公网环境可改回 python:3.11-slim）
FROM docker.1ms.run/library/python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static ./static

VOLUME /app/data
EXPOSE 8010

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]
