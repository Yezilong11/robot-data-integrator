# tests/unit/adapters/test_selectors.py
"""文件树目标文件选择器（rdi.adapters.selectors）的单元测试。"""

import pytest

from rdi.adapters.selectors import build_download_guide, select_target_file
from rdi.models.common import DataReqType


def _file(
    name: str,
    *,
    size: int = 0,
    path: str | None = None,
    url: str | None = None,
    is_dir: bool = False,
) -> dict:
    """构造一条文件树条目（size 为 0 时省略字段，验证缺失 size 的排序兜底）。"""
    item: dict = {"name": name, "type": "dir" if is_dir else "file"}
    if size:
        item["size"] = size
    if path is not None:
        item["path"] = path
    if url is not None:
        item["url"] = url
    return item


class TestSelectTargetFile:
    """select_target_file 单元测试。"""

    def test_policy_model_filters_ext_and_ranks_by_signals(self) -> None:
        """POLICY_MODEL：扩展名白名单过滤 + 名字信号命中数排序。"""
        tree = [
            _file("random.txt", size=999),
            _file("policy.pt", size=100),
            _file("model.safetensors", size=50),
            _file("actuator_model.bin", size=10),  # 命中 actuator+model，共 2 个信号
        ]
        result = select_target_file(tree, DataReqType.POLICY_MODEL)
        assert [e["name"] for e in result] == [
            "actuator_model.bin",  # 命中 2 个信号优先
            "policy.pt",  # 命中 1 个信号
            "model.safetensors",  # 命中 1 个信号，同分按 size 降序
        ]

    def test_policy_model_tie_breaks_by_size_desc(self) -> None:
        """POLICY_MODEL：同信号分时按 size 降序。"""
        tree = [
            _file("model_a.pt", size=10),
            _file("model_b.pth", size=20),
        ]
        result = select_target_file(tree, DataReqType.POLICY_MODEL)
        assert [e["name"] for e in result] == ["model_b.pth", "model_a.pt"]

    def test_sensor_data_ext_and_signals(self) -> None:
        """SENSOR_DATA：csv/json 白名单 + 信号命中排序。"""
        tree = [
            _file("observations.json", size=900),
            _file("joint_torque.csv", size=100),  # 命中 joint+torque，共 2 个信号
            _file("data.pkl", size=999),  # 扩展名不在白名单
        ]
        result = select_target_file(tree, DataReqType.SENSOR_DATA)
        assert [e["name"] for e in result] == ["joint_torque.csv", "observations.json"]

    def test_grasp_prefers_grasp_label_over_size(self) -> None:
        """GRASP：仅 .npz 白名单，name 含 grasp_label 优先于更大的非标注文件。"""
        tree = [
            _file("scene_data.npz", size=1000),
            _file("grasp_label_test.npz", size=10),
            _file("annotations.pkl", size=999),  # 扩展名不在白名单
        ]
        result = select_target_file(tree, DataReqType.GRASP)
        assert [e["name"] for e in result] == ["grasp_label_test.npz", "scene_data.npz"]

    def test_dataset_fallback_size_desc_skips_metadata(self) -> None:
        """DATASET：无扩展名限制，跳过元数据类文件，按 size 降序。"""
        tree = [
            _file("README.md", size=999),
            _file("license.txt", size=999),
            _file("metadata.json", size=999),
            _file("config.yaml", size=999),
            _file("labels.npz", size=800),
            _file("train_data.csv", size=500),
        ]
        result = select_target_file(tree, DataReqType.DATASET)
        assert [e["name"] for e in result] == ["labels.npz", "train_data.csv"]

    def test_unknown_type_uses_fallback(self) -> None:
        """UNKNOWN：未列出类型走兜底规则（同 DATASET）。"""
        tree = [
            _file("README.md", size=999),
            _file("data.bin", size=300),
        ]
        result = select_target_file(tree, DataReqType.UNKNOWN)
        assert [e["name"] for e in result] == ["data.bin"]

    def test_empty_tree_returns_empty(self) -> None:
        """空 tree 返回 []。"""
        assert select_target_file([], DataReqType.DATASET) == []

    def test_no_candidate_returns_empty(self) -> None:
        """无匹配扩展名候选时返回 []。"""
        tree = [_file("notes.txt", size=999)]
        assert select_target_file(tree, DataReqType.POLICY_MODEL) == []

    def test_only_file_entries_considered(self) -> None:
        """仅选择 type=="file" 条目，dir 被忽略。"""
        tree = [
            _file("policy.pt", size=999, is_dir=True),
            _file("checkpoint.bin", size=100),
        ]
        result = select_target_file(tree, DataReqType.POLICY_MODEL)
        assert [e["name"] for e in result] == ["checkpoint.bin"]

    def test_ext_and_signal_match_case_insensitive(self) -> None:
        """扩展名与信号匹配大小写不敏感。"""
        tree = [_file("MODEL.PTH", size=10), _file("policy.safetensors", size=5)]
        result = select_target_file(tree, DataReqType.POLICY_MODEL)
        assert [e["name"] for e in result] == ["MODEL.PTH", "policy.safetensors"]

    def test_missing_size_treated_as_zero(self) -> None:
        """缺失 size 的条目按 0 处理，排在末尾不崩溃。"""
        tree = [
            _file("checkpoint_a.bin", size=50),
            _file("checkpoint_b.pt"),  # 无 size 字段
        ]
        result = select_target_file(tree, DataReqType.POLICY_MODEL)
        assert [e["name"] for e in result] == ["checkpoint_a.bin", "checkpoint_b.pt"]

    def test_tree_entry_fields_preserved(self) -> None:
        """返回条目保留原 tree 字段（path/url/size）。"""
        tree = [_file("policy.pt", size=42, path="ckpt/policy.pt", url="https://x/policy.pt")]
        result = select_target_file(tree, DataReqType.POLICY_MODEL)
        assert result[0]["path"] == "ckpt/policy.pt"
        assert result[0]["url"] == "https://x/policy.pt"
        assert result[0]["size"] == 42


class TestBuildDownloadGuide:
    """build_download_guide 单元测试。"""

    def test_full_fields(self) -> None:
        """正常情况：download_guide 各字段齐全。"""
        candidate = _file(
            "policy_model.safetensors",
            size=123456,
            path="checkpoints/policy_model.safetensors",
            url="https://example.com/checkpoints/policy_model.safetensors",
        )
        guide = build_download_guide(candidate, "weights unavailable", DataReqType.POLICY_MODEL)
        assert guide["status"] == "not_downloaded"
        assert guide["reason"] == "weights unavailable"
        assert (
            guide["source_file_url"]
            == "https://example.com/checkpoints/policy_model.safetensors"
        )
        assert guide["file_size_bytes"] == 123456
        assert (
            guide["method_hint"]
            == "wget https://example.com/checkpoints/policy_model.safetensors "
            "-O checkpoints/policy_model.safetensors"
        )
        assert guide["selected_by"] == "ext=.safetensors; signals=policy,model"
        assert guide["alternatives"] == []

    def test_url_falls_back_to_path(self) -> None:
        """候选无 url 时 source_file_url / method_hint 回退到 path。"""
        candidate = _file("labels.npz", size=800, path="grasp/labels.npz")
        guide = build_download_guide(candidate, "annotations offline", DataReqType.DATASET)
        assert guide["source_file_url"] == "grasp/labels.npz"
        assert guide["method_hint"] == "wget grasp/labels.npz -O grasp/labels.npz"
        assert guide["selected_by"] == "ext=.npz; size=largest; skipped=metadata"

    def test_req_type_none_describes_ext_only(self) -> None:
        """req_type 缺省时 selected_by 仅基于候选自身描述。"""
        candidate = _file("weights.bin", size=7, url="https://example.com/weights.bin")
        guide = build_download_guide(candidate, "no license")
        assert guide["status"] == "not_downloaded"
        assert guide["selected_by"] == "ext=.bin; size=largest"
        assert guide["method_hint"] == "wget https://example.com/weights.bin -O weights.bin"