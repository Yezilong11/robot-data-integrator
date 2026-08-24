# Checklist

## P0 内容有效性把关
- [x] 元数据代理占位检测实现：`_is_metadata_proxy` 覆盖 reference/DatasetSummary 空 file_tree/<200B fallback 三规则，命中即 content_validity ERROR，不受 is_fallback 豁免（spec: 元数据代理占位检测）
- [x] 语义匹配校验实现：GRASP/MESH/ROBOT_URDF/SIM_CONFIG 启用，术语空跳过，泛词过滤，mismatch 判 ERROR（spec: 目标-内容语义匹配校验）
- [x] assemble 排除占位项：content_validity ERROR 的 req 不入 manifest_files、转 MissingItem，包判 partial/failed（spec: assemble 排除占位项）
- [x] URDF 资产缺失显性化：assets_missing 写入 metadata 并经 parse_convert 透传，validate 判 ERROR（spec: URDF 资产缺失显性化）
- [x] DatasetSkill markdown 消费：`_parse_markdown` fallback summary 字段与 spec 一致（spec: DatasetSkill 消费 markdown 摘要）
- [x] is_fallback 内容校验豁免取消（spec: is_fallback 内容校验豁免取消）

## P1 检索与解析
- [x] validate 重试路由：检索轴 issue 标注 + route 对纯检索轴失败直出 pass（spec: validate 重试路由区分检索轴）
- [x] 抓取解析消歧：GRASP 强词补全 + DATASET→GRASP 单向消歧（spec: 抓取解析消歧）
- [x] LLM 列表输出归一化：list[str] 字段逗号/顿号/分号拆分重试一次（spec: LLM 列表输出归一化）

## P2 工具与记录治理
- [x] failure_category 枚举八类更新 + 旧值等价映射为 WARNING（spec: 记录校验枚举与台账轮次）
- [x] 台账 round 列：round=1 筛选 63、round=2 筛选 59（spec: 记录校验枚举与台账轮次）

## 回归
- [x] `uv run pytest tests/ -q` 全量通过（867 passed, 1 skipped, 9 deselected ～600s）
- [x] `docs/fix_actions_checklist.md` 生成（截图/补正/15 FAIL 处置/复核分配/P0 补位）
- [x] progress.csv 含 round 列且统计重算与台账核对通过（63/59，可用率 59.0% 与修复前一致）