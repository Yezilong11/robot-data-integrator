# Checklist

## kinova 资产缺失显性化
- [x] 网络路径：部分 mesh 下载失败 → `metadata["assets_missing"]` 含缺失清单，下游 parse_convert→ParsedItem.assets_missing→validate 判 ERROR 链路生效（spec: kinova 资产缺失显性化 / 网络资产下载部分失败）
- [x] 本地挂载路径：镜像缺 mesh 文件 → 同样产生 assets_missing（tmp_path 镜像实测）（spec: 本地挂载路径资产缺失）
- [x] 全部成功时无 assets_missing，行为与修复前一致（spec: 资产全部下载成功）
- [x] 单测覆盖网络部分失败/全部成功/本地缺失三场景，无新依赖

## isaac 降级诚实化
- [x] 非 MJCF 输入降级结果携带「降级场景：最小 MJCF 仅含地面+相机，不含真实机器人/任务语义」标记（warnings 通道），validate 对带标记项产生 WARNING（issue_type=degraded_scene，不再 silent passed）（spec: isaac 降级产物语义诚实）
- [x] mjcf/xml 直通与重建分支不受影响（无标记）
- [x] SIM_CONFIG 语义错配回退单测通过：UR5 目标 vs Franka 标识 → content_validity ERROR（spec: SIM_CONFIG 语义错配回退）

## isaac 收录扩充（条件性）
- [x] UR5/UR5e 存在性已核实（GitHub API contents 200 + raw 逐候选 404/ReadError，无虚构）
- [x] 存在 → 已扩充；不存在 → 如实挂账（UR5/UR5e 挂账不补）；真实存在条目 `universal_robots`（UR10/UR10e）、`kinova`（Gen3/Jaco2）已补录 + 2 条 search 单测，总结已说明

## 回归
- [x] `uv run pytest tests/ -q` 全量通过（885 passed, 1 skipped, 9 deselected；kinova/isaac/sim_config/validate 既有用例零回归）