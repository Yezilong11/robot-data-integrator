# src/rdi/adapters/_graspnet_objects.py
"""GraspNet 物体名 → object id 定位的共享工具（graspnet/dexgrasp adapter 复用）。"""

import re
from typing import Any

# 常见物体名 → GraspNet object id 映射（GraspNet-1Billion 使用 WordNet 风格 id，
# 形如 003_cracker_box；通俗名经此表映射，识别不到的物体名由调用方回退现有行为）
OBJECT_ID_MAP: dict[str, str] = {
    "banana": "011_banana",
    "cracker_box": "003_cracker_box",
    "cracker": "003_cracker_box",
    "mug": "025_mug",
    "bowl": "024_bowl",
    "sugar_box": "004_sugar_box",
    "tomato_soup": "005_tomato_soup_can",
    "soup_can": "005_tomato_soup_can",
    "mustard_bottle": "006_mustard_bottle",
    "mustard": "006_mustard_bottle",
    "power_drill": "035_power_drill",
    "scissors": "037_scissors",
}

_OBJECT_ID_RE = re.compile(r"\d{3}_[\w-]+")


def norm_object_name(name: str) -> str:
    """小写并移除分隔符（``003_cracker_box`` → ``003crackerbox``），用于宽松匹配。"""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def extract_object_id(object_name: str) -> str | None:
    """从物体名提取 GraspNet object id；识别不到返回 None。

    ``003_cracker_box`` 风格 id 直接命中，通俗名走映射表 fallback。
    """
    name = object_name.strip()
    if not name:
        return None
    if _OBJECT_ID_RE.fullmatch(name):
        return name
    return OBJECT_ID_MAP.get(name.lower().replace(" ", "_"))


def find_object_grasp_file(
    tree: list[dict[str, Any]],
    object_name: str,
    exts: tuple[str, ...],
) -> str | None:
    """按物体名在文件树中定位 grasp 标注文件。

    文件名包含 object id 或原始物体名（大小写不敏感、忽略分隔符）即命中；
    优先 ``grasp_label/`` 路径，其次任意含 ``grasp`` 的路径。找不到返回 None，
    由调用方回退 ``_find_file_by_ext`` 保持既有行为。
    """
    object_id = extract_object_id(object_name)
    if object_id is None:
        return None
    keys = {norm_object_name(object_id), norm_object_name(object_name)}
    keys.discard("")
    matched = [
        item.get("path", "")
        for item in tree
        if isinstance(item, dict)
        and item.get("path", "").lower().endswith(exts)
        and any(k in norm_object_name(item.get("path", "")) for k in keys)
    ]
    if not matched:
        return None
    for path in matched:
        if "grasp_label" in path or "grasp" in path.lower():
            return str(path)
    return str(matched[0])
