"""
元数据提取脚本

功能：
- 扫描 data/sources/ 全量数据,按文件后缀分发到对应提取器
- 输出标准化的 JSONL 索引到 data/sources/_metadata_index.jsonl
- 支持按子目录(--source)过滤、按文件类型(--type)过滤

支持的格式：
- .urdf / .xacro   -> 提取 link/joint 名称
- .obj / .stl / .ply / .glb -> 顶点/面/包围盒
- .npy / .npz      -> shape/dtype/min/max
- .pdf             -> 页数/作者/标题
- .json            -> 顶层 key 列表/大小
- .xml / .mjcf / .sdf / .usd / .usda -> 通用 XML 解析
- .zip / .tar.gz / .7z -> 压缩包内文件列表

作者：挑战杯团队
创建日期：2026-07-15
"""

import argparse
import hashlib
import json
import sys
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Iterator

# 允许导入同级 config.py / utils.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import config  # noqa: E402


# ─── 各类文件提取器 ───

def mesh_metadata(path: Path) -> dict:
    """提取 3D mesh 文件元数据。"""
    try:
        import trimesh

        mesh = trimesh.load(str(path), force="mesh", process=False)
        return {
            "format": path.suffix.lower(),
            "vertices": int(len(mesh.vertices)),
            "faces": int(len(mesh.faces)),
            "bounds": mesh.bounds.tolist() if mesh.bounds is not None else None,
            "watertight": bool(mesh.is_watertight),
            "volume_mm3": float(mesh.volume) if mesh.is_watertight else None,
        }
    except ImportError:
        return {"format": path.suffix.lower(), "error": "trimesh not installed"}
    except Exception as e:
        return {"format": path.suffix.lower(), "error": str(e)[:200]}


def urdf_metadata(path: Path) -> dict:
    """提取 URDF/XACRO 文件元数据。"""
    try:
        # 若为 xacro,先尝试用 xacro 库展开
        if path.suffix.lower() == ".xacro":
            try:
                import xacro  # type: ignore

                xml_str = xacro.process_file(str(path)).toxml()
                root = ET.fromstring(xml_str)
            except ImportError:
                # xacro 未安装,直接解析(可能漏宏展开)
                tree = ET.parse(path)
                root = tree.getroot()
        else:
            tree = ET.parse(path)
            root = tree.getroot()

        # URDF 根标签是 <robot>
        if root.tag == "robot" or root.find("robot") is not None:
            robot = root if root.tag == "robot" else root.find("robot")
            return {
                "format": path.suffix.lower(),
                "robot_name": robot.get("name"),
                "links": [l.get("name") for l in robot.findall("link")],
                "joints": [j.get("name") for j in robot.findall("joint")],
                "materials": [m.get("name") for m in robot.findall("material")],
                "link_count": len(robot.findall("link")),
                "joint_count": len(robot.findall("joint")),
            }
        # MJCF 根标签是 <mujoco>
        if root.tag == "mujoco":
            return {
                "format": "mjcf",
                "model_name": root.get("model"),
                "bodies": [b.get("name") for b in root.iter("body")],
                "joints": [j.get("name") for j in root.iter("joint")],
                "actuators": [a.get("name") for a in root.iter("actuator")],
            }
        # SDF 根标签是 <sdf>
        if root.tag == "sdf":
            return {
                "format": "sdf",
                "version": root.get("version"),
                "models": [m.get("name") for m in root.iter("model")],
                "links": [l.get("name") for l in root.iter("link")],
            }
        # USD 根标签通常是 <usd> 或 <usda>
        return {
            "format": path.suffix.lower(),
            "root_tag": root.tag,
            "child_count": len(list(root)),
        }
    except ET.ParseError as e:
        return {"format": path.suffix.lower(), "error": f"XML parse: {e}"}
    except Exception as e:
        return {"format": path.suffix.lower(), "error": str(e)[:200]}


def numpy_metadata(path: Path) -> dict:
    """提取 .npy / .npz 文件元数据。"""
    try:
        import numpy as np

        if path.suffix.lower() == ".npz":
            with np.load(path) as data:
                keys = list(data.keys())
                sample = data[keys[0]] if keys else None
                return {
                    "format": "npz",
                    "key_count": len(keys),
                    "keys": keys[:20],  # 仅记录前 20 个 key
                    "sample_shape": list(sample.shape) if sample is not None else None,
                    "sample_dtype": str(sample.dtype) if sample is not None else None,
                }
        else:
            arr = np.load(path, mmap_mode="r")
            return {
                "format": "npy",
                "shape": list(arr.shape),
                "dtype": str(arr.dtype),
                "size": int(arr.size),
                "min": float(arr.min()) if arr.size > 0 else None,
                "max": float(arr.max()) if arr.size > 0 else None,
            }
    except Exception as e:
        return {"format": path.suffix.lower(), "error": str(e)[:200]}


def pdf_metadata(path: Path) -> dict:
    """提取 PDF 文件元数据。"""
    try:
        import fitz  # PyMuPDF

        with fitz.open(str(path)) as doc:
            meta = doc.metadata or {}
            return {
                "format": "pdf",
                "page_count": doc.page_count,
                "title": meta.get("title", "")[:200],
                "author": meta.get("author", "")[:200],
                "subject": meta.get("subject", "")[:200],
                "is_encrypted": doc.is_encrypted,
            }
    except ImportError:
        # 退而求其次:仅返回文件大小
        return {"format": "pdf", "size_bytes": path.stat().st_size}
    except Exception as e:
        return {"format": "pdf", "error": str(e)[:200]}


def json_metadata(path: Path) -> dict:
    """提取 JSON 文件元数据。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            keys = list(data.keys())[:20]
            return {
                "format": "json",
                "type": "object",
                "key_count": len(data),
                "keys": keys,
            }
        if isinstance(data, list):
            return {
                "format": "json",
                "type": "array",
                "length": len(data),
                "first_item_type": type(data[0]).__name__ if data else None,
            }
        return {"format": "json", "type": type(data).__name__}
    except json.JSONDecodeError as e:
        return {"format": "json", "error": f"JSON parse: {e}"}
    except Exception as e:
        return {"format": "json", "error": str(e)[:200]}


def xml_metadata(path: Path) -> dict:
    """通用 XML 文件元数据。"""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        return {
            "format": "xml",
            "root_tag": root.tag,
            "root_attrs": dict(root.attrib),
            "child_tags": list({c.tag for c in root})[:20],
            "size_bytes": path.stat().st_size,
        }
    except ET.ParseError as e:
        return {"format": "xml", "error": f"XML parse: {e}"}


def archive_metadata(path: Path) -> dict:
    """压缩包元数据(.zip)。"""
    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                return {
                    "format": "zip",
                    "file_count": len(names),
                    "compressed_size": path.stat().st_size,
                    "uncompressed_size": sum(i.file_size for i in zf.infolist()),
                    "first_files": names[:5],
                }
        return {"format": path.suffix.lower(), "size_bytes": path.stat().st_size}
    except Exception as e:
        return {"format": path.suffix.lower(), "error": str(e)[:200]}


def text_metadata(path: Path) -> dict:
    """文本文件元数据(.md/.txt/.py 等)。"""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return {
            "format": path.suffix.lower(),
            "line_count": content.count("\n") + 1,
            "char_count": len(content),
            "size_bytes": path.stat().st_size,
        }
    except Exception as e:
        return {"format": path.suffix.lower(), "error": str(e)[:200]}


# ─── 调度表 ───

EXTRACTORS = {
    # 3D mesh
    ".obj": mesh_metadata,
    ".stl": mesh_metadata,
    ".ply": mesh_metadata,
    ".glb": mesh_metadata,
    ".dae": mesh_metadata,
    # 机器人描述
    ".urdf": urdf_metadata,
    ".xacro": urdf_metadata,
    ".mjcf": urdf_metadata,
    ".sdf": urdf_metadata,
    ".usd": urdf_metadata,
    ".usda": urdf_metadata,
    # 数值数据
    ".npy": numpy_metadata,
    ".npz": numpy_metadata,
    # 文档
    ".pdf": pdf_metadata,
    # 元数据
    ".json": json_metadata,
    # 通用 XML
    ".xml": xml_metadata,
    # 压缩包
    ".zip": archive_metadata,
    ".tar": archive_metadata,
    ".gz": archive_metadata,
    ".bz2": archive_metadata,
    ".xz": archive_metadata,
    ".7z": archive_metadata,
    # 文本
    ".md": text_metadata,
    ".txt": text_metadata,
    ".py": text_metadata,
}


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in EXTRACTORS


def compute_id(path: Path) -> str:
    """生成稳定 ID:基于路径的 SHA1。"""
    return hashlib.sha1(str(path.absolute()).encode("utf-8")).hexdigest()[:16]


def scan_files(
    root: Path,
    source_filter: str | None = None,
    type_filter: str | None = None,
) -> Iterator[Path]:
    """扫描符合条件的所有文件。"""
    if source_filter:
        root = root / source_filter
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not is_supported(path):
            continue
        if type_filter and path.suffix.lower().lstrip(".") != type_filter.lower():
            continue
        yield path


def extract_one(path: Path, project_root: Path) -> dict:
    """提取单个文件的元数据,统一封装。"""
    extractor = EXTRACTORS[path.suffix.lower()]
    custom: dict = {}
    try:
        custom = extractor(path)
    except Exception as e:
        custom = {"error": str(e), "trace": traceback.format_exc()[:300]}

    rel = path.relative_to(project_root)
    stat = path.stat()
    return {
        "id": compute_id(path),
        "path": str(rel).replace("\\", "/"),
        "abs_path": str(path),
        "name": path.name,
        "ext": path.suffix.lower(),
        "type": classify_type(path),
        "size_bytes": stat.st_size,
        "mtime": int(stat.st_mtime),
        "custom": custom,
    }


def classify_type(path: Path) -> str:
    """按大类归类(用于 ChromaDB metadata 过滤)。"""
    ext = path.suffix.lower()
    if ext in {".obj", ".stl", ".ply", ".glb", ".dae"}:
        return "mesh"
    if ext in {".urdf", ".xacro", ".mjcf", ".sdf", ".usd", ".usda"}:
        return "robot_description"
    if ext in {".npy", ".npz"}:
        return "numeric"
    if ext == ".pdf":
        return "paper"
    if ext == ".json":
        return "metadata"
    if ext in {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z"}:
        return "archive"
    if ext in {".xml"}:
        return "xml"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description="提取数据源元数据")
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="仅扫描特定子目录(相对 data/sources/),如 'api/arxiv'",
    )
    parser.add_argument(
        "--type",
        type=str,
        default=None,
        help="仅处理特定文件类型(扩展名),如 'pdf'",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出文件路径,默认 data/sources/_metadata_index.jsonl",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  元数据提取脚本")
    print("=" * 70)

    data_root = config.DATA_DIR
    project_root = config.PROJECT_ROOT
    output_path = (
        Path(args.output) if args.output else data_root / "_metadata_index.jsonl"
    )

    if not data_root.exists():
        print(f"❌ 数据目录不存在: {data_root}")
        sys.exit(1)

    print(f"数据根: {data_root}")
    print(f"输出:   {output_path}")
    if args.source:
        print(f"子目录过滤: {args.source}")
    if args.type:
        print(f"类型过滤: {args.type}")
    print()

    # ─── 扫描 ───
    print("[1/2] 扫描文件...")
    files = list(scan_files(data_root, args.source, args.type))
    if not files:
        print("  ℹ️  未发现符合条件文件")
        return
    print(f"  发现 {len(files)} 个待处理文件")

    # 按类型统计
    type_count: dict[str, int] = {}
    for f in files:
        type_count[f.suffix.lower()] = type_count.get(f.suffix.lower(), 0) + 1
    print("  类型分布:")
    for ext, count in sorted(type_count.items(), key=lambda x: -x[1]):
        print(f"    {ext}: {count}")
    print()

    # ─── 提取 ───
    print("[2/2] 提取元数据...")
    start = time.time()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok_count = 0
    err_count = 0

    with open(output_path, "w", encoding="utf-8") as fout:
        for i, f in enumerate(files, 1):
            try:
                rec = extract_one(f, project_root)
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                ok_count += 1
            except Exception as e:
                err_count += 1
                print(f"  ❌ {f.name}: {e}")
            # 进度
            if i % 20 == 0 or i == len(files):
                pct = i / len(files) * 100
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(files) - i) / rate if rate > 0 else 0
                print(
                    f"\r  进度: {i}/{len(files)} ({pct:.1f}%) "
                    f"[{elapsed:.1f}s, ETA {eta:.1f}s]",
                    end="",
                    flush=True,
                )
        print()

    print()
    print(f"✅ 完成: 成功 {ok_count}, 失败 {err_count}, 耗时 {time.time()-start:.1f}s")
    print(f"📄 输出: {output_path}")


if __name__ == "__main__":
    main()
