#!/bin/bash
set -e

echo "============================================"
echo "  弹幕评论区智能分析 · Docker 启动"
echo "============================================"

PROVIDER=${LLM_PROVIDER:-local}
echo "🔌 LLM 后端: $PROVIDER"

# 只有走本地模型时才需要预下载权重；走 API 时跳过，省掉 1.2GB 下载和启动等待
if [ "$PROVIDER" = "local" ]; then
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
else
  echo "  ⏭  使用远程 API，跳过本地模型下载"
fi

echo ""
echo "🚀 启动 Web 服务..."
echo "   访问 http://localhost:8000"
echo "============================================"

exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
