#!/usr/bin/env python3
"""
训练样本质量检验脚本
检查生成的JSON样本是否符合判断型训练的要求
"""

import json
import sys
from pathlib import Path
from typing import Dict, List
from collections import defaultdict, Counter
import re

class SampleQualityChecker:
    """样本质量检验器"""

    # 质量标准权重
    QUALITY_WEIGHTS = {
        'has_verdict': 0.25,           # 是否有明确结论（❌/✅/⚠️）
        'is_judgment': 0.25,           # 是否为判断型（非代码生成）
        'has_reasoning': 0.20,         # 是否有详细理由
        'has_evidence': 0.10,          # 是否有依据（协议/源码）
        'completeness': 0.10,          # 字段完整性
        'content_length': 0.10,        # 内容长度
    }

    def __init__(self):
        self.results = {
            'summary': {},
            'modules': {},
            'issues': defaultdict(list),
            'statistics': {}
        }

    def check_samples_file(self, samples_file: str) -> Dict:
        """检查单个样本文件"""
        print(f"\n{'='*80}")
        print(f"📋 检查文件: {samples_file}")
        print(f"{'='*80}\n")

        try:
            with open(samples_file, 'r', encoding='utf-8') as f:
                samples = json.load(f)
        except Exception as e:
            print(f"❌ 无法读取文件: {e}")
            return {'error': str(e)}

        if not isinstance(samples, list):
            print(f"❌ 文件格式错误：应该是数组，实际是 {type(samples)}")
            return {'error': '格式错误'}

        print(f"✅ 样本总数: {len(samples)}\n")

        # 检查每个样本
        module_results = []
        quality_scores = []

        for i, sample in enumerate(samples):
            score, issues = self._check_single_sample(sample, i)
            quality_scores.append(score)

            for issue in issues:
                self.results['issues'][issue['type']].append({
                    'sample_index': i,
                    'module': sample.get('module', 'unknown'),
                    **issue
                })

            module_results.append({
                'index': i,
                'score': score,
                'issues': len(issues)
            })

        # 统计
        self._calculate_statistics(samples, quality_scores, module_results)

        return {
            'file': samples_file,
            'total_samples': len(samples),
            'module_results': module_results,
            'statistics': self.results['statistics']
        }

    def _check_single_sample(self, sample: Dict, index: int) -> tuple:
        """检查单个样本，返回(分数, 问题列表)"""
        score = 0.0
        issues = []

        # 1. 检查字段完整性
        required_fields = ['instruction', 'output', 'category', 'difficulty', 'verdict_type']
        missing_fields = [f for f in required_fields if f not in sample]

        if missing_fields:
            issues.append({
                'type': 'missing_fields',
                'severity': 'critical',
                'message': f'缺少字段: {missing_fields}'
            })
        else:
            score += self.QUALITY_WEIGHTS['completeness']

        # 2. 检查是否为判断型（instruction）
        instruction = sample.get('instruction', '')
        if self._is_judgment_instruction(instruction):
            score += self.QUALITY_WEIGHTS['is_judgment']
        else:
            issues.append({
                'type': 'not_judgment',
                'severity': 'high',
                'message': f'instruction不是判断型: "{instruction[:50]}..."'
            })

        # 3. 检查output是否有明确结论
        output = sample.get('output', '')
        verdict_info = self._check_verdict_in_output(output)
        if verdict_info['has_verdict']:
            score += self.QUALITY_WEIGHTS['has_verdict']
        else:
            issues.append({
                'type': 'no_verdict',
                'severity': 'medium',
                'message': 'output缺少明确结论（❌/✅/⚠️）'
            })

        # 4. 检查是否有详细理由
        if self._has_detailed_reasoning(output):
            score += self.QUALITY_WEIGHTS['has_reasoning']
        else:
            issues.append({
                'type': 'no_reasoning',
                'severity': 'medium',
                'message': '理由不够详细（<200字符）'
            })

        # 5. 检查是否有依据（引用协议/源码）
        if self._has_evidence(output):
            score += self.QUALITY_WEIGHTS['has_evidence']
        else:
            issues.append({
                'type': 'no_evidence',
                'severity': 'low',
                'message': '缺少依据（协议/源码引用）'
            })

        # 6. 检查内容长度
        if len(output) >= 300:
            score += self.QUALITY_WEIGHTS['content_length']
        else:
            issues.append({
                'type': 'too_short',
                'severity': 'low',
                'message': f'output过短 ({len(output)} < 300字符)'
            })

        # 7. 检查是否基于真实代码
        if sample.get('source') == 'zephyr_code':
            score += 0.05  # 额外加分

        return min(score, 1.0), issues

    def _is_judgment_instruction(self, instruction: str) -> bool:
        """判断是否为判断型instruction"""
        # 判断型关键词
        judgment_patterns = [
            r'是否正确',
            r'是否合适',
            r'是否必须',
            r'是否可以',
            r'是否需要',
            r'是否.*合规',
            r'是否.*违反',
            r'分析.*问题',
            r'检查.*边界',
            r'判断.*实现',
            r'evaluate|review|check',
            r'correct|incorrect|safe|unsafe'
        ]

        instruction_lower = instruction.lower()

        # 排除代码生成型
        code_gen_patterns = [
            r'^实现',
            r'^编写',
            r'^生成',
            r'^创建',
            r'^设计',
        ]

        for pattern in code_gen_patterns:
            if re.match(pattern, instruction):
                return False

        # 检查判断型关键词
        for pattern in judgment_patterns:
            if re.search(pattern, instruction_lower):
                return True

        return False

    def _check_verdict_in_output(self, output: str) -> Dict:
        """检查output中是否有明确的结论标记"""
        verdict_info = {
            'has_verdict': False,
            'verdicts': []
        }

        # 改进的正则表达式 - 匹配emoji后跟任意内容（包括**加粗**）
        verdict_patterns = [
            (r'❌', 'incorrect'),
            (r'✅', 'correct'),
            (r'⚠️', 'conditional'),
        ]

        for pattern, verdict_type in verdict_patterns:
            if re.search(pattern, output):
                verdict_info['has_verdict'] = True
                verdict_info['verdicts'].append(verdict_type)
                break  # 找到一个标记就够了

        return verdict_info

    def _has_detailed_reasoning(self, output: str) -> bool:
        """检查是否有详细理由"""
        return len(output) >= 200

    def _has_evidence(self, output: str) -> bool:
        """检查是否有依据（引用协议、源码、文档）"""
        evidence_patterns = [
            r'BLE Spec',
            r'Bluetooth Core Spec',
            r'Zephyr.*实现',
            r'规范依据',
            r'源文件.*:',
            r'源码参考',
            r'参考代码',
            r'协议依据',
            r'协议规范',
            r'Zephyr API',
            r'源码参考',
        ]

        for pattern in evidence_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return True

        return False

    def _calculate_statistics(self, samples: List, scores: List[float], results: List[Dict]):
        """计算统计信息"""
        scores_array = [s for s in scores if s >= 0]

        if not scores_array:
            self.results['statistics'] = {'error': '没有有效样本'}
            return

        self.results['statistics'] = {
            'total_samples': len(samples),
            'avg_score': sum(scores_array) / len(scores_array),
            'min_score': min(scores_array),
            'max_score': max(scores_array),
            'quality_distribution': self._get_distribution(scores_array)
        }

    def _get_distribution(self, scores: List[float]) -> Dict:
        """获取质量分布"""
        distribution = {
            'excellent (>=0.9)': 0,
            'good (0.7-0.9)': 0,
            'fair (0.5-0.7)': 0,
            'poor (0.3-0.5)': 0,
            'bad (<0.3)': 0
        }

        for score in scores:
            if score >= 0.9:
                distribution['excellent (>=0.9)'] += 1
            elif score >= 0.7:
                distribution['good (0.7-0.9)'] += 1
            elif score >= 0.5:
                distribution['fair (0.5-0.7)'] += 1
            elif score >= 0.3:
                distribution['poor (0.3-0.5)'] += 1
            else:
                distribution['bad (<0.3)'] += 1

        return distribution

    def generate_report(self, output_file: str = None):
        """生成质量报告"""
        if output_file:
            out_path = Path(output_file)
        else:
            out_path = Path('dataset/quality_report.txt')

        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, 'w', encoding='utf-8') as f:
            # 写入报告
            f.write("="*80 + "\n")
            f.write("📊 样本质量检验报告\n")
            f.write("="*80 + "\n\n")

            # 统计摘要
            if 'statistics' in self.results and self.results['statistics']:
                stats = self.results['statistics']
                f.write("## 📈 统计摘要\n\n")
                f.write(f"总样本数: {stats.get('total_samples', 0)}\n")
                if 'avg_score' in stats:
                    f.write(f"平均质量分: {stats['avg_score']:.2f}/1.00\n")
                    f.write(f"最低分: {stats['min_score']:.2f}\n")
                    f.write(f"最高分: {stats['max_score']:.2f}\n\n")

                # 质量分布
                if 'quality_distribution' in stats:
                    f.write("### 质量分布\n\n")
                    for level, count in stats['quality_distribution'].items():
                        pct = count / stats['total_samples'] * 100 if stats['total_samples'] > 0 else 0
                        bar = '█' * int(pct / 5)
                        f.write(f"{level:20s}: {bar} {count} ({pct:.1f}%)\n")

                f.write("\n")

            # 问题分类统计
            if self.results['issues']:
                f.write("## ⚠️ 问题分类统计\n\n")
                for issue_type, issues in self.results['issues'].items():
                    f.write(f"### {issue_type}: {len(issues)} 个\n")

                    # 按严重程度分组
                    severity_count = defaultdict(int)
                    for issue in issues:
                        severity_count[issue['severity']] += 1

                    for severity in ['critical', 'high', 'medium', 'low']:
                        if severity_count[severity] > 0:
                            f.write(f"  - {severity}: {severity_count[severity]}\n")

                f.write("\n")

            # 具体问题示例
            f.write("## 🔍 问题示例（每个类型最多5个）\n\n")
            shown_examples = set()

            for issue_type, issues in self.results['issues'].items():
                f.write(f"### {issue_type}\n\n")

                count = 0
                for issue in issues:
                    if count >= 5:
                        break

                    # 创建唯一标识
                    example_key = f"{issue['module']}_{issue.get('message', '')[:30]}"
                    if example_key in shown_examples:
                        continue

                    shown_examples.add(example_key)
                    count += 1

                    f.write(f"**示例 {count}**\n")
                    f.write(f"  样本#{issue['sample_index']}\n")
                    f.write(f"  模块: {issue['module']}\n")
                    f.write(f"  严重性: {issue['severity']}\n")
                    f.write(f"  问题: {issue['message']}\n")

                    # 如果有instruction，显示部分内容
                    if 'instruction' in issue:
                        inst = issue['instruction'][:100]
                        f.write(f"  Instruction: \"{inst}...\"\n")

                    f.write("\n")

            # 改进建议
            f.write("="*80 + "\n")
            f.write("## 💡 改进建议\n\n")
            f.write(self._generate_recommendations())

            f.write("\n" + "="*80 + "\n")

        print(f"\n✅ 质量报告已保存到: {out_path}")
        print(f"   可以查看报告了解详细问题和改进建议")

    def _generate_recommendations(self) -> str:
        """生成改进建议"""
        recommendations = []

        # 基于问题类型生成建议
        issue_types = set(self.results['issues'].keys())

        if 'not_judgment' in issue_types:
            recommendations.append("""
**问题：样本不是判断型**
   - 当前：instruction 是"实现xxx"
   - 建议：改为"xxx实现是否正确？为什么？"
   - 目标：让模型学习判断而非生成
""")

        if 'no_verdict' in issue_types:
            recommendations.append("""
**问题：缺少明确结论**
   - 当前：output 中没有 ❌/✅/⚠️ 标记
   - 建议：在 output 开头添加明确结论
   - 示例：❌ **不正确**\n\n**问题分析：**...
""")

        if 'no_reasoning' in issue_types:
            recommendations.append("""
**问题：理由不够详细**
   - 当前：output < 200字符
   - 建议：展开分析，至少200-500字符
   - 包括：问题分析、代码示例、正确做法
""")

        if 'no_evidence' in issue_types:
            recommendations.append("""
**问题：缺少依据**
   - 当前：没有引用协议或源码
   - 建议：添加引用
   - 示例：- 参考：Bluetooth Core Spec Vol 3, Part F
           - 源码：`subsys/bluetooth/host/gatt.c:xxx`
""")

        if 'missing_fields' in issue_types:
            recommendations.append("""
**问题：缺少必需字段**
   - 当前：缺少 module, category, difficulty, verdict_type
   - 建议：确保包含所有必需字段
   - 参考：README.md 中的样本格式
""")

        if 'too_short' in issue_types:
            recommendations.append("""
**问题：output过短**
   - 当前：output < 300字符
   - 建议：扩展到至少500-1000字符
   - 包含：详细分析、代码示例、修复方案
""")

        if not recommendations:
            return """
**整体建议：**
样本质量良好！可以继续使用当前生成策略。

下一步：
1. 增加样本数量（每个模块50-100个）
2. 扩展到更多模块
3. 开始训练模型
"""

        return '\n'.join(recommendations)


def check_all_modules(modules_dir: str = 'dataset/modules') -> Dict:
    """检查所有模块的样本"""
    checker = SampleQualityChecker()
    modules_path = Path(modules_dir)

    print(f"\n{'='*80}")
    print(f"🔍 检查所有模块的样本质量")
    print(f"{'='*80}\n")

    if not modules_path.exists():
        print(f"❌ 目录不存在: {modules_dir}")
        return {}

    # 找到所有样本文件
    sample_files = list(modules_path.glob('*_samples.json'))

    if not sample_files:
        print(f"❌ 没有找到样本文件: {modules_dir}/*_samples.json")
        return {}

    print(f"✅ 找到 {len(sample_files)} 个样本文件\n")

    all_results = {}

    for sample_file in sorted(sample_files):
        module_name = sample_file.stem.replace('_samples', '')
        print(f"\n处理模块: {module_name}")

        result = checker.check_samples_file(str(sample_file))

        # 保存结果
        all_results[module_name] = result

        # 显示摘要
        if 'statistics' in result:
            stats = result['statistics']
            print(f"  样本数: {stats.get('total_samples', 0)}")
            if 'avg_score' in stats:
                print(f"  平均分: {stats['avg_score']:.2f}")
            print(f"  问题数: {sum(len(v) for v in checker.results['issues'].values())}")

    # 生成综合报告
    checker.generate_report('dataset/quality_report_all_modules.txt')

    return all_results


def check_specific_modules(modules: List[str], modules_dir: str = 'dataset/modules'):
    """检查指定模块的样本"""
    checker = SampleQualityChecker()
    modules_path = Path(modules_dir)

    print(f"\n{'='*80}")
    print(f"🔍 检查指定模块: {', '.join(modules)}")
    print(f"{'='*80}\n")

    all_results = {}

    for module_name in modules:
        sample_file = modules_path / f"{module_name}_samples.json"

        if not sample_file.exists():
            print(f"⚠️ 模块 {module_name} 的样本文件不存在")
            continue

        print(f"\n处理模块: {module_name}")
        result = checker.check_samples_file(str(sample_file))
        all_results[module_name] = result

        # 显示摘要
        if 'statistics' in result:
            stats = result['statistics']
            print(f"  样本数: {stats.get('total_samples', 0)}")
            if 'avg_score' in stats:
                print(f"  平均分: {stats['avg_score']:.2f}")

    # 生成报告
    checker.generate_report(f'dataset/quality_report_{"_".join(modules)}.txt')

    return all_results


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="检查训练样本质量，评估是否符合判断型训练要求",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 检查单个模块
  python3 %(prog)s --module host_gatt

  # 检查多个模块
  python3 %(prog)s --modules host_gatt host_conn host_l2cap

  # 检查所有模块
  python3 %(prog)s --all
        """
    )

    parser.add_argument(
        '--module',
        type=str,
        help='检查单个模块'
    )
    parser.add_argument(
        '--modules',
        nargs='+',
        help='检查多个模块（空格分隔）'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='检查所有模块'
    )
    parser.add_argument(
        '--modules-dir',
        type=str,
        default='dataset/modules',
        help='模块样本目录（默认：dataset/modules）'
    )

    args = parser.parse_args()

    # 执行检查
    if args.all:
        check_all_modules(args.modules_dir)
    elif args.modules:
        check_specific_modules(args.modules, args.modules_dir)
    elif args.module:
        check_specific_modules([args.module], args.modules_dir)
    else:
        print("❌ 请指定要检查的模块")
        print("  --module <name>   检查单个模块")
        print("  --modules <n1> <n2> ...  检查多个模块")
        print("  --all             检查所有模块")
        return 1

    print("\n✅ 质量检验完成！")
    print("💡 查看报告文件了解详细问题和改进建议")

    return 0


if __name__ == '__main__':
    exit(main())
