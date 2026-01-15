#!/usr/bin/env python3
"""
基于真实 Zephyr 源码生成判断型训练样本
从模块分析结果中获取文件列表，分析源码，生成样本
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ZephyrCodeAnalyzer:
    """Zephyr 代码分析器 - 从源码中提取信息"""

    def __init__(self, zephyr_path: str):
        self.zephyr_path = Path(zephyr_path)

    def extract_functions_from_file(self, file_path: str) -> List[Dict]:
        """从文件中提取函数定义"""
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

        # 匹配函数定义
        # 模式：返回类型 函数名(参数) { 函数体
        pattern = r'(?:static\s+)?(?:const\s+)?(?:\w+\s+)+?(\w+)\s*\([^)]*\)\s*\{'

        matches = re.finditer(pattern, content)

        for match in matches:
            func_name = match.group(1)

            # 跳过一些函数
            if func_name.startswith('_') and len(func_name) < 3:
                continue
            if func_name in ['printk', 'memcpy', 'memset', 'strlen']:
                continue

            # 获取函数体（简化版）
            start_pos = match.start()
            brace_start = content.find('{', start_pos)

            if brace_start == -1:
                continue

            # 提取函数体前500字符作为样本
            brace_end = self._find_matching_brace(content, brace_start)
            if brace_end == -1:
                func_body = content[brace_start:brace_start+500]
            else:
                func_body = content[brace_start:min(brace_end, brace_start+500)]

            functions.append({
                'name': func_name,
                'file': file_path,
                'body': func_body,
                'start': start_pos
            })

        return functions

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

    def __init__(self, zephyr_path: str, module_analysis_file: str):
        self.zephyr_path = Path(zephyr_path)
        self.analyzer = ZephyrCodeAnalyzer(zephyr_path)
        self.module_data = self._load_module_analysis(module_analysis_file)

    def _load_module_analysis(self, analysis_file: str) -> Dict:
        """加载模块分析结果"""
        with open(analysis_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def generate_for_module(self, module_id: str, num_samples: int = 50) -> List[Dict]:
        """为指定模块生成样本"""
        if module_id not in self.module_data["modules"]:
            logger.error(f"模块不存在: {module_id}")
            return []

        module_info = self.module_data["modules"][module_id]
        logger.info(f"🎯 为模块 {module_info['info']['name']} 生成 {num_samples} 个样本")

        samples = []

        # 1. 从源文件中提取函数，生成函数分析样本
        functions_samples = self._generate_function_analysis_samples(
            module_id, module_info, num_samples // 2
        )
        samples.extend(functions_samples)

        # 2. 从API使用中生成判断样本
        api_samples = self._generate_api_usage_samples(
            module_id, module_info, num_samples // 2
        )
        samples.extend(api_samples)

        # 3. 如果还不够，生成通用样本
        if len(samples) < num_samples:
            generic_samples = self._generate_generic_samples(
                module_id, module_info, num_samples - len(samples)
            )
            samples.extend(generic_samples)

        # 限制到请求的数量
        return samples[:num_samples]

    def _generate_function_analysis_samples(
        self, module_id: str, module_info: Dict, num_samples: int
    ) -> List[Dict]:
        """基于函数分析生成样本"""
        samples = []
        files = module_info.get('files', [])

        for file_path in files[:20]:  # 最多处理20个文件
            if len(samples) >= num_samples:
                break

            functions = self.analyzer.extract_functions_from_file(file_path)

            for func in functions:
                if len(samples) >= num_samples:
                    break

                # 生成函数分析样本
                sample = self._create_function_sample(module_id, func, file_path)
                if sample:
                    samples.append(sample)

        logger.info(f"  📝 生成了 {len(samples)} 个函数分析样本")
        return samples

    def _generate_api_usage_samples(
        self, module_id: str, module_info: Dict, num_samples: int
    ) -> List[Dict]:
        """基于API使用生成样本"""
        samples = []
        files = module_info.get('files', [])
        apis = module_info.get('apis', [])

        # 从API名称推断前缀
        api_prefixes = self._extract_api_prefixes(apis)

        for file_path in files[:10]:
            if len(samples) >= num_samples:
                break

            patterns = self.analyzer.extract_api_usage_patterns(file_path, api_prefixes)

            for pattern in patterns:
                if len(samples) >= num_samples:
                    break

                sample = self._create_api_usage_sample(module_id, pattern, file_path)
                if sample:
                    samples.append(sample)

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

    def _create_function_sample(self, module_id: str, func: Dict, file_path: str) -> Dict:
        """创建函数分析样本"""
        func_name = func['name']
        func_body = func['body']
        file_rel = file_path

        # 根据函数名判断类型
        if 'read' in func_name or 'write' in func_name:
            return self._create_read_write_sample(module_id, func_name, func_body, file_rel)
        elif 'notify' in func_name or 'indicate' in func_name:
            return self._create_notify_sample(module_id, func_name, func_body, file_rel)
        elif 'discovery' in func_name or 'discover' in func_name:
            return self._create_discovery_sample(module_id, func_name, func_body, file_rel)
        else:
            return self._create_general_function_sample(module_id, func_name, func_body, file_rel)

    def _create_read_write_sample(
        self, module_id: str, func_name: str, func_body: str, file_path: str
    ) -> Dict:
        """创建读写操作样本"""
        # 清理函数体
        clean_body = self._clean_code(func_body[:300])

        if not clean_body or len(clean_body) < 50:
            return None

        # 分析代码特征
        has_offset_check = 'offset' in clean_body and ('if' in clean_body or 'check' in clean_body.lower())
        has_len_check = ('len' in clean_body or 'sizeof' in clean_body or 'size' in clean_body) and '>' in clean_body
        has_error_handling = ('return' in clean_body) and ('err' in clean_body or 'EINVAL' in clean_body or 'BT_ATT' in clean_body)
        has_null_check = 'NULL' in clean_body or ('!' in clean_body and ('ptr' in clean_body or 'conn' in clean_body))

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

        # 分析代码特征
        has_conn_check = 'conn' in clean_body and ('if' in clean_body or '!' in clean_body)
        has_ccc_check = ('ccc' in clean_body.lower() or 'config' in clean_body.lower() or
                         'notify' in clean_body.lower() or 'enabled' in clean_body.lower())
        has_error_handling = 'err' in clean_body and ('return' in clean_body or 'if' in clean_body)
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

    def save_samples(self, module_id: str, samples: List[Dict]):
        """保存样本"""
        if not samples:
            logger.warning(f"模块 {module_id} 没有生成样本")
            return

        output_dir = Path('dataset/modules')
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{module_id}_samples.json"

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


def main():
    import argparse

    parser = argparse.ArgumentParser(description="基于真实Zephyr源码生成判断型训练样本")
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

    args = parser.parse_args()

    # 创建生成器
    generator = JudgmentSampleGenerator(args.zephyr, args.module_analysis)

    # 生成样本
    samples = generator.generate_for_module(args.module, args.num_samples)

    # 保存
    generator.save_samples(args.module, samples)

    return 0


if __name__ == '__main__':
    exit(main())
