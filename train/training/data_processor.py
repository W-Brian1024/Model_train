#!/usr/bin/env python3
"""
数据处理模块 - 处理和准备训练数据
"""

import os
import json
import logging
import random
import re
from typing import Dict, List
from pathlib import Path
from datetime import datetime

import torch
from transformers import AutoTokenizer

logger = logging.getLogger(__name__)

class DataAugmenter:
    """数据增强器"""

    def __init__(self):
        self.code_patterns = {
            'c': r'```c\n(.*?)\n```',
            'python': r'```python\n(.*?)\n```',
            'javascript': r'```javascript\n(.*?)\n```'
        }

    def vary_instruction_style(self, instruction: str) -> str:
        """改变指令风格"""
        variations = [
            f"请实现：{instruction}",
            f"编写代码：{instruction}",
            f"如何实现：{instruction}",
            instruction,
            f"实现以下功能：{instruction}"
        ]
        return random.choice(variations)

    def extract_and_enhance_code(self, text: str) -> str:
        """提取并增强代码块"""
        code_blocks = re.findall(r'```(?:c|cpp|python|javascript)\n(.*?)\n```', text, re.DOTALL)
        if code_blocks:
            return self._format_code(code_blocks[0])
        return text

    def _format_code(self, code: str) -> str:
        """格式化代码"""
        lines = code.split('\n')
        formatted_lines = []
        prev_empty = False

        for line in lines:
            stripped = line.rstrip()
            if stripped:
                formatted_lines.append(stripped)
                prev_empty = False
            elif not prev_empty:
                formatted_lines.append('')
                prev_empty = True

        return '\n'.join(formatted_lines)

class DataProcessor:
    """数据处理模块"""

    def __init__(self):
        self.augmenter = DataAugmenter()
        self.stats = {
            'total_samples': 0,
            'filtered_samples': 0,
            'augmented_samples': 0,
            'categories': {},
            'languages': {}
        }

    def load_training_data(self, data_path: str) -> List[Dict]:
        """加载训练数据"""
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"加载了 {len(data)} 条训练数据")
        return data

    def filter_low_quality_samples(self, samples: List[Dict]) -> List[Dict]:
        """过滤低质量样本"""
        filtered_samples = []

        for sample in samples:
            if not all(key in sample for key in ['instruction', 'output']):
                continue

            if len(sample['instruction']) < 10 or len(sample['output']) < 20:
                continue

            if not self._contains_code(sample['output']):
                continue

            if self._is_repetitive(sample['output']):
                continue

            filtered_samples.append(sample)

        self.stats['filtered_samples'] = len(samples) - len(filtered_samples)
        logger.info(f"过滤了 {self.stats['filtered_samples']} 条低质量样本")
        return filtered_samples

    def _contains_code(self, text: str) -> bool:
        """检查文本是否包含代码"""
        code_indicators = [
            '```', 'int ', 'void ', 'char ', 'struct ', 'if ', 'for ', 'while ',
            'def ', 'class ', 'function ', 'var ', 'let ', 'const ',
            '#include', '#define', 'BT_', 'bt_', 'BLE_', 'ble_',
            'hci_', 'HCI_', 'gatt_', 'GATT_'
        ]
        return any(indicator in text for indicator in code_indicators)

    def _is_repetitive(self, text: str) -> bool:
        """检查文本是否过于重复"""
        words = text.split()
        if len(words) < 10:
            return False
        unique_words = set(words)
        repetition_rate = 1 - (len(unique_words) / len(words))
        return repetition_rate > 0.7

    def augment_data(self, samples: List[Dict], augmentation_factor: float = 0.3) -> List[Dict]:
        """数据增强"""
        augmented_samples = samples.copy()
        num_augment = int(len(samples) * augmentation_factor)

        for i in range(num_augment):
            original = random.choice(samples)
            augmented = self._create_augmented_sample(original)
            augmented_samples.append(augmented)

        self.stats['augmented_samples'] = len(augmented_samples) - len(samples)
        logger.info(f"生成了 {self.stats['augmented_samples']} 条增强样本")
        return augmented_samples

    def _create_augmented_sample(self, original: Dict) -> Dict:
        """创建增强样本"""
        augmented = original.copy()

        # 改变指令风格
        augmented['instruction'] = self.augmenter.vary_instruction_style(original['instruction'])

        # 增强代码输出
        if '```' in original['output']:
            augmented['output'] = self.augmenter.extract_and_enhance_code(original['output'])

        augmented['augmented'] = True
        return augmented

    def balance_categories(self, samples: List[Dict], target_samples_per_category: int = 100) -> List[Dict]:
        """平衡各类别样本数量"""
        category_groups = {}
        for sample in samples:
            category = sample.get('category', 'general')
            if category not in category_groups:
                category_groups[category] = []
            category_groups[category].append(sample)

        balanced_samples = []
        for category, category_samples in category_groups.items():
            if len(category_samples) > target_samples_per_category:
                selected = random.sample(category_samples, target_samples_per_category)
            else:
                multiplier = (target_samples_per_category // len(category_samples)) + 1
                selected = (category_samples * multiplier)[:target_samples_per_category]
            balanced_samples.extend(selected)
            logger.info(f"类别 '{category}': {len(selected)} 个样本")

        random.shuffle(balanced_samples)
        return balanced_samples

    def format_for_training(self, samples: List[Dict], tokenizer) -> List[Dict]:
        """格式化为训练数据"""
        formatted_samples = []

        for sample in samples:
            instruction = sample['instruction'].strip()
            input_text = sample.get('input', '').strip()
            output = sample['output'].strip()

            if input_text:
                prompt = f"### 指令:\n{instruction}\n\n### 输入:\n{input_text}\n\n### 输出:\n{output}"
            else:
                prompt = f"### 指令:\n{instruction}\n\n### 输出:\n{output}"

            prompt += tokenizer.eos_token

            formatted_sample = {
                "text": prompt,
                "instruction": instruction,
                "output": output,
                "category": sample.get('category', 'general'),
                "language": self._detect_language(output),
                "tokens": len(tokenizer.encode(prompt))
            }
            formatted_samples.append(formatted_sample)

        self._update_stats(formatted_samples)
        return formatted_samples

    def _detect_language(self, text: str) -> str:
        """检测代码语言"""
        language_patterns = {
            'c': [r'#include', r'int\s+\w+\s*\(', r'void\s+\w+\s*\(', r'struct\s+\w+'],
            'cpp': [r'#include', r'class\s+\w+', r'std::', r'namespace\s+\w+'],
            'python': [r'def\s+\w+\s*\(', r'class\s+\w+:', r'import\s+\w+', r'print\s*\('],
            'javascript': [r'function\s+\w+\s*\(', r'const\s+\w+\s*=', r'let\s+\w+\s*=', r'console\.log']
        }

        scores = {}
        for lang, patterns in language_patterns.items():
            score = sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))
            scores[lang] = score

        return max(scores.items(), key=lambda x: x[1])[0] if any(scores.values()) else 'unknown'

    def _update_stats(self, samples: List[Dict]):
        """更新统计信息"""
        self.stats['total_samples'] = len(samples)
        for sample in samples:
            category = sample.get('category', 'general')
            language = sample.get('language', 'unknown')
            self.stats['categories'][category] = self.stats['categories'].get(category, 0) + 1
            self.stats['languages'][language] = self.stats['languages'].get(language, 0) + 1

    def save_processed_data(self, samples: List[Dict], output_path: str):
        """保存处理后的数据"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)
        logger.info(f"处理后的数据已保存到: {output_path}")

    def save_statistics(self, output_path: str):
        """保存统计信息"""
        stats_path = output_path.replace('.json', '_stats.json')
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)
        logger.info(f"统计信息已保存到: {stats_path}")

    def print_summary(self):
        """打印处理摘要"""
        print("\n" + "="*60)
        print("📊 数据处理摘要")
        print("="*60)
        print(f"总样本数: {self.stats['total_samples']}")
        print(f"过滤样本数: {self.stats['filtered_samples']}")
        print(f"增强样本数: {self.stats['augmented_samples']}")

        print(f"\n📂 类别分布:")
        for category, count in self.stats['categories'].items():
            print(f"  {category}: {count}")

        print(f"\n💻 语言分布:")
        for language, count in self.stats['languages'].items():
            print(f"  {language}: {count}")
        print("="*60)

class TrainingDataProcessor:
    """训练数据处理器主类"""

    def __init__(self, config: Dict):
        self.config = config
        self.augmenter = DataAugmenter()
        self.processor = DataProcessor()

    def process(self) -> bool:
        """完整的数据处理流程"""
        try:
            logger.info("🔄 开始数据处理...")

            # 加载原始数据
            raw_data = self.processor.load_training_data(self.config['raw_data_path'])

            # 数据处理流程
            filtered_data = self.processor.filter_low_quality_samples(raw_data)
            augmented_data = self.processor.augment_data(
                filtered_data,
                self.config.get('data_augmentation_factor', 0.3)
            )
            balanced_data = self.processor.balance_categories(
                augmented_data,
                self.config.get('target_samples_per_category', 100)
            )

            # 延迟加载分词器
            logger.info("加载分词器...")
            tokenizer = AutoTokenizer.from_pretrained(
                self.config['model_name'],
                trust_remote_code=True
            )
            tokenizer.pad_token = tokenizer.eos_token

            # 格式化数据
            formatted_data = self.processor.format_for_training(balanced_data, tokenizer)

            # 保存数据
            self.processor.save_processed_data(formatted_data, self.config['data_path'])
            self.processor.save_statistics(self.config['data_path'])

            # 保存处理配置
            config_path = self.config['data_path'].replace('.json', '_config.json')
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)

            # 打印摘要
            self.processor.print_summary()

            logger.info("✅ 数据处理完成")
            return True

        except Exception as e:
            logger.error(f"数据处理失败: {e}")
            return False

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="训练数据处理器")
    parser.add_argument("--config", type=str, default="data_config.json",
                       help="配置文件路径")
    parser.add_argument("--input", type=str, default="../data/processed/bluetooth_training_data.json",
                       help="输入数据文件")
    parser.add_argument("--output", type=str, default="../data/processed/training_data.json",
                       help="输出数据文件")
    parser.add_argument("--augmentation-factor", type=float, default=0.3,
                       help="数据增强因子")
    parser.add_argument("--target-per-category", type=int, default=100,
                       help="每类别的目标样本数")

    args = parser.parse_args()

    # 加载或创建配置
    import json
    if os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        # 默认配置
        config = {
            'model_name': 'deepseek-ai/DeepSeek-Coder-V2-Lite-16B',
            'raw_data_path': args.input,
            'data_path': args.output,
            'data_augmentation_factor': args.augmentation_factor,
            'target_samples_per_category': args.target_per_category
        }

    # 添加命令行参数
    config['data_augmentation_factor'] = args.augmentation_factor
    config['target_samples_per_category'] = args.target_per_category
    config['raw_data_path'] = args.input
    config['data_path'] = args.output

    # 创建处理器
    processor = TrainingDataProcessor(config)

    # 执行处理
    success = processor.process()

    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()