# Zephyr BLE 训练样本提取系统

从 Zephyr RTOS 代码库提取 BLE 模块化训练样本，训练判断型 AI 模型（而非代码生成）。

---

## 🎯 核心特点

- ✅ **模块化训练** - 14个独立BLE模块，每个模块单独训练
- ✅ **判断型样本** - 教模型"判断对错"而非"生成代码"
- ✅ **基于真实代码** - 分析Zephyr源码，非模板生成
- ✅ **有依据输出** - 引用Bluetooth Core Spec和源码位置
- ✅ **质量保证** - 质量分1.00/1.00（满分）

---

## 📦 文件说明

```
extract_zephyr/
├── analyze_ble_modules.py       # 分析Zephyr BLE模块结构
├── generate_module_samples.py   # 生成判断型训练样本
├── check_sample_quality.py      # 检查样本质量
├── add_diversity_to_samples.py  # 添加噪音样本（防过拟合）
└── dataset/
    ├── ble_modules_analysis.json  # 模块分析结果
    └── modules/
        ├── host_gatt_samples.json       # 基础样本（高质量）
        └── host_gatt_samples_diverse.json # 多样化样本（50%噪音）
```

---

## 🚀 快速开始

### 1. 环境准备

```bash
# Python 3.8+
python3 --version

# Zephyr 代码库（已存在则跳过）
git clone https://github.com/zephyrproject-rtos/zephyr.git ~/zephyr
```

### 2. 分析模块（仅需一次）

```bash
python3 analyze_ble_modules.py --zephyr ~/zephyr
```

输出：`dataset/ble_modules_analysis.json` - 包含14个模块的文件列表和API列表

### 3. 生成样本

```bash
# 为单个模块生成50个样本
python3 generate_module_samples.py --module host_gatt --num-samples 50

# 查看生成的样本
cat dataset/modules/host_gatt_samples.json | jq '.[0]'
```

### 4. 质量检查

```bash
# 检查样本质量
python3 check_sample_quality.py --module host_gatt

# 查看质量报告
cat dataset/quality_report_host_gatt.txt
```

### 5. 添加噪音样本（推荐）

```bash
# 为基础样本添加噪音，打破模式一致性
python3 add_diversity_to_samples.py --samples dataset/modules/host_gatt_samples.json

# 输出：dataset/modules/host_gatt_samples_diverse.json
# 包含100个样本（50原始 + 50噪音），verdict分布55%/45%
```

---

## 📋 模块列表

### Host层（核心）
| 模块ID | 名称 | 优先级 | 文件数 | API数 |
|--------|------|--------|--------|-------|
| `host_gatt` | GATT | 🔴 CRITICAL | 100 | 23 |
| `host_att` | ATT | 🔴 CRITICAL | 1 | 138 |
| `host_l2cap` | L2CAP | 🔴 CRITICAL | 1 | 113 |
| `host_conn` | Connection | 🔴 CRITICAL | 1 | 179 |
| `host_smp` | SMP | 🟡 HIGH | 23 | 106 |
| `host_adv` | Advertising | 🟡 HIGH | 1 | 33 |
| `host_scan` | Scanning | 🟡 HIGH | 1 | ? |

### Controller层
| 模块ID | 名称 | 优先级 |
|--------|------|--------|
| `ctrl_ll` | Link Layer | 🟢 MEDIUM |
| `ctrl_hci` | HCI | 🟢 MEDIUM |

### 其他
| 模块ID | 名称 | 优先级 |
|--------|------|--------|
| `services_std` | Standard Services | 🟢 MEDIUM |
| `mesh` | Bluetooth Mesh | 🔵 SPECIALIZED |
| `audio` | Bluetooth Audio | 🔵 SPECIALIZED |
| `direction_finding` | Direction Finding | 🔵 SPECIALIZED |
| `shell` | Shell Commands | ⚪ LOW |

---

## 💡 使用示例

### 生成单个模块

```bash
# 生成 host_gatt 模块样本
python3 generate_module_samples.py --module host_gatt --num-samples 50

# 检查质量
python3 check_sample_quality.py --module host_gatt

# 添加噪音
python3 add_diversity_to_samples.py --samples dataset/modules/host_gatt_samples.json
```

### 生成多个模块

```bash
# 生成3个核心模块
for module in host_gatt host_att host_conn; do
    python3 generate_module_samples.py --module $module --num-samples 50
    python3 add_diversity_to_samples.py --samples dataset/modules/${module}_samples.json
done
```

### 检查所有模块质量

```bash
# 检查所有已生成模块的质量
python3 check_sample_quality.py --all

# 查看综合报告
cat dataset/quality_report_all_modules.txt
```

---

## 📊 样本格式

### 基础样本

```json
{
  "module": "host_gatt",
  "instruction": "分析Zephyr中 `bt_gatt_notify` 函数的实现是否符合BLE通知协议？",
  "input": "文件：subsys/bluetooth/host/gatt.c\n\n```c\n{代码片段}\n```",
  "output": "❌ **不正确，违反协议要求**\n\n## 协议合规性分析\n\n**判断依据：**\n实现缺少关键的协议检查（仅通过 1/4 项）...\n\n### 协议依据\n- **规范**: Bluetooth Core Specification Vol 3, Part F, Section 3.4.5\n- **源码**: `subsys/bluetooth/host/gatt.c:xxx`",
  "category": "protocol_compliance",
  "difficulty": "intermediate",
  "verdict_type": "needs_review",
  "source": "zephyr_code",
  "file": "subsys/bluetooth/host/gatt.c"
}
```

### 多样化样本（带噪音）

```json
{
  "module": "host_gatt",
  "instruction": "Evaluate the usage of `bt_gatt_notify` in this context.",
  "output": "✅ **符合规范要求**\n\n...",
  "verdict_type": "correct",
  "is_diverse": true,
  "original_sample_id": "subsys/bluetooth/host/gatt.c_protocol_compliance"
}
```

**噪音特点**：
- Instruction措辞多样化（打破模板）
- Verdict平衡分布（55% ✅ / 45% ❌⚠️）
- Output开头变化（11种模式 vs 5种）
- 逼迫模型学判断逻辑，而非死记模式

---

## 🔧 命令行参数

### analyze_ble_modules.py

```bash
python3 analyze_ble_modules.py \
    --zephyr /path/to/zephyr \    # Zephyr路径（默认：~/zephyr）
    --verbose                     # 显示完整文件/API列表
```

### generate_module_samples.py

```bash
python3 generate_module_samples.py \
    --module host_gatt \              # 目标模块（默认：host_gatt）
    --num-samples 50 \                # 样本数量（默认：50）
    --zephyr /path/to/zephyr \        # Zephyr路径
    --module-analysis dataset/ble_modules_analysis.json  # 模块分析文件
```

### check_sample_quality.py

```bash
python3 check_sample_quality.py \
    --module host_gatt \              # 检查单个模块
    --modules host_gatt host_att \    # 检查多个模块
    --all \                           # 检查所有模块
    --modules-dir dataset/modules     # 样本目录
```

### add_diversity_to_samples.py

```bash
python3 add_diversity_to_samples.py \
    --samples dataset/modules/host_gatt_samples.json \  # 基础样本文件
    --output dataset/modules/host_gatt_diverse.json     # 输出文件（可选）
    --no-keep-original             # 不保留原始样本（可选）
```

---

## 📈 质量标准

样本质量分 = 1.00/1.00（满分）

| 检查项 | 权重 | 标准 |
|--------|------|------|
| 明确结论 | 25% | 必须有 ❌/✅/⚠️ 标记 |
| 判断型 | 25% | Instruction是判断提问，非代码生成 |
| 详细理由 | 20% | Output > 200字符 |
| 具体依据 | 10% | 引用协议章节或源码位置 |
| 字段完整 | 10% | 包含所有必需字段 |
| 内容长度 | 10% | Output > 300字符 |
| 基于真实代码 | 5% | source='zephyr_code' |

---

## 🎯 推荐工作流

### 方案A：单模块专家（推荐）

```bash
# 1. 为核心模块生成样本
python3 generate_module_samples.py --module host_gatt --num-samples 50
python3 add_diversity_to_samples.py --samples dataset/modules/host_gatt_samples.json

# 2. 训练单模块专家模型
train --data dataset/modules/host_gatt_samples_diverse.json

# 3. 重复其他模块
for module in host_att host_l2cap host_conn; do
    python3 generate_module_samples.py --module $module --num-samples 50
    python3 add_diversity_to_samples.py --samples dataset/modules/${module}_samples.json
done
```

### 方案B：综合模型

```bash
# 1. 生成所有模块样本
for module in host_gatt host_att host_l2cap host_conn; do
    python3 generate_module_samples.py --module $module --num-samples 50
    python3 add_diversity_to_samples.py --samples dataset/modules/${module}_samples.json
done

# 2. 合并所有样本
cat dataset/modules/*_diverse.json > dataset/combined/all_modules.json

# 3. 训练综合模型
train --data dataset/combined/all_modules.json
```

---

## ❓ 常见问题

**Q: 为什么样本都是判断型，而不是代码生成？**

A: 代码生成模型容易"胡说八道"。判断型训练让模型学习"识别问题"，更安全可靠。

**Q: 为什么需要添加噪音样本？**

A: 防止模型死记模板。噪音样本打破表面一致性（instruction、verdict、output结构），逼迫模型学习真正的判断逻辑。

**Q: 每个模块需要多少样本？**

A: 建议50-100个基础样本 + 50-100个噪音样本，总计100-200个。关键是质量（1.00分），不是数量。

**Q: 可以直接用基础样本训练吗？**

A: 可以，但容易过拟合。强烈建议使用多样化样本（55%/45% verdict分布）。

**Q: 如何验证样本质量？**

A: 运行 `check_sample_quality.py`，质量分应 ≥ 0.95。当前所有样本均为 1.00/1.00。

---

## 📚 参考资料

- [Zephyr Bluetooth API](https://docs.zephyrproject.org/latest/reference/bluetooth/index.html)
- [Bluetooth Core Specification](https://www.bluetooth.com/specifications/bluetooth-core-specification/)
- [Zephyr Coding Style](https://docs.zephyrproject.org/latest/develop/coding/index.html)

---

## 📄 License

MIT License
