"""
数据统计脚本

功能：
- 扫描 data/sources/ 目录下的所有数据
- 按数据类型分类统计
- 输出详细的统计报告

作者：挑战杯团队
创建日期：2026-07-15
"""

import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config


def count_files_by_extension(directory: Path) -> dict[str, int]:
    """统计目录下各扩展名的文件数量"""
    counts = defaultdict(int)
    if directory.exists():
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                ext = file_path.suffix.lower()
                counts[ext] += 1
    return dict(counts)


def count_files_by_type(directory: Path) -> dict[str, int]:
    """按数据类型统计文件数量"""
    type_counts = defaultdict(int)
    
    if not directory.exists():
        return dict(type_counts)
    
    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue
        
        ext = file_path.suffix.lower()
        
        # 按扩展名分类
        if ext == ".pdf":
            type_counts["论文 PDF"] += 1
        elif ext == ".json":
            # 进一步细分 JSON 类型
            rel_path = file_path.relative_to(directory)
            if "metadata" in str(rel_path):
                type_counts["元数据 JSON"] += 1
            elif "records" in str(rel_path):
                type_counts["Zenodo 记录"] += 1
            else:
                type_counts["其他 JSON"] += 1
        elif ext in [".obj", ".stl", ".ply", ".glb"]:
            type_counts["3D 模型文件"] += 1
        elif ext in [".urdf", ".xacro", ".sdf", ".mjcf"]:
            type_counts["机器人描述文件"] += 1
        elif ext in [".npy", ".npz"]:
            type_counts["数值数据文件"] += 1
        elif ext in [".xml", ".usd", ".usda"]:
            type_counts["配置文件"] += 1
        elif ext in [".zip", ".tar", ".gz", ".bz2", ".7z"]:
            type_counts["压缩包"] += 1
        else:
            type_counts["其他文件"] += 1
    
    return dict(type_counts)


def get_directory_stats(directory: Path) -> dict:
    """获取目录统计信息"""
    if not directory.exists():
        return {"exists": False, "file_count": 0, "size_bytes": 0}
    
    file_count = 0
    total_size = 0
    
    for file_path in directory.rglob("*"):
        if file_path.is_file():
            file_count += 1
            total_size += file_path.stat().st_size
    
    return {
        "exists": True,
        "file_count": file_count,
        "size_bytes": total_size,
        "size_mb": round(total_size / (1024 * 1024), 2)
    }


def main():
    print("=" * 70)
    print("  数据统计报告")
    print("=" * 70)
    print()
    
    data_root = config.DATA_DIR
    
    if not data_root.exists():
        print(f"❌ 数据目录不存在: {data_root}")
        return
    
    # 1. 总体统计
    print("【1】总体统计")
    print("-" * 70)
    total_stats = get_directory_stats(data_root)
    print(f"数据根目录: {data_root}")
    print(f"总文件数: {total_stats['file_count']}")
    print(f"总大小: {total_stats['size_mb']} MB ({total_stats['size_bytes']} bytes)")
    print()
    
    # 2. 按数据类型统计
    print("【2】按数据类型统计")
    print("-" * 70)
    type_counts = count_files_by_type(data_root)
    
    if type_counts:
        for data_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"{data_type:25s} : {count:5d} 个文件")
    else:
        print("未发现任何数据文件")
    print()
    
    # 3. 按扩展名统计
    print("【3】按扩展名统计")
    print("-" * 70)
    ext_counts = count_files_by_extension(data_root)
    
    if ext_counts:
        for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1]):
            print(f"{ext:10s} : {count:5d} 个文件")
    else:
        print("未发现任何数据文件")
    print()
    
    # 4. 按数据源目录统计
    print("【4】按数据源目录统计")
    print("-" * 70)
    
    sources = {
        "arXiv 论文元数据": data_root / "api" / "arxiv" / "metadata",
        "arXiv 论文 PDF": data_root / "api" / "arxiv" / "pdfs",
        "Zenodo 记录": data_root / "api" / "zenodo" / "records",
        "GitHub 仓库": data_root / "api" / "github" / "repos",
        "HuggingFace 模型": data_root / "api" / "huggingface" / "models",
        "Papers with Code": data_root / "web" / "paperswithcode" / "papers",
        "GraspNet 数据集": data_root / "datasets" / "graspnet",
        "DexGraspNet 数据集": data_root / "datasets" / "dexgraspnet",
        "YCB 物体模型": data_root / "datasets" / "ycb" / "models",
        "Google Scanned 模型": data_root / "datasets" / "google_scanned" / "models",
        "Franka URDF": data_root / "web" / "franka" / "panda",
        "Robotiq URDF": data_root / "web" / "robotiq" / "grippers",
        "Allegro URDF": data_root / "web" / "allegro" / "hand",
        "MuJoCo 配置": data_root / "web" / "mujoco" / "examples",
        "Isaac Sim 配置": data_root / "web" / "isaac" / "examples",
        "代表性论文": data_root / "papers",
    }
    
    for source_name, source_dir in sources.items():
        stats = get_directory_stats(source_dir)
        if stats["exists"] and stats["file_count"] > 0:
            status = "✅"
            size_info = f"{stats['size_mb']:.2f} MB"
        elif stats["exists"]:
            status = "⚠️ "
            size_info = "0 MB (空目录)"
        else:
            status = "❌"
            size_info = "目录不存在"
        
        print(f"{status} {source_name:25s} : {stats['file_count']:5d} 个文件, {size_info}")
    print()
    
    # 5. 汇总表格
    print("【5】数据类型与数量对应关系汇总表")
    print("-" * 70)
    print(f"{'数据类型':<25s} | {'数量':>8s} | {'占比':>8s}")
    print("-" * 70)
    
    total_files = sum(type_counts.values()) if type_counts else 0
    
    if type_counts and total_files > 0:
        for data_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            percentage = (count / total_files * 100) if total_files > 0 else 0
            print(f"{data_type:<25s} | {count:>8d} | {percentage:>7.1f}%")
        
        print("-" * 70)
        print(f"{'总计':<25s} | {total_files:>8d} | {'100.0%':>8s}")
    else:
        print("暂无数据")
    print()
    
    # 6. 特殊文件
    print("【6】特殊文件统计")
    print("-" * 70)
    metadata_index = data_root / "_metadata_index.jsonl"
    if metadata_index.exists():
        line_count = sum(1 for _ in open(metadata_index, encoding="utf-8"))
        size_mb = metadata_index.stat().st_size / (1024 * 1024)
        print(f"元数据索引 (_metadata_index.jsonl):")
        print(f"  - 条目数: {line_count}")
        print(f"  - 大小: {size_mb:.2f} MB")
    else:
        print("元数据索引文件不存在")
    print()
    
    print("=" * 70)
    print("统计完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
