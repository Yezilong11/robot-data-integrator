# src/rdi/graph/nodes/parse_convert.py
"""数据解析与标准化节点。

遍历 ``retrieval_results``，通过 ``SkillRegistry`` 按 ``req_type`` 分发到对应
Skill，把 ``RawData.data`` 字节解析标准化为 ``ParsedItem``；处理失败或无对应
Skill 时装配 ``MissingItem``。``data_requirements`` 缺失某 ``req_id`` 时由原始
数据格式兜底推断 ``req_type``，推断失败则跳过并记 warning。

返回 state 字段：``parsed_data`` / ``missing_items`` / ``provenance`` / ``errors``。
"""

from datetime import datetime
from typing import Any

from rdi.graph.state import SystemState
from rdi.models import DataReq, DataReqType, MissingItem, ParsedItem, Priority, RetrievalResult
from rdi.skills import default_registry

# format → DataReqType 兜底映射（data_requirements 缺失该 req_id 时使用）
_FORMAT_TO_REQ_TYPE: dict[str, DataReqType] = {
    "urdf": DataReqType.ROBOT_URDF,
    "xacro": DataReqType.ROBOT_URDF,
    "stl": DataReqType.MESH,
    "obj": DataReqType.MESH,
    "ply": DataReqType.MESH,
    "dae": DataReqType.MESH,
    "npz": DataReqType.GRASP,
    "pkl": DataReqType.GRASP,
    "xml": DataReqType.SIM_CONFIG,
    "pt": DataReqType.POLICY_MODEL,
    "pth": DataReqType.POLICY_MODEL,
    "safetensors": DataReqType.POLICY_MODEL,
    "onnx": DataReqType.POLICY_MODEL,
    "csv": DataReqType.SENSOR_DATA,
    "json": DataReqType.SENSOR_DATA,
    "bag": DataReqType.SENSOR_DATA,
}


def _infer_req_type(format_str: str) -> DataReqType | None:
    """由原始数据格式推断 DataReqType；未知格式返回 None。"""
    return _FORMAT_TO_REQ_TYPE.get(format_str.lower())


def _extract_object_name(requirements: list[DataReq]) -> str:
    """从 mesh 需求中提取物体名（优先 keywords，其次 description）。"""
    for req in requirements:
        if req.req_type == DataReqType.MESH:
            if req.keywords:
                return req.keywords[0]
            desc = req.description.strip()
            if desc:
                return desc
            break
    return "object"


def _build_sim_config_context(
    requirements: list[DataReq], parsed_data: dict[str, ParsedItem]
) -> dict[str, Any]:
    """为 sim_config 构建上下文：从已成功解析的项中提取 URDF/Mesh 输出路径。"""
    context: dict[str, Any] = {}
    type_to_key = {
        DataReqType.ROBOT_URDF: "urdf_path",
        DataReqType.MESH: "mesh_path",
    }
    for req in requirements:
        key = type_to_key.get(req.req_type)
        if key is None:
            continue
        parsed = parsed_data.get(req.req_id)
        if parsed and parsed.output_path:
            context[key] = parsed.output_path
    return context


def node_parse_convert(state: SystemState) -> dict[str, Any]:
    """数据解析与标准化节点：用 SkillRegistry 替换占位逻辑。

    对每个 ``RetrievalResult``：由 ``data_requirements`` 查 ``DataReq`` 得
    ``req_type``（缺失则由原始格式兜底推断），调用 ``default_registry``
    分发到对应 Skill，按返回结果装配 ``ParsedItem`` 或 ``MissingItem``，
    并追加带时间戳与 Skill 名的 provenance 日志。

    sim_config 项会延后处理，以便从已解析的 URDF/Mesh 项中获取输出路径，
    传给 SimConfigSkill 生成最小 MJCF。

    Returns:
        更新 state 的字段：parsed_data, missing_items, provenance, errors
    """
    now = datetime.now()
    registry = default_registry
    retrieval_results = state.get("retrieval_results", {})
    requirements = state.get("data_requirements", [])
    req_by_id: dict[str, DataReq] = {req.req_id: req for req in requirements}

    parsed_data: dict[str, ParsedItem] = {}
    missing_items: list[MissingItem] = []
    provenance: list[str] = []

    # 预先解析/推断所有 req_id，避免多遍循环重复记录跳过日志
    resolved: dict[str, DataReq] = {}
    for req_id, result in retrieval_results.items():
        req = req_by_id.get(req_id)
        if req is not None:
            resolved[req_id] = req
            continue
        if result.data is None:
            continue
        inferred = _infer_req_type(result.data.format)
        if inferred is None:
            provenance.append(
                f"[{now.isoformat()}] parse_convert: 跳过 {req_id} "
                "(无 data_requirements 且无法推断 req_type)"
            )
            continue
        resolved[req_id] = DataReq(
            req_id=req_id,
            req_type=inferred,
            description="",
            priority=Priority.OPTIONAL,
        )

    def _process_one(req_id: str, result: RetrievalResult, context: dict[str, Any] | None) -> None:
        req = resolved.get(req_id)
        if req is None:
            return
        outcome = registry.process_retrieval_result(result, req, context=context)
        skill = registry.get_skill(req.req_type)
        skill_name = skill.skill_name if skill is not None else "no-skill"
        if isinstance(outcome, ParsedItem):
            parsed_data[req_id] = outcome
            provenance.append(
                f"[{now.isoformat()}] parse_convert: {skill_name} 处理 {req_id} → 成功"
            )
        else:
            missing_items.append(outcome)
            provenance.append(
                f"[{now.isoformat()}] parse_convert: {skill_name} 处理 {req_id} → 缺失"
            )

    # 第一遍：先解析 URDF/Mesh 等资产，建立 parsed_data
    for req_id, result in retrieval_results.items():
        req = resolved.get(req_id)
        if req is None or req.req_type == DataReqType.SIM_CONFIG:
            continue
        context: dict[str, Any] | None = None
        if req.req_type == DataReqType.GRASP:
            context = {"object_name": _extract_object_name(requirements)}
        _process_one(req_id, result, context=context)

    # 第二遍：解析 sim_config，传入已成功解析的 URDF/Mesh 路径
    sim_config_context = _build_sim_config_context(requirements, parsed_data)
    for req_id, result in retrieval_results.items():
        req = resolved.get(req_id)
        if req is None or req.req_type != DataReqType.SIM_CONFIG:
            continue
        _process_one(req_id, result, context=sim_config_context)

    return {
        "parsed_data": parsed_data,
        "missing_items": missing_items,
        "provenance": provenance,
        "errors": [],
    }
