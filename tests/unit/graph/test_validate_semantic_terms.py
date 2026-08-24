"""semantic_terms 语义约束词校验单元测试（阶段一：语义校验补牙齿）。

覆盖：LLM 提炼的 semantic_terms 参与需求-内容语义匹配（DATASET 等类型启用）、
semantic_terms 为空时 fail-open（行为与现状一致）、空串跳过与命中不误报。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from rdi.graph.nodes.validate import _extract_semantic_terms, _semantic_mismatch
from rdi.models import DataReqType, DataSource, ParsedItem, Priority
from rdi.models.common import ProvenanceEntry
from rdi.models.goal import DataReq

_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)


def _provenance(fmt: str = "bin", url: str = "https://example.com/asset/a.bin") -> ProvenanceEntry:
    return ProvenanceEntry(
        source=DataSource.ZENODO,
        source_url=url,
        retrieved_at=_FIXED_TIME,
        original_format=fmt,
    )


def _item(
    req_id: str,
    req_type: DataReqType,
    data: object,
    fmt: str = "bin",
    name: str | None = None,
    url: str = "https://example.com/asset/a.bin",
    source_title: str = "",
    source_description: str = "",
) -> ParsedItem:
    return ParsedItem(
        req_id=req_id,
        req_type=req_type,
        name=name or req_id,
        source_title=source_title,
        source_description=source_description,
        canonical_format=fmt,
        output_path="files/out.bin",
        data=data,
        provenance=_provenance(fmt, url),
    )


def _req(
    req_id: str,
    req_type: DataReqType,
    description: str = "",
    semantic_terms: list[str] | None = None,
) -> DataReq:
    return DataReq(
        req_id=req_id,
        req_type=req_type,
        description=description,
        priority=Priority.REQUIRED,
        semantic_terms=semantic_terms or [],
    )


def test_semantic_terms_mismatch_dataset_eclipse() -> None:
    """DATASET 需求语义约束词（robot manipulation / action labels）对全为英日食内容文本零重叠。"""
    req = _req(
        "r1",
        DataReqType.DATASET,
        description="robot manipulation dataset with action labels",
        semantic_terms=["robot", "manipulation", "action labels"],
    )
    item = _item(
        "r1",
        DataReqType.DATASET,
        {"title": "2024-04-08 Total Solar Eclipse", "file_tree": ["eclipse.zip"]},
        fmt="DatasetSummary",
        name="total_solar_eclipse",
    )
    mismatch = _semantic_mismatch(req, item)
    assert mismatch
    assert "内容与需求语义不符" in mismatch


def test_semantic_terms_empty_no_object_no_keywords_returns_empty() -> None:
    """semantic_terms 为空且无 object_name/keywords → 提取为空，语义校验跳过（fail-open）。"""
    req = _req("r1", DataReqType.DATASET, description="抓取数据集")
    item = _item(
        "r1",
        DataReqType.DATASET,
        {"title": "unrelated", "file_tree": ["labels.zip"]},
        fmt="DatasetSummary",
        name="unrelated_dataset",
    )
    assert _extract_semantic_terms(req) == set()
    assert _semantic_mismatch(req, item) == ""


def test_semantic_terms_match_content_no_mismatch() -> None:
    """语义约束词命中内容（title 含 robot manipulation / action labels）→ 不误报。"""
    req = _req(
        "r1",
        DataReqType.DATASET,
        description="robot manipulation dataset with action labels",
        semantic_terms=["robot manipulation", "action labels"],
    )
    item = _item(
        "r1",
        DataReqType.DATASET,
        {"title": "Robot Manipulation Dataset with Action Labels"},
        fmt="DatasetSummary",
        name="robot_manipulation_dataset",
        url="https://example.com/robot-manipulation/dataset",
    )
    assert _semantic_mismatch(req, item) == ""


def test_semantic_terms_skip_empty_strings() -> None:
    """semantic_terms 中空串/空白项被跳过，其余按原文采用（失败时也可用 null 兜底）。"""
    req = _req(
        "r1",
        DataReqType.POLICY_MODEL,
        description="policy weights",
        semantic_terms=["", "   ", "policy weight", "action labels"],
    )
    assert _extract_semantic_terms(req) == {"policy weight", "action labels"}


def test_semantic_terms_stopwords_and_symbols_filtered() -> None:
    """审查问题 3：语义约束词中的容器词与纯符号串被过滤，防止钝化语义校验。

    "robot" 已从泛词移入锚词集（fix4 锚词约束由 _semantic_mismatch 单独判定），
    因此不再被 _extract_semantic_terms 过滤，作为锚词保留。
    """
    req = _req(
        "r1",
        DataReqType.DATASET,
        description="robot manipulation dataset with action labels",
        semantic_terms=["robot", "data", "模型", "!!!", "robot manipulation", "action labels"],
    )
    # "data"/"模型" 容器词与 "!!!" 纯符号串被剔除；"robot" 为锚词保留；短语保留
    assert _extract_semantic_terms(req) == {"robot", "robot manipulation", "action labels"}


@pytest.mark.parametrize(
    "req_type",
    [DataReqType.DATASET, DataReqType.SENSOR_DATA, DataReqType.POLICY_MODEL],
)
def test_new_semantic_types_enabled(req_type: DataReqType) -> None:
    """DATASET / SENSOR_DATA / POLICY_MODEL 均已启用语义匹配：语义约束词零重叠 → 非空。"""
    req = _req("r1", req_type, description="robot manipulation", semantic_terms=["action labels"])
    item = _item(
        "r1",
        req_type,
        {"title": "2024-04-08 Total Solar Eclipse"},
        fmt="DatasetSummary",
        name="eclipse_data",
    )
    assert _semantic_mismatch(req, item)


def test_glued_compound_identifier_no_false_mismatch() -> None:
    """2026-08-23 真实重放回归：领域词无缝粘连进标识（unidexgrasp）不应误判语义不符
    （修复前 ms_014/ss_github_004 将真实抓取策略库 PKU-EPIC/UniDexGrasp 判为不符；
    需求目标语为存活的词组 "grasp policy" 等，见 2026-08-23 错误消息）。"""
    req = _req(
        "r1",
        DataReqType.POLICY_MODEL,
        description="grasp policy hugging face model weights 抓取策略 预训练权重",
        semantic_terms=["grasp policy", "hugging face", "model weights", "抓取策略", "预训练权重"],
    )
    item = _item(
        "r1",
        DataReqType.POLICY_MODEL,
        {"model_id": "PKU-EPIC/UniDexGrasp"},
        fmt="json",
        name="pku_epic_unidexgrasp",
        url="https://huggingface.co/PKU-EPIC/UniDexGrasp",
    )
    assert _semantic_mismatch(req, item) == ""


def test_phrase_term_no_false_match_on_unrelated_content() -> None:
    """词组逐词兜底不扩大误报：grasp policy 不应命中无关日食内容（边界保护回归）。"""
    req = _req(
        "r1",
        DataReqType.POLICY_MODEL,
        description="grasp policy model",
        semantic_terms=["grasp policy"],
    )
    item = _item(
        "r1",
        DataReqType.POLICY_MODEL,
        {"title": "2024-04-08 Total Solar Eclipse"},
        fmt="json",
        name="total_solar_eclipse",
    )
    assert _semantic_mismatch(req, item)


def test_short_term_boundary_still_guarded() -> None:
    """短术语（<5 字符）保持整词边界：cup 不应命中 cupboard（防误命中回归）。"""
    from rdi.graph.nodes.validate import _term_in

    assert not _term_in("cupboard", "cup")
    assert _term_in("party cup", "cup")


def test_three_word_phrase_requires_all_words() -> None:
    """fix4c: ≥3 词短语要求全部词命中——"force torque sensor" 不能被
    "Force-torque measurements"（缺 sensor）误放行。2026-08-24 真实重放：
    Zenodo keywords 拼入候选描述文本后，RBO 记录（1036660，RGB-D 视频序列）
    靠 "Force-torque measurements" 的 force/torque 独立命中评成 2 分，
    压过真实力觉记录（11096791/11078469，1 分）；全词约束下 11096791
    （标题 "Force/Torque Sensor Measurements..."）三词齐备仍正常命中。"""
    from rdi.graph.nodes.validate import _term_in

    # RBO keywords 摘要（缺 sensor）：不再算 "force torque sensor" 命中
    assert not _term_in(
        "the rbo dataset of articulated objects and interactions robotics "
        "force-torque measurements interactive perception",
        "force torque sensor",
    )
    # 真实力觉记录标题：三个实义词齐全 → 命中
    assert _term_in(
        "accelerometer and force/torque sensor measurements for parameter and "
        "state estimation of an unknown robot end effector",
        "force torque sensor",
    )
    # 两词短语保留逐词兜底（粘连标识 unidexgrasp 场景需要 grasp 单词）
    assert _term_in("pku epic unidexgrasp huggingface", "grasp policy")


def test_three_word_phrase_requires_all_words_retrieve_candidate() -> None:
    """fix4c 检索期视角：RBO（1036660）不得再评 2 分盖过真实 F/T 记录。

    2026-08-24 真实重放：ss_sensor_zenodo_002 检索期选中 RBO 1036660
    （description 含 keywords "Force-torque measurements"、"Robotics"），
    语义打分 2（"force torque sensor" 由 force/torque 误命中 +
    "robotic gripper" 由 robotic 子串命中 robotics）压过真实
    11078469/11096791（1 分）；装配期才被语义校验拦截成 FAIL。
    """
    from types import SimpleNamespace

    from rdi.graph.nodes.validate import semantic_score

    req = SimpleNamespace(
        description="Find a force-torque sensor dataset for a robotic gripper on Zenodo",
        keywords=["force torque sensor", "robotic gripper"],
        object_name="",
        semantic_terms=["force torque sensor", "robotic gripper", "力/力矩传感器", "时序数据"],
    )
    rbo_desc = (
        "The RBO Dataset of Articulated Objects and Interactions Robotics "
        "Articulated objects Human interaction Kinematics RGB-D video "
        "Force-torque measurements Interactive perception "
        "The RBO dataset of articulated objects and interactions is a collection "
        "of 358 RGB-D video sequences"
    )
    real_desc = (
        "Accelerometer and Force/Torque Sensor Measurements for Parameter and "
        "State Estimation of an Unknown Robot End Effector "
        "Recognized this dataset was created as part of a study"
    )
    # RBO：2 词短语 "robotic gripper" 可命中 robotics 中的 robotic，但
    # "force torque sensor" 因缺 sensor 不再命中 → 总分不高于真实记录
    rbo_score = semantic_score(req, rbo_desc, "https://zenodo.org/records/1036660", "")
    real_score = semantic_score(req, real_desc, "https://zenodo.org/records/11096791", "")
    # 真实记录必须严格高于（或至少不低于）RBO，避免预筛继续选错
    assert real_score > rbo_score or (real_score == rbo_score and real_score >= 1)


# ─── fix4: 来源标题参与校验（source_title） + robot 锚词约束 ───


def test_source_title_ftsensor_record_no_false_mismatch() -> None:
    """2026-08-24 重放回归：Zenodo 11078469 标题含 Force/Torque Sensor + Robot，
    此前 Skill 产物无标题使匹配文本只剩 record id → 误判"语义不符"；source_title
    透传后标题命中实义词 force torque → 放行。"""
    req = _req(
        "r1",
        DataReqType.SENSOR_DATA,
        description="检索机械臂力觉传感器数据",
        semantic_terms=["force torque", "force torque sensor", "力/力矩传感器", "力觉传感器"],
    )
    item = _item(
        "r1",
        DataReqType.SENSOR_DATA,
        {"signals": {"ft": [1.0, 2.0]}},  # SensorDataset 序列化形态，无 title/description
        fmt="SensorDataset",
        name="11078469",
        url="https://zenodo.org/records/11078469",
        source_title="Force/Torque Sensor Measurements for Estimating the Mass Center of an Unknown Robot End Effector",
    )
    assert _semantic_mismatch(req, item) == ""


def test_source_description_imu_record_no_false_mismatch() -> None:
    """fix4b：2026-08-24 重放回归 —— 14965635 "Boxing punch data" 标题不含
    imu/inertial，但 record 描述含 "This dataset contains IMU (Inertial
    Measurement Unit)..."；source_description 透传后放行真实命中记录。"""
    req = _req(
        "r1",
        DataReqType.SENSOR_DATA,
        description="帮我找 Zenodo 上的 IMU 传感器数据",
        semantic_terms=["imu", "inertial measurement unit", "加速度", "时序数据", "角速度"],
    )
    item = _item(
        "r1",
        DataReqType.SENSOR_DATA,
        {"signals": {"acc": [1.0, 2.0]}},
        fmt="SensorDataset",
        name="14965635",
        url="https://zenodo.org/records/14965635",
        source_title="Boxing punch data",
        source_description=(
            "Boxing punch data This dataset contains IMU (Inertial Measurement Unit) "
            "measurements of professional boxer punches, sampled at 100 Hz..."
        ),
    )
    assert _semantic_mismatch(req, item) == ""


def test_source_description_not_used_when_empty() -> None:
    """source_description 为空时匹配文本与 fix4 前一致（不引入额外命中）。"""
    req = _req(
        "r1",
        DataReqType.SENSOR_DATA,
        description="检索机械臂力觉传感器数据",
        semantic_terms=["force torque", "力觉传感器"],
    )
    item = _item(
        "r1",
        DataReqType.SENSOR_DATA,
        {"signals": {"ft": [1.0]}},
        fmt="SensorDataset",
        name="11078469",
        url="https://zenodo.org/records/11078469",
        source_title="Force/Torque Sensor Measurements for Estimating the Mass Center of an Unknown Robot End Effector",
    )
    # 标题已命中，移除描述不影响放行
    assert _semantic_mismatch(req, item) == ""


def test_anchor_robot_blocked_on_unrelated_biomechanics() -> None:
    """8371258 回归：跑步生物力学的 "Joint angles during sprint..." 对机械臂关节
    需求仅 1 词命中且需求含锚词 robot arm——锚词在来源标题不命中 → 拦截。"""
    req = _req(
        "r1",
        DataReqType.SENSOR_DATA,
        description="检索机械臂关节数据",
        semantic_terms=["joint angles", "joint torques", "robot arm", "关节数据"],
    )
    item = _item(
        "r1",
        DataReqType.SENSOR_DATA,
        {"signals": {"x": [1.0]}},
        fmt="SensorDataset",
        name="8371258",
        url="https://zenodo.org/records/8371258",
        source_title="Joint angles during early sprint acceleration with wearable resistance among Australian Rules football players",
    )
    assert _semantic_mismatch(req, item)


def test_anchor_without_substantive_hit_blocks_market_report() -> None:
    """US Robotic Sensors Market：robotic 命中锚词但无非锚实义词（force/torque
    等不出现）→ 拦截，避免"机械臂关节力矩传感器"拿到市场报告。"""
    req = _req(
        "r1",
        DataReqType.SENSOR_DATA,
        description="帮我找 GitHub 上的机械臂关节力矩传感器数据",
        semantic_terms=["robot arm", "joint torque", "关节力矩"],
    )
    item = _item(
        "r1",
        DataReqType.SENSOR_DATA,
        {"signals": {"y": [1.0]}},
        fmt="SensorDataset",
        name="15834751",
        url="https://zenodo.org/api/records/15834751/files/US%20Robotic%20Sensors%20Market.csv/content",
        source_title="US Robotic Sensors Market",
    )
    assert _semantic_mismatch(req, item)


def test_anchor_with_robot_and_substantive_hit_passes() -> None:
    """11096791 回归：含 Robot 与 Force/Torque Sensor 的末端执行器力觉记录 →
    锚词命中 + 实词命中 → 放行（此类是力觉需求的真实命中）。"""
    req = _req(
        "r1",
        DataReqType.SENSOR_DATA,
        description="Find a force-torque sensor dataset for a robotic gripper on Zenodo",
        semantic_terms=["force-torque sensor", "robotic gripper", "力/力矩传感器"],
    )
    item = _item(
        "r1",
        DataReqType.SENSOR_DATA,
        {"signals": {"acc": [1.0], "ft": [2.0]}},
        fmt="SensorDataset",
        name="11096791",
        url="https://zenodo.org/records/11096791",
        source_title="Accelerometer and Force/Torque Sensor Measurements for Parameter and State Estimation of an Unknown Robot End Effector",
    )
    assert _semantic_mismatch(req, item) == ""
