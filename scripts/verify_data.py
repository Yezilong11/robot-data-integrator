"""
数据完整性校验脚本

功能：
- 验证每个数据源的文件完整性
- 检查文件数量、格式、大小
- 生成校验报告

输出：data/verification_report.md

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


class DataVerifier:
    """数据完整性校验器。"""

    def __init__(self):
        self.data_dir = get_data_dir()
        self.results: list[dict] = []

    def _count_files(self, directory: Path, extension: str = "") -> int:
        """统计目录下文件数量。"""
        if not directory.exists():
            return 0
        if extension:
            return len(list(directory.rglob(f"*{extension}")))
        return len([f for f in directory.rglob("*") if f.is_file()])

    def _get_total_size(self, directory: Path) -> int:
        """统计目录总大小。"""
        if not directory.exists():
            return 0
        return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())

    def verify_arxiv(self) -> dict:
        """校验 arXiv 数据。"""
        base = self.data_dir / "api" / "arxiv"
        pdf_count = self._count_files(base / "pdfs", ".pdf")
        meta_count = self._count_files(base / "metadata", ".json")
        total_size = self._get_total_size(base)

        return {
            "source": "arXiv",
            "status": "✅" if pdf_count > 0 else "❌",
            "pdf_count": pdf_count,
            "metadata_count": meta_count,
            "target_pdfs": 50,
            "total_size": format_size(total_size),
            "details": f"{pdf_count}/50 PDF, {meta_count} 元数据文件",
        }

    def verify_ieee(self) -> dict:
        """校验 IEEE 数据。"""
        base = self.data_dir / "api" / "ieee"
        meta_count = self._count_files(base / "metadata", ".json")
        total_size = self._get_total_size(base)

        return {
            "source": "IEEE Xplore",
            "status": "✅" if meta_count > 0 else "⚠️",
            "metadata_count": meta_count,
            "target_papers": 20,
            "total_size": format_size(total_size),
            "details": f"{meta_count}/20 元数据 (需API Key)",
        }

    def verify_github(self) -> dict:
        """校验 GitHub 数据。"""
        base = self.data_dir / "api" / "github" / "repos"
        repo_count = len([d for d in base.iterdir() if d.is_dir()]) if base.exists() else 0
        readme_count = self._count_files(base, "README.md")
        total_size = self._get_total_size(self.data_dir / "api" / "github")

        return {
            "source": "GitHub",
            "status": "✅" if repo_count > 0 else "❌",
            "repo_count": repo_count,
            "readme_count": readme_count,
            "target_repos": 30,
            "total_size": format_size(total_size),
            "details": f"{repo_count}/30 仓库, {readme_count} README",
        }

    def verify_huggingface(self) -> dict:
        """校验 HuggingFace 数据。"""
        base = self.data_dir / "api" / "huggingface" / "models"
        model_count = len([d for d in base.iterdir() if d.is_dir()]) if base.exists() else 0
        total_size = self._get_total_size(self.data_dir / "api" / "huggingface")

        return {
            "source": "HuggingFace",
            "status": "✅" if model_count > 0 else "❌",
            "model_count": model_count,
            "target_models": 10,
            "total_size": format_size(total_size),
            "details": f"{model_count}/10 模型",
        }

    def verify_paperswithcode(self) -> dict:
        """校验 Papers with Code 数据。"""
        base = self.data_dir / "web" / "paperswithcode"
        has_metadata = (base / "papers" / "metadata.json").exists()
        total_size = self._get_total_size(base)

        return {
            "source": "Papers with Code",
            "status": "✅" if has_metadata else "❌",
            "has_metadata": has_metadata,
            "total_size": format_size(total_size),
            "details": "元数据已下载" if has_metadata else "未下载",
        }

    def verify_zenodo(self) -> dict:
        """校验 Zenodo 数据。"""
        base = self.data_dir / "api" / "zenodo" / "records"
        record_count = len([d for d in base.iterdir() if d.is_dir()]) if base.exists() else 0
        total_size = self._get_total_size(self.data_dir / "api" / "zenodo")

        return {
            "source": "Zenodo",
            "status": "✅" if record_count > 0 else "❌",
            "record_count": record_count,
            "target_records": 10,
            "total_size": format_size(total_size),
            "details": f"{record_count}/10 记录",
        }

    def verify_graspnet(self) -> dict:
        """校验 GraspNet 数据。"""
        base = self.data_dir / "datasets" / "graspnet"
        has_data = (base / "dataset").exists() and self._count_files(base / "dataset") > 0
        total_size = self._get_total_size(base)

        return {
            "source": "GraspNet",
            "status": "✅" if has_data else "⚠️",
            "total_size": format_size(total_size),
            "target_size": "~30 GB",
            "details": "数据已下载" if has_data else "大型数据集，需手动确认下载",
        }

    def verify_dexgraspnet(self) -> dict:
        """校验 DexGraspNet 数据。"""
        base = self.data_dir / "datasets" / "dexgraspnet" / "data"
        file_count = self._count_files(base)
        total_size = self._get_total_size(self.data_dir / "datasets" / "dexgraspnet")

        return {
            "source": "DexGraspNet",
            "status": "✅" if file_count > 0 else "⚠️",
            "file_count": file_count,
            "total_size": format_size(total_size),
            "target_size": "~5 GB",
            "details": f"{file_count} 文件" if file_count > 0 else "需手动下载",
        }

    def verify_ycb(self) -> dict:
        """校验 YCB 数据。"""
        base = self.data_dir / "datasets" / "ycb" / "models"
        model_count = len([d for d in base.iterdir() if d.is_dir()]) if base.exists() else 0
        total_size = self._get_total_size(self.data_dir / "datasets" / "ycb")

        return {
            "source": "YCB Objects",
            "status": "✅" if model_count > 0 else "⚠️",
            "model_count": model_count,
            "target_objects": 20,
            "total_size": format_size(total_size),
            "details": f"{model_count}/20 物体模型",
        }

    def verify_google_scanned(self) -> dict:
        """校验 Google Scanned Objects 数据。"""
        base = self.data_dir / "datasets" / "google_scanned" / "models"
        model_count = len([d for d in base.iterdir() if d.is_dir()]) if base.exists() else 0
        total_size = self._get_total_size(self.data_dir / "datasets" / "google_scanned")

        return {
            "source": "Google Scanned",
            "status": "✅" if model_count > 0 else "⚠️",
            "model_count": model_count,
            "total_size": format_size(total_size),
            "target_size": "~10 GB",
            "details": f"{model_count} 模型" if model_count > 0 else "需手动下载",
        }

    def verify_franka(self) -> dict:
        """校验 Franka URDF 数据。"""
        base = self.data_dir / "web" / "franka" / "panda"
        urdf_count = self._count_files(base, ".urdf")
        total_size = self._get_total_size(base)

        return {
            "source": "Franka",
            "status": "✅" if urdf_count > 0 else "❌",
            "urdf_count": urdf_count,
            "total_size": format_size(total_size),
            "details": f"{urdf_count} URDF文件",
        }

    def verify_robotiq(self) -> dict:
        """校验 Robotiq URDF 数据。"""
        base = self.data_dir / "web" / "robotiq" / "grippers"
        urdf_count = self._count_files(base, ".urdf")
        total_size = self._get_total_size(base)

        return {
            "source": "Robotiq",
            "status": "✅" if urdf_count > 0 else "❌",
            "urdf_count": urdf_count,
            "total_size": format_size(total_size),
            "details": f"{urdf_count} URDF文件",
        }

    def verify_allegro(self) -> dict:
        """校验 Allegro URDF 数据。"""
        base = self.data_dir / "web" / "allegro" / "hand"
        urdf_count = self._count_files(base, ".urdf") + self._count_files(base, ".xacro")
        total_size = self._get_total_size(base)

        return {
            "source": "Allegro",
            "status": "✅" if urdf_count > 0 else "❌",
            "urdf_count": urdf_count,
            "total_size": format_size(total_size),
            "details": f"{urdf_count} URDF/XACRO文件",
        }

    def verify_mujoco(self) -> dict:
        """校验 MuJoCo 示例数据。"""
        base = self.data_dir / "web" / "mujoco" / "examples"
        xml_count = self._count_files(base, ".xml")
        total_size = self._get_total_size(base)

        return {
            "source": "MuJoCo",
            "status": "✅" if xml_count > 0 else "❌",
            "xml_count": xml_count,
            "total_size": format_size(total_size),
            "details": f"{xml_count} XML示例",
        }

    def verify_isaac(self) -> dict:
        """校验 Isaac Sim 示例数据。"""
        base = self.data_dir / "web" / "isaac" / "examples"
        file_count = self._count_files(base)
        total_size = self._get_total_size(base)

        return {
            "source": "Isaac Sim",
            "status": "✅" if file_count > 0 else "⚠️",
            "file_count": file_count,
            "total_size": format_size(total_size),
            "details": f"{file_count} 文件" if file_count > 0 else "需通过 Omniverse Launcher 获取",
        }

    def verify_papers(self) -> dict:
        """校验代表性论文数据。"""
        base = self.data_dir / "papers"
        pdf_count = self._count_files(base, ".pdf")
        total_size = self._get_total_size(base)

        return {
            "source": "代表性论文",
            "status": "✅" if pdf_count > 0 else "❌",
            "pdf_count": pdf_count,
            "target_pdfs": 10,
            "total_size": format_size(total_size),
            "details": f"{pdf_count}/10 篇PDF",
        }

    def run(self) -> str:
        """运行所有校验，生成 Markdown 报告。"""
        print("=" * 60)
        print("  数据完整性校验")
        print("=" * 60)

        # 运行所有校验
        verifiers = [
            self.verify_arxiv,
            self.verify_ieee,
            self.verify_github,
            self.verify_huggingface,
            self.verify_paperswithcode,
            self.verify_zenodo,
            self.verify_graspnet,
            self.verify_dexgraspnet,
            self.verify_ycb,
            self.verify_google_scanned,
            self.verify_franka,
            self.verify_robotiq,
            self.verify_allegro,
            self.verify_mujoco,
            self.verify_isaac,
            self.verify_papers,
        ]

        for v in verifiers:
            result = v()
            self.results.append(result)
            print(f"  {result['status']} {result['source']}: {result['details']}")

        # 生成报告
        return self._generate_report()

    def _generate_report(self) -> str:
        """生成 Markdown 校验报告。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# 数据完整性校验报告\n",
            f"> 校验时间：{now}",
            f"> 数据目录：{self.data_dir}\n",
            "## 校验结果汇总\n",
            "| 数据源 | 状态 | 详细信息 |",
            "|--------|------|---------|",
        ]

        for r in self.results:
            lines.append(f"| {r['source']} | {r['status']} | {r['details']} |")

        # 统计
        success = sum(1 for r in self.results if r["status"] == "✅")
        warning = sum(1 for r in self.results if r["status"] == "⚠️")
        failed = sum(1 for r in self.results if r["status"] == "❌")
        total = len(self.results)

        lines.extend([
            f"\n## 统计\n",
            f"- 总计: {total} 个数据源",
            f"- ✅ 成功: {success} 个",
            f"- ⚠️ 部分完成/需手动处理: {warning} 个",
            f"- ❌ 未完成: {failed} 个\n",
            "## 详细结果\n",
        ])

        for r in self.results:
            lines.append(f"### {r['source']}\n")
            for key, value in r.items():
                if key not in ("source", "status"):
                    lines.append(f"- {key}: {value}")
            lines.append("")

        return "\n".join(lines)


def main() -> None:
    verifier = DataVerifier()
    report = verifier.run()

    # 保存报告
    report_path = config.REPORT_DIR / "verification_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"\n校验报告已生成: {report_path}")


if __name__ == "__main__":
    main()
