#!/bin/bash

# Qwen3-8B FastAPI 启动脚本
export CUDA_VISIBLE_DEVICES=0
export MODEL_PATH="/home/weng/code/ai/code_ai/workspace/models/qwen3-bluetooth/Qwen3-8B"
export LOAD_IN_8BIT=true
export DEVICE=cuda

echo "=== Qwen3-8B API Server (Claude Code Compatible) ==="
echo "Model: $MODEL_PATH"
echo "Quantization: 8-bit"
echo "Claude Code Support: Enabled"
echo "Starting server on port 8000..."

python main.py