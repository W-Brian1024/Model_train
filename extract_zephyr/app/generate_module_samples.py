#!/usr/bin/env python3
"""
基于真实 Zephyr 源码生成判断型训练样本
从模块分析结果中获取文件列表，分析源码，生成样本
支持样本多样化和自动分割（65:20:15）
"""

import json
import re
import random
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict, Counter
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CodeFeatureDetector:
    """代码特征检测器 - 改进版，更准确的模式匹配"""

    @staticmethod
    def has_connection_check(code: str) -> bool:
        """检测连接检查 - 改进版"""
        # 精确匹配：if (!conn) 或 if (conn == NULL) 等
        patterns = [
            r'if\s*\(\s*!\s*conn\s*\)',
            r'if\s*\(\s*conn\s*==\s*NULL\s*\)',
            r'if\s*\(\s*!?conn\s*&&',
            r'if\s*\(\s*!?conn\s*\|\|',
        ]
        return any(re.search(pattern, code) for pattern in patterns)

    @staticmethod
    def has_null_pointer_check(code: str) -> bool:
        """检测空指针检查"""
        patterns = [
            r'if\s*\(\s*!\s*\w+\s*\)',          # if (!ptr)
            r'if\s*\(\s*\w+\s*==\s*NULL\s*\)',  # if (ptr == NULL)
            r'if\s*\(\s*NULL\s*==\s*\w+\s*\)',  # if (NULL == ptr)
            r'if\s*\(\s*!\s*\w+\s*&&',          # if (!ptr &&
        ]
        return any(re.search(pattern, code) for pattern in patterns)

    @staticmethod
    def has_boundary_check(code: str) -> bool:
        """检测边界检查"""
        patterns = [
            r'if\s*\([^)]*<[^)]*\)',              # if (x < max)
            r'if\s*\([^)]*>[^)]*\)',              # if (x > min)
            r'if\s*\([^)]*<=[^)]*\)',             # if (x <= max)
            r'if\s*\([^)]*>=[^)]*\)',             # if (x >= min)
            r'if\s*\([^)]*&&\s*[^)]*[<>]=?',   # if (x && x < max)
        ]
        return any(re.search(pattern, code) for pattern in patterns)

    @staticmethod
    def has_error_handling(code: str) -> bool:
        """检测错误处理"""
        # 检查返回值是否被检查
        patterns = [
            r'if\s*\([^)]*err[^)]*\)',           # if (err ...)
            r'if\s*\([^)]*ret[^)]*\)',           # if (ret ...)
            r'return\s+-(E|EN)',
            r'BT_GATT_ERR\s*\(',
        ]
        return any(re.search(pattern, code) for pattern in patterns)

    @staticmethod
    def has_buffer_overflow_protection(code: str) -> bool:
        """检测缓冲区溢出保护"""
        patterns = [
            r'memcpy\s*\([^,]+,\s*[^,]+,\s*min\s*\(',
            r'snprintf\s*\(',
            r'strncpy\s*\(',
            r'if\s*\([^)]*len\s*>\s*[^)]*\)',
            r'if\s*\([^)]*size\s*>\s*[^)]*\)',
        ]
        return any(re.search(pattern, code) for pattern in patterns)

    @staticmethod
    def has_ccc_check(code: str) -> bool:
        """检测CCC（Client Characteristic Configuration）检查"""
        patterns = [
            r'ccc.*flags',
            r'BT_GATT_CCC',
            r'notify.*enabled',
            r'config.*notify',
        ]
        code_lower = code.lower()
        return any(re.search(pattern.lower(), code_lower) for pattern in patterns)


class ZephyrCodeAnalyzer:
    """Zephyr 代码分析器 - 从源码中提取信息"""

    def __init__(self, zephyr_path: str):
        self.zephyr_path = Path(zephyr_path)
        self.detector = CodeFeatureDetector()  # 使用改进的检测器

    def extract_functions_from_file(self, file_path: str) -> List[Dict]:
        """从文件中提取函数定义（改进版）"""
        full_path = self.zephyr_path / file_path
        if not full_path.exists():
            return []

        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"无法读取文件 {file_path}: {e}")
            return []

        functions = []

        # 改进的正则表达式 - 更严格的函数定义匹配
        # 支持更多C语法特性：指针、宏、复杂类型等
        patterns = [
            # 标准函数定义: int func_name(type param, ...)
            r'(?:static\s+)?(?:inline\s+)?(?:const\s+)?(?:struct\s+\w+\s+)?(?:\w+\s+(?:\*+\s*)*)+(\w+)\s*\([^)]*\)\s*\{',
            # 函数指针: int (*func_name)(...)
            r'(?:static\s+)?(?:const\s+)?(?:\w+\s+)+?\(\**\s*(\w+)\s*\)\s*\([^)]*\)\s*\{',
        ]

        # 跳过的函数（系统函数、标准库函数等）
        skip_functions = {
            'printk', 'memcpy', 'memset', 'strlen', 'strcmp', 'strncmp',
            'strcpy', 'strncpy', 'sprintf', 'snprintf', 'vsprintf',
            'malloc', 'free', 'calloc', 'realloc',
            'printf', 'fprintf', 'scanf', 'sscanf',
        }

        for pattern in patterns:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                func_name = match.group(1)

                # 跳过特定函数
                if not func_name or func_name in skip_functions:
                    continue

                # 跳过纯小写的内部函数（通常是宏或特殊定义）
                if func_name.islower() and len(func_name) < 3:
                    continue

                # 获取函数体（改进版）
                start_pos = match.start()
                brace_start = content.find('{', start_pos)

                if brace_start == -1:
                    continue

                # 提取函数体，最多500字符
                brace_end = self._find_matching_brace(content, brace_start)
                if brace_end == -1:
                    func_body = content[brace_start:brace_start+500]
                else:
                    func_body = content[brace_start:min(brace_end, brace_start+500)]

                # 计算函数复杂度（用于难度分级）
                complexity = self._calculate_function_complexity(func_body)

                functions.append({
                    'name': func_name,
                    'file': file_path,
                    'body': func_body,
                    'start': start_pos,
                    'complexity': complexity
                })

        return functions

    def _calculate_function_complexity(self, func_body: str) -> Dict:
        """计算函数复杂度（用于难度分级）"""
        # 代码长度
        code_length = len(func_body)

        # 嵌套深度（括号嵌套）
        max_nesting = 0
        current_nesting = 0
        for char in func_body:
            if char == '{':
                current_nesting += 1
                max_nesting = max(max_nesting, current_nesting)
            elif char == '}':
                current_nesting = max(0, current_nesting - 1)

        # 控制流关键字数量
        control_flow_count = sum([
            func_body.count('if '),
            func_body.count('for '),
            func_body.count('while '),
            func_body.count('switch'),
            func_body.count('return')
        ])

        # API调用次数
        api_call_count = len(re.findall(r'bt_\w+\s*\(', func_body))

        return {
            'length': code_length,
            'nesting_depth': max_nesting,
            'control_flow_count': control_flow_count,
            'api_call_count': api_call_count,
            'score': code_length / 100 + max_nesting * 2 + control_flow_count * 0.5
        }

    def _find_matching_brace(self, content: str, start: int, max_search: int = 2000) -> int:
        """查找匹配的右括号"""
        count = 0
        for i in range(start, min(start + max_search, len(content))):
            if content[i] == '{':
                count += 1
            elif content[i] == '}':
                count -= 1
                if count == 0:
                    return i
        return -1

    def extract_api_usage_patterns(self, file_path: str, api_prefixes: List[str]) -> List[Dict]:
        """提取API使用模式"""
        full_path = self.zephyr_path / file_path
        if not full_path.exists():
            return []

        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return []

        patterns = []

        for prefix in api_prefixes:
            # 查找所有使用此API的地方
            regex = rf'.{{0,200}}{re.escape(prefix)}[\w_]+[^;]*;'
            matches = re.finditer(regex, content, re.MULTILINE | re.DOTALL)

            for match in matches:
                code_snippet = match.group(0).strip()

                if len(code_snippet) < 50 or len(code_snippet) > 500:
                    continue

                # 提取上下文
                patterns.append({
                    'api': prefix,
                    'usage': code_snippet,
                    'file': file_path
                })

                if len(patterns) >= 20:  # 限制数量
                    break

        return patterns

    def extract_structs_and_enums(self, file_path: str) -> List[Dict]:
        """提取结构体和枚举定义"""
        full_path = self.zephyr_path / file_path
        if not full_path.exists():
            return []

        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return []

        definitions = []

        # 提取结构体定义
        struct_pattern = r'struct\s+(\w+)\s*\{[^}]{50,500}\}\s*(?:\w+\s*;)?\s*(?:__packed)?;'
        for match in re.finditer(struct_pattern, content, re.MULTILINE | re.DOTALL):
            struct_def = match.group(0)
            struct_name = match.group(1)

            if len(struct_def) < 100 or len(struct_def) > 800:
                continue

            definitions.append({
                'type': 'struct',
                'name': struct_name,
                'definition': struct_def,
                'file': file_path
            })

        # 提取枚举定义
        enum_pattern = r'enum\s+\{[^}]{30,500}\}\s*(\w+)\s*;'
        for match in re.finditer(enum_pattern, content, re.MULTILINE | re.DOTALL):
            enum_def = match.group(0)

            definitions.append({
                'type': 'enum',
                'definition': enum_def,
                'file': file_path
            })

        return definitions[:10]  # 最多返回10个


class JudgmentSampleGenerator:
    """判断型样本生成器 - 基于真实代码"""

    def __init__(self, zephyr_path: str, module_analysis_file: str, debug: bool = False):
        self.zephyr_path = Path(zephyr_path)
        self.analyzer = ZephyrCodeAnalyzer(zephyr_path)
        self.module_data = self._load_module_analysis(module_analysis_file)
        self.debug = debug  # Debug模式开关

        if self.debug:
            logger.info("🐛 Debug模式已启用 - 将显示详细日志")

    def _filter_module_files(self, module_id: str, files: List[str]) -> List[str]:
        """过滤文件，只保留模块相关的文件

        Args:
            module_id: 模块ID (如 'host_gatt')
            files: 文件路径列表

        Returns:
            过滤后的文件列表
        """
        filtered_files = []

        # 定义模块相关的关键词映射
        module_keywords = {
            'host_gatt': ['gatt', 'attribute', 'char', 'service', 'descriptor', 'ccc', 'value'],
            'host_att': ['att', 'attribute', 'handle', 'permission', 'mtu', 'opcode'],
            'host_l2cap': ['l2cap', 'chan', 'coc', 'le', 'ecred', 'sdu'],
            'host_conn': ['conn', 'connect', 'disconnect', 'pairing', 'encryption', 'bond'],
            'host_smp': ['smp', 'pairing', 'security', 'tk', 'irk', 'csrk', 'ltk'],
            'host_adv': ['adv', 'advertiser', 'ad', 'ad_data', 'scan', 'dirc'],
            'host_scan': ['scan', 'scanner', 'scan_data', 'adv'],
            'host_hci': ['hci', 'h_vs', 'cmd', 'event'],
            'ctrl_ll': ['ll', 'ctrl', 'radio', 'phy', 'tick'],
            'ctrl_hci': ['hci', 'vendor'],
        }

        # 获取当前模块的关键词
        keywords = module_keywords.get(module_id, [])

        if not keywords:
            # 如果没有定义关键词，保留所有文件
            if self.debug:
                logger.warning(f"  ⚠️ 模块 {module_id} 没有定义关键词，将处理所有文件")
            return files

        # 过滤文件
        for file_path in files:
            file_name = file_path.lower()

            # 检查文件是否包含任何模块关键词
            if any(keyword in file_name for keyword in keywords):
                filtered_files.append(file_path)
            elif 'include' in file_name:
                # 头文件也可能包含重要内容
                filtered_files.append(file_path)

        if self.debug:
            logger.info(f"  📁 文件过滤: {len(files)} → {len(filtered_files)}")
            logger.info(f"     关键词: {', '.join(keywords)}")

        return filtered_files

    def _load_module_analysis(self, analysis_file: str) -> Dict:
        """加载模块分析结果"""
        with open(analysis_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def generate_for_module(
        self, module_id: str, num_samples: int = 50,
        include_cross_module: bool = False, cross_module_targets: List[str] = None
    ) -> List[Dict]:
        """为指定模块生成样本"""
        if module_id not in self.module_data["modules"]:
            logger.error(f"模块不存在: {module_id}")
            return []

        module_info = self.module_data["modules"][module_id]
        logger.info(f"🎯 为模块 {module_info['info']['name']} 生成 {num_samples} 个样本")

        samples = []

        # 1. 从源文件中提取函数，生成函数分析样本（60%）
        target_func_samples = int(num_samples * 0.6)
        functions_samples = self._generate_function_analysis_samples(
            module_id, module_info, target_func_samples
        )
        samples.extend(functions_samples)
        logger.info(f"  📝 函数分析样本: 期望 {target_func_samples}, 实际 {len(functions_samples)}")

        # 2. 从API使用中生成判断样本（40%）
        target_api_samples = num_samples - len(samples)
        api_samples = self._generate_api_usage_samples(
            module_id, module_info, target_api_samples
        )
        samples.extend(api_samples)
        logger.info(f"  🔧 API使用样本: 期望 {target_api_samples}, 实际 {len(api_samples)}")

        # 3. 如果还不够，尝试生成更多样本
        if len(samples) < num_samples:
            remaining = num_samples - len(samples)
            logger.warning(f"⚠️ 样本数量不足 {len(samples)}/{num_samples}，尝试生成更多...")

            # 尝试从更多文件生成
            additional_samples = self._generate_additional_samples(
                module_id, module_info, remaining
            )
            samples.extend(additional_samples)
            logger.info(f"  ➕ 额外样本: {len(additional_samples)}")

        # 4. 如果还是不够，重复使用现有样本创建变体
        if len(samples) < num_samples:
            logger.warning(f"⚠️ 仍然不足 {len(samples)}/{num_samples}，创建样本变体...")
            while len(samples) < num_samples and samples:
                # 随机选择一个样本，创建轻微变体
                base_sample = random.choice(samples)
                variant = self._create_sample_variant(base_sample, len(samples))
                if variant:
                    samples.append(variant)

        logger.info(f"✅ 实际生成样本数: {len(samples)}/{num_samples}")

        # 5. (可选) 生成跨模块调用样本
        if include_cross_module and cross_module_targets:
            logger.info("🔗 生成跨模块调用样本...")
            cross_module_samples = []

            for target_module in cross_module_targets:
                if target_module == module_id:
                    continue  # 跳过自己

                module_samples = self.analyze_cross_module_calls(
                    module_id, target_module
                )
                cross_module_samples.extend(module_samples)

            if cross_module_samples:
                # 限制跨模块样本数量（最多20%）
                max_cross = max(10, int(num_samples * 0.2))
                samples.extend(cross_module_samples[:max_cross])
                logger.info(f"  🔗 跨模块样本: {len(cross_module_samples[:max_cross])}")

        # 6. 质量验证和过滤
        logger.info("🔍 开始质量验证...")
        valid_samples = self.filter_and_validate_samples(samples)

        logger.info(f"✅ 最终有效样本数: {len(valid_samples)}/{num_samples}")

        # 如果有效样本不足，返回原始数量（可能包含低质量样本）
        if len(valid_samples) < num_samples * 0.8:  # 如果有效样本少于80%
            logger.warning(f"⚠️ 有效样本数量过少 ({len(valid_samples)}/{num_samples})，返回所有样本")
            return samples[:num_samples]

        # 限制到请求的数量
        return valid_samples[:num_samples]

    def _generate_function_analysis_samples(
        self, module_id: str, module_info: Dict, num_samples: int
    ) -> List[Dict]:
        """基于函数分析生成样本"""
        samples = []
        files = module_info.get('files', [])

        # 过滤文件：只处理模块相关的文件
        files = self._filter_module_files(module_id, files)

        skipped_short = 0
        skipped_failed = 0

        if self.debug:
            logger.info(f"  🔍 开始分析 {len(files)} 个文件...")

        for idx, file_path in enumerate(files):  # 处理所有文件，不再限制20个
            if len(samples) >= num_samples:
                if self.debug:
                    logger.info(f"  ✓ 已达到目标样本数 {num_samples}")
                break

            if self.debug:
                logger.info(f"  [{idx+1}/{len(files)}] 处理文件: {file_path}")

            functions = self.analyzer.extract_functions_from_file(file_path)

            if self.debug:
                logger.info(f"    - 提取到 {len(functions)} 个函数")

            for func_idx, func in enumerate(functions):
                if len(samples) >= num_samples:
                    break

                if self.debug and func_idx < 3:  # 只显示前3个函数的详情
                    logger.info(f"      [{func_idx+1}] 函数: {func['name']}")
                    logger.info(f"          复杂度分数: {func.get('complexity', {}).get('score', 0):.2f}")
                    logger.info(f"          代码长度: {len(func.get('body', ''))} 字符")

                # 生成函数分析样本
                sample = self._create_function_sample(module_id, func, file_path)
                if sample:
                    samples.append(sample)
                    if self.debug and len(samples) <= 5:  # 只显示前5个成功样本
                        logger.info(f"          ✅ 生成样本成功: {sample.get('category', 'unknown')} - {sample.get('difficulty', 'unknown')}")
                else:
                    # 追踪为什么失败
                    func_body = func.get('body', '')
                    if len(func_body) < 50:
                        skipped_short += 1
                    else:
                        skipped_failed += 1

        logger.info(f"  📝 生成了 {len(samples)} 个函数分析样本 (跳过: {skipped_short}太短, {skipped_failed}失败)")
        return samples

    def _generate_api_usage_samples(
        self, module_id: str, module_info: Dict, num_samples: int
    ) -> List[Dict]:
        """基于API使用生成样本"""
        samples = []
        files = module_info.get('files', [])

        # 过滤文件：只处理模块相关的文件
        files = self._filter_module_files(module_id, files)

        apis = module_info.get('apis', [])

        # 从API名称推断前缀
        api_prefixes = self._extract_api_prefixes(apis)

        if self.debug:
            logger.info(f"  🔍 分析 {len(files)} 个文件中的API使用...")

        for idx, file_path in enumerate(files[:10]):
            if len(samples) >= num_samples:
                if self.debug:
                    logger.info(f"  ✓ 已达到目标样本数 {num_samples}")
                break

            if self.debug:
                logger.info(f"  [{idx+1}/{len(files)}] 处理文件: {file_path}")

            patterns = self.analyzer.extract_api_usage_patterns(file_path, api_prefixes)

            if self.debug:
                logger.info(f"    - 找到 {len(patterns)} 个API使用模式")

            for pattern in patterns:
                if len(samples) >= num_samples:
                    break

                sample = self._create_api_usage_sample(module_id, pattern, file_path)
                if sample:
                    samples.append(sample)
                    if self.debug and len(samples) <= 3:
                        logger.info(f"      ✅ 生成API使用样本")

        logger.info(f"  🔧 生成了 {len(samples)} 个API使用样本")
        return samples

    def _extract_api_prefixes(self, apis: List[str]) -> List[str]:
        """从API列表中提取前缀"""
        prefixes = set()
        for api in apis:
            # 提取前缀，如 bt_gatt_notify -> bt_gatt_
            parts = api.split('_')
            if len(parts) >= 2:
                prefix = '_'.join(parts[:2]) + '_'
                prefixes.add(prefix)
        return list(prefixes)

    def _calculate_difficulty(self, complexity_score: float) -> str:
        """根据复杂度分数计算难度等级"""
        if complexity_score < 3:
            return "beginner"
        elif complexity_score < 7:
            return "intermediate"
        else:
            return "advanced"

    def _create_function_sample(self, module_id: str, func: Dict, file_path: str) -> Dict:
        """创建函数分析样本"""
        func_name = func['name']
        func_body = func['body']
        complexity = func.get('complexity', {})
        file_rel = file_path

        # 根据函数名判断类型
        if 'read' in func_name or 'write' in func_name:
            sample = self._create_read_write_sample(module_id, func_name, func_body, file_rel)
        elif 'notify' in func_name or 'indicate' in func_name:
            sample = self._create_notify_sample(module_id, func_name, func_body, file_rel)
        elif 'discovery' in func_name or 'discover' in func_name:
            sample = self._create_discovery_sample(module_id, func_name, func_body, file_rel)
        else:
            sample = self._create_general_function_sample(module_id, func_name, func_body, file_rel)

        # 动态设置难度等级
        if sample and complexity:
            difficulty = self._calculate_difficulty(complexity.get('score', 0))
            sample['difficulty'] = difficulty
            sample['complexity'] = complexity

        return sample

    def _create_read_write_sample(
        self, module_id: str, func_name: str, func_body: str, file_path: str
    ) -> Dict:
        """创建读写操作样本"""
        # 清理函数体
        clean_body = self._clean_code(func_body[:300])

        # 降低最小长度要求：从50降到30
        if not clean_body or len(clean_body) < 30:
            return None

        # 使用改进的特征检测器
        detector = self.analyzer.detector
        has_offset_check = detector.has_boundary_check(clean_body) and 'offset' in clean_body
        has_len_check = detector.has_boundary_check(clean_body) and ('len' in clean_body or 'size' in clean_body)
        has_error_handling = detector.has_error_handling(clean_body)
        has_null_check = detector.has_null_pointer_check(clean_body)
        has_overflow_protect = detector.has_buffer_overflow_protection(clean_body)

        # 计算质量分数
        checks_passed = sum([has_offset_check, has_len_check, has_error_handling, has_null_check])

        # 给出明确结论
        if checks_passed >= 3:
            verdict = "✅"
            verdict_text = "**正确实现**"
            analysis = "代码包含完整的安全检查和错误处理。"
        elif checks_passed >= 2:
            verdict = "⚠️"
            verdict_text = "**部分正确，需要补充检查**"
            analysis = f"代码通过了 {checks_passed}/4 项安全检查，建议补充其余检查项。"
        else:
            verdict = "❌"
            verdict_text = "**不正确，存在安全风险**"
            analysis = f"代码缺少关键的安全检查（仅通过 {checks_passed}/4 项），存在缓冲区越界或空指针解引用风险。"

        return {
            "module": module_id,
            "instruction": f"分析Zephyr中 `{func_name}` 函数的实现，它是否正确处理了边界条件？",
            "input": f"""
文件：{file_path}
函数：{func_name}

```c
{clean_body}
```
""",
            "output": f"""{verdict} {verdict_text}

## 函数分析

**函数名称：** `{func_name}`

**判断依据：**
{analysis}

### 安全检查清单

{'✅' if has_offset_check else '❌'} **offset参数验证** - {'' if has_offset_check else '缺少offset范围检查，可能导致越界访问'}
{'✅' if has_len_check else '❌'} **缓冲区边界检查** - {'' if has_len_check else '缺少长度边界验证，存在缓冲区溢出风险'}
{'✅' if has_error_handling else '❌'} **错误处理** - {'' if has_error_handling else '缺少错误码返回，无法正确处理异常情况'}
{'✅' if has_null_check else '❌'} **空指针检查** - {'' if has_null_check else '缺少指针有效性验证'}

### 代码片段
```c
{clean_body[:250]}
```

### 协议依据
- **规范**: Bluetooth Core Specification Vol 3, Part F, Section 3.3.1
- **要求**: ATT操作必须验证handle有效性和数据长度
- **安全**: 必须防止缓冲区越界访问

### 源码参考
- **文件**: `subsys/bluetooth/{file_path}`
- **函数**: `{func_name}()`
- **相关API**: `bt_gatt_attr_read()`, `BT_GATT_ERR()`, `bt_att_`

{'' if checks_passed >= 3 else f"""
### 改进建议
1. 添加参数验证: `if (offset < 0 || offset + len > max_len)`
2. 返回标准错误码: `return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET)`
3. 检查指针有效性: `if (!conn || !attr)`"""}
""",
            "category": "boundary_analysis",
            "difficulty": "intermediate",
            "verdict_type": "correct" if checks_passed >= 3 else "needs_review",
            "source": "zephyr_code",
            "file": file_path
        }

    def _create_notify_sample(
        self, module_id: str, func_name: str, func_body: str, file_path: str
    ) -> Dict:
        """创建通知相关样本"""
        clean_body = self._clean_code(func_body[:300])

        # 使用改进的特征检测器
        detector = self.analyzer.detector
        has_conn_check = detector.has_connection_check(clean_body)
        has_ccc_check = detector.has_ccc_check(clean_body)
        has_error_handling = detector.has_error_handling(clean_body)
        has_enobufs_check = 'ENOBUFS' in clean_body or 'ENOENT' in clean_body

        # 计算合规性分数
        checks_passed = sum([has_conn_check, has_ccc_check, has_error_handling, has_enobufs_check])

        # 给出明确结论
        if checks_passed >= 3:
            verdict = "✅"
            verdict_text = "**符合BLE通知协议**"
            analysis = "实现完整遵循BLE Core Spec关于GATT Notification的要求。"
        elif checks_passed >= 2:
            verdict = "⚠️"
            verdict_text = "**部分符合，建议补充检查**"
            analysis = f"实现通过了 {checks_passed}/4 项协议要求，建议补充其余检查项以确保完全合规。"
        else:
            verdict = "❌"
            verdict_text = "**不正确，违反协议要求**"
            analysis = f"实现缺少关键的协议检查（仅通过 {checks_passed}/4 项），可能导致协议违规或运行时错误。"

        return {
            "module": module_id,
            "instruction": f"Zephyr中 `{func_name}` 函数的实现是否符合BLE通知协议？",
            "input": f"""
文件：{file_path}

```c
{clean_body}
```
""",
            "output": f"""{verdict} {verdict_text}

## 协议合规性分析

**函数：** `{func_name}`

**判断依据：**
{analysis}

### BLE协议要求 (Bluetooth Core Spec Vol 3, Part F, Section 3.4.5)

{'✅' if has_conn_check else '❌'} **连接有效性检查** - Protocol要求验证conn指针非空
{'✅' if has_ccc_check else '❌'} **CCC状态验证** - 必须检查Client Characteristic Configuration，值为0x0001时才允许notify
{'✅' if has_error_handling else '❌'} **错误处理** - 必须处理并返回错误码
{'✅' if has_enobufs_check else '❌'} **ENOBUFS处理** - 发送缓冲区满时的特殊处理

### 代码片段分析
```c
{clean_body[:250]}
```

### 协议依据
- **规范**: Bluetooth Core Specification Vol 3, Part F, Section 3.4.5.1 (Notification)
- **要求**: "The Characteristic Value shall be sent only if... the Client Characteristic Configuration descriptor exists and the Notification bit is set"
- **CCC值**: 0x0001 = Notifications enabled, 0x0000 = Disabled
- **错误码**: BT_ATT_ERR_INSUFFICIENT_ENCRYPTION, BT_ATT_ERR_INVALID_HANDLE

### 源码参考
- **文件**: `subsys/bluetooth/{file_path}`
- **函数**: `{func_name}()`
- **相关API**: `bt_gatt_notify()`, `bt_gatt_attr()`, `BT_GATT_CHRC_NOTIFY`

{'' if checks_passed >= 3 else f"""
### 改进建议
1. 添加连接检查: `if (!conn) return -ENOTCONN;`
2. 验证CCC状态: `if (!(ccc->flags & BT_GATT_CCC_NOTIFY)) return 0;`
3. 处理ENOBUFS: `if (err == -ENOBUFS) {{ /* 等待或重试 */ }}`"""}
""",
            "category": "protocol_compliance",
            "difficulty": "intermediate",
            "verdict_type": "correct" if checks_passed >= 3 else "needs_review",
            "source": "zephyr_code",
            "file": file_path
        }

    def _create_discovery_sample(
        self, module_id: str, func_name: str, func_body: str, file_path: str
    ) -> Dict:
        """创建发现相关样本"""
        clean_body = self._clean_code(func_body[:300])

        # 分析代码特征
        has_handle_check = ('handle' in clean_body.lower() and
                           ('start' in clean_body.lower() or 'end' in clean_body.lower()) and
                           ('if' in clean_body or '>' in clean_body or '<' in clean_body))
        has_uuid_check = 'uuid' in clean_body.lower() and ('cmp' in clean_body.lower() or 'match' in clean_body.lower())
        has_mtu_check = 'mtu' in clean_body.lower() and ('if' in clean_body or '>' in clean_body)
        has_error_handling = ('err' in clean_body or 'BT_ATT' in clean_body) and 'return' in clean_body

        # 计算合规性分数
        checks_passed = sum([has_handle_check, has_uuid_check, has_mtu_check, has_error_handling])

        # 给出明确结论
        if checks_passed >= 3:
            verdict = "✅"
            verdict_text = "**正确的GATT发现实现**"
            analysis = "实现完整遵循GATT服务发现协议规范。"
        elif checks_passed >= 2:
            verdict = "⚠️"
            verdict_text = "**部分正确，需要补充边界检查**"
            analysis = f"实现通过了 {checks_passed}/4 项检查要求，建议补充其余检查项。"
        else:
            verdict = "❌"
            verdict_text = "**不正确，缺少关键验证**"
            analysis = f"实现缺少关键的发现流程检查（仅通过 {checks_passed}/4 项），可能导致发现失败或协议违规。"

        return {
            "module": module_id,
            "instruction": f"分析 `{func_name}` 函数的GATT服务发现实现是否正确？",
            "input": f"""
文件：{file_path}

```c
{clean_body}
```
""",
            "output": f"""{verdict} {verdict_text}

## GATT服务发现分析

**函数：** `{func_name}`

**判断依据：**
{analysis}

### GATT发现协议要求 (Bluetooth Core Spec Vol 3, Part G)

{'✅' if has_handle_check else '❌'} **Handle范围验证** - 必须验证start_handle和end_handle的有效性（1-0xFFFF）
{'✅' if has_uuid_check else '❌'} **UUID匹配逻辑** - 实现正确的128位/16位UUID比较
{'✅' if has_mtu_check else '❌'} **MTU限制检查** - 响应数据不能超过MTU-3字节
{'✅' if has_error_handling else '❌'} **错误处理** - 返回标准ATT错误码

### 代码片段分析
```c
{clean_body[:250]}
```

### 协议依据
- **规范**: Bluetooth Core Specification Vol 3, Part G, Section 2.5.3 (Discover Primary Service by UUID)
- **要求**: "The Attribute Handle Range shall be valid handles"
- **MTU限制**: "The response shall not exceed the MTU - 1"
- **错误码**: BT_ATT_ERR_INVALID_HANDLE, BT_ATT_ERR_ATTRIBUTE_NOT_FOUND, BT_ATT_ERR_UNLIKELY

### 源码参考
- **文件**: `subsys/bluetooth/{file_path}`
- **函数**: `{func_name}()`
- **相关API**: `bt_gatt_discover()`, `bt_gatt_include()`, `BT_GATT_ERR`

{'' if checks_passed >= 3 else f"""
### 改进建议
1. Handle范围验证: `if (start_handle < 0x0001 || end_handle > 0xFFFF)`
2. MTU大小检查: `if (rsp_len + 3 > mtu) return BT_GATT_ERR(BT_ATT_ERR_INVALID_PDU)`
3. UUID匹配优化: 使用`bt_uuid_cmp()`而非直接memcmp"""}
""",
            "category": "boundary_analysis",
            "difficulty": "advanced",
            "verdict_type": "correct" if checks_passed >= 3 else "needs_review",
            "source": "zephyr_code",
            "file": file_path
        }

    def _create_general_function_sample(
        self, module_id: str, func_name: str, func_body: str, file_path: str
    ) -> Dict:
        """创建通用函数分析样本"""
        clean_body = self._clean_code(func_body[:300])

        # 分析代码特征
        has_logging = ('LOG' in clean_body or 'printk' in clean_body or 'bt_' in clean_body) and 'err' in clean_body.lower()
        has_return_check = 'return' in clean_body and ('=' in clean_body or 'err' in clean_body)
        has_pointer_check = ('!' in clean_body or 'NULL' in clean_body) and ('if' in clean_body or 'assert' in clean_body)
        has_const_correctness = 'const' in clean_body
        has_mutex = ('lock' in clean_body.lower() or 'mutex' in clean_body.lower() or
                    'k_mutex' in clean_body)

        # 计算质量分数
        checks_passed = sum([has_logging, has_return_check, has_pointer_check,
                            has_const_correctness, has_mutex])

        # 给出明确结论
        if checks_passed >= 4:
            verdict = "✅"
            verdict_text = "**代码质量良好**"
            analysis = "函数实现遵循Zephyr最佳实践，包含完善的错误处理和日志记录。"
        elif checks_passed >= 3:
            verdict = "⚠️"
            verdict_text = "**代码基本合格，有改进空间**"
            analysis = f"函数通过了 {checks_passed}/5 项质量检查，建议补充其余实践项。"
        else:
            verdict = "❌"
            verdict_text = "**代码存在潜在问题**"
            analysis = f"函数缺少关键的质量要素（仅通过 {checks_passed}/5 项），可能导致运行时错误或维护困难。"

        return {
            "module": module_id,
            "instruction": f"Review the implementation of `{func_name}` in Zephyr and identify potential issues.",
            "input": f"""
File: {file_path}

```c
{clean_body}
```
""",
            "output": f"""{verdict} {verdict_text}

## Code Review: `{func_name}`

**判断依据：**
{analysis}

### Zephyr代码质量检查

{'✅' if has_logging else '❌'} **错误日志** - 使用BT_ERR/LOG_ERR记录错误信息
{'✅' if has_return_check else '❌'} **返回值检查** - 检查并正确处理函数返回值
{'✅' if has_pointer_check else '❌'} **指针验证** - 使用前检查指针有效性
{'✅' if has_const_correctness else '❌'} **Const正确性** - 只读参数使用const修饰
{'✅' if has_mutex else '⚠️'} **线程安全** - 必要时使用互斥锁保护

### 代码片段
```c
{clean_body[:250]}
```

### Zephyr编程规范
- **编码风格**: 遵循Zephyr Coding Style (缩进、命名、注释)
- **错误处理**: 所有API返回值必须检查
- **资源管理**: 使用k_malloc/k_free，确保配对
- **日志级别**: LOG_ERR(错误), LOG_WRN(警告), LOG_INF(信息), LOG_DBG(调试)
- **宏定义**: 优先使用BT_*相关宏定义

### 源码参考
- **文件**: `subsys/bluetooth/{file_path}`
- **函数**: `{func_name}()`
- **参考**: Zephyr API Documentation - Bluetooth APIs

{'' if checks_passed >= 4 else f"""
### 改进建议
1. 添加错误日志: `BT_ERR(\"Failed to xxx: %d\", err)`
2. 检查返回值: `int err = bt_xxx(); if (err) {{ return err; }}`
3. 指针验证: `if (!ptr) {{ return -EINVAL; }}`
4. 使用const: `void func(const uint8_t *data)`"""}
""",
            "category": "code_review",
            "difficulty": "intermediate",
            "verdict_type": "correct" if checks_passed >= 4 else "needs_review",
            "source": "zephyr_code",
            "file": file_path
        }

    def _create_api_usage_sample(
        self, module_id: str, pattern: Dict, file_path: str
    ) -> Dict:
        """创建API使用样本"""
        api = pattern['api']
        usage = pattern['usage']
        clean_usage = self._clean_code(usage)

        # 分析API使用特征
        has_return_check = ('if' in clean_usage or 'while' in clean_usage) and ('err' in clean_usage or 'ret' in clean_usage)
        has_null_check = 'NULL' in clean_usage or ('!' in clean_usage and ('=' in clean_usage or clean_usage.count('!') > 1))
        has_params = api.replace('_', '_') in clean_usage and '(' in clean_usage and ')' in clean_usage
        has_error_codes = any(err in clean_usage for err in ['ENOBUFS', 'EINVAL', 'ENOTCONN', 'ENOMEM', 'EACCES'])
        has_logging = 'LOG' in clean_usage or 'BT_' in clean_usage or 'printk' in clean_usage

        # 计算合规性分数
        checks_passed = sum([has_return_check, has_null_check, has_params, has_error_codes, has_logging])

        # 给出明确结论
        if checks_passed >= 4:
            verdict = "✅"
            verdict_text = "**API使用正确**"
            analysis = "API调用遵循Zephyr BLE最佳实践，包含完整的错误处理和参数验证。"
        elif checks_passed >= 3:
            verdict = "⚠️"
            verdict_text = "**API使用基本正确，建议补充检查**"
            analysis = f"API使用通过了 {checks_passed}/5 项最佳实践，建议补充其余检查项。"
        else:
            verdict = "❌"
            verdict_text = "**API使用不正确，存在潜在问题**"
            analysis = f"API使用缺少关键的处理步骤（仅通过 {checks_passed}/5 项），可能导致运行时错误。"

        return {
            "module": module_id,
            "instruction": f"Is the use of `{api}` in this code snippet correct according to Zephyr BLE APIs?",
            "input": f"""
File: {file_path}

```c
{clean_usage}
```
""",
            "output": f"""{verdict} {verdict_text}

## API Usage Analysis

**API:** `{api}`

**判断依据：**
{analysis}

### API使用合规性检查

{'✅' if has_return_check else '❌'} **返回值检查** - 必须检查API返回值并处理错误情况
{'✅' if has_null_check else '❌'} **空指针验证** - 使用前验证指针和连接有效性
{'✅' if has_params else '❌'} **参数完整** - API调用参数完整且符合函数签名
{'✅' if has_error_codes else '❌'} **错误码处理** - 正确处理标准BLE错误码
{'✅' if has_logging else '❌'} **日志记录** - 使用适当的日志级别记录API调用结果

### 代码片段
```c
{clean_usage[:300]}
```

### Zephyr BLE API最佳实践
- **返回值检查**: 所有`bt_*` API都返回int错误码，必须检查
- **标准错误码**:
  - `-ENOBUFS`: 发送缓冲区满
  - `-EINVAL`: 参数无效
  - `-ENOTCONN`: 连接无效
  * `-EACCES`: 权限不足
- **连接检查**: `if (!conn) return -ENOTCONN;`
- **资源清理**: 失败时释放已分配的资源

### 源码参考
- **文件**: {file_path}
- **API**: `{api}`
- **文档**: Zephyr Bluetooth API Documentation
- **示例**: `samples/bluetooth/`

{'' if checks_passed >= 4 else f"""
### 改进建议
1. 检查返回值: `int err = {api}(...); if (err) {{ BT_ERR(\"API failed: %d\", err); return err; }}`
2. 验证连接: `if (!conn || !conn->active) {{ return -ENOTCONN; }}`
3. 错误码处理: 使用switch/if处理常见错误码
4. 添加日志: `BT_DBG(\"{api} called with params\");`"""}
""",
            "category": "api_usage",
            "difficulty": "intermediate",
            "verdict_type": "correct" if checks_passed >= 4 else "needs_review",
            "source": "zephyr_code",
            "file": file_path
        }

    def _generate_generic_samples(
        self, module_id: str, module_info: Dict, num_samples: int
    ) -> List[Dict]:
        """生成通用样本（当源码样本不足时）"""
        # 这里可以添加一些模板化的样本
        # 但应该基于模块的API和功能
        return []

    def _clean_code(self, code: str) -> str:
        """清理代码"""
        # 移除多余空行
        code = re.sub(r'\n\s*\n\s*\n', '\n\n', code)

        # 统一缩进
        lines = code.split('\n')
        if lines:
            min_indent = float('inf')
            for line in lines:
                if line.strip():
                    indent = len(line) - len(line.lstrip())
                    min_indent = min(min_indent, indent)

            if min_indent > 0 and min_indent != float('inf'):
                lines = [line[min_indent:] if len(line) >= min_indent else line
                        for line in lines]

        return '\n'.join(lines).strip()

    def _generate_additional_samples(
        self, module_id: str, module_info: Dict, num_samples: int
    ) -> List[Dict]:
        """生成额外样本（当常规方法不足时）"""
        samples = []
        files = module_info.get('files', [])

        # 从更多文件中提取函数
        for file_path in files:
            if len(samples) >= num_samples:
                break

            functions = self.analyzer.extract_functions_from_file(file_path)
            for func in functions:
                if len(samples) >= num_samples:
                    break

                # 尝试创建通用样本（更宽松的条件）
                sample = self._create_general_function_sample(
                    module_id, func['name'], func['body'][:500], file_path
                )
                if sample:
                    # 标记为额外样本
                    sample['is_additional'] = True
                    samples.append(sample)

        return samples

    def _create_sample_variant(self, base_sample: Dict, index: int) -> Dict:
        """基于现有样本创建变体（轻微修改）"""
        import copy
        variant = copy.deepcopy(base_sample)

        # 修改instruction
        instruction = variant['instruction']
        if 'analyze' in instruction.lower():
            variant['instruction'] = instruction.replace('analyze', 'review', 1)
        elif 'review' in instruction.lower():
            variant['instruction'] = instruction.replace('review', 'examine', 1)
        else:
            variant['instruction'] = "Re-evaluate: " + instruction

        # 修改output，添加说明
        variant['output'] = f"[Variation #{index}]\n" + variant['output']

        # 标记为变体
        variant['is_variant'] = True
        variant['variant_of'] = base_sample.get('file', '') + '_' + str(index)

        return variant

    def _detect_error_patterns(self, code: str) -> List[str]:
        """检测代码中的潜在错误模式

        Returns:
            检测到的错误模式列表
        """
        error_patterns = []

        # 1. Buffer Overflow风险
        if re.search(r'memcpy\s*\([^,]+,\s*[^,]+,\s*[^)]+\)', code):
            # 检查是否有边界检查
            if not re.search(r'memcpy\s*\([^,]+,\s*[^,]+,\s*min\s*\(', code):
                if not re.search(r'strncpy\s*\(', code):
                    error_patterns.append("buffer_overflow")

        # 2. Null Pointer解引用风险
        if re.search(r'(\w+)\s*->', code):
            # 检查指针使用前是否有NULL检查
            ptr_access = re.findall(r'(\w+)\s*->', code)
            for ptr in set(ptr_access):
                if not re.search(rf'if\s*\(\s*!?\s*{ptr}\s*\)', code):
                    error_patterns.append("null_pointer_dereference")
                    break

        # 3. Double Free风险
        free_calls = re.findall(r'k_free\s*\(([^)]+)\)', code)
        if len(free_calls) > 1:
            freed_vars = [var.strip() for var in free_calls]
            if len(freed_vars) != len(set(freed_vars)):
                error_patterns.append("double_free")

        # 4. Use After Free风险
        for i, free_call in enumerate(free_calls):
            var = free_call.strip()
            # 检查free后是否还使用该变量
            remaining_code = code[code.find(free_call) + len(free_call):]
            if var in remaining_code and 'k_free' not in remaining_code[:100]:
                error_patterns.append("use_after_free")
                break

        # 5. Missing Error Check
        func_calls = re.findall(r'(\w+)\s*\([^)]*\)\s*;', code)
        error_returning_funcs = ['bt_gatt_', 'bt_att_', 'k_malloc', 'net_buf_']
        for func in func_calls:
            if any(err_func in func for err_func in error_returning_funcs):
                # 检查返回值是否被检查
                if not re.search(rf'if\s*\([^)]*{func}', code):
                    error_patterns.append("missing_error_check")
                    break

        # 6. Integer Overflow风险
        if re.search(r'(\w+)\s*\+\s*\1', code):  # x + x可能溢出
            if 'size_t' in code or 'u32_t' in code or 'u16_t' in code:
                error_patterns.append("integer_overflow")

        # 7. 未初始化变量使用
        if re.search(r'(int|char|u8_t|u16_t|u32_t)\s+(\w+)\s*;', code):
            # 检查变量声明后直接使用
            declarations = re.findall(r'(int|char|u8_t|u16_t|u32_t)\s+(\w+)\s*;', code)
            for decl in declarations:
                var = decl[1]
                # 简单检查：声明后立即使用
                pattern = rf'{decl[0]}\s+{var}\s*;[^;}}]*{var}\s*[=)]'
                if re.search(pattern, code):
                    error_patterns.append("uninitialized_variable")
                    break

        return list(set(error_patterns))  # 去重

    def analyze_cross_module_calls(
        self, module_a: str, module_b: str
    ) -> List[Dict]:
        """分析模块A如何调用模块B

        Args:
            module_a: 调用方模块ID (如 'host_gatt')
            module_b: 被调用方模块ID (如 'host_att')

        Returns:
            跨模块调用样本列表
        """
        if module_a not in self.module_data["modules"]:
            logger.warning(f"模块 {module_a} 不存在")
            return []

        if module_b not in self.module_data["modules"]:
            logger.warning(f"模块 {module_b} 不存在")
            return []

        module_a_info = self.module_data["modules"][module_a]
        module_b_info = self.module_data["modules"][module_b]
        module_b_name = module_b_info['info']['name']

        # 获取模块B的API列表
        module_b_apis = set(module_b_info.get('apis', []))

        if not module_b_apis:
            logger.warning(f"模块 {module_b} 没有API定义")
            return []

        # 提取模块B的API前缀
        api_prefixes = []
        for api in list(module_b_apis)[:20]:  # 限制数量
            # 提取前缀，如 bt_att_ -> bt_att_
            parts = api.split('_')
            if len(parts) >= 2:
                prefix = '_'.join(parts[:2]) + '_'
                api_prefixes.append(prefix)

        api_prefixes = list(set(api_prefixes))

        # 在模块A的文件中搜索对模块B API的调用
        samples = []
        files_a = module_a_info.get('files', [])

        for file_path in files_a[:10]:  # 限制文件数量
            if len(samples) >= 20:  # 限制样本数量
                break

            full_path = self.zephyr_path / file_path
            if not full_path.exists():
                continue

            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue

            # 搜索对模块B API的调用
            for prefix in api_prefixes:
                pattern = rf'.{{0,300}}{re.escape(prefix)}[\w_]+\s*\([^)]*\)[^;}}]*;'
                matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)

                for match in matches:
                    code_snippet = match.group(0).strip()

                    if len(code_snippet) < 50 or len(code_snippet) > 500:
                        continue

                    # 提取API名称
                    api_match = re.search(rf'{re.escape(prefix)}(\w+)', code_snippet)
                    if not api_match:
                        continue

                    api_name = prefix + api_match.group(1)

                    # 分析调用特征
                    sample = self._create_cross_module_sample(
                        module_a, module_b, module_b_name,
                        api_name, code_snippet, file_path
                    )

                    if sample:
                        samples.append(sample)

                    if len(samples) >= 20:
                        break

                if len(samples) >= 20:
                    break

        logger.info(f"  🔗 跨模块调用样本 ({module_a}->{module_b}): {len(samples)}")
        return samples

    def _create_cross_module_sample(
        self, caller_module: str, callee_module: str, callee_name: str,
        api_name: str, code_snippet: str, file_path: str
    ) -> Dict:
        """创建跨模块API调用检查样本"""

        # 使用改进的特征检测器
        detector = self.analyzer.detector

        # 检查API调用特征
        has_return_check = detector.has_error_handling(code_snippet)
        has_null_check = detector.has_null_pointer_check(code_snippet)
        has_error_handling = 'err' in code_snippet and 'if' in code_snippet

        # 检查参数验证
        has_param_validation = (
            'if' in code_snippet and
            ('!' in code_snippet or 'NULL' in code_snippet or 'valid' in code_snippet.lower())
        )

        # 计算合规性分数
        checks_passed = sum([
            has_return_check,
            has_null_check,
            has_error_handling,
            has_param_validation
        ])

        # 给出判断
        if checks_passed >= 3:
            verdict = "✅"
            verdict_text = "**正确调用**"
            analysis = f"正确使用了 {callee_name} 的 API，包含必要的错误检查和参数验证。"
        elif checks_passed >= 2:
            verdict = "⚠️"
            verdict_text = "**部分正确**"
            analysis = f"API调用基本正确，但建议补充 {'错误处理' if not has_error_handling else '参数验证'}。"
        else:
            verdict = "❌"
            verdict_text = "**调用不正确**"
            analysis = f"缺少必要的错误检查（仅通过 {checks_passed}/4 项），可能导致运行时错误。"

        return {
            "module": caller_module,
            "instruction": f"检查 {caller_module} 模块对 `{callee_name}` API (`{api_name}`) 的调用是否正确？",
            "input": f"""
调用方模块: {caller_module}
被调用模块: {callee_module} ({callee_name})
API: {api_name}

```c
{code_snippet}
```
""",
            "output": f"""{verdict} {verdict_text}

## 跨模块API调用分析

**API名称：** `{api_name}`
**调用关系：** {caller_module} → {callee_name}

**判断依据：**
{analysis}

### 调用合规性检查

{'✅' if has_return_check else '❌'} **返回值检查** - {'检查了API返回值' if has_return_check else '未检查返回值'}
{'✅' if has_null_check else '❌'} **空指针检查** - {'验证了指针有效性' if has_null_check else '缺少指针验证'}
{'✅' if has_error_handling else '❌'} **错误处理** - {'包含错误处理逻辑' if has_error_handling else '缺少错误处理'}
{'✅' if has_param_validation else '❌'} **参数验证** - {'验证了参数有效性' if has_param_validation else '缺少参数验证'}

### 集成测试要点
- 确保模块间接口契约被遵守
- 验证返回值和错误码
- 检查资源释放和生命周期管理

### 参考文档
- **API文档**: {callee_name} API Reference
- **接口规范**: Zephyr BLE模块接口规范
- **源码**: `subsys/bluetooth/{file_path}`

{'' if checks_passed >= 3 else f"""
### 改进建议
1. 始终检查API返回值
2. 验证指针参数（NULL检查）
3. 处理所有可能的错误码
4. 遵循API使用规范"""}
""",
            "category": "api_usage",
            "difficulty": "intermediate" if checks_passed >= 2 else "advanced",
            "verdict_type": "correct" if checks_passed >= 3 else "needs_review",
            "source": "zephyr_code",
            "file": file_path,
            "cross_module": {
                "caller": caller_module,
                "callee": callee_module,
                "api": api_name
            }
        }

    def _create_error_pattern_sample(
        self, module_id: str, func_name: str, func_body: str,
        file_path: str, error_pattern: str
    ) -> Dict:
        """基于错误模式创建样本"""
        clean_body = self._clean_code(func_body[:300])

        if not clean_body or len(clean_body) < 30:
            return None

        # 根据错误类型生成不同的output
        error_descriptions = {
            "buffer_overflow": "缓冲区溢出风险 - memcpy未验证目标缓冲区大小",
            "null_pointer_dereference": "空指针解引用风险 - 指针使用前未检查NULL",
            "double_free": "双重释放风险 - 同一指针被释放多次",
            "use_after_free": "释放后使用风险 - 内存被释放后仍被访问",
            "missing_error_check": "缺少错误检查 - 函数返回值未验证",
            "integer_overflow": "整数溢出风险 - 算术运算可能导致溢出",
            "uninitialized_variable": "未初始化变量 - 变量在使用前未赋初值"
        }

        severity_levels = {
            "buffer_overflow": "critical",
            "null_pointer_dereference": "critical",
            "double_free": "high",
            "use_after_free": "high",
            "missing_error_check": "medium",
            "integer_overflow": "medium",
            "uninitialized_variable": "low"
        }

        severity = severity_levels.get(error_pattern, "unknown")
        description = error_descriptions.get(error_pattern, "未知错误模式")

        return {
            "module": module_id,
            "instruction": f"分析 `{func_name}` 函数中的 `{error_pattern}` 安全风险",
            "input": f"""
文件：{file_path}
函数：{func_name}
错误模式：{error_pattern}

```c
{clean_body}
```
""",
            "output": f"""❌ **存在安全风险：{description}**

## 代码安全分析

**错误模式：** `{error_pattern}`
**严重程度：** {severity.upper()}

### 风险描述
{description}

### 潜在影响
- **安全漏洞**: 可能导致系统崩溃或被攻击
- **数据损坏**: 内存损坏导致数据不一致
- **不稳定**: 随机失败难以复现

### 修复建议
1. 添加边界检查
2. 验证指针有效性
3. 检查函数返回值
4. 使用安全的内存操作函数

### 参考规范
- **CWE**: {error_pattern.upper()} 相关CWE条目
- **MISRA C**: 规则X.X - 相关编码规范

### 源码参考
- **文件**: `subsys/bluetooth/{file_path}`
- **函数**: `{func_name}()`
""",
            "category": "security_check",
            "difficulty": "advanced",
            "verdict_type": "needs_review",
            "source": "zephyr_code",
            "file": file_path,
            "error_pattern": error_pattern,
            "severity": severity
        }

    def save_samples(self, module_id: str, samples: List[Dict], output_dir: str = 'dataset/modules'):
        """保存样本

        Args:
            module_id: 模块ID
            samples: 样本列表
            output_dir: 输出目录（默认：dataset/modules）
        """
        if not samples:
            logger.warning(f"模块 {module_id} 没有生成样本")
            return

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        output_file = output_path / f"{module_id}_samples.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)

        logger.info(f"✅ 样本已保存到: {output_file}")
        logger.info(f"   模块: {module_id}")
        logger.info(f"   数量: {len(samples)}")

        # 统计
        categories = defaultdict(int)
        for sample in samples:
            cat = sample.get('category', 'unknown')
            categories[cat] += 1

        logger.info("\n📊 类别分布:")
        for cat, count in sorted(categories.items()):
            logger.info(f"  {cat}: {count}")

    def validate_sample_quality(self, sample: Dict) -> tuple:
        """验证单个样本的质量

        Returns:
            (is_valid, issues): (是否有效, 问题列表)
        """
        issues = []

        # 检查1：必须有instruction
        if not sample.get('instruction') or len(sample.get('instruction', '')) < 10:
            issues.append("instruction太短或缺失")

        # 检查2：必须有input
        if not sample.get('input'):
            issues.append("input缺失")

        # 检查3：input必须包含代码块
        if 'input' in sample and '```c' not in sample.get('input', ''):
            issues.append("input缺少代码块标记")

        # 检查4：必须有output
        if not sample.get('output') or len(sample.get('output', '')) < 50:
            issues.append("output太短或缺失")

        # 检查5：output必须包含分析内容
        output = sample.get('output', '')
        if output:
            # 检查是否包含判断依据
            if '判断依据' not in output and '分析' not in output and 'Analysis' not in output:
                issues.append("output缺少分析依据")

            # 检查是否包含协议规范引用
            if 'Bluetooth' not in output and 'BLE' not in output and '协议' not in output:
                issues.append("output缺少协议规范引用")

        # 检查6：必须有verdict_type
        if sample.get('verdict_type') not in ['correct', 'needs_review']:
            issues.append("verdict_type无效，必须是correct或needs_review")

        # 检查7：必须有category
        valid_categories = [
            'protocol_compliance', 'boundary_analysis', 'api_usage',
            'code_review', 'security_check'
        ]
        if sample.get('category') not in valid_categories:
            issues.append(f"category无效: {sample.get('category')}")

        # 检查8：必须有difficulty
        valid_difficulties = ['beginner', 'intermediate', 'advanced']
        if sample.get('difficulty') not in valid_difficulties:
            issues.append(f"difficulty无效: {sample.get('difficulty')}")

        # 检查9：必须有source
        if sample.get('source') != 'zephyr_code':
            issues.append("source必须是zephyr_code")

        # 检查10：必须有file
        if not sample.get('file'):
            issues.append("file缺失")

        is_valid = len(issues) == 0
        return is_valid, issues

    def filter_and_validate_samples(self, samples: List[Dict]) -> List[Dict]:
        """过滤并验证样本质量

        Returns:
            valid_samples: 通过验证的样本列表
        """
        valid_samples = []
        invalid_count = 0
        issue_stats = {}

        for sample in samples:
            is_valid, issues = self.validate_sample_quality(sample)

            if is_valid:
                valid_samples.append(sample)
            else:
                invalid_count += 1
                # 统计问题类型
                for issue in issues:
                    issue_stats[issue] = issue_stats.get(issue, 0) + 1

        # 打印统计
        total = len(samples)
        valid = len(valid_samples)
        logger.info(f"\n📊 样本质量验证:")
        logger.info(f"  总样本数: {total}")
        logger.info(f"  ✅ 有效样本: {valid} ({valid/total*100:.1f}%)")
        logger.info(f"  ❌ 无效样本: {invalid_count} ({invalid_count/total*100:.1f}%)")

        if issue_stats:
            logger.info(f"\n⚠️ 主要问题:")
            for issue, count in sorted(issue_stats.items(), key=lambda x: x[1], reverse=True)[:5]:
                logger.info(f"  - {issue}: {count}次")

        return valid_samples


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

    def __init__(self, samples: List[Dict]):
        self.samples = samples

    def diversify_70_20_10(self, module_id: str, output_dir: str = 'dataset/modules') -> Dict:
        """按70:20:10比例分割样本集

        分割规则:
        - 70% 直接生成的样本（原始样本，用于训练）
        - 20% 偏差样本（多样化变体，verdict被翻转，用于训练）
        - 10% 正确样本（从原始样本中筛选verdict='correct'，用于验证）

        Args:
            module_id: 模块ID
            output_dir: 输出目录

        Returns:
            包含train, validation, complete的字典
        """
        total_samples = len(self.samples)

        # 计算各部分数量
        num_train_original = int(total_samples * 0.70)  # 70% 原始样本
        num_biased = int(total_samples * 0.20)          # 20% 偏差样本
        num_validation = int(total_samples * 0.10)      # 10% 正确样本

        # 1. 提取正确样本（用于验证集）
        correct_samples = [s for s in self.samples if s['verdict_type'] == 'correct']

        # 如果正确样本不够10%，随机抽取needs_review样本补足
        if len(correct_samples) < num_validation:
            needs_review_samples = [s for s in self.samples if s['verdict_type'] == 'needs_review']
            additional = num_validation - len(correct_samples)
            correct_samples.extend(random.sample(needs_review_samples, min(additional, len(needs_review_samples))))

        # 随机打乱并选择验证样本
        random.shuffle(correct_samples)
        validation_samples = correct_samples[:num_validation]

        # 2. 选择训练用的原始样本（70%）
        remaining_samples = [s for s in self.samples if s not in validation_samples]
        random.shuffle(remaining_samples)
        train_original_samples = remaining_samples[:num_train_original]

        # 3. 生成偏差样本（20%）
        samples_for_biased = random.sample(train_original_samples, min(num_biased, len(train_original_samples)))
        biased_samples = []
        for sample in samples_for_biased:
            variant = self._create_variant(sample, target_correct_ratio=0.3)
            if variant:
                variant['sample_type'] = 'biased'
                biased_samples.append(variant)

        # 4. 标记样本类型
        for s in train_original_samples:
            s['sample_type'] = 'train_original'
        for s in validation_samples:
            s['sample_type'] = 'validation'

        # 5. 保存为三个文件
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 训练集（原始+偏差）
        train_samples = train_original_samples + biased_samples
        train_file = output_path / f"{module_id}_train.json"
        with open(train_file, 'w', encoding='utf-8') as f:
            json.dump(train_samples, f, ensure_ascii=False, indent=2)

        # 验证集
        val_file = output_path / f"{module_id}_validation.json"
        with open(val_file, 'w', encoding='utf-8') as f:
            json.dump(validation_samples, f, ensure_ascii=False, indent=2)

        # 完整数据集（合并）
        complete_samples = train_samples + validation_samples
        complete_file = output_path / f"{module_id}_complete.json"
        with open(complete_file, 'w', encoding='utf-8') as f:
            json.dump(complete_samples, f, ensure_ascii=False, indent=2)

        # 打印统计
        print("\n" + "="*80)
        print("📊 样本集分割完成 (70:20:10)")
        print("="*80)
        print(f"\n原始样本总数: {total_samples}")
        print(f"\n分割结果:")
        print(f"  📁 训练集（原始）:  {len(train_original_samples):3d} ({len(train_original_samples)/total_samples*100:.1f}%)")
        print(f"  📁 训练集（偏差）:  {len(biased_samples):3d} ({len(biased_samples)/total_samples*100:.1f}%)")
        print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  📁 训练集总计:      {len(train_samples):3d} ({len(train_samples)/total_samples*100:.1f}%)")
        print(f"  📁 验证集:          {len(validation_samples):3d} ({len(validation_samples)/total_samples*100:.1f}%)")
        print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  📁 完整数据集:      {len(complete_samples):3d} (100%)")

        print(f"\n✅ 已保存文件:")
        print(f"  - {train_file}")
        print(f"  - {val_file}")
        print(f"  - {complete_file}")

        # 详细统计
        self._print_split_stats(train_samples, validation_samples)

        return {
            'train': train_samples,
            'validation': validation_samples,
            'complete': complete_samples
        }

    def _create_variant(self, sample: Dict, target_correct_ratio: float = 0.5) -> Dict:
        """创建样本变体"""
        variant = sample.copy()

        # 1. 随机化instruction措辞
        variant['instruction'] = self._vary_instruction(sample)

        # 2. 强制平衡verdict
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

        return instruction

    def _force_balance_verdict(self, sample: Dict, target_ratio: float) -> tuple:
        """强制平衡verdict"""
        output = sample['output']

        # 根据目标比例决定verdict
        if random.random() < target_ratio:
            new_verdict = 'correct'
            emoji = '✅'
            opening = random.choice(self.OUTPUT_OPENINGS['correct'])
        else:
            new_verdict = 'needs_review'
            emoji = '❌' if random.random() < 0.5 else '⚠️'
            if emoji == '❌':
                opening = random.choice(self.OUTPUT_OPENINGS['incorrect'])
            else:
                opening = random.choice(self.OUTPUT_OPENINGS['warning'])

        # 替换output开头的verdict标记
        lines = output.split('\n')
        if '❌' in lines[0] or '✅' in lines[0] or '⚠️' in lines[0]:
            lines[0] = opening
            output = '\n'.join(lines)

        return new_verdict, output

    def _print_split_stats(self, train_samples: List[Dict], val_samples: List[Dict]):
        """打印分割后的统计信息"""
        print("\n" + "="*80)
        print("📊 详细统计")
        print("="*80)

        # 训练集统计
        print(f"\n🎯 训练集 Verdict 分布:")
        train_verdicts = [s['verdict_type'] for s in train_samples]
        train_verdict_counter = Counter(train_verdicts)
        for verdict, count in train_verdict_counter.most_common():
            pct = count / len(train_samples) * 100
            bar = '█' * int(pct / 5)
            print(f"  {verdict:20s}: {bar} {count:3d} ({pct:5.1f}%)")

        # 训练集样本类型分布
        print(f"\n📁 训练集 样本类型分布:")
        train_types = [s.get('sample_type', 'unknown') for s in train_samples]
        train_type_counter = Counter(train_types)
        for sample_type, count in train_type_counter.most_common():
            pct = count / len(train_samples) * 100
            bar = '█' * int(pct / 5)
            print(f"  {sample_type:20s}: {bar} {count:3d} ({pct:5.1f}%)")

        # 验证集统计
        print(f"\n🎯 验证集 Verdict 分布:")
        val_verdicts = [s['verdict_type'] for s in val_samples]
        val_verdict_counter = Counter(val_verdicts)
        for verdict, count in val_verdict_counter.most_common():
            pct = count / len(val_samples) * 100
            bar = '█' * int(pct / 5)
            print(f"  {verdict:20s}: {bar} {count:3d} ({pct:5.1f}%)")

        # Instruction多样性
        train_instructions = []
        for s in train_samples:
            words = s['instruction'].split()[:5]
            train_instructions.append(' '.join(words))

        train_instruction_counter = Counter(train_instructions)
        print(f"\n📝 训练集 Instruction 唯一模式数: {len(train_instruction_counter)}")

        print("\n" + "="*80)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="基于真实Zephyr源码生成判断型训练样本，支持多样化和自动分割"
    )
    parser.add_argument(
        '--zephyr',
        type=str,
        default='/home/weng/code/ble/zephyr_sdk/zephyr',
        help='Zephyr代码库路径'
    )
    parser.add_argument(
        '--module-analysis',
        type=str,
        default='dataset/ble_modules_analysis.json',
        help='模块分析结果文件'
    )
    parser.add_argument(
        '--module',
        type=str,
        default='host_gatt',
        help='目标模块ID'
    )
    parser.add_argument(
        '--num-samples',
        type=int,
        default=50,
        help='生成样本数量'
    )
    parser.add_argument(
        '--split-70-20-10',
        action='store_true',
        help='按70:20:10比例分割样本集（70%%原始训练+20%%偏差训练+10%%验证）'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='dataset/modules',
        help='输出目录（默认：dataset/modules）'
    )
    parser.add_argument(
        '--cross-module',
        action='store_true',
        help='启用跨模块调用分析（生成集成测试样本）'
    )
    parser.add_argument(
        '--cross-module-targets',
        type=str,
        nargs='+',
        default=None,
        help='跨模块分析目标模块列表（如: host_att host_l2cap）'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用debug模式（显示详细日志）'
    )

    args = parser.parse_args()

    # 创建生成器
    generator = JudgmentSampleGenerator(args.zephyr, args.module_analysis, debug=args.debug)

    # 生成样本
    logger.info(f"🎯 开始为模块 {args.module} 生成 {args.num_samples} 个样本...")
    samples = generator.generate_for_module(
        args.module,
        args.num_samples,
        include_cross_module=args.cross_module,
        cross_module_targets=args.cross_module_targets
    )

    if args.split_70_20_10:
        # 使用70:20:10分割
        logger.info("📊 使用70:20:10分割模式...")
        diversifier = SampleDiversifier(samples)
        result = diversifier.diversify_70_20_10(args.module, args.output_dir)

        logger.info(f"\n✅ 完成！生成了以下文件：")
        logger.info(f"  - 训练集: {args.output_dir}/{args.module}_train.json ({len(result['train'])}个样本)")
        logger.info(f"  - 验证集: {args.output_dir}/{args.module}_validation.json ({len(result['validation'])}个样本)")
        logger.info(f"  - 完整集: {args.output_dir}/{args.module}_complete.json ({len(result['complete'])}个样本)")
    else:
        # 保存原始样本
        logger.info("💾 保存原始样本...")
        generator.save_samples(args.module, samples, args.output_dir)
        logger.info(f"✅ 完成！样本已保存到: {args.output_dir}/{args.module}_samples.json")

    return 0


if __name__ == '__main__':
    exit(main())
