# 蜀道安全助手 后端镜像（Python 3.12）
# 构建：docker build -f backend/Dockerfile -t shudao-backend .
# 说明：RAG 本地模型（bge-large-zh/bge-reranker-base）与 Chroma 知识库体积大，
#       默认以卷挂载方式接入（见 docker-compose.yml），镜像内不打包模型。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 系统依赖（pdfplumber/pdfminer 需要；libgl 供 PIL 处理图片）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgl1 libglib2.0-0 libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖再拷代码（利用层缓存）
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY backend/database ./database
COPY backend/scripts/init_db.py ./scripts/init_db.py

EXPOSE 8000

# 建表与初始化（幂等）；随后启动服务。
# DATABASE_URL 等由 docker-compose 环境变量注入；本地模型/知识库目录以卷挂载。
CMD ["sh", "-c", "python scripts/init_db.py 2>/dev/null || true; uvicorn app.main:app --host 0.0.0.0 --port 8000"]
