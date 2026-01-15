#!/usr/bin/env python3
"""
训练执行脚本 - 主要的训练入口
"""

import sys
import os
import json
import logging
import torch
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent.parent))
sys.path.append(str(Path(__file__).parent))

from data_processor import TrainingDataProcessor
from trainer import BluetoothTrainer

def main():
    """主训练函数"""
    import argparse

    parser = argparse.ArgumentParser(description="蓝牙代码生成模型训练器")
    parser.add_argument("--mode", choices=["process", "train", "full"], default="full",
                       help="运行模式: process-仅数据处理, train-仅训练, full-完整流程")
    parser.add_argument("--config", type=str, default="training_config.json",
                       help="配置文件路径")
    parser.add_argument("--data", type=str, default="../data/processed/training_data.json",
                       help="训练数据文件")
    parser.add_argument("--output", type=str, default="../outputs/bluetooth-coder",
                       help="输出目录")
    parser.add_argument("--skip-process", action="store_true",
                       help="跳过数据处理")

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    logger.info("🎉 蓝牙代码生成模型训练器启动")
    logger.info(f"设备: {torch.device('cuda' if torch.cuda.is_available() else 'cpu')}")
    logger.info(f"运行模式: {args.mode}")

    # 加载或创建配置
    if os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        # 默认配置
        config = {
            'model_name': 'deepseek-ai/DeepSeek-Coder-V2-Lite-16B',
            'data_path': args.data,
            'output_dir': args.output,
            'raw_data_path': '../data/processed/bluetooth_training_data.json',
            'num_train_epochs': 3,
            'learning_rate': 2e-4,
            'per_device_train_batch_size': 1,
            'gradient_accumulation_steps': 8,
            'warmup_steps': 100,
            'max_seq_length': 2048,
            'lora_r': 16,
            'lora_alpha': 32,
            'lora_dropout': 0.05,
            'eval_steps': 200,
            'save_steps': 200,
            'logging_steps': 10,
            'save_total_limit': 3,
            'load_best_model_at_end': True,
            'metric_for_best_model': 'eval_loss',
            'fp16': True,
            'dataloader_pin_memory': False,
            'report_to': ["tensorboard"],
            'data_augmentation_factor': 0.3,
            'target_samples_per_category': 100
        }

        # 保存默认配置
        with open(args.config, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"创建默认配置: {args.config}")

    # 命令行参数覆盖
    config['data_path'] = args.data
    config['output_dir'] = args.output

    # 创建必要的目录
    os.makedirs(config['output_dir'], exist_ok=True)
    os.makedirs(os.path.dirname(config['data_path']), exist_ok=True)

    try:
        success = True
        if args.mode == "process":
            if not args.skip_process:
                processor = TrainingDataProcessor(config)
                success = processor.process()
            else:
                logger.info("跳过数据处理")
        elif args.mode == "train":
            trainer = BluetoothTrainer(config)
            success = trainer.train()
        else:  # full
            # 数据处理
            if not args.skip_process:
                processor = TrainingDataProcessor(config)
                success = processor.process()
            else:
                logger.info("跳过数据处理")

            # 模型训练
            if success:
                trainer = BluetoothTrainer(config)
                success = trainer.train()

        if success:
            logger.info("🎉 训练任务完成！")
            logger.info("="*60)
            logger.info("训练结果:")
            logger.info(f"  模型路径: {config['output_dir']}")
            logger.info(f"  数据路径: {config['data_path']}")
            logger.info(f"  配置文件: {args.config}")
            logger.info("="*60)
        else:
            logger.error("❌ 训练任务失败")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("⏹️ 用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 训练失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()