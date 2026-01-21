#!/usr/bin/env python3
"""
Zephyr BLE 模块解析器
分析Zephyr BLE代码库的结构，识别各个模块，为分模块训练做准备
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BLEModuleClassifier:
    """BLE模块分类器"""

    # Zephyr BLE模块定义
    BLE_MODULES = {
        # === Host层模块 ===
        "host_gatt": {
            "name": "Host - GATT",
            "description": "Generic Attribute Profile - 属性协议和配置文件",
            "keywords": ["gatt", "service", "characteristic", "descriptor", "ccc"],
            "api_prefixes": ["bt_gatt_", "BT_GATT_"],
            "dirs": ["subsys/bluetooth/host"],
            "priority": "CRITICAL"
        },
        "host_l2cap": {
            "name": "Host - L2CAP",
            "description": "Logical Link Control and Adaptation Protocol - 逻辑链路控制",
            "keywords": ["l2cap", "channel", "le_coc", "ecred"],
            "api_prefixes": ["bt_l2cap_", "BT_L2CAP_"],
            "dirs": ["subsys/bluetooth/host/l2cap.c"],
            "priority": "CRITICAL"
        },
        "host_att": {
            "name": "Host - ATT",
            "description": "Attribute Protocol - 属性协议",
            "keywords": ["att", "mtu", "handle", "permission"],
            "api_prefixes": ["bt_att_", "BT_ATT_"],
            "dirs": ["subsys/bluetooth/host/att.c"],
            "priority": "CRITICAL"
        },
        "host_smp": {
            "name": "Host - SMP",
            "description": "Security Manager Protocol - 安全管理协议",
            "keywords": ["smp", "pairing", "encryption", "bonding", "mitm"],
            "api_prefixes": ["bt_smp_", "BT_SMP_"],
            "dirs": ["subsys/bluetooth/host/smp"],
            "priority": "HIGH"
        },
        "host_conn": {
            "name": "Host - Connection",
            "description": "连接管理 - 连接参数、状态管理",
            "keywords": ["conn", "connection", "disconnect", "le_param"],
            "api_prefixes": ["bt_conn_", "BT_CONN_"],
            "dirs": ["subsys/bluetooth/host/conn.c"],
            "priority": "CRITICAL"
        },
        "host_adv": {
            "name": "Host - Advertising",
            "description": "广播管理 - 广播参数、数据",
            "keywords": ["adv", "advertising", "ad", "scan_response"],
            "api_prefixes": ["bt_le_adv_", "BT_LE_ADV_"],
            "dirs": ["subsys/bluetooth/host/adv.c"],
            "priority": "HIGH"
        },
        "host_scan": {
            "name": "Host - Scanning",
            "description": "扫描管理 - 设备发现",
            "keywords": ["scan", "scanning", "discovery"],
            "api_prefixes": ["bt_le_scan_", "BT_LE_SCAN_"],
            "dirs": ["subsys/bluetooth/host/scan.c"],
            "priority": "HIGH"
        },

        # === Controller层模块 ===
        "ctrl_ll": {
            "name": "Controller - Link Layer",
            "description": "链路层 - 底层协议实现",
            "keywords": ["link layer", "ull", "lll", "radio"],
            "api_prefixes": ["ll_", "ull_"],
            "dirs": ["subsys/bluetooth/controller/ll_sw"],
            "priority": "LOW"
        },
        "ctrl_hci": {
            "name": "Controller - HCI",
            "description": "Host Controller Interface - 主机控制器接口",
            "keywords": ["hci", "command", "event", "acl"],
            "api_prefixes": ["bt_hci_", "BT_HCI_"],
            "dirs": ["subsys/bluetooth/controller/hci"],
            "priority": "MEDIUM"
        },

        # === Services模块 ===
        "services_std": {
            "name": "Services - Standard",
            "description": "标准GATT服务（心率、电池等）",
            "keywords": ["bas", "hrs", "dis", "battery", "heart_rate"],
            "api_prefixes": ["bt_bas_", "bt_hrs_"],
            "dirs": ["subsys/bluetooth/services"],
            "priority": "MEDIUM"
        },

        # === 特殊应用领域 ===
        "mesh": {
            "name": "Bluetooth Mesh",
            "description": "蓝牙Mesh网络",
            "keywords": ["mesh", "provision", "proxy", "network"],
            "api_prefixes": ["bt_mesh_", "BT_MESH_"],
            "dirs": ["subsys/bluetooth/mesh"],
            "priority": "SPECIALIZED"
        },
        "audio": {
            "name": "Bluetooth Audio",
            "description": "蓝牙音频（LE Audio）",
            "keywords": ["audio", "a2dp", "hfp", "bap", "asp", "pacs"],
            "api_prefixes": ["bt_audio_", "bt_bap_"],
            "dirs": ["subsys/bluetooth/audio"],
            "priority": "SPECIALIZED"
        },
        "direction_finding": {
            "name": "Direction Finding",
            "description": "方向查找/AoA/AoD",
            "keywords": ["df", "direction finding", "aoa", "aod", "cte"],
            "api_prefixes": ["bt_df_", "BT_DF_"],
            "dirs": ["subsys/bluetooth/host/df"],
            "priority": "SPECIALIZED"
        },

        # === 工具和调试 ===
        "shell": {
            "name": "Shell Commands",
            "description": "蓝牙Shell命令和调试工具",
            "keywords": ["shell", "cmd", "debug"],
            "api_prefixes": ["bt_shell_"],
            "dirs": ["subsys/bluetooth/shell"],
            "priority": "LOW"
        },
    }

    def __init__(self, zephyr_path: str):
        self.zephyr_path = Path(zephyr_path)
        self.module_files = defaultdict(list)
        self.module_apis = defaultdict(set)
        self.file_modules = {}

    def analyze_all(self) -> Dict:
        """分析所有BLE模块"""
        logger.info("🔍 开始分析Zephyr BLE模块结构...")

        results = {
            "modules": {},
            "statistics": {
                "total_files": 0,
                "total_apis": 0,
                "module_coverage": {}
            }
        }

        # 1. 识别每个模块的文件
        for module_id, module_info in self.BLE_MODULES.items():
            logger.info(f"📦 分析模块: {module_info['name']}")

            module_files = self._identify_module_files(module_id)
            module_apis = self._extract_module_apis(module_id, module_files)

            results["modules"][module_id] = {
                "info": module_info,
                "files": module_files,
                "apis": sorted(list(module_apis)),
                "file_count": len(module_files),
                "api_count": len(module_apis)
            }

            results["statistics"]["total_files"] += len(module_files)
            results["statistics"]["total_apis"] += len(module_apis)

        # 2. 生成模块关系图
        results["dependencies"] = self._analyze_module_dependencies()

        # 3. 生成训练优先级建议
        results["training_priority"] = self._calculate_training_priority(results)

        return results

    def _identify_module_files(self, module_id: str) -> List[str]:
        """识别属于某个模块的文件"""
        module_info = self.BLE_MODULES[module_id]
        files = []

        # 方法1：基于目录
        if "dirs" in module_info:
            for dir_pattern in module_info["dirs"]:
                dir_path = self.zephyr_path / dir_pattern
                if dir_path.exists():
                    if dir_path.is_file():
                        files.append(str(dir_path.relative_to(self.zephyr_path)))
                    else:
                        for ext in ['*.c', '*.h']:
                            for file_path in dir_path.rglob(ext):
                                rel_path = str(file_path.relative_to(self.zephyr_path))
                                files.append(rel_path)

        # 方法2：基于关键词搜索
        if not files and "keywords" in module_info:
            keywords = module_info["keywords"]
            search_dirs = [
                self.zephyr_path / "subsys" / "bluetooth" / "host",
                self.zephyr_path / "subsys" / "bluetooth" / "services"
            ]

            for search_dir in search_dirs:
                if search_dir.exists():
                    for file_path in search_dir.rglob('*.c'):
                        # 检查文件内容是否包含关键词
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                if any(kw in content.lower() for kw in keywords):
                                    rel_path = str(file_path.relative_to(self.zephyr_path))
                                    if rel_path not in files:
                                        files.append(rel_path)
                        except Exception:
                            continue

        return sorted(list(set(files)))

    def _extract_module_apis(self, module_id: str, files: List[str]) -> Set[str]:
        """从文件中提取模块相关的API"""
        module_info = self.BLE_MODULES[module_id]
        apis = set()

        if "api_prefixes" not in module_info:
            return apis

        api_prefixes = module_info["api_prefixes"]

        for file_rel in files[:50]:  # 限制文件数量避免太慢
            file_path = self.zephyr_path / file_rel
            if not file_path.exists():
                continue

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                for prefix in api_prefixes:
                    # 查找API定义和使用
                    pattern = rf'\b{re.escape(prefix)}[\w_]+'
                    matches = re.findall(pattern, content)
                    apis.update(matches)

            except Exception as e:
                logger.warning(f"读取文件失败 {file_rel}: {e}")

        return apis

    def _analyze_module_dependencies(self) -> Dict[str, List[str]]:
        """分析模块间依赖关系"""
        dependencies = defaultdict(set)

        # 简化版：基于已知的依赖关系
        known_deps = {
            "host_gatt": ["host_att", "host_conn"],
            "host_att": ["host_l2cap", "host_conn"],
            "host_l2cap": ["host_conn"],
            "host_smp": ["host_conn", "host_l2cap"],
            "host_adv": ["host_conn"],
            "host_scan": ["host_conn"],
            "services_std": ["host_gatt", "host_conn"],
            "mesh": ["host_gatt", "host_adv"],
            "audio": ["host_gatt", "host_conn"],
        }

        for module, deps in known_deps.items():
            if module in self.BLE_MODULES:
                dependencies[module] = [d for d in deps if d in self.BLE_MODULES]

        return dict(dependencies)

    def _calculate_training_priority(self, results: Dict) -> List[Dict]:
        """计算训练优先级"""
        priority_list = []

        # 优先级评分
        priority_scores = {
            "CRITICAL": 100,
            "HIGH": 80,
            "MEDIUM": 60,
            "SPECIALIZED": 40,
            "LOW": 20
        }

        for module_id, module_data in results["modules"].items():
            info = module_data["info"]
            priority_score = priority_scores.get(info["priority"], 50)

            # 根据文件数量调整
            file_score = min(module_data["file_count"], 50)
            total_score = priority_score + file_score

            priority_list.append({
                "module_id": module_id,
                "name": info["name"],
                "priority": info["priority"],
                "file_count": module_data["file_count"],
                "api_count": module_data["api_count"],
                "score": total_score
            })

        # 按分数排序
        priority_list.sort(key=lambda x: x["score"], reverse=True)

        return priority_list

    def _print_summary(self, results: Dict, verbose: bool = False):
        """打印分析摘要"""
        print("\n" + "=" * 80)
        print("📊 Zephyr BLE 模块分析摘要")
        print("=" * 80)

        print(f"\n总文件数: {results['statistics']['total_files']}")
        print(f"总API数: {results['statistics']['total_apis']}")
        print(f"模块数量: {len(results['modules'])}")

        print("\n" + "=" * 80)
        print("🎯 模块详情 (Top 10):")
        print("=" * 80)

        for i, module_priority in enumerate(results["training_priority"][:10], 1):
            module_id = module_priority['module_id']
            module_data = results["modules"][module_id]
            files = module_data.get('files', [])
            apis = module_data.get('apis', [])

            print(f"\n{i}. {module_priority['name']} ({module_id})")
            print(f"   优先级: {module_priority['priority']}")
            print(f"   文件数: {module_priority['file_count']}")
            print(f"   API数:  {module_priority['api_count']}")
            print(f"   评分:   {module_priority['score']}")

            # 显示关键文件（前5个）
            if files:
                print(f"   关键文件:")
                display_count = len(files) if verbose else min(5, len(files))
                for j, file_path in enumerate(files[:display_count], 1):
                    print(f"     {j}. {file_path}")
                if not verbose and len(files) > 5:
                    print(f"     ... 还有 {len(files) - 5} 个文件 (使用 --verbose 查看全部)")

            # 显示关键API（前5个）
            if apis:
                print(f"   关键API:")
                display_count = len(apis) if verbose else min(5, len(apis))
                for j, api in enumerate(sorted(apis)[:display_count], 1):
                    print(f"     {j}. {api}")
                if not verbose and len(apis) > 5:
                    print(f"     ... 还有 {len(apis) - 5} 个API")

        print("\n" + "=" * 80)
        print("📈 训练优先级建议:")
        print("=" * 80)

        for i, module in enumerate(results["training_priority"], 1):
            print(f"{i:2d}. {module['name']:40s} [文件:{module['file_count']:3d}, API:{module['api_count']:4d}]")

    def save_results(self, results: Dict, output_file: str):
        """保存分析结果"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        logger.info(f"✅ 分析结果已保存到: {output_file}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="分析Zephyr BLE模块结构")
    parser.add_argument(
        '--zephyr',
        type=str,
        default='/home/weng/code/ble/zephyr_sdk/zephyr',
        help='Zephyr代码库路径'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='dataset/ble_modules_analysis.json',
        help='输出文件路径'
    )
    parser.add_argument(
        '--module',
        type=str,
        help='只分析指定模块（可选）'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='显示完整的文件和API列表'
    )

    args = parser.parse_args()

    # 创建分析器
    classifier = BLEModuleClassifier(args.zephyr)

    # 执行分析
    if args.module:
        logger.info(f"只分析模块: {args.module}")
        # TODO: 实现单模块分析
        results = {}
    else:
        results = classifier.analyze_all()

        # 使用 verbose 参数控制输出详细程度
        classifier._print_summary(results, verbose=args.verbose)

        classifier.save_results(results, args.output)

    print("\n✅ 模块分析完成！")
    print("💡 下一步：根据模块分析结果，为每个模块生成专门的训练样本")
    print("💡 提示：使用 --verbose 参数查看完整的文件和API列表")

    return 0


if __name__ == '__main__':
    exit(main())
