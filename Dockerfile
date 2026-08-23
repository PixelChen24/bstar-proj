FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV HF_ENDPOINT=https://hf-mirror.com

# LLM 后端：local（本地 Qwen）/ openai（OpenAI 兼容接口）/ anthropic
# 走 API 时无需 GPU，用 docker run -e 覆盖即可
ENV LLM_PROVIDER=local
ENV LLM_MODEL=Qwen/Qwen3-0.6B
ENV LLM_CONFIG_PATH=/app/config/llm.json

# 安装 Python 3.10
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip python3.10-venv curl && \
    ln -sf /usr/bin/python3.10 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存
COPY requirements.txt .

# 安装 Python 依赖（torch 需要单独装 GPU 版）
RUN pip install --no-cache-dir \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 && \
    pip install --no-cache-dir transformers accelerate sentencepiece safetensors && \
    pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY bilibili/ bilibili/
COPY analysis/ analysis/
COPY fetch_video.py .
COPY analyze_video.py .
COPY server.py .
COPY danmaku-comment-insight-demo.html .
COPY start.sh .
RUN chmod +x start.sh

# 输出目录 + LLM 配置目录（配置文件含 API Key，挂载 volume 持久化）
RUN mkdir -p /app/output /app/config

# 模型缓存目录
ENV HF_HOME=/root/.cache/huggingface
RUN mkdir -p $HF_HOME

# 构建时预下载模型（可选，使镜像自包含约 +1.2GB）
# 用 --build-arg PRELOAD_MODEL=1 启用；只走 API 时无需启用
ARG PRELOAD_MODEL=0
RUN if [ "$PRELOAD_MODEL" = "1" ]; then \
    python -c "import os; from transformers import AutoTokenizer, AutoModelForCausalLM; \
    m = os.environ.get('LLM_MODEL', 'Qwen/Qwen3-0.6B'); \
    AutoTokenizer.from_pretrained(m, trust_remote_code=True); \
    AutoModelForCausalLM.from_pretrained(m, trust_remote_code=True)"; \
    echo '✔ 模型已预装到镜像中'; \
    fi

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

ENTRYPOINT ["./start.sh"]
