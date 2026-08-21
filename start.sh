#!/bin/bash
set -e

echo "============================================"
echo "  弹幕评论区智能分析 · Docker 启动"
echo "============================================"

# 预下载模型（如果未缓存）
MODEL=${LLM_MODEL:-"Qwen/Qwen3-0.6B"}
echo "📦 检查模型: $MODEL"
python -c "
from transformers import AutoTokenizer, AutoModelForCausalLM
import os
model = os.environ.get('LLM_MODEL', 'Qwen/Qwen3-0.6B')
print(f'  下载/验证模型: {model}')
AutoTokenizer.from_pretrained(model, trust_remote_code=True)
print('  ✔ Tokenizer 就绪')
AutoModelForCausalLM.from_pretrained(model, trust_remote_code=True, torch_dtype='auto')
print('  ✔ 模型权重就绪')
"

echo ""
echo "🚀 启动 Web 服务..."
echo "   访问 http://localhost:8000"
echo "============================================"

exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
