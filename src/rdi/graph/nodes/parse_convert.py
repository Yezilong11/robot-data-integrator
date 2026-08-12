# src/rdi/graph/nodes/parse_convert.py
"""数据解析与标准化节点。

遍历 ``retrieval_results``，通过 ``SkillRegistry`` 按 ``req_type`` 分发到对应
Skill，把 ``RawData.data`` 字节解析标准化为 ``ParsedItem``；处理失败或无对应
Skill 时装配 ``MissingItem``。``data_requirements`` 缺失某 ``req_id`` 时由原始
数据格式兜底推断 ``req_type``，推断失败则跳过并记 warning。

返回 state 字段：``parsed_data`` / ``missing_items`` / ``provenance`` / ``semantic_map``。
"""

import os
import time
from datetime import datetime
from typing import Any

import numpy as np

from rdi.graph.state import SystemState
from rdi.intelligence.schemas import SemanticConvention
from rdi.logging import get_logger
from rdi.models import (
    DataReq,
    DataReqType,
    DataSource,
    MissingItem,
    ParsedItem,
    Priority,
    RawData,
    RetrievalResult,
)
from rdi.skills import default_registry

logger = get_logger(__name__)

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


def _is_trimesh(data: Any) -> bool:
    """判断 data 是否为 trimesh 网格对象（有 export 方法且模块名含 trimesh）。"""
    return hasattr(data, "export") and "trimesh" in data.__class__.__module__


def _strip_numpy(obj: Any) -> Any:
    """递归把嵌套的 numpy 标量转为 Python 原生类型（msgpack 无法序列化 np.generic）。"""
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _strip_numpy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_numpy(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_strip_numpy(v) for v in obj)
    return obj


def _normalize_for_checkpoint(item: ParsedItem) -> ParsedItem:
    """把 ParsedItem.data 归一化为 checkpoint 可序列化形态。

    真实流程中 ParsedItem 随 state 写入 MemorySaver checkpoint（msgpack）：
    trimesh 对象与 numpy 标量都会抛 ``TypeError: Type is not msgpack
    serializable``，导致 resume（``graph.ainvoke(Command(resume=...))``）崩溃。
    在节点层统一归一化（不动 skill/registry 层产出，保持其测试断言不变）：
    - trimesh.Trimesh → 导出 STL bytes，canonical_format 同步改为 "stl"
      （assemble 落盘扩展名仍为 .stl，validate 支持从 bytes 加载 mesh）；
    - 嵌套 numpy 标量 → 递归转 Python 原生。
    """
    data = item.data
    if _is_trimesh(data):
        return item.model_copy(
            update={"data": data.export(file_type="stl"), "canonical_format": "stl"}
        )
    stripped = _strip_numpy(data)
    if stripped is not data:
        return item.model_copy(update={"data": stripped})
    return item


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
        更新 state 的字段：parsed_data, missing_items, provenance
    """
    now = datetime.now()
    registry = default_registry
    # 本地文件注入：前端通过 state.local_files（req_id → 路径）跳过外部检索，
    # 直接把本地文件作为 RetrievalResult 参与解析；local 优先于外部检索结果。
    local_files = state.get("local_files") or {}
    local_results: dict[str, RetrievalResult] = {}
    for req_id, path in local_files.items():
        if not req_id or not path or not os.path.isfile(str(path)):
            continue
        with open(str(path), "rb") as fh:
            data = fh.read()
        ext = str(path).rsplit(".", 1)[-1].lower() if "." in str(path) else "bin"
        local_results[req_id] = RetrievalResult(
            req_id=req_id,
            status="success",
            data=RawData(
                source=DataSource.LOCAL,
                item_id=str(path),
                format=ext,
                data=data,
                url=f"local://{path}",
            ),
        )
    retrieval_results = {**local_results, **state.get("retrieval_results", {})}
    requirements = state.get("data_requirements", [])
    req_by_id: dict[str, DataReq] = {req.req_id: req for req in requirements}

    parsed_data: dict[str, ParsedItem] = {}
    missing_items: list[MissingItem] = []
    provenance: list[str] = []
    # D2: LLM 语义统一 —— 未知数据集约定经 LLM 识别后按 req_id 登记（assemble 落盘 semantic_map.json）
    semantic_map: dict[str, SemanticConvention] = {}
    # D2: 语义统一的 LLM 决策调用记录，装配进 state.llm_usage（成功与降级都记录）
    llm_usage_entries: dict[str, dict[str, Any]] = {}

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
            logger.warning(
                "parse_convert.skip",
                req_id=req_id,
                format=str(result.data.format),
                reason="unknown_req_type",
            )
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
        start = time.monotonic()
        outcome = registry.process_retrieval_result(result, req, context=context)
        elapsed = time.monotonic() - start
        usage = getattr(outcome, "llm_usage", None)
        if usage:
            llm_usage_entries[req_id] = {**usage, "req_id": req_id}
        skill = registry.get_skill(req.req_type)
        skill_name = skill.skill_name if skill is not None else "no-skill"
        if isinstance(outcome, ParsedItem):
            parsed_data[req_id] = _normalize_for_checkpoint(outcome)
            status = "success"
            provenance.append(
                f"[{now.isoformat()}] parse_convert: {skill_name} 处理 {req_id} → 成功"
            )
            # D2: 该 req 的语义约定由 LLM 识别 → 登记 state.semantic_map 供 assemble 落盘
            sc = getattr(outcome, "semantic_convention", None)
            if sc:
                convention = SemanticConvention.model_validate(sc)
                semantic_map[req_id] = convention
                provenance.append(
                    f"[{now.isoformat()}] parse_convert: {skill_name} 处理 {req_id} "
                    f"→ 语义由 LLM 识别（{convention.semantic_type}）"
                )
        else:
            missing_items.append(outcome)
            status = "missing"
            provenance.append(
                f"[{now.isoformat()}] parse_convert: {skill_name} 处理 {req_id} → 缺失"
            )
        logger.info(
            "parse_convert.item",
            req_id=req_id,
            req_type=req.req_type.value,
            skill=skill_name,
            status=status,
            elapsed_seconds=round(elapsed, 3),
        )

    # 第一遍：先解析 URDF/Mesh 等资产，建立 parsed_data
    for req_id, result in retrieval_results.items():
        req = resolved.get(req_id)
        if req is None or req.req_type == DataReqType.SIM_CONFIG:
            continue
        context: dict[str, Any] | None = None
        if req.req_type == DataReqType.GRASP:
            # C1: 优先用该 GRASP 需求自身的 object_name，缺失时退回从 MESH 需求提取
            context = {
                "object_name": (
                    getattr(req, "object_name", "") or _extract_object_name(requirements)
                )
            }
        _process_one(req_id, result, context=context)

    # 第二遍：解析 sim_config，传入已成功解析的 URDF/Mesh 路径
    sim_config_context = _build_sim_config_context(requirements, parsed_data)
    for req_id, result in retrieval_results.items():
        req = resolved.get(req_id)
        if req is None or req.req_type != DataReqType.SIM_CONFIG:
            continue
        _process_one(req_id, result, context=sim_config_context)

    logger.info(
        "parse_convert.done",
        parsed=len(parsed_data),
        missing=len(missing_items),
        skipped=len(retrieval_results) - len(parsed_data) - len(missing_items),
    )
    return {
        "parsed_data": parsed_data,
        "missing_items": missing_items,
        "provenance": provenance,
        "semantic_map": semantic_map,
        "llm_usage": list(llm_usage_entries.values()),
    }
