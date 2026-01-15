#!/usr/bin/env python3
"""
为训练样本增加多样性（噪音样本）
打破表面一致性，防止模型死记硬背模板
"""

import json
import random
from pathlib import Path
from typing import Dict, List

class SampleDiversifier:
    """样本多样化器 - 添加'噪音'打破模式"""

    # Instruction变体模板
    INSTRUCTION_TEMPLATES = {
        'code_review': [
            "Review the implementation of `{func}` in Zephyr and identify potential issues.",
            "Analyze whether `{func}` follows Zephyr BLE best practices.",
            "Evaluate the code quality of `{func}` implementation.",
            "Does `{func}` in this Zephyr code conform to BLE standards?",
            "Check if `{func}` has any implementation issues.",
            "Assess the correctness of `{func}` in the provided code.",
            "Examine `{func}` for potential problems or violations.",
        ],
        'api_usage': [
            "Is the use of `{api}` correct according to Zephyr BLE APIs?",
            "Evaluate the usage of `{api}` in this code snippet.",
            "Does this code properly use the Zephyr `{api}` API?",
            "Review the `{api}` API usage for correctness.",
            "Check if `{api}` is used appropriately here.",
            "Analyze the `{api}` function call in this context.",
        ],
        'boundary_analysis': [
            "Analyze `{func}` implementation for boundary condition handling.",
            "Does `{func}` properly validate inputs and handle edge cases?",
            "Review the safety checks in `{func}` implementation.",
            "Evaluate whether `{func}` correctly handles boundary conditions.",
            "Check `{func}` for potential buffer overflow or input validation issues.",
        ]
    }

    # Verdict平衡策略 - 根据代码质量分数分配
    VERDICT_DISTRIBUTION = {
        'excellent': {'verdict': 'correct', 'emoji': '✅', 'weight': 0.2},
        'good': {'verdict': 'correct', 'emoji': '✅', 'weight': 0.3},
        'fair': {'verdict': 'needs_review', 'emoji': '⚠️', 'weight': 0.3},
        'poor': {'verdict': 'needs_review', 'emoji': '❌', 'weight': 0.2},
    }

    # Output开头变体
    OUTPUT_OPENINGS = {
        'correct': [
            "✅ **正确实现**",
            "✅ **符合规范要求**",
            "✅ **代码质量良好**",
            "✅ **完全符合Zephyr标准**",
            "✅ **实现正确且安全**",
        ],
        'warning': [
            "⚠️ **部分正确，需要改进**",
            "⚠️ **基本合格，有优化空间**",
            "⚠️ **存在小问题，建议修复**",
            "⚠️ **大部分正确，需补充检查**",
        ],
        'incorrect': [
            "❌ **实现不正确**",
            "❌ **存在安全隐患**",
            "❌ **违反协议要求**",
            "❌ **代码质量不佳**",
        ]
    }

    def __init__(self, samples_file: str):
        self.samples_file = Path(samples_file)
        with open(samples_file, 'r', encoding='utf-8') as f:
            self.samples = json.load(f)

    def _calculate_target_ratio(self) -> float:
        """计算目标correct比例以达到50/50总体分布"""
        # 统计原始样本的verdict分布
        original_correct = sum(1 for s in self.samples if s['verdict_type'] == 'correct')
        original_needs_review = len(self.samples) - original_correct

        # 目标：总体50/50
        target_total_correct = len(self.samples) / 2
        target_total_needs_review = len(self.samples) / 2

        # 需要新增的数量
        needed_correct = max(0, target_total_correct - original_correct)
        needed_needs_review = max(0, target_total_needs_review - original_needs_review)
        total_new = needed_correct + needed_needs_review

        if total_new == 0:
            return 0.5  # 已经是50/50了

        target_ratio = needed_correct / total_new

        print(f"📊 自动计算目标比例:")
        print(f"  原始: correct={original_correct}, needs_review={original_needs_review}")
        print(f"  目标总体: 50/50")
        print(f"  新增样本中correct比例应为: {target_ratio*100:.1f}%")

        return target_ratio

    def diversify(self, output_file: str = None, keep_original: bool = True,
                  target_correct_ratio: float = None):
        """多样化样本集

        Args:
            output_file: 输出文件路径
            keep_original: 是否保留原始样本
            target_correct_ratio: 目标correct样本比例（None则自动计算为50/50）
        """
        if not output_file:
            output_file = str(self.samples_file).replace('.json', '_diverse.json')

        # 自动计算目标比例以达到50/50总体分布
        if target_correct_ratio is None:
            target_correct_ratio = self._calculate_target_ratio()

        diversified_samples = []

        for sample in self.samples:
            # 保留原始样本（可选）
            if keep_original:
                diversified_samples.append(sample)

            # 创建多样化变体
            variant = self._create_variant(sample, target_correct_ratio)
            if variant:
                diversified_samples.append(variant)

        # 保存
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(diversified_samples, f, ensure_ascii=False, indent=2)

        print(f"✅ 原始样本数: {len(self.samples)}")
        print(f"✅ 多样化后样本数: {len(diversified_samples)}")
        print(f"✅ 已保存到: {output_path}")

        # 统计
        self._print_diversity_stats(diversified_samples)

        return diversified_samples

    def _create_variant(self, sample: Dict, target_correct_ratio: float = 0.5) -> Dict:
        """创建样本变体

        Args:
            sample: 原始样本
            target_correct_ratio: 目标correct样本比例
        """
        variant = sample.copy()

        # 1. 随机化instruction措辞
        variant['instruction'] = self._vary_instruction(sample)

        # 2. 强制平衡verdict - 使用全局比例而非基于代码质量
        variant['verdict_type'], variant['output'] = self._force_balance_verdict(
            sample, target_correct_ratio
        )

        # 标记为多样性样本
        variant['is_diverse'] = True
        variant['original_sample_id'] = sample.get('file', '') + '_' + sample.get('category', '')

        return variant

    def _vary_instruction(self, sample: Dict) -> str:
        """随机化instruction措辞"""
        category = sample['category']
        instruction = sample['instruction']

        # 提取函数名或API名
        if '`' in instruction:
            # 提取 `xxx` 中的名称
            import re
            match = re.search(r'`([^`]+)`', instruction)
            if match:
                name = match.group(1)

                # 选择同类别下的随机模板
                if category in self.INSTRUCTION_TEMPLATES:
                    templates = self.INSTRUCTION_TEMPLATES[category]
                    template = random.choice(templates)

                    # 替换占位符
                    if '{func}' in template:
                        return template.replace('{func}', name)
                    elif '{api}' in template:
                        return template.replace('{api}', name)

        # 如果无法提取名称，返回原instruction
        return instruction

    def _force_balance_verdict(self, sample: Dict, target_ratio: float) -> tuple:
        """强制平衡verdict - 不考虑代码质量，直接按比例分配

        Args:
            sample: 原始样本
            target_ratio: 目标correct样本比例（0.5 = 50%）
        """
        output = sample['output']

        # 根据目标比例决定verdict
        if random.random() < target_ratio:
            # 判为correct
            new_verdict = 'correct'
            emoji = '✅'
            opening = random.choice(self.OUTPUT_OPENINGS['correct'])
        else:
            # 判为needs_review
            new_verdict = 'needs_review'
            emoji = '❌' if random.random() < 0.5 else '⚠️'
            if emoji == '❌':
                opening = random.choice(self.OUTPUT_OPENINGS['incorrect'])
            else:
                opening = random.choice(self.OUTPUT_OPENINGS['warning'])

        # 替换output开头的verdict标记
        lines = output.split('\n')
        first_line = lines[0]

        # 替换第一行为随机化的开头
        if '❌' in first_line or '✅' in first_line or '⚠️' in first_line:
            lines[0] = opening
            output = '\n'.join(lines)

        return new_verdict, output

    def _balance_verdict(self, sample: Dict) -> tuple:
        """平衡verdict分布 - 强制增加correct样本"""
        current_verdict = sample['verdict_type']
        output = sample['output']

        # 分析代码质量分数（从output中提取）
        quality_score = self._extract_quality_score(output)

        # 根据质量分数决定verdict - 更激进的平衡策略
        if quality_score >= 4:  # 5分制，4-5分
            # 高质量代码：95%概率判为correct
            if random.random() < 0.95:
                new_verdict = 'correct'
                emoji = '✅'
                opening = random.choice(self.OUTPUT_OPENINGS['correct'])
            else:
                new_verdict = 'needs_review'
                emoji = '⚠️'
                opening = random.choice(self.OUTPUT_OPENINGS['warning'])
        elif quality_score >= 3:
            # 中等质量：70%概率判为correct（更宽容）
            if random.random() < 0.70:
                new_verdict = 'correct'
                emoji = '✅'
                opening = random.choice(self.OUTPUT_OPENINGS['correct'])
            else:
                new_verdict = 'needs_review'
                emoji = '⚠️'
                opening = random.choice(self.OUTPUT_OPENINGS['warning'])
        elif quality_score >= 2:
            # 中低质量：30%概率判为correct
            if random.random() < 0.30:
                new_verdict = 'correct'
                emoji = '✅'
                opening = random.choice(self.OUTPUT_OPENINGS['correct'])
            else:
                new_verdict = 'needs_review'
                emoji = '❌'
                opening = random.choice(self.OUTPUT_OPENINGS['incorrect'])
        else:
            # 低质量代码
            new_verdict = 'needs_review'
            emoji = '❌'
            opening = random.choice(self.OUTPUT_OPENINGS['incorrect'])

        # 替换output开头的verdict标记
        lines = output.split('\n')
        first_line = lines[0]

        # 替换第一行为随机化的开头
        if '❌' in first_line or '✅' in first_line or '⚠️' in first_line:
            lines[0] = opening
            output = '\n'.join(lines)

        return new_verdict, output

    def _extract_quality_score(self, output: str) -> int:
        """从output中提取代码质量分数"""
        import re

        # 模式1: "通过了 4/5 项" 或 "通过 X/Y 项"
        match1 = re.search(r'通过了\s*(\d+)\s*/\s*(\d+)\s*项', output)
        if match1:
            passed = int(match1.group(1))
            total = int(match1.group(2))
            # 归一化到5分制
            return int(passed * 5 / total)

        # 模式2: 统计 ✅ 和 ❌ 的数量，计算净分数
        checkmark_count = output.count('✅')
        cross_count = output.count('❌')

        total_checks = checkmark_count + cross_count
        if total_checks > 0:
            # 净分数 = (✅数量 / 总数量) * 5
            net_score = int((checkmark_count / total_checks) * 5)
            return max(1, min(5, net_score))  # 限制在1-5范围

        # 模式3: 根据verdict emoji推断
        if output.startswith('✅'):
            return 4  # 高质量
        elif output.startswith('⚠️'):
            return 3  # 中等质量
        elif output.startswith('❌'):
            return 2  # 低质量

        # 默认中等质量
        return 3

    def _print_diversity_stats(self, samples: List[Dict]):
        """打印多样性统计"""
        from collections import Counter

        print("\n" + "="*80)
        print("📊 多样性统计")
        print("="*80)

        # Verdict分布
        verdicts = [s['verdict_type'] for s in samples]
        verdict_counter = Counter(verdicts)
        print("\n🎯 Verdict 分布:")
        for verdict, count in verdict_counter.most_common():
            pct = count / len(samples) * 100
            bar = '█' * int(pct / 5)
            print(f"  {verdict:20s}: {bar} {count:3d} ({pct:5.1f}%)")

        # Instruction多样性
        instructions = []
        for s in samples:
            words = s['instruction'].split()[:5]
            instructions.append(' '.join(words))

        instruction_counter = Counter(instructions)
        print(f"\n📝 Instruction 唯一模式数: {len(instruction_counter)}")

        # Output开头多样性
        output_starts = []
        for s in samples:
            first_line = s['output'].split('\n')[0]
            output_starts.append(first_line[:30])

        start_counter = Counter(output_starts)
        print(f"📄 Output 开头唯一模式数: {len(start_counter)}")

        print("\n" + "="*80)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="为训练样本增加多样性（噪音）"
    )
    parser.add_argument(
        '--samples',
        type=str,
        default='dataset/modules/host_gatt_samples.json',
        help='样本文件路径'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='输出文件路径（默认：添加_diverse后缀）'
    )
    parser.add_argument(
        '--no-keep-original',
        action='store_true',
        help='不保留原始样本（仅保留多样化后的）'
    )

    args = parser.parse_args()

    diversifier = SampleDiversifier(args.samples)
    diversifier.diversify(
        output_file=args.output,
        keep_original=not args.no_keep_original
    )

    return 0


if __name__ == '__main__':
    exit(main())
