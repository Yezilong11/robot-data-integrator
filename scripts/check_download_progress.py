"""
下载进度检查脚本

功能：
- 检查所有数据源的下载进度
- 显示文件数量和大小
- 生成进度报告

作者：挑战杯团队
创建日期：2026-07-14
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config
from utils import format_size, get_data_dir


def count_files(directory: Path, extensions: list[str] | None = None) -> int:
    """统计目录中的文件数量。"""
    if not directory.exists():
        return 0
    if extensions:
        return sum(1 for _ in directory.rglob("*") if _.is_file() and _.suffix in extensions)
    return sum(1 for _ in directory.rglob("*") if _.is_file())


def get_dir_size(directory: Path) -> int:
    """获取目录总大小。"""
    if not directory.exists():
        return 0
    return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())


def check_data_source(name: str, path: Path, target_count: int, target_size_mb: float, extensions: list[str] | None = None) -> dict:
    """检查单个数据源。"""
    count = count_files(path, extensions)
    size_mb = get_dir_size(path) / (1024 * 1024)

    count_pct = (count / target_count) * 100 if target_count > 0 else 0
    size_pct = (size_mb / target_size_mb) * 100 if target_size_mb > 0 else 0
    avg_pct = (count_pct + size_pct) / 2

    return {
        "name": name,
        "path": str(path.relative_to(config.PROJECT_ROOT)),
        "count": count,
        "target_count": target_count,
        "size_mb": round(size_mb, 2),
        "target_size_mb": target_size_mb,
        "count_pct": round(count_pct, 1),
        "size_pct": round(size_pct, 1),
        "avg_pct": round(avg_pct, 1),
        "status": "✅" if avg_pct > 80 else "⚠️" if avg_pct > 30 else "❌" if avg_pct > 0 else "⏳",
    }


def main() -> None:
    print("=" * 70)
    print("  数据源下载进度检查")
    print("=" * 70)

    data_dir = get_data_dir()

    # 检查项配置
    checks = [
        # 论文源
        ("arXiv PDF", data_dir / "api" / "arxiv" / "pdfs", 50, 200, [".pdf"]),
        ("arXiv Metadata", data_dir / "api" / "arxiv" / "metadata", 50, 5, [".json"]),
        ("IEEE", data_dir / "api" / "ieee" / "metadata", 20, 5, [".json"]),

        # 代码与模型源
        ("GitHub", data_dir / "api" / "github" / "repos", 30, 50, [".md", ".py"]),
        ("HuggingFace", data_dir / "api" / "huggingface" / "models", 10, 100, [".json"]),
        ("Papers with Code", data_dir / "web" / "paperswithcode" / "papers", 1, 10, [".json"]),

        # 数据集源
        ("GraspNet", data_dir / "datasets" / "graspnet", 100000, 30000, []),
        ("DexGraspNet", data_dir / "datasets" / "dexgraspnet" / "data", 1000, 5000, [".npy", ".npz"]),
        ("YCB", data_dir / "datasets" / "ycb" / "models", 20, 5000, []),
        ("Google Scanned", data_dir / "datasets" / "google_scanned" / "models", 27, 1000, []),

        # 硬件与仿真源
        ("Franka", data_dir / "web" / "franka" / "panda", 5, 50, [".urdf", ".xacro"]),
        ("Robotiq", data_dir / "web" / "robotiq" / "grippers", 3, 20, [".urdf", ".xacro"]),
        ("Allegro", data_dir / "web" / "allegro" / "hand", 5, 30, [".urdf", ".xacro", ".stl"]),
        ("MuJoCo", data_dir / "web" / "mujoco" / "examples", 10, 5, [".xml"]),
        ("Isaac Sim", data_dir / "web" / "isaac" / "examples", 5, 10, []),

        # 代表性论文
        ("代表性论文", data_dir / "papers", 10, 100, [".pdf"]),
    ]

    results = []
    for name, path, target_count, target_size_mb, exts in checks:
        result = check_data_source(name, path, target_count, target_size_mb, exts)
        results.append(result)

    # 打印结果
    print()
    print(f"{'数据源':<20} {'状态':<6} {'文件数':<12} {'大小':<12} {'进度':<8}")
    print("-" * 70)
    for r in results:
        count_str = f"{r['count']}/{r['target_count']}"
        size_str = f"{r['size_mb']:.1f}/{r['target_size_mb']:.0f} MB"
        progress_str = f"{r['avg_pct']:.1f}%"
        print(f"{r['name']:<20} {r['status']:<6} {count_str:<12} {size_str:<12} {progress_str:<8}")

    # 统计
    total_size = sum(r["size_mb"] for r in results)
    completed = sum(1 for r in results if r["avg_pct"] > 80)
    in_progress = sum(1 for r in results if 30 < r["avg_pct"] <= 80)
    not_started = sum(1 for r in results if r["avg_pct"] <= 30)

    print("-" * 70)
    print(f"\n总计: {len(results)} 个数据源")
    print(f"  ✅ 完成 (>80%): {completed}")
    print(f"  ⚠️  进行中 (30-80%): {in_progress}")
    print(f"  ⏳ 未开始 (<30%): {not_started}")
    print(f"  📦 总大小: {format_size(int(total_size * 1024 * 1024))}")

    # 保存 JSON 报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "summary": {
            "total_sources": len(results),
            "completed": completed,
            "in_progress": in_progress,
            "not_started": not_started,
            "total_size_mb": round(total_size, 2),
        },
    }
    report_path = config.REPORT_DIR / "download_progress.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细报告: {report_path}")

    # 显示下一步建议
    print("\n" + "=" * 70)
    print("  下一步建议")
    print("=" * 70)
    pending = [r for r in results if r["avg_pct"] < 80]
    if pending:
        print(f"\n以下数据源需要继续下载:")
        for r in pending[:5]:
            print(f"  - {r['name']} ({r['avg_pct']:.1f}%)")
        if len(pending) > 5:
            print(f"  ... 还有 {len(pending) - 5} 个")
    else:
        print("\n🎉 所有数据源已下载完成！")


if __name__ == "__main__":
    main()
