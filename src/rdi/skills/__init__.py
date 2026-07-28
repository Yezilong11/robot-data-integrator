# src/rdi/skills/__init__.py
"""Skill 能力执行层。

每个 Skill 负责处理一类异构数据（URDF / Mesh / Grasp / SimConfig / Policy /
Sensor），提供 parse → standardize → validate 三步处理流程，输入仅为 ``bytes``
（来自 ``RawData.data``），不直接调用外部 API。

``SkillRegistry`` 按 ``DataReqType`` 分发到对应 Skill 单例，``parse_convert``
节点通过 ``default_registry`` 把 ``RetrievalResult`` 转为 ``ParsedItem`` /
``MissingItem``。所有模块通过此包导入 Skill 与中间表示，禁止从子模块直接导入。
"""

from .base import BaseSkill
from .grasp_parse import DATASET_CONVENTIONS, CanonicalGrasp, GraspSkill
from .mesh_process import MeshSkill
from .policy_interface import PolicyInterfaceDoc, PolicyInterfaceSkill
from .registry import SkillRegistry, default_registry
from .sensor_data import SensorDataset, SensorDataSkill
from .sim_config import Camera, SceneDescription, SceneObject, SimConfigSkill
from .urdf_convert import CanonicalRobot, Joint, Link, URDFSkill

__all__ = [
    # 基类
    "BaseSkill",
    # 6 类 Skill
    "URDFSkill",
    "MeshSkill",
    "GraspSkill",
    "SimConfigSkill",
    "PolicyInterfaceSkill",
    "SensorDataSkill",
    # 中间表示
    "CanonicalRobot",
    "Link",
    "Joint",
    "CanonicalGrasp",
    "DATASET_CONVENTIONS",
    "SceneDescription",
    "SceneObject",
    "Camera",
    "PolicyInterfaceDoc",
    "SensorDataset",
    # 注册表
    "SkillRegistry",
    "default_registry",
]
