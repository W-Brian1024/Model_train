# Zephyr BLE 训练样本生成器

从 Zephyr BLE 源码生成判断型训练样本。

## 🚀 快速开始

### 步骤 1: 分析 Zephyr 模块（只需运行一次）

```bash
python3 zephyr_parse/analyze_ble_modules.py \
    --zephyr /path/to/zephyr \
    --output dataset/ble_modules_analysis.json
```

### 步骤 2: 生成训练样本

```bash
python3 app/generate_module_samples.py \
    --zephyr /path/to/zephyr \
    --module-analysis dataset/ble_modules_analysis.json \
    --module host_gatt \
    --num-samples 100 \
    --split-70-20-10
```

**输出文件：** `dataset/modules/host_gatt_train.json` 和 `host_gatt_validation.json`

---

## 📋 可用模块

| 模块 | 命令 |
|------|------|
| GATT | `--module host_gatt` |
| ATT | `--module host_att` |
| L2CAP | `--module host_l2cap` |
| 连接管理 | `--module host_conn` |

---

## 📊 样本格式

```json
{
  "instruction": "`bt_gatt_notify` 函数是否符合 BLE 协议？",
  "input": "文件：subsys/bluetooth/host/gatt.c\n```c\n{代码}\n```",
  "output": "✅ **符合规范**\n\n详细分析...",
  "verdict_type": "correct"
}
```

---

## 💡 批量生成所有模块

```bash
for module in host_gatt host_att host_l2cap host_conn; do
    python3 app/generate_module_samples.py \
        --module $module \
        --num-samples 100 \
        --split-70-20-10
done
```

---

## 📁 输出文件

- `{module}_train.json` - 训练集（90个样本 = 70原始+20偏差）
- `{module}_validation.json` - 验证集（10个样本）
- `{module}_complete.json` - 完整数据集（100个样本）

---

## 🔧 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--zephyr` | Zephyr 源码路径 | `/home/weng/code/ble/zephyr_sdk/zephyr` |
| `--module` | 目标模块 ID | `host_gatt` |
| `--num-samples` | 生成样本数量 | `50` |
| `--split-70-20-10` | 启用 70:20:10 自动分割 | 无 |

---

- [Zephyr Bluetooth API](https://docs.zephyrproject.org/latest/reference/bluetooth/index.html)
- [Bluetooth Core Specification](https://www.bluetooth.com/specifications/bluetooth-core-specification/)
- [Zephyr 编码规范](https://docs.zephyrproject.org/latest/develop/coding/index.html)
