#!/usr/bin/env python3
"""
Qwen-3-8B 本地模型对话部署
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
from typing import List, Tuple
import sys
import threading
import re
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.formatters import Terminal256Formatter
from pygments.util import ClassNotFound

# -------------------------
# 配置
# -------------------------
MODEL_PATH = "./workspace/models/qwen3-bluetooth/Qwen3-8B"  # 本地路径
MAX_TOKENS = 24576
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# -------------------------
# 对话历史
# -------------------------
history: List[Tuple[str, str]] = []  # [(user, bot), ...]

# -------------------------
# 加载模型（混合精度：8bit + 16bit 关键层）
# -------------------------
print(f"🚀 加载模型: {MODEL_PATH} (混合精度)")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    device_map="auto",
    load_in_8bit=True,  # 主体用 8bit 量化
    torch_dtype=torch.float16,  # 关键层用 16bit
    trust_remote_code=True,
    llm_int8_enable_fp32_cpu_offload=True,  # CPU 上的层用 32bit
    llm_int8_threshold=6.0,  # 调整量化阈值，提升精度
    llm_int8_skip_modules=["lm_head"],  # 跳过输出的量化，保持 16bit
)
print(f"✅ 混合精度模型加载完成，设备: {next(model.parameters()).device}")

# -------------------------
# 代码格式化功能
# -------------------------
def format_code(text: str) -> str:
    """检测并格式化代码块"""
    # 检测代码块格式 - 修复正则表达式
    code_block_pattern = r'```(\w+)?\s*\n(.*?)\n```'

    def replace_code_block(match):
        lang = match.group(1) or 'text'
        code = match.group(2)

        try:
            # 尝试根据语言获取 lexer
            if lang == 'text':
                lexer = guess_lexer(code)
            else:
                lexer = get_lexer_by_name(lang)
        except (ClassNotFound, Exception):
            try:
                lexer = guess_lexer(code)
            except:
                lexer = get_lexer_by_name('text')

        # 应用语法高亮
        formatter = Terminal256Formatter(style='monokai', linenos=False)
        highlighted = highlight(code, lexer, formatter)

        return f"\n\033[1m\033[97m--- {lang.upper()} CODE ---\033[0m\n{highlighted}\033[1m\033[97m--- END CODE ---\033[0m\n"

    # 替换所有代码块
    formatted_text = re.sub(code_block_pattern, replace_code_block, text, flags=re.DOTALL)
    return formatted_text

def format_markdown(text: str) -> str:
    """简单的 Markdown 格式化"""
    # 替换常见 Markdown 元素为终端友好格式
    formatted = text

    # 标题格式化
    formatted = re.sub(r'^### (.*)', r'\033[1;36m### \1\033[0m', formatted, flags=re.MULTILINE)
    formatted = re.sub(r'^## (.*)', r'\033[1;34m## \1\033[0m', formatted, flags=re.MULTILINE)
    formatted = re.sub(r'^# (.*)', r'\033[1;32m# \1\033[0m', formatted, flags=re.MULTILINE)

    # 粗体和斜体
    formatted = re.sub(r'\*\*(.*?)\*\*', r'\033[1m\1\033[0m', formatted)
    formatted = re.sub(r'\*(.*?)\*', r'\033[3m\1\033[0m', formatted)

    # 行内代码
    formatted = re.sub(r'`(.*?)`', r'\033[0;37m\033[40m\1\033[0m', formatted)

    return formatted

# -------------------------
# 对话功能
# -------------------------
def generate_response_stream(message: str, history: List[Tuple[str, str]]):
    """流式生成回复"""
    # 构建 ChatML 格式的对话上下文
    messages = []

    # 添加历史对话
    for u, b in history:
        messages.append({"role": "user", "content": u})
        messages.append({"role": "assistant", "content": b})

    # 添加当前用户消息
    messages.append({"role": "user", "content": message})

    # 使用 tokenizer 的 chat_template，关闭 thinking 功能
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False  # 关闭 thinking 功能
    )

    # 流式生成设置
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    streamer = TextIteratorStreamer(
        tokenizer,
        skip_special_tokens=True,
        skip_prompt=True,
        clean_up_tokenization_spaces=True
    )

    # 在单独线程中生成
    generation_kwargs = dict(
        **inputs,
        max_new_tokens=MAX_TOKENS,
        temperature=0.3,
        do_sample=True,
        top_p=0.8,
        top_k=40,
        repetition_penalty=1.05,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
        use_cache=True,
        num_beams=1,
        streamer=streamer
    )

    thread = threading.Thread(target=model.generate, kwargs=generation_kwargs)
    thread.start()

    return streamer

def main():
    """主对话循环（流式输出）"""
    print("🤖 Qwen-3-8B 流式对话机器人 (输入 'quit', 'exit' 或 'q' 退出)")
    print("=" * 50)

    while True:
        try:
            # 获取用户输入
            user_input = input("\n你: ").strip()

            # 检查退出命令
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 再见！")
                break

            if not user_input:
                continue

            print("🤖 回复: ", end="", flush=True)

            # 流式生成并输出
            streamer = generate_response_stream(user_input, history)
            full_response = ""

            for new_text in streamer:
                print(new_text, end="", flush=True)
                full_response += new_text

            print()  # 换行

            # 应用代码高亮和格式化
            formatted_response = format_code(full_response)
            formatted_response = format_markdown(formatted_response)

            # 如果检测到代码块，重新输出格式化版本
            if '```' in full_response:
                print("\n🎨 格式化版本:")
                print(formatted_response)

            # 更新历史记录
            history.append((user_input, full_response.strip()))

            # 保持历史记录在合理范围内
            if len(history) > 10:
                history.pop(0)

        except KeyboardInterrupt:
            print("\n👋 再见！")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")

# -------------------------
# 启动对话
# -------------------------
if __name__ == "__main__":
    main()
