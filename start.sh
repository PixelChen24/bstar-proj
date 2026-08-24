#!/bin/bash
set -e

echo "============================================"
echo "  弹幕评论区智能分析"
echo "============================================"
echo "🔌 LLM 后端: ${LLM_PROVIDER:-anthropic}"
echo "🚀 启动 Web 服务..."
echo "   访问 http://localhost:8000"
echo "============================================"

exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
