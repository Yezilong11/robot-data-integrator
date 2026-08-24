# sim_config 类记录 runtime_check（mj_step）复核确认

- 复核人：D（Day3）
- 复核日期：2026-08-15
- 依据：《docs/process/Day3_执行中段与多源交叉.md》任务 3「逐个确认 sim_config 类记录的 runtime_check（mj_step 通过/失败）和 fallback 标记」
- 复核对象：C 团队 `deliverables/day3/C` 下全部 SIM_CONFIG 类记录（ss_mujoco_001~005、ss_isaac_001~002）

## 1. 复核结论摘要

| case_id | 输入 | record.runtime_check | 包引用 | 包是否存在 | 判定 |
|---|---|---|---|---|---|
| ss_mujoco_001 | mujoco_menagerie 中 franka 真实场景 | empty | package-20260814-120347 | 否（已清理） | FAIL/P1_PARSE |
| ss_mujoco_002 | mujoco_menagerie 中 aloha 真实场景 | passed | package-20260814-132556 | 否（已清理） | FAIL/P1_PARSE |
| ss_mujoco_003 | mujoco_menagerie 中 ur5 真实场景 | passed | package-20260814-132712 | 否（已清理） | FAIL/P1_PARSE |
| ss_mujoco_004 | mujoco_menagerie 中 robotiq 夹爪场景 | empty | package-20260814-121630 | 否（已清理） | PASS_WITH_FALLBACK |
| ss_mujoco_005 | mujoco_menagerie 中 shadow hand 场景 | passed | package-20260814-132751 | 否（已清理） | FAIL/P1_PARSE |
| ss_isaac_001 | Franka 的 Isaac Sim 场景配置 | empty | package-20260814-122937 | 否（已清理） | FAIL/P1_PARSE |
| ss_isaac_002 | UR5 的 Isaac Sim 场景配置 | empty | package-20260814-123023 | 否（已清理） | FAIL/P1_PARSE |

> 说明：C 的 record.json 引用的 7 个包目录当前已不存在于 `data/output_packages`（已被清理/覆盖）。
> 为消除「无法溯源」的缺口，本复核同时基于现存证据链独立验证（见 §2、§3）。

## 2. 现存可独立验证的证据链

`data/output_packages` 中与 mujoco SIM_CONFIG 相关的现存包（2026-08-14 15:32~15:41 由 Day2-D 重跑 franka panda 场景产生）：

| package_id | manifest.runtime_check | detail | is_fallback |
|---|---|---|---|
| package-20260814-153254 | req_001.status=passed | MuJoCo 加载与一步仿真成功 | 全部 false |
| package-20260814-153507 | req_001.status=passed | MuJoCo 加载与一步仿真成功 | 全部 false |
| package-20260814-153825 | req_001.status=passed | MuJoCo 加载与一步仿真成功 | 全部 false |
| package-20260814-154110 | req_001.status=passed | MuJoCo 加载与一步仿真成功 | 全部 false |

对应文件结构：`sim_config/req_001.xml`（franka_emika_panda/scene.xml）+ `sim_config/panda.xml` + `sim_config/assets/*`（88 个 mesh/stl），与 `robots/req_000.urdf` 及其 meshes 同包共存。

## 3. 独立运行复核（mj_step 实测）

对 package-20260814-154110 的 `sim_config/req_001.xml`（含 assets 完整复制至临时目录后加载）：

```
mujoco.MjModel.from_xml_path(req_001.xml) → OK
mujoco.MjData(model) → OK
mujoco.mj_step(model, data) → PASS  bodies=12  time=0.002s
```

结论：mj_step 真实通过，与 manifest 中 `status=passed` 一致。

## 4. 代码路径核对

`src/rdi/graph/nodes/validate.py::_mujoco_runtime_check`（L286-351）：

- 仅 `SIM_CONFIG` 且 canonical_format ∈ {xml, mjcf} 时触发 MuJoCo 运行时验证（L365-378）；
- 加载 + `mj_step` 成功 → `{"status": "passed", "detail": "MuJoCo 加载与一步仿真成功"}`（L351）；
- 带 assets 仍缺资源 → 降级 WARNING + `status=skipped`（L321-330）；
- 真实编译/仿真错误 → ERROR + `status=failed`（L313-320）；
- `mujoco` 未安装 → `status=skipped`（L304-305）；
- 非 xml/mjcf 格式（python/urdf/其他）不产生 runtime_check（返回 None）→ 前端/记录表现为 `empty`。

即：**`passed` = 已加载 MJCF 且 mj_step 成功；`empty` = 该 req 未进入 MuJoCo 验证路径**（可能是格式非 xml/mjcf、检索未返回有效 MJCF、或装配前已被 C4 拦截）。

## 5. 逐条确认

### ss_mujoco_001（franka，empty）
- record：parse 产出 req=[SIM_CONFIG]？record 显示 runtime_check=empty、0 个文件、package failed。
- 确认：检索阶段未拿到可落盘的 MJCF 文件（该 case 在 Day2-D 中经重跑后成功，现存的 4 个 panda 包即重跑产物）。本记录为空属「验证未触发」，非 mj_step 失败。

### ss_mujoco_002 / 003 / 005（aloha / ur5 / shadow hand，passed）
- record：validate.runtime_check=passed，文件 15/69/15 个，均因多解析出 ROBOT_URDF（markdown 类型错配）判 FAIL/P1_PARSE。
- 确认：SIM_CONFIG 主需求（mjcf）通过 MuJoCo 加载与一步仿真 → **mj_step 通过**；FAIL 来自 parse 层的额外 URDF 错配，与 runtime_check 无关。证据：与现存 panda 包相同的代码路径与 detail 文本。

### ss_mujoco_004（robotiq，empty，PASS_WITH_FALLBACK）
- record：retrieve 命中 isaac 源，quality=fallback；1 个文件；runtime_check=empty。
- 确认：**fallback 标记存在**（retrieve.quality=fallback，source=isaac）。runtime_check=empty 表示该 fallback 产物未进入 MuJoCo 验证路径（可能为非 xml/mjcf 的夹爪模型格式）。判定 PASS_WITH_FALLBACK 合理。

### ss_isaac_001 / 002（Franka / UR5 Isaac，empty）
- record：runtime_check=empty，20 个 / 1 个文件。
- 确认：Isaac Sim 场景配置非 MJCF，`_validate_sim_config_loadability` 对非 xml/mjcf 不触发 MuJoCo 验证 → 记录为空符合设计；对应包已清理，无法进一步核实产物内容。

## 6. fallback 标记汇总

| case_id | 是否存在 fallback | 来源 |
|---|---|---|
| ss_mujoco_004 | 是（quality=fallback, source=isaac） | record.json retrieve |
| 其余 mujoco / isaac | 否 | record.json retrieve（quality=real / 错误记录） |
| 现存 panda 包（153254/153507/153825/154110） | 否（全部 is_fallback=false） | manifest.json |

## 7. 复核结论

1. runtime_check 机制与代码路径一致：`passed` 表示 MJCF 加载 + mj_step 成功，`empty` 表示未触发验证；C 记录中无任何 `failed`/`skipped` 字段，说明**所有实际进入验证的 SIM_CONFIG 均 mj_step 通过**。
2. 独立实测（package-20260814-154110）确认 mj_step 通过（12 bodies），与 manifest 一致。
3. fallback 仅 ss_mujoco_004 一处（isaac 源），已正确标记。
4. 缺口：C 引用的 7 个包目录均已清理，无法直接读取其 manifest；本复核以现存 panda 包 + 代码路径 + record 字段三者交叉确认。
