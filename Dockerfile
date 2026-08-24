FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV LLM_CONFIG_PATH=/app/config/llm.json

# 后端选择：openai / anthropic
ENV LLM_PROVIDER=anthropic
ENV LLM_MODEL=

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bilibili/ bilibili/
COPY analysis/ analysis/
COPY fetch_video.py .
COPY analyze_video.py .
COPY server.py .
COPY danmaku-comment-insight-demo.html .

RUN mkdir -p /app/output /app/config

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
