#!/usr/bin/env python3
"""
训练模块 - 模型训练核心功能
"""

import os
import json
import logging
import time
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import torch
import numpy as np
from transformers import (
    AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer,
    DataCollatorForLanguageModeling, EarlyStoppingCallback, TrainerCallback,
    BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, TaskType, PeftModel
from datasets import Dataset

# 可选导入
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import wandb
    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False

logger = logging.getLogger(__name__)

class MetricsTracker:
    """训练指标跟踪器"""

    def __init__(self):
        self.history = {
            'train_loss': [],
            'eval_loss': [],
            'learning_rate': [],
            'epoch': [],
            'step': [],
            'timestamp': []
        }
        self.best_eval_loss = float('inf')
        self.best_model_step = 0

    def update(self, metrics: Dict, step: int, epoch: float):
        """更新指标"""
        timestamp = datetime.now().isoformat()

        if 'train_loss' in metrics:
            self.history['train_loss'].append(metrics['train_loss'])
        if 'eval_loss' in metrics:
            self.history['eval_loss'].append(metrics['eval_loss'])
            if metrics['eval_loss'] < self.best_eval_loss:
                self.best_eval_loss = metrics['eval_loss']
                self.best_model_step = step
        if 'learning_rate' in metrics:
            self.history['learning_rate'].append(metrics['learning_rate'])

        self.history['epoch'].append(epoch)
        self.history['step'].append(step)
        self.history['timestamp'].append(timestamp)

    def save_metrics(self, output_dir: str):
        """保存指标历史"""
        os.makedirs(output_dir, exist_ok=True)
        metrics_path = os.path.join(output_dir, 'training_metrics.json')
        with open(metrics_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(self.history, f, ensure_ascii=False, indent=2)
        logger.info(f"训练指标已保存到: {metrics_path}")

    def plot_curves(self, output_dir: str):
        """绘制训练曲线"""
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("matplotlib未安装，跳过图表生成")
            return

        os.makedirs(output_dir, exist_ok=True)
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('Training Progress', fontsize=16)

        # 训练损失
        if self.history['train_loss']:
            axes[0, 0].plot(self.history['step'], self.history['train_loss'])
            axes[0, 0].set_title('Training Loss')
            axes[0, 0].set_xlabel('Step')
            axes[0, 0].set_ylabel('Loss')
            axes[0, 0].grid(True)

        # 验证损失
        if self.history['eval_loss']:
            axes[0, 1].plot(self.history['step'], self.history['eval_loss'], 'orange')
            axes[0, 1].set_title('Validation Loss')
            axes[0, 1].set_xlabel('Step')
            axes[0, 1].set_ylabel('Loss')
            axes[0, 1].grid(True)

        # 学习率
        if self.history['learning_rate']:
            axes[1, 0].plot(self.history['step'], self.history['learning_rate'], 'green')
            axes[1, 0].set_title('Learning Rate')
            axes[1, 0].set_xlabel('Step')
            axes[1, 0].set_ylabel('Learning Rate')
            axes[1, 0].grid(True)

        # 损失对比
        if self.history['train_loss'] and self.history['eval_loss']:
            axes[1, 1].plot(self.history['step'], self.history['train_loss'],
                           label='Train Loss', alpha=0.7)
            axes[1, 1].plot(self.history['step'], self.history['eval_loss'],
                           label='Eval Loss', alpha=0.7)
            axes[1, 1].set_title('Train vs Validation Loss')
            axes[1, 1].set_xlabel('Step')
            axes[1, 1].set_ylabel('Loss')
            axes[1, 1].legend()
            axes[1, 1].grid(True)

        plt.tight_layout()
        plot_path = os.path.join(output_dir, 'training_curves.png')
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.close()
        logger.info(f"训练曲线已保存到: {plot_path}")

class TrainingCallback(TrainerCallback):
    """训练回调"""

    def __init__(self, metrics_tracker: MetricsTracker):
        self.metrics_tracker = metrics_tracker
        self.start_time = time.time()

    def on_log(self, args, state, control, logs=None, **kwargs):
        """日志记录时的回调"""
        if logs is None:
            return

        step = state.global_step
        epoch = state.epoch

        # 更新指标跟踪器
        self.metrics_tracker.update(logs, step, epoch)

        # 计算训练速度
        elapsed_time = time.time() - self.start_time
        if step > 0 and step % 100 == 0:
            steps_per_sec = step / elapsed_time
            # 安全格式化日志，避免类型错误
            train_loss = logs.get('train_loss', 'N/A')
            eval_loss = logs.get('eval_loss', 'N/A')

            try:
                train_loss_str = f"{train_loss:.4f}" if isinstance(train_loss, (int, float)) else str(train_loss)
            except (ValueError, TypeError):
                train_loss_str = str(train_loss)

            try:
                eval_loss_str = f"{eval_loss:.4f}" if isinstance(eval_loss, (int, float)) else str(eval_loss)
            except (ValueError, TypeError):
                eval_loss_str = str(eval_loss)

            logger.info(f"Step {step}, Epoch {epoch:.2f}, "
                       f"Train Loss: {train_loss_str}, "
                       f"Eval Loss: {eval_loss_str}, "
                       f"Speed: {steps_per_sec:.2f} steps/sec")

    def on_train_end(self, args, state, control, **kwargs):
        """训练结束时的回调"""
        total_time = time.time() - self.start_time
        logger.info(f"训练完成！总用时: {total_time/3600:.2f} 小时")

        # 保存最终指标和图表
        self.metrics_tracker.save_metrics(args.output_dir)
        self.metrics_tracker.plot_curves(args.output_dir)

class BluetoothTrainer:
    """蓝牙代码生成训练器"""

    def __init__(self, config: Dict):
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.tokenizer = None
        self.metrics_tracker = MetricsTracker()

        # 设置环境
        self._setup_environment()

    def _setup_environment(self):
        """设置训练环境"""
        torch.manual_seed(42)
        np.random.seed(42)

        if torch.cuda.is_available():
            logger.info(f"使用GPU: {torch.cuda.get_device_name()}")
            logger.info(f"GPU显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            logger.warning("未检测到GPU，将使用CPU训练（速度较慢）")

        # 初始化wandb
        if WANDB_AVAILABLE and "wandb" in self.config.get('report_to', []):
            wandb.init(
                project="bluetooth-coder-training",
                config=self.config,
                name=f"training-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )

    def load_model_and_tokenizer(self):
        """加载模型和分词器"""
        logger.info("🚀 加载模型和分词器...")

        # 加载分词器
        if self.tokenizer is None:
            model_path = self.config['model_name']
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"模型路径不存在: {model_path}，请确保模型已下载到本地")

            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                local_files_only=True,
                trust_remote_code=True
            )
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # 直接从本地加载模型
        model_path = self.config['model_name']
        logger.info(f"从本地加载模型: {model_path}")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型路径不存在: {model_path}，请确保模型已下载到本地")

        # 使用 BitsAndBytesConfig 对象（与原始脚本一致）
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=self.config['load_in_4bit'],
            bnb_4bit_use_double_quant=self.config['bnb_4bit_use_double_quant'],
            bnb_4bit_quant_type=self.config['bnb_4bit_quant_type'],
            bnb_4bit_compute_dtype=getattr(torch, self.config['bnb_4bit_compute_dtype']),
        )

        # 尝试多种兼容性配置
        model_configs = [
            # 配置1：使用最基础的参数
            {
                "quantization_config": bnb_config,
                "device_map": "auto",
                "local_files_only": True,
                "trust_remote_code": True,
                "torch_dtype": torch.float16,
            },
            # 配置2：禁用缓存
            {
                "quantization_config": bnb_config,
                "device_map": "auto",
                "local_files_only": True,
                "trust_remote_code": True,
                "torch_dtype": torch.float16,
                "use_cache": False,
            }
        ]

        for i, model_kwargs in enumerate(model_configs):
            try:
                logger.info(f"尝试配置 {i+1} 加载模型...")
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    **model_kwargs
                )
                logger.info(f"✅ 成功使用配置 {i+1} 加载模型")
                break
            except Exception as e:
                logger.warning(f"配置 {i+1} 加载失败: {e}")
                if i == len(model_configs) - 1:  # 最后一个配置也失败了
                    raise e
                continue

        # 配置LoRA - 强制从配置文件读取所有参数
        lora_config = LoraConfig(
            r=self.config['lora_r'],
            lora_alpha=self.config['lora_alpha'],
            lora_dropout=self.config['lora_dropout'],
            target_modules=self.config['target_modules'],
            bias=self.config['lora_bias'],
            task_type=TaskType.CAUSAL_LM,
        )

        self.model = get_peft_model(self.model, lora_config)

        # 强制禁用模型缓存，避免DynamicCache问题
        if hasattr(self.model, 'config'):
            self.model.config.use_cache = False
        if hasattr(self.model, 'gradient_checkpointing_disable'):
            self.model.gradient_checkpointing_disable()

        # 遍历所有模块，禁用缓存
        for name, module in self.model.named_modules():
            if hasattr(module, 'config') and hasattr(module.config, 'use_cache'):
                module.config.use_cache = False

        self.model.print_trainable_parameters()
        logger.info("✅ 模型加载完成，已禁用缓存机制")

    def train(self) -> bool:
        """开始训练"""
        try:
            logger.info("🎯 开始模型训练...")

            # 加载模型和分词器
            self.load_model_and_tokenizer()

            # 加载训练数据
            with open(self.config['data_path'], 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"加载了 {len(data)} 条训练样本")

            # 创建Dataset和tokenization
            dataset = Dataset.from_list(data)

            # 首先将instruction/input/output格式转换为text
            def format_instruction_text(example):
                """将instruction/input/output格式转换为训练文本"""
                instruction = example.get("instruction", "")
                input_text = example.get("input", "")
                output_text = example.get("output", "")

                # 格式化为训练文本
                if input_text.strip():
                    formatted_text = f"指令: {instruction}\n输入: {input_text}\n输出: {output_text}"
                else:
                    formatted_text = f"指令: {instruction}\n输出: {output_text}"

                return {"text": formatted_text}

            def tokenize_function(examples):
                return self.tokenizer(
                    examples["text"],
                    truncation=True,
                    padding=False,
                    max_length=self.config['max_seq_length'],
                    return_tensors=None,
                )

            # 第一步：格式化数据
            formatted_dataset = dataset.map(format_instruction_text)
            logger.info(f"✅ 数据格式化完成，样本数: {len(formatted_dataset)}")

            # 显示转换示例
            if len(data) > 0:
                original_sample = data[0]
                formatted_sample = formatted_dataset[0]
                logger.info(f"📋 转换示例:")
                logger.info(f"原始格式: instruction={original_sample.get('instruction', '')[:50]}...")
                logger.info(f"转换后文本: {formatted_sample['text'][:100]}...")

            # 第二步：tokenization
            tokenized_dataset = formatted_dataset.map(
                tokenize_function,
                batched=True,
                remove_columns=formatted_dataset.column_names
            )

            # 根据评估策略决定是否分割数据集
            if self.config.get('evaluation_strategy') != "no":
                # 需要评估：分割训练集和验证集
                split_dataset = tokenized_dataset.train_test_split(test_size=0.1, seed=42)
                logger.info(f"训练集: {len(split_dataset['train'])}, 验证集: {len(split_dataset['test'])}")
                train_dataset = split_dataset['train']
                eval_dataset = split_dataset['test']
            else:
                # 不需要评估：全部用于训练
                train_dataset = tokenized_dataset
                eval_dataset = None
                logger.info(f"仅训练模式，样本数: {len(tokenized_dataset)}")

            # 使用配置文件中的warmup_steps（与原始脚本一致）
            warmup_steps = self.config['warmup_steps']
            logger.info(f"使用配置文件中的warmup_steps: {warmup_steps}")

            # 训练参数 - 强制从配置文件读取所有参数（与原始脚本一致）
            # 添加兼容性参数，避免DynamicCache问题
            training_args = TrainingArguments(
                output_dir=self.config['output_dir'],
                overwrite_output_dir=True,
                num_train_epochs=self.config['num_train_epochs'],
                learning_rate=self.config['learning_rate'],
                per_device_train_batch_size=self.config['per_device_train_batch_size'],
                gradient_accumulation_steps=self.config['gradient_accumulation_steps'],
                weight_decay=self.config['weight_decay'],
                max_grad_norm=self.config['max_grad_norm'],
                warmup_steps=warmup_steps,
                max_steps=self.config['max_steps'],
                eval_strategy=self.config['evaluation_strategy'],
                eval_steps=self.config['eval_steps'] if self.config['evaluation_strategy'] != "no" else None,
                save_steps=self.config['save_steps'],
                save_total_limit=self.config['save_total_limit'],
                load_best_model_at_end=self.config.get('load_best_model_at_end', False) if self.config['evaluation_strategy'] != "no" else False,
                metric_for_best_model=self.config.get('metric_for_best_model', 'eval_loss') if self.config['evaluation_strategy'] != "no" else None,
                greater_is_better=self.config.get('greater_is_better', False) if self.config['evaluation_strategy'] != "no" else False,
                fp16=self.config['fp16'],
                bf16=False,
                dataloader_pin_memory=self.config['dataloader_pin_memory'],
                optim=self.config['optim'],
                report_to=self.config['report_to'],
                logging_steps=self.config['logging_steps'],
                seed=42,
                # 兼容性参数 - 避免缓存问题
                gradient_checkpointing=False,  # 禁用梯度检查点
                dataloader_num_workers=0,      # 使用单进程数据加载
                remove_unused_columns=False,   # 保留所有列
                include_inputs_for_metrics=False,  # 避免计算指标时的缓存问题
            )

            # 数据整理器
            data_collator = DataCollatorForLanguageModeling(
                tokenizer=self.tokenizer,
                mlm=False,
                pad_to_multiple_of=8
            )

            # 回调函数 - 根据评估策略决定是否使用早停
            callbacks = [TrainingCallback(self.metrics_tracker)]

            # 只有在启用评估时才使用早停
            if self.config.get('evaluation_strategy') != "no":
                callbacks.append(EarlyStoppingCallback(early_stopping_patience=3))

            # 创建Trainer
            trainer_kwargs = {
                'model': self.model,
                'args': training_args,
                'train_dataset': train_dataset,
                'data_collator': data_collator,
                'tokenizer': self.tokenizer,
                'callbacks': callbacks
            }

            # 只有在需要评估时才添加eval_dataset
            if eval_dataset is not None:
                trainer_kwargs['eval_dataset'] = eval_dataset

            trainer = Trainer(**trainer_kwargs)

            # 保存训练配置
            self._save_training_config()

            # 开始训练
            trainer.train()

            # 保存最终模型
            trainer.save_model()
            self.tokenizer.save_pretrained(self.config['output_dir'])

            # 根据评估策略决定是否评估
            if eval_dataset is not None:
                # 评估模型
                eval_results = trainer.evaluate()
                logger.info(f"最终评估结果: {eval_results}")

                # 保存评估结果
                eval_results_path = os.path.join(self.config['output_dir'], "eval_results.json")
                with open(eval_results_path, 'w') as f:
                    json.dump(eval_results, f, indent=2)
            else:
                logger.info("✅ 训练完成！跳过评估步骤")

            logger.info("✅ 训练完成！")
            return True

        except Exception as e:
            logger.error(f"训练失败: {e}")
            return False

    def _save_training_config(self):
        """保存训练配置"""
        config_path = os.path.join(self.config['output_dir'], "training_config.json")
        os.makedirs(self.config['output_dir'], exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        logger.info(f"训练配置已保存到: {config_path}")

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="蓝牙代码生成模型训练器")
    parser.add_argument("--config", type=str, required=True,
                       help="训练配置文件 (必需)")

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 强制要求配置文件
    if not os.path.exists(args.config):
        print(f"❌ 配置文件不存在: {args.config}")
        print(f"💡 请确保配置文件存在，包含所有必要的训练参数")
        sys.exit(1)

    # 加载配置文件
    with open(args.config, 'r', encoding='utf-8') as f:
        config = json.load(f)

    print(f"✅ 从配置文件加载所有参数: {args.config}")
    print(f"📋 关键参数检查:")
    print(f"   - 模型路径: {config.get('model_name', '❌ 未设置')}")
    print(f"   - 数据路径: {config.get('data_path', '❌ 未设置')}")
    print(f"   - 输出目录: {config.get('output_dir', '❌ 未设置')}")
    print(f"   - 训练轮数: {config.get('num_train_epochs', '❌ 未设置')}")
    print(f"   - 学习率: {config.get('learning_rate', '❌ 未设置')}")
    print(f"   - LoRA rank: {config.get('lora_r', '❌ 未设置')}")
    print(f"   - LoRA alpha: {config.get('lora_alpha', '❌ 未设置')}")

    # 验证必需参数
    required_params = [
        # 基础参数
        'model_name', 'data_path', 'output_dir', 'num_train_epochs',
        'learning_rate', 'per_device_train_batch_size', 'gradient_accumulation_steps',
        'max_seq_length',

        # LoRA参数
        'lora_r', 'lora_alpha', 'lora_dropout', 'lora_bias', 'target_modules',

        # 训练策略参数
        'weight_decay', 'max_grad_norm', 'warmup_steps', 'max_steps',
        'save_steps', 'save_total_limit', 'logging_steps',
        'fp16', 'dataloader_pin_memory', 'optim',

        # 4bit量化参数
        'load_in_4bit', 'bnb_4bit_compute_dtype', 'bnb_4bit_quant_type', 'bnb_4bit_use_double_quant',

        # 评估策略
        'evaluation_strategy',

        # 报告配置
        'report_to'
    ]

    missing_params = [param for param in required_params if param not in config]
    if missing_params:
        print(f"❌ 配置文件缺少必需参数: {', '.join(missing_params)}")
        sys.exit(1)

    # 创建必要的目录
    os.makedirs(config['output_dir'], exist_ok=True)

    # 创建训练器
    trainer = BluetoothTrainer(config)

    # 开始训练
    success = trainer.train()

    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()