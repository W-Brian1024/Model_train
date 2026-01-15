#!/bin/bash

# 蓝牙代码生成AI训练系统 - 环境配置脚本
# 作者: Claude Code Assistant
# 用途: 自动配置训练环境和依赖

echo "🚀 开始配置蓝牙代码生成AI训练环境..."

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/bluetooth_ai"

# 检查虚拟环境是否存在
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 创建Python虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi

# 激活虚拟环境
echo "🔄 激活虚拟环境..."
source "$VENV_DIR/bin/activate"

# 升级pip
echo "⬆️ 升级pip..."
pip install --upgrade pip

# 安装深度学习核心依赖
echo "🧠 安装PyTorch (CPU版本)..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 安装Transformers和相关库
echo "🤖 安装Transformers生态系统..."
pip install transformers peft datasets accelerate

# 安装科学计算和可视化
echo "📊 安装数据处理库..."
pip install numpy pandas matplotlib seaborn

# 安装其他必要依赖
echo "🔧 安装其他依赖..."
pip install tqdm scikit-learn wandb tensorboard

# 创建必要目录
echo "📁 创建工作目录..."
mkdir -p "$SCRIPT_DIR/workspace"
mkdir -p "$SCRIPT_DIR/workspace/models"
mkdir -p "$SCRIPT_DIR/workspace/logs"
mkdir -p "$SCRIPT_DIR/workspace/checkpoints"

echo "✅ 环境配置完成！"
echo ""
echo "🎯 下一步操作："
echo "1. 激活虚拟环境: source $VENV_DIR/bin/activate"
echo "2. 运行数据收集: python main.py collect --quick"
echo "3. 开始模型训练: python main.py train --mode full"
echo ""
echo "💡 提示: 每次使用前都需要激活虚拟环境"