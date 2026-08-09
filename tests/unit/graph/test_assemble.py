"""assemble 节点单元测试：数据包按 req_type 结构化子目录落盘。

验证 manifest ``files[].path`` 与实际磁盘路径一致，
且各 ``DataReqType`` 正确映射到子目录。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from rdi.config.settings import settings
from rdi.graph.nodes.assemble import node_assemble
from rdi.models import DataReqType, DataSource, ParsedItem
from rdi.models.common import ProvenanceEntry

if TYPE_CHECKING:
    from rdi.graph.state import SystemState

_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)


def _provenance() -> ProvenanceEntry:
    return ProvenanceEntry(
        source=DataSource.GITHUB,
        source_url="https://example.com",
        retrieved_at=_FIXED_TIME,
        original_format="bin",
    )


def _item(req_id: str, req_type: DataReqType, fmt: str) -> ParsedItem:
    return ParsedItem(
        req_id=req_id,
        req_type=req_type,
        name=req_id,
        canonical_format=fmt,
        output_path="unused",
        data=b"<payload>",
        provenance=_provenance(),
    )


# req_type → 期望子目录
_CASES: dict[str, tuple[DataReqType, str, str]] = {
    "req_000": (DataReqType.ROBOT_URDF, "urdf", "robots/req_000.urdf"),
    "req_001": (DataReqType.MESH, "stl", "objects/req_001.stl"),
    "req_002": (DataReqType.GRASP, "CanonicalGrasp", "grasps/req_002.bin"),
    "req_003": (DataReqType.SIM_CONFIG, "xml", "sim_config/req_003.xml"),
    "req_004": (DataReqType.POLICY_MODEL, "text", "policies/req_004.txt"),
    "req_005": (DataReqType.CODE, "text", "resources/req_005.txt"),
    "req_006": (DataReqType.DATASET, "json", "resources/req_006.json"),
    "req_007": (DataReqType.PAPER, "markdown", "resources/req_007.md"),
    "req_008": (DataReqType.UNKNOWN, "bin", "resources/req_008.bin"),
}


@pytest.fixture
def output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把全局 settings.output_dir 指向临时目录。"""
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))
    return tmp_path


def test_assemble_writes_structured_subdirs(output_dir: Path) -> None:
    """各类 req_type 落盘到对应子目录，manifest path 与磁盘路径一致。"""
    parsed_data = {
        req_id: _item(req_id, req_type, fmt)
        for req_id, (req_type, fmt, _) in _CASES.items()
    }
    state: SystemState = {
        "parsed_data": parsed_data,
        "data_requirements": [],
        "missing_items": [],
        "validation_issues": [],
    }

    out = node_assemble(state)
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    assert len(pkg.files) == len(_CASES)
    for f in pkg.files:
        expected_path = _CASES[f.req_id][2]
        assert f.path == expected_path
        # manifest 相对路径与实际磁盘文件一致
        assert (package_dir / f.path).is_file()
        assert not f.path.startswith("files/")

    # 抽查各类子目录均真实存在于磁盘
    for rel in ("robots", "objects", "grasps", "sim_config", "policies", "resources"):
        assert (package_dir / rel).is_dir()


def test_assemble_unknown_type_falls_back_to_resources(output_dir: Path) -> None:
    """未收录的 req_type（如 SENSOR_DATA）兜底到 resources/。"""
    state: SystemState = {
        "parsed_data": {
            "req_009": _item("req_009", DataReqType.SENSOR_DATA, "npz"),
        }
    }

    out = node_assemble(state)
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    assert pkg.files[0].path == "resources/req_009.npz"
    assert (package_dir / "resources" / "req_009.npz").is_file()


def test_assemble_carries_revision_history(output_dir: Path) -> None:
    """state.revision_history 原样挂到 manifest.revision_history。"""
    revision_history = [
        {
            "revision": 1,
            "decision": "revised",
            "feedback": ["换 UR5"],
            "revised_goal": "用 UR5 在 PyBullet 中抓取 mug",
            "timestamp": "2026-07-23T12:00:00",
        }
    ]
    state: SystemState = {"revision_history": revision_history}

    out = node_assemble(state)
    pkg = out["experiment_package"]

    assert pkg.revision_history == revision_history
