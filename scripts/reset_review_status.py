#!/usr/bin/env python3
"""
重置 Golden Testset 的审核状态

将所有问题的审核状态改回未审查，以便重新进行审核流程。
用法:
    pixi run python scripts/reset_review_status.py <input_file> [output_file]

示例:
    pixi run python scripts/reset_review_status.py data/golden_testset/golden_150.json
    pixi run python scripts/reset_review_status.py data/golden_testset/golden_150.json data/golden_testset/golden_150_reset.json
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


def reset_review_status(input_path: str, output_path: str = None):
    """重置问题的审核状态"""
    input_file = Path(input_path)

    if not input_file.exists():
        print(f"错误：文件不存在 - {input_file}")
        sys.exit(1)

    # 如果没有指定输出文件，则原地修改并先备份
    if output_path is None:
        output_file = input_file
        backup_file = input_file.with_suffix(
            f".backup{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        print(f"创建备份：{backup_file}")
        shutil.copy2(input_file, backup_file)
    else:
        output_file = Path(output_path)

    # 读取文件
    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)

    # 统计信息
    total_questions = len(data.get("questions", []))
    reset_count = 0

    # 重置每个问题的审核状态
    for question in data.get("questions", []):
        if "metadata" in question:
            metadata = question["metadata"]

            # 检查是否需要重置
            if any(
                key in metadata for key in ["review_status", "reviewed", "reviewed_at"]
            ):
                # 删除审核相关字段
                metadata.pop("review_status", None)
                metadata.pop("reviewed", None)
                metadata.pop("reviewed_at", None)
                metadata.pop("reviewer_notes", None)
                reset_count += 1

    # 保存文件
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 输出结果
    print(f"\n{'=' * 60}")
    print("审核状态重置完成")
    print(f"{'=' * 60}")
    print(f"输入文件：{input_file}")
    print(f"输出文件：{output_file}")
    print(f"总题目数：{total_questions}")
    print(f"已重置：{reset_count} 题")
    print(f"未变更：{total_questions - reset_count} 题")

    if output_path is None:
        print(f"\n备份文件：{backup_file}")
        print(f"如需恢复，可运行：cp {backup_file} {input_file}")

    print("\n现在可以重新运行审核脚本:")
    print(f"  pixi run python scripts/review_golden_testset.py {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("错误：请提供输入文件路径")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    reset_review_status(input_path, output_path)
