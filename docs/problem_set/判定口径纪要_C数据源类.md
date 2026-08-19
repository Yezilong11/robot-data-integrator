# 判定口径纪要（C 数据源类题目：quality / format）

> 版本：1.0（已确认）
> 编制：C（数据工程师）
> 日期：2026-08-12
> 对齐双方：C ↔ A（组长）
> 状态：**已确认（A 2026-08-12）**；为执行期判定唯一依据
> 依据：《docs/problem_set/问题集构建策略.md》§4.2/§5.5、《docs/problem_set/问题集规模与源配额.md》、`src/rdi/skills/registry.py`、`src/rdi/models/manifest.py`

---

## 1. 判定三档总则（复述策略 §5.5，A 确认后不再逐题仲裁）

| 值 | 条件 |
|---|---|
| PASS | 数据包完整、无 ERROR、文件可加载，且无任何降级标记 |
| PASS_WITH_FALLBACK | 包可用，但 manifest 有显式降级记录（文件级 `is_fallback=true` 或包级 `missing_items` 非空且已显式标注） |
| FAIL | 无数据包 / 崩溃 / 含 ERROR / 产出内容错误 / **无标记的静默降级** |

> 铁律：**降级不算失败，但必须显式可追溯**。manifest 中无 `is_fallback`/`missing_items` 记录却实际走了兜底路径 → 一律记 FAIL。

---

## 2. quality 判定标准

### 2.1 四档来源质量定义（以 manifest 文件级 `data_source_quality` 为准）

| 值 | 判定口径 | 示例 |
|---|---|---|
| `real` | 从官方源直接获取，未走任何兜底/镜像/生成 | arXiv API、GitHub 官方仓库 raw、zenodo 官方记录、HF 官方文件 |
| `fallback` | 走了备选源、镜像或降级产物，且 `is_fallback=true` 显式标记 | hf-mirror 镜像、jsdelivr 兜底、isaac 最小 MJCF、graspnet→dexgrasp 兜底 |
| `synthetic` | 由代码生成而非源获取 | 场景生成、占位模型 |
| `unknown` | 来源不可判定（manifest 默认值，**不再隐式标 fallback**） | 仅远端引用、未下载 |

### 2.2 期望值 vs 实际值的判定规则

对每道题读取 `expected.quality` 列表，按实际产出的 `data_source_quality` 判定：

| 期望列表 | 实际 real | 实际 fallback（显式标记） | 实际 fallback（无标记） | 实际 synthetic/unknown |
|---|---|---|---|---|
| `["real"]` | PASS | FAIL | FAIL | FAIL |
| `["real","fallback"]` | PASS | PASS_WITH_FALLBACK | FAIL | FAIL |
| `["fallback"]` | 记 PASS_WITH_FALLBACK（超预期，仍合格） | PASS | FAIL | FAIL |
| 其他组合 | 按上述原则类推：实际值 ∈ 期望列表 → PASS/PASS_WITH_FALLBACK；∉ → FAIL | | | |

> 补充：PASS_WITH_FALLBACK 与 PASS 均算"通过"，计入通过率；仅 FAIL 计入失败率。PASS_WITH_FALLBACK 单独统计降级率（策略 §6.5-5）。

### 2.3 显式降级的判定标准

显式降级成立，需同时满足：
1. 文件级：`ManifestFile.is_fallback = true`，或
2. 包级：`missing_items` 含对应 `req_id` 条目，且 `reason` 写明降级原因、`alternatives` 非空（可追溯到兜底路径），或
3. 溯源：`provenance_log` 有对应降级记录，能还原"主源失败 → 备选源"过程。

三者至少满足其一，否则按静默降级记 FAIL。

### 2.4 与探活可达性的约束（防"题设不可达"）

- 题设 `expected.quality` **不得高于探活实测可达水平**：探活显示某源仅能产出 fallback，题目就不得只允许 `real`。
- 例外：8 源 fetch 阻塞属代码缺陷（待修复），修复后可达 `real`——修复完成前，相关 P0 题（如 `ss_graspnet_002`、`ss_mujoco_001`）执行若因该缺陷失败，记 **P3_SOURCE（代码缺陷）** 而非 P5_RUNTIME，不判执行人责任；修复后按正常口径。

---

## 3. format 判定标准

### 3.1 第一道闸：系统 C4 校验（既有实现，直接采信）

装配节点已按 `_REQ_EXPECTED_FORMATS`（`src/rdi/skills/registry.py`）对 `RawData.format` 做类型错配校验，不匹配自动写入 `missing_items`（reason 含"类型错配"）。**该闸通过 ≠ 判定通过，仅作为格式合法性的系统级证据。**

### 3.2 各类别允许格式表（与系统 C4 一致，执行期按此对照）

| DataReqType | 允许格式（registry 权威） |
|---|---|
| GRASP | npz / pkl / npy / mat / json / h5 / hdf5 |
| ROBOT_URDF | urdf / xacro / zip / json |
| MESH | obj / stl / ply / dae / glb / gltf / zip / json |
| SIM_CONFIG | xml / mjcf / mujoco / json / py / python / yaml |
| PAPER / CODE / DATASET / POLICY_MODEL / SENSOR_DATA | 无 C4 闸，按题设 `expected.format` 判定 |

### 3.3 题设 `expected.format` 判定口径

| 场景 | 判定 |
|---|---|
| 包内文件格式 ⊆ 题设 `expected.format` | PASS（该维度） |
| 包内出现题设外格式（超集） | 容忍：不判 FAIL，但需 `transformations` 说明；若影响可加载性则降级为 PASS_WITH_FALLBACK |
| 格式变体（xacro↔urdf、obj↔glb、npz↔pkl、xml↔yaml） | 允许经 skill 转换后产出；转换记录于 `transformations`。**转换失败 → P4_FORMAT** |
| 关键文件格式不匹配且无法转换 | P4_FORMAT（类型错配，见 `missing_items` 的"类型错配"条目） |

### 3.4 min_files 口径

- `min_files` = 数据包内**已下载到本地（`downloaded=true` 且 `local_path` 非空）的有效文件数下限**；仅远端引用（未下载）不计。
- 目录结构以 `robots/objects/grasps/sim_config/` 分类目录与 `manifest.json` 记录一致为准（策略 §6.3-5）。
- 不足 `min_files` → 按缺文件数记入 `quality_report.missing`，判定 FAIL。

---

## 4. 特殊源判定口径（结合探活结论）

| 源 | 探活状态 | 执行期判定口径 |
|---|---|---|
| ieee | blocked-by-user（无 API Key） | 1 题（ss_ieee_001）执行时记 **P7_ENV**，verdict 记 FAIL 但归因 blocked-by-user，不阻碍验收线（A 已拍板：剔除 ss_ieee_002/003） |
| huggingface | search OK / 单仓库 fetch FAIL | 换仓库重试一次；仍失败 → P3_SOURCE，在 `missing_items.reason` 写明仓库与错误 |
| graspnet / dexgrasp / ycb / mujoco / isaac / franka / allegro / robotiq | fetch 全 FAIL（代码缺陷，待修复） | 修复前记 P3_SOURCE（代码缺陷）；修复后按 2.4 正常口径 |
| isaac | 仅 fallback 最小 MJCF 可达 | 产出 fallback MJCF 且 `is_fallback=true` → PASS_WITH_FALLBACK；无标记 → FAIL |
| graspnet | tar 死路径 | 必须显式降级（→dexgrasp 兜底）并记录；静默降级 → FAIL |

---

## 5. 判定与失败分类码映射（供 record.json 填写）

| 观察点 | 记录字段 | 分类码 |
|---|---|---|
| 目标解析产出 req 类型错/漏/UNKNOWN | observations.parse_goal | P1_PARSE |
| 检索无结果 / timeout / rate_limit | observations.retrieve | P2_RETRIEVE |
| 源不可用（404/401/tar 无法单文件获取） | observations.retrieve | P3_SOURCE |
| 格式不兼容（xacro/glb/python 场景） | observations.validate | P4_FORMAT |
| 运行验证失败（MuJoCo 加载/mesh 缺面） | observations.validate.runtime_check | P5_RUNTIME |
| 前端流程问题（interrupt 卡死/resume 失败） | observations | P6_FRONTEND |
| 环境问题（Key 缺失/依赖/网络） | env | P7_ENV |
| 其他（产出内容错误） | observations.package | P8_OTHER |

---

## 6. 已确认决策（A 2026-08-12 拍板，执行期判定唯一依据）

- [x] §2.2 期望列表判定表（含 `["fallback"]` 时 real 记为 PASS_WITH_FALLBACK 的口径）—— A 确认（2026-08-12）
- [x] §2.3 显式降级三条件是否充分 —— A 确认（2026-08-12）
- [x] §3.3 超集容忍 + 变体转换口径是否认可 —— A 确认（2026-08-12）
- [x] §3.4 min_files 只计本地已下载文件的定义 —— A 确认（2026-08-12）
- [x] §4 ieee 处理：保留 ss_ieee_001（P7_ENV 记 FAIL 不阻碍验收线），剔除 ss_ieee_002/003（A 2026-08-12 拍板）
- [x] §4 8 源 fetch 代码缺陷的归因口径（P3_SOURCE 不判执行人责任）—— A 确认（2026-08-12）
- [x] ycb/github 归属：随 C+D 合并定案——ycb mesh×3 归 D（ss_ycb_001~003）、grasp×2 归 C（ss_ycb_004/005）；ss_github_002 保留 C（A 2026-08-12）
- [x] P0 验收线口径：C+D 合并后 **11 个 P0**，通过率 **≥ 2/3（≥8/11 生成可用数据包）**；**PASS + PASS_WITH_FALLBACK 均算通过，仅 FAIL 不算**（A 2026-08-12 确认）
- [x] 多源 ms_001~008 采用：由 D 的 multi_source_notes 转正式题（A 2026-08-12 确认）
- [x] graspnet/dexgrasp 仅返回元数据 JSON（无真实 npz/pkl）：按**显式降级**处理——missing_items 含 reason + alternatives（可追溯），判定 **PASS_WITH_FALLBACK**；validate 缺失项与 min_files 缺口对显式降级需求放行（工具 `fallback_explicit=true` 时跳过 errors/file_count 检查）（A 2026-08-14 确认）
- [x] ms_004 题设补 `grasp` 需求：目标 "UR5 with Robotiq 2F-85 grasps YCB apple" 语义含抓取数据需求，系统解析出 grasp 属预期（A 2026-08-14 确认）

---

## 7. 补充决策（A 2026-08-14 拍板，执行期判定唯一依据）

- [x] **多需求补充源口径**：题设核心需求（`expected.req_types`）全部命中且命中题设源 → 该维度无降级；LLM 额外解析出的**题设外补充需求**（如 ss_mujoco_001 的 robot_urdf 由 franka 源补足）成功获取且可加载验证通过 → **不算静默降级**，记录 `vs_expected=partial` 达标，verdict 可记 PASS。补充需求未满足仍记 ERROR。校验工具同步修订：`source_mismatch`/format 检查仅对核心需求生效，题设外 req_type 成功获取记 WARNING（A 2026-08-14 确认，D 的 ss_mujoco_001 适用）
- [x] **package.dir/manifest_path 跨机校验降级**：数据包被 `.gitignore` 排除、在各执行机本地化，验收端无法验证路径存在性 → 路径存在性检查由 ERROR 降为 WARNING（人工复核）；字段必填性（placeholder）保持 ERROR（A 2026-08-14 确认）
