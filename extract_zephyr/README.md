# Zephyr BLE Training Dataset Generator

Generate judgment-based training samples from Zephyr BLE source code.

## 🚀 Quick Start

### Step 1: Analyze Zephyr Modules (Run Once)

```bash
python3 zephyr_parse/analyze_ble_modules.py \
    --zephyr /path/to/zephyr \
    --output dataset/ble_modules_analysis.json
```

### Step 2: Generate Training Samples

```bash
python3 app/generate_module_samples.py \
    --zephyr /path/to/zephyr \
    --module-analysis dataset/ble_modules_analysis.json \
    --module host_gatt \
    --num-samples 100 \
    --split-65-20-15
```

**Output:** `dataset/modules/host_gatt_train.json` and `host_gatt_validation.json`

---

## 📋 Available Modules

| Module | Command |
|--------|---------|
| GATT | `--module host_gatt` |
| ATT | `--module host_att` |
| L2CAP | `--module host_l2cap` |
| Connection | `--module host_conn` |

---

## 📊 Sample Format

```json
{
  "instruction": "Does `bt_gatt_notify` comply with BLE protocol?",
  "input": "File: subsys/bluetooth/host/gatt.c\n```c\n{code}\n```",
  "output": "✅ **Correct**\n\nDetailed analysis...",
  "verdict_type": "correct"
}
```

---

## 💡 Generate for All Modules

```bash
for module in host_gatt host_att host_l2cap host_conn; do
    python3 app/generate_module_samples.py \
        --module $module \
        --num-samples 100 \
        --split-65-20-15
done
```

---

## 📁 Output Files

- `{module}_train.json` - Training set (85 samples)
- `{module}_validation.json` - Validation set (15 samples)
- `{module}_complete.json` - Complete dataset (100 samples)

---
- [Zephyr Bluetooth API](https://docs.zephyrproject.org/latest/reference/bluetooth/index.html)
- [Bluetooth Core Specification](https://www.bluetooth.com/specifications/bluetooth-core-specification/)
- [Zephyr Coding Style](https://docs.zephyrproject.org/latest/develop/coding/index.html)