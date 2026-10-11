FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models/hf-cache \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=4 \
    LANG=C.UTF-8

WORKDIR /app

# build-essential 用于部分包的源码编译；curl 用于容器内排障
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 默认装全量依赖（RAG 需要）。快速迭代界面时可传
# --build-arg REQ_FILE=requirements-base.txt 跳过 torch 等大包。
ARG REQ_FILE=requirements.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt requirements-base.txt ./
RUN pip install --index-url ${PIP_INDEX_URL} -r ${REQ_FILE}

COPY . .

RUN mkdir -p /data /models/hf-cache

EXPOSE 8000

CMD ["gunicorn", "-k", "gthread", "-w", "2", "--threads", "8", \
     "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", \
     "-b", "0.0.0.0:8000", "wsgi:app"]

